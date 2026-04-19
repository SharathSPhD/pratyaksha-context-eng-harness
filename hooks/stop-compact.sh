#!/usr/bin/env bash
# Stop hook for pratyaksha-context-eng-harness.
#
# Purpose: when the agent finishes its turn, append a short follow-up
# nudge if the local budget gauge shows the session is getting hot.
# We never block stop; we only annotate.
#
# Output protocol (Claude Code Stop hooks):
#   - JSON on stdout. We can return `decision: "block"` with `reason`
#     to ask the model to keep going, but we *do not* want to do that
#     here — that would cause infinite-loop turns. We only emit
#     `additionalContext` (advisory) or no-op.
#   - Exit 0 always. A flaky hook should never prevent a clean stop.

set -uo pipefail

cat >/dev/null

gauge="${HOME}/.cache/pratyaksha/budget.json"

# Default: silent no-op.
no_op() {
  printf '{}\n'
  exit 0
}

if [[ ! -r "$gauge" ]]; then no_op; fi
if ! command -v jq >/dev/null 2>&1; then no_op; fi

total=$(jq -r '.total // 0' "$gauge" 2>/dev/null || echo 0)
used=$(jq -r '.used // 0' "$gauge" 2>/dev/null || echo 0)

if [[ "$total" -le 0 ]]; then no_op; fi

pct=$(( (used * 100) / total ))

if [[ "$pct" -lt 75 ]]; then
  no_op
fi

# Hot session — emit an advisory hookSpecificOutput so the next user
# turn sees a small reminder. We do NOT call the MCP server directly
# from a hook; the agent decides whether to act.
cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "Stop",
    "additionalContext": "[pratyaksha] This session has consumed ${pct}% of the local token budget (${used}/${total}). Before the next major step, consider running /compact-now to drop below-threshold context, or /budget to inspect recent spend."
  }
}
JSON
