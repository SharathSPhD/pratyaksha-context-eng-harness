#!/usr/bin/env bash
# PreToolUse hook for pratyaksha-context-eng-harness.
#
# Purpose: before any pratyaksha MCP tool runs, glance at the local
# cost-ledger gauge (~/.cache/pratyaksha/budget.json) and warn the
# agent if the local budget is near exhaustion. This is *advisory by
# default* — Claude Code's own runtime budget is authoritative; this
# hook just gives the agent a chance to self-throttle (e.g., switch
# to a smaller model, batch retrievals, or compact early).
#
# Strict mode:
#   - If the env var PRATYAKSHA_BUDGET_STRICT is set to "1", the hook
#     additionally emits `permissionDecision: "deny"` once the local
#     budget is exhausted. The agent then either has to /budget reset,
#     /compact-now, or pick a different tool.
#   - If PRATYAKSHA_BUDGET_STRICT is unset/0, the hook is purely
#     advisory and always allows.
#
# Output protocol (Claude Code PreToolUse hooks):
#   - JSON on stdout with `permissionDecision` = "allow" | "deny" | "ask"
#     and optional `permissionDecisionReason` (visible to the model).
#   - Exit 0 always. We do NOT want a flaky hook to deny a real tool
#     call accidentally; deny is only emitted when *both* the gauge
#     says exhausted *and* strict mode is on.
#
# Robustness:
#   - If the gauge file is missing or unreadable, the hook silently
#     allows (cold start case).
#   - If `jq` is missing, the hook silently allows (we never want to
#     hard-fail a tool call because of an absent helper).

set -uo pipefail

# Drain stdin so the runtime doesn't SIGPIPE.
cat >/dev/null

gauge="${HOME}/.cache/pratyaksha/budget.json"

emit_decision() {
  local decision="$1"
  local reason="${2:-}"
  if [[ -n "$reason" ]]; then
    cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "${decision}",
    "permissionDecisionReason": "${reason}"
  }
}
JSON
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"%s"}}\n' "${decision}"
  fi
  exit 0
}

emit_allow() { emit_decision "allow" "${1:-}"; }
emit_deny()  { emit_decision "deny"  "${1:-}"; }

# Absent gauge or absent jq → silently allow.
if [[ ! -r "$gauge" ]]; then emit_allow ""; fi
if ! command -v jq >/dev/null 2>&1; then emit_allow ""; fi

# Read the gauge. The MCP server's budget_record / budget_status tools
# write a small JSON document with these fields:
#   { "total": <int>, "used": <int>, "remaining": <int> }
total=$(jq -r '.total // 0' "$gauge" 2>/dev/null || echo 0)
used=$(jq -r '.used // 0' "$gauge" 2>/dev/null || echo 0)
remaining=$(jq -r '.remaining // 0' "$gauge" 2>/dev/null || echo 0)

# Sanity-clamp.
if [[ "$total" -le 0 ]]; then emit_allow ""; fi

pct=$(( (used * 100) / total ))

strict="${PRATYAKSHA_BUDGET_STRICT:-0}"

if [[ "$remaining" -le 0 ]]; then
  msg="[pratyaksha budget] EXHAUSTED: ${used}/${total} tokens used. Consider /compact-now and a smaller model before further MCP calls."
  if [[ "$strict" == "1" ]]; then
    emit_deny "${msg} (strict mode: tool denied; unset PRATYAKSHA_BUDGET_STRICT to override)"
  else
    emit_allow "$msg"
  fi
elif [[ "$pct" -ge 90 ]]; then
  emit_allow "[pratyaksha budget] WARNING: ${pct}% of local budget consumed (${used}/${total}, ${remaining} remaining). Consider /compact-now."
else
  emit_allow ""
fi
