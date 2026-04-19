# pratyaksha-context-eng-harness

> **Long-context discipline for Claude Code, grounded in Vedic epistemology.**
> Typed retrieval (Avacchedaka), conflict-resolution by sublation (bādha),
> witness invariants (Sākṣī), event-boundary compaction, and a 7-class
> hallucination taxonomy (Khyātivāda) — surfaced as **15 MCP tools, 3
> skills, 3 agents, 4 slash commands, and 3 lifecycle hooks**.

> **New here?** Jump to [**QUICKSTART.md**](QUICKSTART.md) for a
> 30-minute hands-on tour with five challenging end-to-end examples.

## Why

Long context windows do not solve long-context problems. The failure modes
that hurt agents in production are *not* "the window is too small" but
**topic drift**, **stale-claim retrieval**, **conflicting sources**,
**discourse-boundary blindness**, and **silent confabulation**. This
plugin addresses each one with a discrete, auditable mechanism:

| Failure mode                  | Mechanism                       | MCP tool(s)                                          |
|-------------------------------|---------------------------------|------------------------------------------------------|
| Topic drift in retrieval      | Avacchedaka-typed query         | `context_insert`, `context_retrieve`                 |
| Stale / contradicted claims   | Sublation (bādha)               | `sublate_with_evidence`, `context_sublate`           |
| Conflicting sources           | Pairwise conflict detection     | `detect_conflict`                                    |
| System-prompt drift           | Sākṣī (witness) invariant       | `set_sakshi`, `get_sakshi`                           |
| Discourse-boundary blindness  | Surprise-spike compaction       | `boundary_compact`, `compact`                        |
| Silent confabulation          | Khyātivāda 7-class taxonomy     | `classify_khyativada`                                |
| Token-budget blindness        | Local cost ledger               | `budget_status`, `budget_record`                     |

Mechanisms compose: every retrieval is typed; every conflict is sublated
without deletion; every Manas/Buddhi turn carries the Sākṣī as a true
system message; every long phase ends with a scoped compaction.

## Install

This repo ships as a Claude Code marketplace plugin. Pick one of three
paths.

### A. One-line install via Claude Code (recommended)

```bash
# 0. One-time prerequisite (skip if already installed):
curl -LsSf https://astral.sh/uv/install.sh | sh

# 1. From any Claude Code session (CLI, VS Code, Cursor, or desktop):
/plugin marketplace add SharathSPhD/pratyaksha-context-eng-harness
/plugin install pratyaksha-context-eng-harness@pratyaksha-context-eng-harness
```

The first MCP tool call takes ~30 s while `uv` downloads `mcp`,
`pydantic`, and `tiktoken`. Subsequent calls are instant.

### B. Local clone (for development or air-gapped machines)

```bash
git clone https://github.com/SharathSPhD/pratyaksha-context-eng-harness.git ~/.claude/plugins/pratyaksha-context-eng-harness
/plugin marketplace add ~/.claude/plugins/pratyaksha-context-eng-harness
/plugin install pratyaksha-context-eng-harness@pratyaksha-context-eng-harness
```

### C. Cursor / IDE smoke-test (MCP-only, no plugin loader)

If you only want the 15 MCP tools (no skills/agents/commands/hooks),
register the server directly. From the cloned repo root:

```bash
uv run --no-project mcp/server.py   # smoke-test it boots; Ctrl-C to exit
```

