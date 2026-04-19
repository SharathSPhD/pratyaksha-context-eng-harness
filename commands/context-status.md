---
description: Show current state of the Pratyakṣa context store — qualificand surface, per-bucket counts, mean precisions, witness invariant token count, and recent ledger spend.
---

# /context-status

Show the current state of the per-session Pratyakṣa context store: the
qualificand surface, per-bucket counts and mean precisions, the witness
invariant token count, and recent sublations.

## Usage

```
/context-status
```

## Instructions

When this command is invoked:

1. Call `list_qualificands()` to enumerate active typed buckets.
2. Call `get_sakshi()` to fetch the current witness invariant.
3. Call `budget_status({last_n: 5})` for a recent-spend snapshot.
4. Format with the template below.

## Output Template

```
## Pratyakṣa context status

**Witness (Sākṣī):** {sakshi_present ? "set" : "unset"} ({sakshi_tokens} tokens)
**Token budget:** {budget_used} / {budget_total} ({remaining} remaining)

### Qualificands ({n_qualificands} active)

| Qualificand | Count | Mean precision |
|---|---|---|
| {q.qualificand} | {q.count} | {q.mean_precision:.2f} |
| ... | ... | ... |

### Recent ledger entries

| ts | tokens | model | note |
|---|---|---|---|
| {r.ts} | {r.tokens} | {r.model} | {r.note} |
| ... | ... | ... | ... |

---

**Health checks:**
- {n_low_precision} qualificands have mean precision < 0.40 → consider /compact-now
- {n_buckets_with_singletons} qualificands have only one element → no conflict surface yet
- {n_high_precision} qualificands at mean precision ≥ 0.85 → high-confidence zone
```

## Why this command

A long Claude Code session accumulates typed claims silently. Without a
status read, the agent (and the user) cannot tell whether the store has
become noisy, whether the witness invariant is still in place, or whether
the local budget is about to be exhausted. `/context-status` answers all
three in one read.

This command reads only — it does not mutate the store, the witness, or
the ledger.
