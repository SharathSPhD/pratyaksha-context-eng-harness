---
name: sublate-on-conflict
description: Use when the agent encounters two retrieved claims that contradict each other, when fresh tool output disagrees with a previously-stored claim, when the user corrects an earlier statement, or when `detect_conflict` flags a pair. Resolves the conflict via sublation (precision-weighted overwrite with audit trail) instead of silent deletion or arbitrary tie-breaking.
---

# Sublate on conflict

When two claims about the same `(qualificand, condition)` bucket disagree,
the agent must not silently pick one. The classical Vedāntic resolution is
**bādha** (sublation): the contradicted claim is preserved in the store but
its precision drops to 0.0 and a `sublated_by` pointer is set, so future
retrievals never see it but auditors always can.

## When to use

- `detect_conflict` returns one or more `conflict_pairs`.
- A tool result (file read, API call, search hit) contradicts a claim the
  agent previously inserted via `context_insert`.
- The user corrects an earlier agent statement.
- The agent is about to overwrite an existing element id — `context_insert`
  refuses unless `overwrite=true`; the correct response is to sublate.

## Decision procedure

For each conflict pair `(a, b)`:

1. **Compare provenances.** A claim from official primary documentation,
   user-asserted ground truth, or the project's own source code beats a
   claim from a search snippet, an old chat turn, or a generic Q&A blog.
2. **Compare precisions.** If one element already has a markedly higher
   precision (`>= 0.15` gap), it wins by default.
3. **Compare timestamps within the same source class.** If both are equal
   provenance and within the same precision band, the more recent one wins.
4. **If still tied, ask the user.** Do NOT pick arbitrarily — context that
   contains an unresolved conflict is worse than context that contains
   neither claim.

Once the winner is identified, call `sublate_with_evidence` (preferred,
single atomic call) or the lower-level `context_sublate` (when the newer
claim is already in the store):

```
sublate_with_evidence({
  older_id: <loser>,
  newer_content: <winner content>,
  newer_precision: <strictly greater than older.precision>,
  qualificand: <same as the loser>,
  qualifier: <same as the loser>,
  condition: <same as the loser>,
  provenance: <winner source>
})
```

## Hard rules

- **Never delete the loser.** `context_sublate` is destructive of *retrieval*,
  not of *audit*. The element stays with `precision=0.0` and `sublated_by` set.
- **Never sublate downward.** `newer_precision <= older.precision` is
  rejected by the API — if the agent has a less-confident newer claim, the
  correct response is to leave both claims and surface the conflict, not to
  promote the weaker one.
- **Sublation is asymmetric.** `sublate(a, by=b)` is not the same as
  `sublate(b, by=a)`. The pointer always goes loser → winner.
- **Verify after sublation.** Re-run the original `context_retrieve` and
  confirm the loser no longer appears.

## Worked example

```text
# Step 1 — initial state shows a conflict
detect_conflict({qualificand: "redis_default_port"})
→ {conflict_pairs: [{a_id: "claim_42", b_id: "claim_67",
                     a_precision: 0.85, b_precision: 0.93,
                     jaccard: 0.31}]}

# Step 2 — inspect both
context_get({element_id: "claim_42"})
→ "Redis 6.x default is bound to 127.0.0.1:6379"  (provenance: "search snippet, 2024")
context_get({element_id: "claim_67"})
→ "Redis 7.2 default is bound to 0.0.0.0:6379"    (provenance: "redis.io/docs, 2025")

# Step 3 — sublate the older, lower-precision claim
sublate_with_evidence({
  older_id: "claim_42",
  newer_content: "Redis 7.2 default bind is 0.0.0.0:6379",
  newer_precision: 0.97,
  qualificand: "redis_default_port",
  qualifier: "bind_address",
  condition: "version=7.2",
  provenance: "https://redis.io/docs/..."
})

# Step 4 — verify
context_retrieve({qualificand: "redis_default_port", condition: "version=7.2"})
→ exactly one element, the new winner
```

## What NOT to do

| Action                                              | Why it's wrong                                     |
|-----------------------------------------------------|----------------------------------------------------|
| Picking the higher-precision claim silently         | Loses provenance — auditor can't see the conflict  |
| `context_insert(overwrite=true)` over the loser     | Loses the audit trail entirely                     |
| Calling `compact` to drop the loser by precision    | Compact is for stale low-precision noise, not for resolving live conflicts |
| Telling the user "both could be true"               | Avoids the resolution; the agent should make a defensible call |
