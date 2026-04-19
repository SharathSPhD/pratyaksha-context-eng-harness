#!/usr/bin/env bash
# SessionStart hook for pratyaksha-context-eng-harness.
#
# Purpose: emit a one-shot context message that tells the agent how to
# bootstrap the Sākṣī (witness invariant) for this session. The hook is
# *advisory only* — it does not call any MCP tool itself, so it cannot
# fail the session if the MCP server is offline or uv is missing.
#
# Output protocol (Claude Code SessionStart hooks):
#   - stdout JSON with `additionalContext` is injected into the system
#     turn before the model's first response.
#   - exit 0 always; we never want to block session start.
#
# Idempotency:
#   - The hook fires every SessionStart, but the message is identical
#     on every run; the agent treats it as a no-op once Sākṣī is set
#     for the session (it can detect this via `get_sakshi`).

set -euo pipefail

# Drain stdin (hooks always receive a JSON payload on stdin; we don't
# need any field from it for this advisory message, but we must consume
# it so the runtime doesn't see a SIGPIPE).
cat >/dev/null

# Look for a CLAUDE.md in the cwd to mention by name. Fall back to a
# generic phrasing.
claude_md_hint=""
if [[ -f "CLAUDE.md" ]]; then
  claude_md_hint=" The repository's CLAUDE.md is the canonical source for hard rules — derive the witness invariant from it."
fi

# Emit additionalContext for the agent. Keep this short (≤150 tokens)
# so it does not consume the user's actual context budget.
cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "[pratyaksha-context-eng-harness] Active. Before your first non-trivial response: (1) call mcp__pratyaksha_mcp__get_sakshi to check whether a Sākṣī (witness invariant) is set; (2) if not, derive a ≤500-token Sākṣī from the user's hard rules and call mcp__pratyaksha_mcp__set_sakshi. The Sākṣī is automatically prepended as a system message on every Manas/Buddhi subagent call.${claude_md_hint} Use mcp__pratyaksha_mcp__context_insert / context_retrieve for typed long-context storage with provenance and precision. Conflict resolution is via mcp__pratyaksha_mcp__sublate_with_evidence (bādha), never by deletion."
  }
}
JSON
