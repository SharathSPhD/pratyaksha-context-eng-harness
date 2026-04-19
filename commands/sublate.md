---
description: Manually sublate (bādha) one element by another, or sublate with new evidence. Refuses if newer precision does not strictly exceed older.
argument-hint: "<older_id> [by <newer_id> | with-evidence \"<content>\" precision=<0..1> qualificand=<...> qualifier=<...> condition=<...>]"
---

# /sublate

Manually sublate (bādha) one element by another. Use when the agent has
not auto-detected a conflict but the user knows a stored claim is now
superseded.

## Usage

```
/sublate <older_id> [by <newer_id>]
/sublate <older_id> with-evidence "<newer content>" precision=<0..1> qualificand=<...> qualifier=<...> condition=<...>
```

If `by <newer_id>` is omitted and `with-evidence` is provided, the command
inserts the newer element and atomically sublates the older one in a
single audited operation.

## Instructions

When this command is invoked:

1. Parse the older element id and either `by <newer_id>` or the
   `with-evidence` payload.
2. Call `context_get({element_id: <older_id>})` to confirm it exists and
   show the user what is about to be sublated.
3. Two paths:
   - **Path A (`by <newer_id>`):** Call `context_get` on `newer_id` to
     verify it exists, then call `context_sublate({element_id: <older_id>,
     by_element_id: <newer_id>})`.
   - **Path B (`with-evidence ...`):** Validate that the newer
     `precision` strictly exceeds the older's, then call
     `sublate_with_evidence({...})`.
4. Re-run `context_retrieve` on the older element's `(qualificand,
   condition)` and confirm the older element no longer appears.
5. Print a summary block.

## Output Template

```
## Sublation complete

**Older:** {older.id}  precision {older_precision:.2f} → 0.00
  > "{older.content}"
**Newer:** {newer.id}  precision {newer.precision:.2f}
  > "{newer.content}"
**Audit:** older element preserved with `sublated_by={newer.id}`.

### Verification
- `context_retrieve(qualificand={q}, condition={c})` returned {n} elements,
  {older.id} is {present ? "STILL PRESENT (sublation failed)" : "absent ✓"}.
```

## Hard rules

- The command refuses if `newer_precision <= older.precision` — that's a
  protected invariant on `sublate_with_evidence`.
- The command refuses if either id does not exist.
- The command does NOT delete anything. Sublation is *retrieval-invisible*,
  not destructive.

## See also

- The `sublate-on-conflict` skill for the auto-detection flow.
- `/context-status` to inspect what's eligible for sublation.
