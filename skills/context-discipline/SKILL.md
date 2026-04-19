---
name: context-discipline
description: Discipline for long-context Claude Code sessions. Use when the working session crosses ~30k tokens, when the agent is about to consume retrieval results, when a tool produces multi-file output that may contain stale claims, or when the user asks for "what do we know about X right now" — anywhere implicit context drift would silently corrupt subsequent reasoning.
---

# Context discipline (Avacchedaka + Sublation + Witness)

This skill teaches the agent the three operations that keep long-context
sessions epistemically clean: **typed insertion**, **sublation on conflict**,
and **boundary-triggered compaction**. It is automatically activated in any
session where the Pratyakṣa Context Engineering Harness is installed.

## When to use

Activate this skill the moment any of these signals appear:

- the conversation has accumulated more than ~30k tokens
- the agent is about to call `context_retrieve` or `context_window` and feed
  the result to a planning step
- a fresh tool output contradicts something the agent stated earlier
- the user says "what's the current state of X?", "summarise our progress",
  or asks the agent to pick up a paused thread
- the agent is about to compact / truncate the session and would otherwise
  drop important typed claims indiscriminately

If none of these apply, do nothing — the harness is opt-in by design.

## Three operations (in order)

### 1. Insert with type, not just text

Every claim that the agent might later retrieve goes through `context_insert`
with an Avacchedaka triple `(qualificand, qualifier, condition)`:

| Field         | Meaning                                              | Example                              |
|---------------|------------------------------------------------------|--------------------------------------|
| `qualificand` | What is being qualified — the subject of the claim   | `"redis_default_port"`               |
| `qualifier`   | The qualifier or property being asserted             | `"port_number"`                      |
| `condition`   | AND-conjunctive limitor tokens scoping the claim     | `"version=7.2 AND env=prod"`         |
| `precision`   | Calibrated confidence in `[0, 1]`                    | `0.95` (from official docs)          |
| `provenance`  | Source URL, file:line, or tool call id               | `"https://redis.io/docs/..."`        |

Without the triple, two claims with the same surface text but different
contexts collapse into one — exactly the silent corruption we want to
prevent. Two `redis_default_port` claims with different `version=` conditions
are first-class distinct.

### 2. Sublate when newer evidence contradicts older claims

When the agent finds a higher-precision claim that contradicts an older one,
**do not delete** the older claim. Call `sublate_with_evidence` instead:

```
sublate_with_evidence({
  older_id: "claim_42",
  newer_content: "Redis 7.2 changed the default to 0.0.0.0:6379",
  newer_precision: 0.97,
  qualificand: "redis_default_port",
  qualifier: "port_number",
  condition: "version=7.2 AND env=prod",
  provenance: "https://redis.io/docs/latest/operate/oss_and_stack/management/config/"
})
```

Sublation preserves the older claim with `precision=0.0` and
`sublated_by=newer_id` — auditable, but invisible to future
`context_retrieve` calls. This is the Bādha (sublation) operation from
classical Vedānta: the rope is not erased when it's seen-as-rope-not-snake;
the snake-perception is sublated by the rope-perception.

### 3. Compact at event boundaries, not on token-count alone

When the agent detects a discourse boundary — task switch, phase transition,
user interrupt with a fresh topic — call `boundary_compact` on the recent
text window. The harness's surprise-spike detector identifies the boundary
and triggers a scoped `compact` so only low-precision claims in the closing
phase are dropped. **Never** call generic "summarize and truncate" on a long
session that has typed claims in the store; you will silently lose
auditability.

## Witness invariants (Sākṣī)

Any invariant that must remain true across every model call this session —
the user's identity, the project's hard rules, the active hypothesis under
test — should be set once via `set_sakshi`. The `witness-prefix` skill
guarantees it is pushed as a real Claude `system` field at every model
call (NOT inlined into user content, which is what naive prompt-stitching
implementations do — see G9 in the project's `docs/v0_retrospective.md`).

## Anti-patterns the harness catches

| Anti-pattern                                                    | Harness response                                            |
|-----------------------------------------------------------------|-------------------------------------------------------------|
| Inserting two contradictory claims with the same id             | `context_insert` rejects unless `overwrite=true`            |
| Dropping older context to "fit the window"                      | `compact` requires a scope; `boundary_compact` requires a real boundary |
| Treating sakshi as user content                                 | `set_sakshi` returns a `system_message` block to push verbatim |
| Calling `context_retrieve` without a `qualificand`              | The schema requires it — no implicit cross-topic drift      |

## Diagnostic commands

- `/context-status` — show per-qualificand element counts and mean precision
- `/sublate <older_id>` — open the sublation dialog for a specific element
- `/compact-now` — force boundary compaction on the recent window
- `/budget` — show tokens used so far in this session
