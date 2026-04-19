---
description: Force a boundary-triggered compaction on the recent conversation window with optional scope (qualificand, task_context) and z-score threshold.
argument-hint: "[threshold=<float>] [qualificand=<name>] [task_context=\"<AND-tokens>\"]"
---

# /compact-now

Force a boundary-triggered compaction on the recent conversation window.
Use when the agent did not auto-detect a discourse boundary but the user
knows a phase has ended and wants to scope-compress now.

## Usage

```
/compact-now                                    # default scope, threshold_z=2.0
/compact-now threshold=2.5                      # raise the boundary detector strictness
/compact-now qualificand=<name>                 # restrict compaction to one qualificand
/compact-now task_context="lang=en AND task=qa" # AND-conjunctive scope
```

## Instructions

When this command is invoked:

1. Parse `threshold=<float>`, `qualificand=<str>`, and `task_context=<str>`
   from the args (all optional; sensible defaults).
2. Estimate the recent text window (last ~16 conversation turns) and
   pass it as `text_window` to `boundary_compact`.
3. If the boundary detector finds a spike, the same call also compacts
   matching elements scoped by `qualificand` / `task_context`. Otherwise
   no mutation occurs.
4. Print a summary block; if no boundary was detected, explain why and
   point the user at `/context-status` to inspect what's eligible.

## Output Template

```
## Boundary compaction

**Boundary:** {boundary_detected ? "✓ detected" : "✗ not detected"}
{boundary_detected ?
  "**Max z-score:** {max_z:.3f} (threshold {threshold_z})\n
   **Spike at token index:** {spike_token_index}" :
  "**Max z-score:** {max_z:.3f} below threshold {threshold_z}; nothing compacted."}

### Compaction
- Eligible scope: qualificand={qualificand or "all"}, task_context={task_context or "any"}
- Elements compressed (precision → 0.0): {n_compressed}

#### Compressed ids
{compressed_ids: bulleted list}

---
**Reminder:** Compaction is *retrieval-invisible*, not destructive. The
elements remain in the store with `precision=0.0` for audit; they will
not be returned by `context_retrieve` unless the threshold is lowered.
```

## When NOT to use

- **During an active reasoning chain.** Compaction at the wrong moment
  can drop context the next step needs. Wait for a real phase boundary.
- **As a substitute for `/sublate`.** If two claims conflict, the right
  tool is `/sublate` — compaction does not resolve conflicts, it only
  drops below-threshold noise.
- **To free tokens for a long retrieval.** If you need a bigger window,
  raise `max_tokens` on the next `context_window` call instead. The
  store is unbounded; the budget is the runtime.

## See also

- `/context-status` to see what would be eligible before compacting.
- The `context-discipline` skill for the design rationale.
