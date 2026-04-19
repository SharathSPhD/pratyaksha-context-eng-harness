---
name: witness-prefix
description: Use at session start to capture the session-stable invariant (Sākṣī) — user identity, project hard rules, the active hypothesis or contract under test — and ensure it is pushed as a real Claude `system` message at every model call. Use whenever the user changes the project, switches contexts, or states a new hard constraint that must persist across all subsequent reasoning.
---

# Witness prefix (Sākṣī)

The Sākṣī is the *witness consciousness* — the unmoving observer against
which all variable cognition is measured. In this plugin it has a precise
operational meaning: a frozen, ≤500-token system message that is pushed as
the Claude `system` field at every model call within the session.

## When to use

- **Session start.** The `session-start.sh` hook fires this skill if the
  workspace `CLAUDE.md` declares hard project rules. Capture them once.
- **User declares a new hard constraint.** "Never edit the production
  database directly" or "All tests must use pytest, never unittest" —
  these are invariants, not turn-by-turn instructions.
- **A new hypothesis becomes the active one.** When the agent enters an
  experiment branch, the hypothesis statement should become the witness so
  that every subsequent step is measured against it.
- **The user switches projects** or asks the agent to context-switch — the
  old witness is wiped and a new one is set.

## How to use

```text
# Capture
set_sakshi({
  content: "User: Sharath. Project: pratyaksha-context-eng-harness.\n
            Hard rules:\n
            - Never modify the v0 baseline files in docs/v0_retrospective_*\n
            - All tests must run under `uv run --active pytest`\n
            - The shipped plugin must not import attractor-flow or ralph-loop\n
            Active hypothesis: H1 (Avacchedaka improves precision-recall)"
})
→ {ok: true, tokens: 87, system_message: "<sakshi_prefix>...</sakshi_prefix>"}

# Inspect at any time
get_sakshi()
```

## Why this matters

In the v0 implementation (see `docs/v0_retrospective.md`, Gap G9), the
Sākṣī content was inlined into the user-message context fed to the Buddhi
verifier. That collapses two distinct epistemic modalities — variable
cognition (claims being reasoned about) and witness invariance (the frame
they are reasoned against) — into the same channel, which means the model
can be talked out of its invariants by adversarial later turns.

The fix is structural: the Sākṣī goes through the Anthropic `system` field,
which Claude treats as separate from the user/assistant turn stream and
which prompt-caching can pin permanently. The `witness-prefix` skill
exists to make sure callers actually do this, instead of falling back to
the easier-but-broken "just paste it into the user message" pattern.

## Hard rules

- **Stable.** A Sākṣī that changes every turn is not an invariant. If the
  candidate content changes more than once per ~10 turns, it does not
  belong here — push it through `context_insert` with appropriate
  precision instead.
- **Short.** Hard limit: 500 tokens. A long Sākṣī defeats prompt caching
  and bloats every call. If the invariant cannot be expressed in 500
  tokens, factor it: keep the invariant claim in Sākṣī and store the
  supporting elaboration in the typed context store.
- **Witness, not narrative.** Imperatives, identities, hard rules,
  hypotheses-under-test. Never include conversational state, transient
  goals, or observations.

## Anti-patterns

| Anti-pattern                                                       | Why it's wrong                                              |
|--------------------------------------------------------------------|-------------------------------------------------------------|
| Setting Sākṣī to the user's last message                           | That's variable cognition, not invariance                   |
| Setting Sākṣī to a 5000-token style guide                          | Bloats every call; defeats caching; should live in context store |
| Inlining the witness into a Buddhi/Manas user message              | Reproduces G9; recursive prompt-stitching corrupts the frame |
| Updating Sākṣī mid-turn during reasoning                           | Invariants don't slide                                      |

## Diagnostic commands

- `/context-status` — also reports current Sākṣī token count