Then point your IDE at `mcp/server.py` (Cursor / VS Code / any
MCP-aware client). See the [Cursor smoke-test
section](#cursor-vs-code-mcp-only) below for an exact `~/.cursor/mcp.json`
snippet.

No `claude mcp add`, no virtualenv, no `pip install`. The plugin's
`mcp/server.py` is a [PEP 723](https://peps.python.org/pep-0723/)
self-installing script — `uv` reads its inline header and provisions
dependencies on first run.

## Components

### MCP server: `pratyaksha`

15 tools across 6 families:

```
Family                | Tools
--------------------- | --------------------------------------------------
Avacchedaka store     | context_insert / context_retrieve / context_get /
                      |   context_sublate / list_qualificands
Sublation             | sublate_with_evidence / detect_conflict
Compaction            | compact / boundary_compact / context_window
Witness (Sākṣī)       | set_sakshi / get_sakshi
Hallucination class   | classify_khyativada
Budget / observability| budget_status / budget_record
```

All tools are exposed under the `mcp__pratyaksha_mcp__*` namespace.
Mutating calls are appended to a JSONL audit log at
`~/.cache/pratyaksha/audit.jsonl`; you can `tail -f` it during a
long session to watch exactly what the agent did.

### Skills

- `context-discipline` — when and how to use typed insertion, sublation
  on conflict, and boundary-triggered compaction.
- `sublate-on-conflict` — bādha decision procedure based on provenance,
  precision, and timestamps.
- `witness-prefix` — Sākṣī authoring rules: ≤500 tokens, stable, no
  reasoning content, pushed as a real `system` field.

### Agents

- `manas` — fast/intuitive subagent that produces first drafts using
  the typed store and the Sākṣī. Sets `needs_buddhi: true` when
  uncertain.
- `buddhi` — slow/deliberate verifier subagent. Re-fetches evidence,
  sublates contradicted claims with `sublate_with_evidence`, and
  emits final answers with citations.
- `sakshi-keeper` — owns the witness invariant: derives it from
  `CLAUDE.md` + user input, updates on hard-rule changes, and
  enforces the ≤500-token budget.

### Slash commands

- `/context-status` — current store state, qualificand surface, mean
  precisions, Sākṣī token count, recent ledger entries.
- `/sublate <id> [by <id> | with-evidence ...]` — manual bādha; refuses
  if newer precision does not strictly exceed older.
- `/budget [last <n> | reset]` — local gauge + ledger summary.
- `/compact-now [threshold=2.5] [qualificand=…] [task_context=…]` —
  force boundary compaction over the recent window.

### Lifecycle hooks

- `SessionStart` — emits one-shot guidance to bootstrap the Sākṣī.
- `PreToolUse` (`mcp__pratyaksha_mcp__.*`) — warns the agent when the
  local budget is ≥90% used or exhausted; never blocks.
- `Stop` — appends a `/compact-now` nudge when the session has spent
  ≥75% of the local budget.

All hooks **fail open**. A missing gauge file, missing `jq`, or any
other transient failure silently allows the underlying action; the
hooks are advisory, not gating.

## Self-containment

The shipped plugin tree contains **zero** runtime dependencies on
`attractor-flow`, `ralph-loop`, `vllm`, `mlflow`, `chromadb`, or any
other heavy ML stack. The only Python imports are `mcp`, `pydantic`,
and `tiktoken` — all installed automatically by `uv`. The Khyātivāda
classifier in `mcp/server.py` is a pure-Python heuristic that mirrors
the few-shot guardrails of the project's research-time classifier; if
you want the LLM-backed equivalent, install the optional
`pratyaksha-context-eng-harness[surprise]` extras from the parent
research repo.

## Layout

```
pratyaksha-context-eng-harness/
├── .claude-plugin/plugin.json     # Plugin manifest
├── .mcp.json                      # MCP server registration
├── marketplace.json               # Marketplace metadata
├── LICENSE                        # MIT
├── README.md                      # ← you are here
├── agents/
│   ├── manas.md                   # Fast/intuitive draft subagent
│   ├── buddhi.md                  # Slow/deliberate verifier subagent
│   └── sakshi-keeper.md           # Sākṣī invariant manager
├── commands/
│   ├── context-status.md
│   ├── sublate.md
│   ├── budget.md
│   └── compact-now.md
├── hooks/
│   ├── hooks.json                 # SessionStart / PreToolUse / Stop
│   ├── session-start.sh
│   ├── pretooluse-budget.sh
│   └── stop-compact.sh
├── mcp/
│   └── server.py                  # FastMCP server, 15 tools, PEP 723
└── skills/
    ├── context-discipline/SKILL.md
    ├── sublate-on-conflict/SKILL.md
    └── witness-prefix/SKILL.md
```

## Cursor / VS Code (MCP-only)

Cursor and VS Code don't yet load Claude Code marketplace plugins
(skills/agents/commands/hooks live behind the Claude Code plugin
loader). You can still use the **15 MCP tools** by registering
`mcp/server.py` directly.

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "pratyaksha": {
      "command": "uv",
      "args": [
        "run",
        "--no-project",
        "/absolute/path/to/pratyaksha-context-eng-harness/mcp/server.py"
      ]
    }
  }
}
```

Restart Cursor. The 15 tools appear under the `pratyaksha` namespace
(`pratyaksha.context_insert`, `pratyaksha.sublate_with_evidence`, …).

> Skills, agents, commands, and hooks require the Claude Code plugin
> loader and only run inside Claude Code today. The MCP server itself
> is portable to any MCP-aware client.

## Validation

The mechanisms shipped here are validated in the parent research
repository against:

- **Long-context**: RULER, HELMET, NoCha
- **Hallucination**: HaluEval, TruthfulQA, FACTS-Grounding
- **Code generation**: SWE-bench Verified

See the project preprint (linked from the repo) for the full
hypothesis registry (H1–H7), multi-seed runs, paired permutation tests,
and effect sizes.

## License

MIT — see [`LICENSE`](LICENSE).
