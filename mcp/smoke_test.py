#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.0.0",
# ]
# ///
"""Smoke test for the pratyaksha MCP server.

Spawns the server under uv via stdio and exercises every one of the 15
tools end-to-end through JSON-RPC. Verifies:

  * Server boots and answers `tools/list` with exactly 15 tools.
  * Each tool's input schema is well-formed (tested implicitly by the
    fact that valid calls succeed).
  * Avacchedaka store: insert, retrieve, get, list_qualificands.
  * Sublation: explicit `context_sublate` and `sublate_with_evidence`
    (rejects non-improving precision; accepts strict improvement).
  * Conflict detection: detect_conflict surfaces low-Jaccard pairs.
  * Compaction: scoped `compact` and `boundary_compact` (heuristic
    backend on a synthetic surprise-spike text window).
  * Witness: set_sakshi (rejects > 500 tokens) and get_sakshi.
  * Khyativada: classifies asatkhyati and viparitakhyati cases.
  * Budget: budget_record + budget_status round-trip, including the
    on-disk gauge mirror at $PRATYAKSHA_CACHE_DIR/budget.json.
  * Audit log + cost ledger files written.

Run with:

    uv run --no-project plugin/pratyaksha-context-eng-harness/mcp/smoke_test.py

Exits 0 on success, 1 on any check failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_DIR = Path(__file__).resolve().parent
SERVER_PATH = SERVER_DIR / "server.py"


class SmokeFailure(AssertionError):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SmokeFailure(msg)


def _content_to_dict(result) -> dict:
    """FastMCP returns CallToolResult; pull the JSON dict out of the first content block."""
    if not result.content:
        raise SmokeFailure(f"empty content in tool result: {result!r}")
    block = result.content[0]
    text = getattr(block, "text", None)
    if text is None:
        raise SmokeFailure(f"non-text content block: {block!r}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}


async def run_smoke(cache_dir: Path) -> None:
    env = os.environ.copy()
    env["PRATYAKSHA_CACHE_DIR"] = str(cache_dir)

    params = StdioServerParameters(
        command="uv",
        args=["run", "--no-project", str(SERVER_PATH)],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ---- 1. tools/list ----
            tools_result = await session.list_tools()
            tools = tools_result.tools
            check(len(tools) == 15, f"expected 15 tools, got {len(tools)}: {[t.name for t in tools]}")
            tool_names = sorted(t.name for t in tools)
            expected = sorted([
                "context_insert", "context_retrieve", "context_get",
                "context_sublate", "list_qualificands",
                "sublate_with_evidence", "detect_conflict",
                "compact", "boundary_compact", "context_window",
                "set_sakshi", "get_sakshi",
                "classify_khyativada",
                "budget_status", "budget_record",
            ])
            check(tool_names == expected, f"tool name mismatch:\n  got      {tool_names}\n  expected {expected}")
            print("[1/9] tools/list: 15 tools ✓")

            # ---- 2. context_insert / get / retrieve / list_qualificands ----
            r = await session.call_tool("context_insert", {"args": {
                "id": "claim_v1", "content": "uv version is 0.11.2",
                "precision": 0.7, "qualificand": "uv_version",
                "qualifier": "is", "condition": "lang=en AND year=2026",
                "provenance": "smoke_test"
            }})
            d = _content_to_dict(r)
            check(d["ok"] is True, f"insert failed: {d}")

            r = await session.call_tool("context_insert", {"args": {
                "id": "claim_v1", "content": "duplicate", "precision": 0.5,
                "qualificand": "x", "qualifier": "y", "condition": "z=1"
            }})
            d = _content_to_dict(r)
            check(d["ok"] is False, f"duplicate id should reject: {d}")

            r = await session.call_tool("context_get", {"args": {"element_id": "claim_v1"}})
            d = _content_to_dict(r)
            check(d["ok"] is True and d["element"]["precision"] == 0.7, f"get round-trip wrong: {d}")

            r = await session.call_tool("context_retrieve", {"args": {
                "qualificand": "uv_version", "condition": "lang=en", "precision_threshold": 0.5
            }})
            d = _content_to_dict(r)
            check(d["count"] == 1, f"retrieve should find 1: {d}")

            r = await session.call_tool("list_qualificands", {})
            d = _content_to_dict(r)
            check(any(row["qualificand"] == "uv_version" for row in d["qualificands"]),
                  f"list_qualificands missing uv_version: {d}")
            print("[2/9] insert / get / retrieve / list_qualificands ✓")

            # ---- 3. sublate_with_evidence ----
            r = await session.call_tool("sublate_with_evidence", {"args": {
                "older_id": "claim_v1", "newer_content": "uv version is 0.12.0",
                "newer_precision": 0.7, "qualificand": "uv_version",
                "qualifier": "is", "condition": "lang=en AND year=2026"
            }})
            d = _content_to_dict(r)
            check(d["ok"] is False, f"non-strict precision should reject: {d}")

            r = await session.call_tool("sublate_with_evidence", {"args": {
                "older_id": "claim_v1", "newer_content": "uv version is 0.12.0",
                "newer_precision": 0.95, "qualificand": "uv_version",
                "qualifier": "is", "condition": "lang=en AND year=2026"
            }})
            d = _content_to_dict(r)
            check(d["ok"] is True, f"sublate_with_evidence failed: {d}")
            newer_id = d["newer_id"]

            # Older claim should now be sublated; retrieve should return only the newer.
            r = await session.call_tool("context_retrieve", {"args": {
                "qualificand": "uv_version", "condition": "lang=en"
            }})
            d = _content_to_dict(r)
            check(d["count"] == 1 and d["elements"][0]["id"] == newer_id,
                  f"retrieve should return only newer: {d}")
            print("[3/9] sublate_with_evidence + retrieval-invisible older ✓")

            # ---- 4. context_sublate (manual id-by-id) ----
            await session.call_tool("context_insert", {"args": {
                "id": "manual_a", "content": "fact A v1", "precision": 0.6,
                "qualificand": "manual_q", "qualifier": "is", "condition": "v=1"
            }})
            await session.call_tool("context_insert", {"args": {
                "id": "manual_b", "content": "fact A v2", "precision": 0.85,
                "qualificand": "manual_q", "qualifier": "is", "condition": "v=2"
            }})
            r = await session.call_tool("context_sublate", {"args": {
                "element_id": "manual_a", "by_element_id": "manual_b"
            }})
            d = _content_to_dict(r)
            check(d["ok"] is True, f"context_sublate failed: {d}")
            print("[4/9] context_sublate ✓")

            # ---- 5. detect_conflict ----
            await session.call_tool("context_insert", {"args": {
                "id": "conf_a", "content": "the cat sat on the mat under the sun",
                "precision": 0.7, "qualificand": "story", "qualifier": "claim",
                "condition": "topic=cats"
            }})
            await session.call_tool("context_insert", {"args": {
                "id": "conf_b", "content": "ducks swimming over rivers near forests",
                "precision": 0.7, "qualificand": "story", "qualifier": "claim",
                "condition": "topic=cats"
            }})
            r = await session.call_tool("detect_conflict", {"args": {
                "qualificand": "story", "condition": "topic=cats", "precision_threshold": 0.5
            }})
            d = _content_to_dict(r)
            check(len(d["conflict_pairs"]) >= 1, f"detect_conflict missed pair: {d}")
            print("[5/9] detect_conflict surfaces low-Jaccard pair ✓")

            # ---- 6. compact / boundary_compact / context_window ----
            await session.call_tool("context_insert", {"args": {
                "id": "low_p", "content": "low precision claim", "precision": 0.2,
                "qualificand": "compactable", "qualifier": "x", "condition": "scope=test"
            }})
            r = await session.call_tool("compact", {"args": {
                "precision_threshold": 0.3, "qualificand": "compactable",
                "task_context": "scope=test"
            }})
            d = _content_to_dict(r)
            check("low_p" in d["compressed_ids"], f"compact missed low_p: {d}")

            text_window = (
                "alpha beta gamma delta " * 16 +
                "ZZZZZ unique unique unique unique unique unique unique unique"
            )
            r = await session.call_tool("boundary_compact", {"args": {
                "text_window": text_window, "threshold_z": 1.0
            }})
            d = _content_to_dict(r)
            check(d["ok"] is True, f"boundary_compact errored: {d}")

            r = await session.call_tool("context_window", {"args": {
                "qualificand": "uv_version", "condition": "lang=en",
                "max_tokens": 4096, "precision_threshold": 0.5
            }})
            d = _content_to_dict(r)
            check(d["n_included"] >= 1 and "uv version" in d["context_window"].lower(),
                  f"context_window missing materialised content: {d}")
            print("[6/9] compact + boundary_compact + context_window ✓")

            # ---- 7. set_sakshi / get_sakshi ----
            r = await session.call_tool("set_sakshi", {"args": {
                "content": "Hard rule: do not modify v0 baseline files. Active hypothesis: H1."
            }})
            d = _content_to_dict(r)
            check(d["ok"] is True and "<sakshi_prefix>" in d["system_message"],
                  f"set_sakshi failed: {d}")

            r = await session.call_tool("set_sakshi", {"args": {"content": "x " * 1000}})
            d = _content_to_dict(r)
            check(d["ok"] is False, f"oversize sakshi should reject: {d}")

            r = await session.call_tool("get_sakshi", {})
            d = _content_to_dict(r)
            check(d["sakshi"] is not None, f"get_sakshi did not retain set value: {d}")
            print("[7/9] set_sakshi + get_sakshi (with token guardrail) ✓")

            # ---- 8. classify_khyativada ----
            r = await session.call_tool("classify_khyativada", {"args": {
                "claim": "The function is called purify_input.",
                "ground_truth": "There is no such function in the codebase."
            }})
            d = _content_to_dict(r)
            check(d["class"] == "asatkhyati", f"asatkhyati misclassified: {d}")

            r = await session.call_tool("classify_khyativada", {"args": {
                "claim": "Increasing temperature decreases creativity.",
                "ground_truth": "The relationship is opposite — higher temperature increases creativity."
            }})
            d = _content_to_dict(r)
            check(d["class"] == "viparitakhyati", f"viparitakhyati misclassified: {d}")
            print("[8/9] classify_khyativada (asat + viparita) ✓")

            # ---- 9. budget_record + budget_status + on-disk gauge ----
            r = await session.call_tool("budget_record", {"args": {
                "tokens": 12345, "model": "claude-sonnet-4-6", "note": "smoke test entry"
            }})
            d = _content_to_dict(r)
            check(d["ok"] is True and d["budget_used"] == 12345, f"budget_record wrong: {d}")

            r = await session.call_tool("budget_status", {"args": {"last_n": 5}})
            d = _content_to_dict(r)
            check(
                d["budget_used"] == 12345 and d["ledger_n_calls"] >= 1
                and d["ledger_by_model"].get("claude-sonnet-4-6") == 12345,
                f"budget_status wrong: {d}",
            )

            gauge_path = cache_dir / "budget.json"
            check(gauge_path.exists(), f"budget gauge file not written at {gauge_path}")
            gauge = json.loads(gauge_path.read_text())
            check(
                gauge["used"] == 12345 and gauge["total"] >= 12345
                and gauge["remaining"] == gauge["total"] - 12345,
                f"gauge contents wrong: {gauge}",
            )

            audit_path = cache_dir / "audit.jsonl"
            ledger_path = cache_dir / "cost_ledger.jsonl"
            check(audit_path.exists() and audit_path.stat().st_size > 0,
                  f"audit log missing/empty at {audit_path}")
            check(ledger_path.exists() and ledger_path.stat().st_size > 0,
                  f"cost ledger missing/empty at {ledger_path}")
            print("[9/9] budget_record + budget_status + gauge mirror + audit/ledger ✓")


def main() -> int:
    cache_dir = Path(tempfile.mkdtemp(prefix="pratyaksha_smoke_"))
    try:
        asyncio.run(run_smoke(cache_dir))
        print("\n=== SMOKE TEST PASSED — all 15 tools exercised end-to-end ===")
        return 0
    except SmokeFailure as e:
        print(f"\n=== SMOKE TEST FAILED ===\n{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n=== SMOKE TEST ERRORED ===\n{type(e).__name__}: {e}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
