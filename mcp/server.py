#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.0.0",
#   "pydantic>=2.6.0",
#   "tiktoken>=0.7.0",
# ]
# ///
"""Pratyakṣa Context Engineering Harness — FastMCP server.

Exposes 15 tools across five families:

    Family                | Tools
    --------------------- | --------------------------------------------------
    Avacchedaka store     | insert / retrieve / get / sublate / list_qualificands
    Sublation             | sublate_with_evidence / detect_conflict
    Compaction            | compact / boundary_compact / context_window
    Witness               | set_sakshi / get_sakshi
    Hallucination class   | classify_khyativada
    Budget / observability| budget_status / budget_record

The server is self-contained: it depends only on `mcp`, `pydantic`, and
`tiktoken`. Heavy components (vLLM, HF transformers, Anthropic SDK) are
NOT required at runtime — the plugin uses pure-Python heuristics so it
works on any machine that has `uv` and Python ≥3.11.

State is per-process (one MCP server instance ↔ one Claude Code session).
A simple JSONL audit log at `~/.cache/pratyaksha/audit.jsonl` records every
mutating call so users can inspect exactly what their agent did.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

logging.basicConfig(level=os.environ.get("PRATYAKSHA_LOG_LEVEL", "INFO"))
logger = logging.getLogger("pratyaksha")


# ----------------------------------------------------------------------
# Configuration & paths
# ----------------------------------------------------------------------

CACHE_DIR = Path(os.environ.get("PRATYAKSHA_CACHE_DIR", str(Path.home() / ".cache" / "pratyaksha")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = CACHE_DIR / "audit.jsonl"
COST_LEDGER = CACHE_DIR / "cost_ledger.jsonl"
BUDGET_GAUGE = CACHE_DIR / "budget.json"

DEFAULT_BUDGET_TOKENS = int(os.environ.get("PRATYAKSHA_DEFAULT_BUDGET", "200000"))


def _audit(event: str, payload: dict[str, Any]) -> None:
    """Append a JSONL audit record for every mutating operation."""
    record = {"ts": time.time(), "event": event, **payload}
    try:
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError as e:
        logger.warning("audit log write failed: %s", e)


def _write_budget_gauge(total: int, used: int) -> None:
    """Mirror the in-memory budget gauge to a small JSON file.

    The gauge is consumed by the plugin's PreToolUse and Stop hooks
    (see hooks/*.sh); they run in separate processes from the MCP
    server, so the gauge must live on disk.
    """
    try:
        BUDGET_GAUGE.write_text(
            json.dumps({"total": total, "used": used, "remaining": max(0, total - used)}),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("budget gauge write failed: %s", e)


# ----------------------------------------------------------------------
# Tokenizer (lazy — tiktoken loads its vocabulary on first call)
# ----------------------------------------------------------------------

_ENCODER = None


def _count_tokens(text: str, *, encoding: str = "o200k_base") -> int:
    """Tokenizer-exact count (G12) using tiktoken's `o200k_base`.

    Falls back to a `len(text) // 4` heuristic only when tiktoken is
    unavailable or its vocabulary cannot be loaded (typical in air-gapped
    CI). Network and disk errors during the one-time vocabulary load are
    caught explicitly; bugs in our own code are not silently swallowed.
    """
    global _ENCODER
    if not text:
        return 0
    if _ENCODER is None:
        try:
            import tiktoken

            _ENCODER = tiktoken.get_encoding(encoding)
        except (ImportError, OSError, ValueError) as exc:
            logger.debug("tiktoken init failed (%s); using heuristic fallback", exc)
            return max(1, len(text) // 4)
    return len(_ENCODER.encode(text, disallowed_special=()))


# ----------------------------------------------------------------------
# Avacchedaka — typed limitor conditions
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class AvacchedakaConditions:
    qualificand: str
    qualifier: str
    condition: str
    relation: str = "inherence"


@dataclass
class ContextElement:
    id: str
    content: str
    precision: float
    avacchedaka: AvacchedakaConditions
    timestamp: float
    provenance: str = ""
    sublated_by: str | None = None
    salience: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Per-session in-memory store + sakshi prefix
# ----------------------------------------------------------------------

class _State:
    def __init__(self) -> None:
        self.elements: dict[str, ContextElement] = {}
        self.sakshi: str | None = None
        self.budget_total: int = DEFAULT_BUDGET_TOKENS
        self.budget_used: int = 0


STATE = _State()


# ----------------------------------------------------------------------
# Pydantic input models
# ----------------------------------------------------------------------

class InsertInput(BaseModel):
    id: str = Field(..., description="Unique element id within this session.")
    content: str = Field(..., description="The verbatim claim or passage.")
    precision: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence in [0, 1].")
    qualificand: str = Field(..., description="What is being qualified (subject of the claim).")
    qualifier: str = Field(..., description="The qualifier (predicate / property).")
    condition: str = Field(..., description='Limitor condition; AND-conjunctive tokens, e.g. "version=2.0 AND lang=en".')
    relation: str = Field("inherence", description="Relational mode (inherence | identity | composition).")
    provenance: str = Field("", description="Source URL, file:line, or tool call id.")
    overwrite: bool = Field(False, description="Replace if id already exists.")


class RetrieveInput(BaseModel):
    qualificand: str
    condition: str = ""
    qualifier: str = ""
    precision_threshold: float = Field(0.5, ge=0.0, le=1.0)
    max_elements: int = Field(20, ge=1, le=200)


class SublateInput(BaseModel):
    element_id: str = Field(..., description="Element being sublated (precision drops to 0.0).")
    by_element_id: str = Field(..., description="The newer/higher-precision element that overrides it.")


class SublateWithEvidenceInput(BaseModel):
    older_id: str
    newer_content: str
    newer_precision: float = Field(..., ge=0.0, le=1.0)
    qualificand: str
    qualifier: str
    condition: str
    provenance: str = ""


class CompactInput(BaseModel):
    precision_threshold: float = Field(0.3, ge=0.0, le=1.0)
    qualificand: str = Field("", description="Optional: only compact within this qualificand.")
    task_context: str = Field("", description='Optional AND-conjunctive scope, e.g. "lang=en AND task=qa".')


class ContextWindowInput(BaseModel):
    qualificand: str
    condition: str = ""
    max_tokens: int = Field(4096, ge=64, le=200_000)
    precision_threshold: float = Field(0.5, ge=0.0, le=1.0)


class BoundaryCompactInput(BaseModel):
    text_window: str = Field(..., description="Recent assistant/user text. Boundary detector runs on this.")
    threshold_z: float = Field(2.0, description="Z-score threshold for surprise spikes.")
    precision_threshold: float = Field(0.3, ge=0.0, le=1.0)


class ClassifyInput(BaseModel):
    claim: str
    ground_truth: str
    context: str = ""


class SetSakshiInput(BaseModel):
    content: str = Field(..., description="The witness invariant. Should be ≤500 tokens, stable across the session.")


class GetByIdInput(BaseModel):
    element_id: str


class BudgetStatusInput(BaseModel):
    last_n: int = Field(20, ge=1, le=1000, description="How many recent ledger records to include in the response.")


# ----------------------------------------------------------------------
# Helpers shared across tools
# ----------------------------------------------------------------------

def _matches(query: RetrieveInput, e: ContextElement) -> bool:
    if e.avacchedaka.qualificand != query.qualificand:
        return False
    if query.qualifier:
        # Substring match honours the typed (qualificand, qualifier, condition) contract
        # promised by the public schema. Empty qualifier means "any qualifier".
        if query.qualifier.lower() not in e.avacchedaka.qualifier.lower():
            return False
    if not query.condition:
        return True
    have = {t.strip() for t in e.avacchedaka.condition.split(" AND ")}
    for tok in query.condition.split(" AND "):
        if tok.strip() not in have:
            return False
    return True


def _retrieve(query: RetrieveInput) -> list[ContextElement]:
    candidates = [
        e for e in STATE.elements.values()
        if e.sublated_by is None and e.precision >= query.precision_threshold and _matches(query, e)
    ]
    candidates.sort(key=lambda e: e.precision, reverse=True)
    return candidates[: query.max_elements]


def _serialize(e: ContextElement) -> dict[str, Any]:
    return {
        "id": e.id,
        "content": e.content,
        "precision": round(e.precision, 4),
        "qualificand": e.avacchedaka.qualificand,
        "qualifier": e.avacchedaka.qualifier,
        "condition": e.avacchedaka.condition,
        "relation": e.avacchedaka.relation,
        "provenance": e.provenance,
        "sublated_by": e.sublated_by,
        "timestamp": e.timestamp,
    }


# ----------------------------------------------------------------------
# Khyativada — pure-Python heuristic classifier (fast, deterministic)
# ----------------------------------------------------------------------

_KHYATIVADA_CLASSES = (
    "anyathakhyati", "atmakhyati", "anirvacaniyakhyati",
    "asatkhyati", "viparitakhyati", "akhyati", "none",
)


def _classify_khyativada(claim: str, ground_truth: str, context: str = "") -> dict[str, Any]:
    """7-class Vedic error taxonomy, heuristic backend.

    Mirrors the few-shot classifier guardrails so the plugin works
    offline without touching the Anthropic API.
    """
    claim_l = claim.lower()
    gt_l = ground_truth.lower()

    if any(c in gt_l for c in (" no such ", " does not exist", " never existed", " is not a ", " has no ")):
        return {"class": "asatkhyati", "confidence": 0.82, "rationale": "Ground truth asserts the referenced entity does not exist."}
    if " but not for " in gt_l or " but not due to " in gt_l or "incorrectly attributed" in gt_l:
        return {"class": "akhyati", "confidence": 0.78, "rationale": "True components combined into a false relation."}
    claim_v = re.findall(r"\d+(?:\.\d+)+", claim)
    gt_v = re.findall(r"\d+(?:\.\d+)+", ground_truth)
    if claim_v and gt_v and set(claim_v) != set(gt_v):
        return {"class": "anyathakhyati", "confidence": 0.80, "rationale": "Version/identifier mismatch — real entity misidentified."}
    if " opposite " in gt_l or " inverted " in gt_l or " swapped " in gt_l:
        return {"class": "viparitakhyati", "confidence": 0.78, "rationale": "Polarity reversed."}
    if " plausible-sounding " in gt_l or " confabulat" in gt_l or " not in any documented" in gt_l:
        return {"class": "anirvacaniyakhyati", "confidence": 0.72, "rationale": "Novel confabulation; neither true nor pre-existing."}
    if claim_l.strip() == gt_l.strip():
        return {"class": "none", "confidence": 0.95, "rationale": "Claim and ground truth coincide."}
    return {"class": "atmakhyati", "confidence": 0.55, "rationale": "Default: subjective projection mistaken for object property."}


# ----------------------------------------------------------------------
# FastMCP server
# ----------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(_app):
    logger.info("pratyaksha MCP server starting; cache=%s", CACHE_DIR)
    yield
    logger.info("pratyaksha MCP server shutting down")


mcp = FastMCP("pratyaksha", lifespan=_lifespan)


# --- Family 1: Avacchedaka store ---

@mcp.tool()
def context_insert(args: InsertInput) -> dict[str, Any]:
    """Insert a typed claim into the per-session context store.

    The Avacchedaka (qualificand, qualifier, condition) triple is the
    primary key for retrieval. Two claims with the same surface text but
    different conditions are treated as distinct.
    """
    if args.id in STATE.elements and not args.overwrite:
        return {"ok": False, "error": f"element {args.id!r} already exists; pass overwrite=true"}
    elem = ContextElement(
        id=args.id,
        content=args.content,
        precision=args.precision,
        avacchedaka=AvacchedakaConditions(
            qualificand=args.qualificand,
            qualifier=args.qualifier,
            condition=args.condition,
            relation=args.relation,
        ),
        timestamp=time.time(),
        provenance=args.provenance,
    )
    STATE.elements[args.id] = elem
    _audit("insert", {"id": args.id, "qualificand": args.qualificand, "precision": args.precision})
    return {"ok": True, "element": _serialize(elem), "store_size": len(STATE.elements)}


@mcp.tool()
def context_retrieve(args: RetrieveInput) -> dict[str, Any]:
    """Retrieve claims matching the typed query, sorted by precision DESC.

    Only non-sublated elements with `precision >= precision_threshold`
    are returned, capped at `max_elements`.
    """
    elements = _retrieve(args)
    return {
        "ok": True,
        "count": len(elements),
        "elements": [_serialize(e) for e in elements],
    }


@mcp.tool()
def context_get(args: GetByIdInput) -> dict[str, Any]:
    """Fetch a single element by id (including sublated ones, for audit)."""
    e = STATE.elements.get(args.element_id)
    if not e:
        return {"ok": False, "error": f"element {args.element_id!r} not found"}
    return {"ok": True, "element": _serialize(e)}


@mcp.tool()
def context_sublate(args: SublateInput) -> dict[str, Any]:
    """Mark `element_id` as sublated by `by_element_id`.

    Sublation is *not* deletion — the element stays in the store with
    `precision=0.0` and `sublated_by` set, so it remains auditable but
    will not be returned by `context_retrieve`.
    """
    if args.element_id not in STATE.elements:
        return {"ok": False, "error": f"element {args.element_id!r} not found"}
    if args.by_element_id not in STATE.elements:
        return {"ok": False, "error": f"sublating element {args.by_element_id!r} not found"}
    STATE.elements[args.element_id] = replace(
        STATE.elements[args.element_id], sublated_by=args.by_element_id, precision=0.0
    )
    _audit("sublate", {"id": args.element_id, "by": args.by_element_id})
    return {"ok": True, "sublated_id": args.element_id, "by": args.by_element_id}


@mcp.tool()
def list_qualificands() -> dict[str, Any]:
    """List unique (qualificand, count, mean_precision) across the store."""
    buckets: dict[str, list[ContextElement]] = {}
    for e in STATE.elements.values():
        if e.sublated_by is not None:
            continue
        buckets.setdefault(e.avacchedaka.qualificand, []).append(e)
    rows = [
        {
            "qualificand": q,
            "count": len(es),
            "mean_precision": round(sum(e.precision for e in es) / len(es), 4) if es else 0.0,
        }
        for q, es in sorted(buckets.items())
    ]
    return {"ok": True, "qualificands": rows}


# --- Family 2: Sublation with evidence ---

@mcp.tool()
def sublate_with_evidence(args: SublateWithEvidenceInput) -> dict[str, Any]:
    """Insert a higher-precision newer element and atomically sublate the older one.

    Use this when the agent discovers fresh evidence that contradicts a
    previously-stored claim — it preserves the audit trail (older element
    stays in the store with `precision=0.0`) while preventing the older
    claim from leaking into future retrievals.
    """
    if args.older_id not in STATE.elements:
        return {"ok": False, "error": f"older element {args.older_id!r} not found"}
    older = STATE.elements[args.older_id]
    # B1 idempotence: short-circuit if the older element has already been sublated.
    # Without this guard, a second call with any positive newer_precision would
    # slip through the precision check (since older.precision was zeroed by the
    # first sublation) and create another sublator silently.
    if older.sublated_by is not None:
        return {
            "ok": True,
            "already_sublated": True,
            "older_id": args.older_id,
            "by": older.sublated_by,
            "note": "no-op; older element was already sublated",
        }
    if args.newer_precision <= older.precision:
        return {
            "ok": False,
            "error": f"newer precision {args.newer_precision} must exceed older {older.precision} to justify sublation",
        }
    # B2 ID collision: combine ms-timestamp with a uuid4 suffix so two sublations
    # in the same millisecond produce distinct ids and never overwrite each other
    # in STATE.elements.
    new_id = f"{args.older_id}__sublator__{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    newer = ContextElement(
        id=new_id,
        content=args.newer_content,
        precision=args.newer_precision,
        avacchedaka=AvacchedakaConditions(
            qualificand=args.qualificand,
            qualifier=args.qualifier,
            condition=args.condition,
        ),
        timestamp=time.time(),
        provenance=args.provenance,
    )
    STATE.elements[new_id] = newer
    STATE.elements[args.older_id] = replace(older, sublated_by=new_id, precision=0.0)
    _audit("sublate_with_evidence", {"older_id": args.older_id, "newer_id": new_id, "delta": args.newer_precision - older.precision})
    return {"ok": True, "newer_id": new_id, "newer": _serialize(newer)}


@mcp.tool()
def detect_conflict(args: RetrieveInput) -> dict[str, Any]:
    """Detect candidate conflicts within a (qualificand, condition) bucket.

    Flags element pairs whose precisions both exceed the threshold but
    whose content differs by more than `_token_jaccard_distance(0.5)` —
    these are surfaced as "needs human or agent sublation".
    """
    elements = _retrieve(args)
    pairs: list[dict[str, Any]] = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            a, b = elements[i], elements[j]
            tokens_a = set(re.findall(r"\w+", a.content.lower()))
            tokens_b = set(re.findall(r"\w+", b.content.lower()))
            if not tokens_a or not tokens_b:
                continue
            jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
            if jaccard < 0.5:
                pairs.append({
                    "a_id": a.id, "b_id": b.id,
                    "a_precision": a.precision, "b_precision": b.precision,
                    "jaccard": round(jaccard, 3),
                })
    return {"ok": True, "conflict_pairs": pairs, "n_examined": len(elements)}


# --- Family 3: Compaction ---

@mcp.tool()
def compact(args: CompactInput) -> dict[str, Any]:
    """Drop precision to 0.0 on non-sublated elements below `precision_threshold`.

    Optional `qualificand` and `task_context` arguments scope the
    compaction (G7 invariant): only elements whose conditions are a
    superset of `task_context` AND-tokens are eligible.
    """
    need_tokens = {t.strip() for t in args.task_context.split(" AND ")} if args.task_context else set()
    compressed: list[str] = []
    for eid, elem in list(STATE.elements.items()):
        if elem.sublated_by is not None:
            continue
        if not (0 < elem.precision < args.precision_threshold):
            continue
        if args.qualificand and elem.avacchedaka.qualificand != args.qualificand:
            continue
        if need_tokens:
            have = {t.strip() for t in elem.avacchedaka.condition.split(" AND ")}
            if not need_tokens.issubset(have):
                continue
        STATE.elements[eid] = replace(elem, precision=0.0)
        compressed.append(eid)
    _audit("compact", {"n_compressed": len(compressed), "qualificand": args.qualificand or None})
    return {"ok": True, "compressed_ids": compressed, "n_compressed": len(compressed)}


@mcp.tool()
def boundary_compact(args: BoundaryCompactInput) -> dict[str, Any]:
    """Detect a discourse boundary in `text_window` via heuristic surprise spikes,
    then trigger `compact` if a boundary is found.

    Heuristic backend: tokenize on word boundaries, treat token novelty
    (1 / log-rank) as a proxy for per-token NLL, smooth, and flag the
    rightmost spike with `z >= threshold_z`. This avoids requiring a
    local LM at runtime; users who want true per-token surprise should
    install the optional `surprise-vllm` extra.
    """
    tokens = re.findall(r"\w+", args.text_window.lower())
    if len(tokens) < 16:
        return {"ok": True, "boundary_detected": False, "reason": "window too short"}
    seen: dict[str, int] = {}
    novelty: list[float] = []
    for i, tok in enumerate(tokens):
        seen[tok] = seen.get(tok, 0) + 1
        novelty.append(1.0 / (1 + seen[tok]))
    mean = sum(novelty) / len(novelty)
    var = sum((x - mean) ** 2 for x in novelty) / len(novelty)
    std = max(var ** 0.5, 1e-6)
    z = [(x - mean) / std for x in novelty]
    spike_idx = max(range(len(z)), key=lambda i: z[i])
    if z[spike_idx] < args.threshold_z:
        return {"ok": True, "boundary_detected": False, "max_z": round(z[spike_idx], 3)}
    compact_args = CompactInput(precision_threshold=args.precision_threshold)
    result = compact(compact_args)
    _audit("boundary_compact", {"max_z": z[spike_idx], "compressed": result["n_compressed"]})
    return {
        "ok": True,
        "boundary_detected": True,
        "max_z": round(z[spike_idx], 3),
        "spike_token_index": spike_idx,
        "compaction": result,
    }


@mcp.tool()
def context_window(args: ContextWindowInput) -> dict[str, Any]:
    """Materialize retrieved elements as a single token-budgeted string.

    Budget is enforced in *tokenizer-exact* tokens (G12 invariant) using
    tiktoken's `o200k_base` encoding. Elements are appended in
    precision-DESC order until the next element would exceed `max_tokens`.
    """
    query = RetrieveInput(
        qualificand=args.qualificand,
        condition=args.condition,
        precision_threshold=args.precision_threshold,
        max_elements=200,
    )
    elements = _retrieve(query)
    parts: list[str] = []
    used = 0
    included: list[str] = []
    for e in elements:
        block = f"[{e.avacchedaka.qualificand}|precision={e.precision:.2f}] {e.content}"
        block_tokens = _count_tokens(block)
        extra = 1 if parts else 0
        if used + block_tokens + extra > args.max_tokens:
            break
        parts.append(block)
        included.append(e.id)
        used += block_tokens + extra
    return {
        "ok": True,
        "context_window": "\n".join(parts),
        "tokens_used": used,
        "tokens_budget": args.max_tokens,
        "n_included": len(included),
        "included_ids": included,
    }


# --- Family 4: Witness (Sākṣī) ---

@mcp.tool()
def set_sakshi(args: SetSakshiInput) -> dict[str, Any]:
    """Set the witness invariant for the current session.

    The Sākṣī content should be pushed to Claude as a system message at
    every model call (the `witness-prefix` skill enforces this). Keep it
    short (≤500 tokens) and stable — invariants that change every turn
    are not invariants.
    """
    tokens = _count_tokens(args.content)
    if tokens > 500:
        return {"ok": False, "error": f"sakshi too long: {tokens} tokens > 500 budget"}
    STATE.sakshi = args.content
    _audit("set_sakshi", {"tokens": tokens})
    return {"ok": True, "tokens": tokens, "system_message": f"<sakshi_prefix>\n{args.content}\n</sakshi_prefix>"}


@mcp.tool()
def get_sakshi() -> dict[str, Any]:
    """Return the current witness invariant (or null if unset)."""
    if STATE.sakshi is None:
        return {"ok": True, "sakshi": None, "tokens": 0}
    return {
        "ok": True,
        "sakshi": STATE.sakshi,
        "tokens": _count_tokens(STATE.sakshi),
        "system_message": f"<sakshi_prefix>\n{STATE.sakshi}\n</sakshi_prefix>",
    }


# --- Family 5: Khyativada classifier ---

@mcp.tool()
def classify_khyativada(args: ClassifyInput) -> dict[str, Any]:
    """Classify a (claim, ground_truth) pair against the 7-class Vedic taxonomy.

    Classes: anyathakhyati, atmakhyati, anirvacaniyakhyati, asatkhyati,
    viparitakhyati, akhyati, none. Heuristic backend — see the project's
    `FewShotKhyativadaClassifier` for the LLM-backed equivalent.
    """
    out = _classify_khyativada(args.claim, args.ground_truth, args.context)
    out["taxonomy"] = list(_KHYATIVADA_CLASSES)
    return {"ok": True, **out}


# --- Family 6: Budget / observability ---

@mcp.tool()
def budget_status(args: BudgetStatusInput) -> dict[str, Any]:
    """Report the user-local token budget plus a cost-ledger summary.

    Combines two views:
      - **gauge**: total budget, tokens used so far this session, remaining.
      - **ledger**: last `last_n` recorded calls plus per-model totals from the
        on-disk JSONL ledger at `~/.cache/pratyaksha/cost_ledger.jsonl`.

    Tokens are recorded via `budget_record` after each agent turn — Claude
    Code's own usage telemetry is authoritative; this is a local mirror so
    the agent can self-throttle without round-tripping the runtime.
    """
    records: list[dict[str, Any]] = []
    if COST_LEDGER.exists():
        for line in COST_LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    by_model: dict[str, int] = {}
    for r in records:
        m = r.get("model", "")
        by_model[m] = by_model.get(m, 0) + r.get("tokens", 0)
    return {
        "ok": True,
        "budget_total": STATE.budget_total,
        "budget_used": STATE.budget_used,
        "remaining": max(0, STATE.budget_total - STATE.budget_used),
        "exhausted": STATE.budget_used >= STATE.budget_total,
        "ledger_n_calls": len(records),
        "ledger_total_tokens": sum(r.get("tokens", 0) for r in records),
        "ledger_by_model": by_model,
        "ledger_recent": records[-args.last_n:],
    }


class BudgetRecordInput(BaseModel):
    tokens: int = Field(..., ge=0, description="Tokens consumed by the most recent turn.")
    model: str = Field("", description="Model identifier (optional, recorded in cost ledger).")
    note: str = Field("", description="Free-form description of the call.")


@mcp.tool()
def budget_record(args: BudgetRecordInput) -> dict[str, Any]:
    """Record a token spend against the local budget and append to the cost ledger.

    Side effect: also rewrites `~/.cache/pratyaksha/budget.json` so the
    plugin's hook scripts (which run in separate processes) can read
    the current gauge.
    """
    STATE.budget_used += args.tokens
    record = {"ts": time.time(), "tokens": args.tokens, "model": args.model, "note": args.note}
    try:
        with COST_LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        logger.warning("cost ledger write failed: %s", e)
    _write_budget_gauge(STATE.budget_total, STATE.budget_used)
    return {
        "ok": True,
        "recorded": record,
        "budget_used": STATE.budget_used,
        "remaining": max(0, STATE.budget_total - STATE.budget_used),
    }


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
