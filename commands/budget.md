---
description: Show local token budget gauge plus recent cost ledger entries (per-model totals, last N calls). Optionally reset the gauge.
argument-hint: "[last <n> | reset]"
---

# /budget

Show the local token budget gauge and recent cost ledger entries for the
current Claude Code session.

## Usage

```
/budget                # show recent 20 ledger entries
/budget last 50        # show recent 50 ledger entries
/budget reset          # zero the local gauge (does not clear the ledger)
```

## Instructions

When this command is invoked:

1. Parse `last <n>` if present (default 20).
2. If the user passed `reset`, ask for explicit confirmation before
   calling the underlying tool — the gauge is informational only, but
   resetting it mid-session loses the running total.
3. Call `budget_status({last_n: n})` and format with the template below.

## Output Template

```
## Local token budget

**Gauge:** {budget_used} / {budget_total} ({pct_used:.1f}% used, {remaining} remaining)
**Status:** {exhausted ? "⛔ EXHAUSTED" : remaining < budget_total * 0.1 ? "⚠️ near limit" : "✅ healthy"}

### Cost ledger
- Total recorded calls: {ledger_n_calls}
- Total recorded tokens: {ledger_total_tokens}

#### By model
| Model | Tokens |
|---|---|
| {model} | {tokens} |
| ... | ... |

#### Recent (last {n})
| ts (UTC) | tokens | model | note |
|---|---|---|---|
| {iso(r.ts)} | {r.tokens} | {r.model} | {r.note} |
| ... | ... | ... | ... |

---
**Tip:** the gauge is a local mirror — Claude Code's own usage telemetry
is authoritative. Budget figures here exist so the agent can self-throttle
without round-tripping the runtime.
```

## Notes

- The plugin does NOT auto-track tokens. Each agent call is responsible
  for calling `budget_record` with the spend it just incurred. The
  `manas` and `buddhi` agents do this automatically; user-level
  `/sublate`, `/compact-now`, and `/context-status` are read-only and
  cost approximately one MCP call each.
- The cost ledger is a JSONL file at `~/.cache/pratyaksha/cost_ledger.jsonl`
  — you can `tail -f` it during long sessions to watch spend in real time.
- Resetting the gauge does not delete ledger history — re-running
  `/budget` after a reset will still show the historical entries.
