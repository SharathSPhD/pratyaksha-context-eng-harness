# Pratyakṣa Context Engineering Harness — Quickstart

A 30-minute hands-on tour of the plugin in real Claude Code, with **five
challenging use cases** that each exercise a different mechanism. Each
case includes:

- A motivating problem (why a vanilla Claude Code session would fail)
- A copy-pasteable user prompt
- Exactly what the harness does, tool by tool
- How to verify it worked (audit log, `/context-status`, files on disk)
- "What would have happened *without* the plugin" sidebar

> **Audience:** anyone who has Claude Code (CLI, VS Code, Cursor, or
> desktop) and wants to see whether typed retrieval, sublation, witness
> invariants, and boundary compaction actually change behaviour on real
> work. No Python knowledge required.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Install (5 min)](#2-install-5-min)
3. [Verify it works (2 min)](#3-verify-it-works-2-min)
4. [Set up a workspace `CLAUDE.md` (3 min)](#4-set-up-a-workspace-claudemd-3-min)
5. [Where the audit lives](#5-where-the-audit-lives)
6. **Use cases**
   - [Case 1 — Version-conflicted documentation (Avacchedaka + Sublation)](#case-1--version-conflicted-documentation-avacchedaka--sublation)
   - [Case 2 — Hard project rule that must survive 50 turns (Sākṣī)](#case-2--hard-project-rule-that-must-survive-50-turns-sākṣī)
   - [Case 3 — Long debugging session that crosses a phase boundary (boundary compaction)](#case-3--long-debugging-session-that-crosses-a-phase-boundary-boundary-compaction)
   - [Case 4 — Cheap-then-careful answer with hallucination guardrails (Manas → Buddhi → Khyātivāda)](#case-4--cheap-then-careful-answer-with-hallucination-guardrails-manas--buddhi--khyātivāda)
   - [Case 5 — Three contradicting PR review comments (detect_conflict at scale)](#case-5--three-contradicting-pr-review-comments-detect_conflict-at-scale)
7. [Troubleshooting](#7-troubleshooting)
8. [What to read next](#8-what-to-read-next)

---

## 1. Prerequisites

| Need                                        | Why                                                         |
|---------------------------------------------|-------------------------------------------------------------|
| Claude Code (CLI, VS Code, Cursor, desktop) | The plugin loader lives here.                               |
| `uv` ≥ 0.4 ([install][uv-install])          | The MCP server is a PEP 723 self-installing script.         |
| ~30 minutes                                 | All five cases are runnable end-to-end.                     |

> Cursor / VS Code users without the Claude Code plugin loader can still
> use the **15 MCP tools** directly — see the [MCP-only path][mcp-only].
> Skills, agents, commands, and hooks need Claude Code today.

[uv-install]: https://docs.astral.sh/uv/getting-started/installation/
[mcp-only]: README.md#cursor--vs-code-mcp-only

---

## 2. Install (5 min)

```bash
# One-time prerequisite (skip if you already have uv):
curl -LsSf https://astral.sh/uv/install.sh | sh

# Inside any Claude Code session (the slash commands work in CLI,
# VS Code, Cursor, and desktop):
/plugin marketplace add SharathSPhD/pratyaksha-context-eng-harness
/plugin install pratyaksha-context-eng-harness@pratyaksha-context-eng-harness
```

The first MCP tool call takes ~30 s while `uv` downloads `mcp`,
`pydantic`, and `tiktoken` (a one-time cost). After that, every call
is instant.

**Air-gapped or development install?** See [README §B][readme-b].

[readme-b]: README.md#b-local-clone-for-development-or-air-gapped-machines

---

## 3. Verify it works (2 min)

In a fresh Claude Code session, type:

```
/context-status
```

Expected output:

```
## Pratyakṣa context status

**Witness (Sākṣī):** unset (0 tokens)
**Token budget:** 0 / 200000 (200000 remaining)

### Qualificands (0 active)

(none)

### Recent ledger entries
(empty)

---

**Health checks:**
- 0 qualificands have mean precision < 0.40 → consider /compact-now
- 0 qualificands have only one element → no conflict surface yet
- 0 qualificands at mean precision ≥ 0.85 → high-confidence zone
```

If you see this template rendered with zero entries, the MCP server is
running, the slash command is wired, and you're ready to go.

If you see `MCP server failed to start` or a Python traceback, jump to
[Troubleshooting §7](#7-troubleshooting).

---

## 4. Set up a workspace `CLAUDE.md` (3 min)

The `session-start.sh` hook reads any project-level `CLAUDE.md` and
turns its hard rules into the session's witness invariant (Sākṣī) at
session start. To make all five use cases concrete, drop this file at
the root of any test project:

```markdown
# CLAUDE.md

## Project rules (hard invariants)

- **Python 3.12 only.** Never suggest `pip install`; this monorepo uses
  `uv add` exclusively.
- **No production DB writes** without explicit user approval.
- **Cite primary sources.** When summarising library behaviour, link to
  the official docs of the *exact* version used in this repo.

## Active hypothesis

H_quickstart: the Pratyakṣa harness reduces silent context drift on
multi-turn coding sessions.
```

That's it. The hook fires once when you open the session and the
`sakshi-keeper` agent will set the Sākṣī from this file automatically.

---

## 5. Where the audit lives

Open a second terminal and tail these files while you work — they are
the source of truth for "did the harness actually do what it said":

```bash
# Every mutating MCP call (insertions, sublations, witness changes, …)
tail -f ~/.cache/pratyaksha/audit.jsonl

# Every recorded token spend
tail -f ~/.cache/pratyaksha/cost_ledger.jsonl
```

The audit log records `tool`, `args` summary, and result for every
mutation. The cost ledger records tokens spent per agent call. Together
they let you reconstruct any session deterministically.

---

# Use cases

Each case takes 5–10 minutes. Run them in order, or pick one — they
are independent.

---

## Case 1 — Version-conflicted documentation (Avacchedaka + Sublation)

**The problem.** You ask Claude Code about Redis defaults. Early in the
session a search snippet from 2024 says "Redis binds to 127.0.0.1:6379
by default." Forty turns later, the agent reads the official 7.2 docs
which say "Redis 7.2 changes the default bind to 0.0.0.0 if the
`protected-mode no` directive is set." A vanilla session silently picks
one — usually the first-seen, regardless of which is correct. The
harness types both claims and resolves the conflict by **sublation**:
the loser is preserved in the audit but invisible to retrieval.

### Run it

```text
You:
  I'm debugging a Redis bind-address issue. Use the harness to record
  what you find as you investigate. First, grep my project for the
  Redis version we use; then fetch the bind-address default for that
  exact version from the official docs. Insert each finding via
  context_insert with a precision score, qualificand
  "redis_bind_default", and a condition that includes the Redis major
  version. If you find conflicting claims, resolve them with sublation
  using sublate_with_evidence — do not silently pick a winner.

  Walk me through your steps.
```

### What the harness does (you'll see this in the agent trace)

1. `Grep "redis" --> requirements.txt | uv.lock` → finds `redis==6.2.13`.
2. `WebFetch https://redis.io/docs/...` for the 6.x bind default.
3. `context_insert({id: "redis_bind_v6", qualificand: "redis_bind_default",
   qualifier: "bind_address", condition: "version=6", precision: 0.92,
   provenance: "redis.io/docs/6.2/...", content: "Redis 6.x default
   bind is 127.0.0.1:6379"})`
4. The agent reads a stale chat snippet that asserts the same claim
   for "all Redis versions". It calls
   `context_insert({id: "old_snippet", qualificand: "redis_bind_default",
   condition: "version=any", precision: 0.40, ...})`.
5. `detect_conflict({qualificand: "redis_bind_default"})` returns a pair.
6. `sublate_with_evidence({older_id: "old_snippet", newer_content: ...,
   newer_precision: 0.92, qualificand: "redis_bind_default", ...})` —
   the snippet is sublated; only the version-typed claim survives
   retrieval.

### Verify

```
/context-status
```

You should see exactly **one** qualificand `redis_bind_default` with a
single retrievable element at precision ≈ 0.92. The sublated snippet
is **not** counted in the active surface but is in the audit log:

```bash
jq -c 'select(.tool == "sublate_with_evidence")' \
  ~/.cache/pratyaksha/audit.jsonl
```

You'll see one line per sublation with `older_id`, `newer_id`, and
preserved provenance.

### Without the plugin

The agent would have stored both bind-address strings as plain text
in its rolling context. On a follow-up turn 30 messages later, when
asked "what's the default bind?", the model would have confidently
recited whichever string happened to be retrieved by lexical
similarity — typically the older snippet, because it appeared earlier
and dominates self-attention. There would be no audit trail of which
claim was dropped or why.

---

## Case 2 — Hard project rule that must survive 50 turns (Sākṣī)

**The problem.** You declare a hard invariant at session start: "this
repo uses `uv`; never suggest `pip install`." Twenty turns later the
agent reads a Stack Overflow answer that says `pip install foo`. Forty
turns later the agent itself drops "you can pip install this" into a
suggestion. The model's effective system prompt has been adversarially
eroded by intervening user/assistant turns. The harness pushes the
invariant through Claude's `system` field via the **Sākṣī** so it
survives every model call verbatim.

### Run it

Make sure `CLAUDE.md` from §4 is in the workspace root.

```text
You (turn 1):
  Confirm the witness for this session — call get_sakshi and read it
  back to me verbatim.

You (turn 2..N — interleave any other coding work):
  ...

You (turn 50, after 49 turns of unrelated work):
  Find me the simplest one-line install command for the `httpx` library
  in this repo.
```

### What the harness does

1. `session-start.sh` fires once at session start. The `sakshi-keeper`
   agent reads `CLAUDE.md` and calls `set_sakshi({content: "Project: ...
   Hard rules: - Python 3.12 only. Never suggest pip install ..."})`.
2. Every subsequent model call — Manas drafts, Buddhi verifications,
   the main thread itself — receives that text as the Anthropic
   `system` message, NOT as a user message. Prompt-caching pins it.
3. On turn 50, when you ask for an install command, the model can see
   the witness alongside the question and answers `uv add httpx`, not
   `pip install httpx`.

### Verify

```
/context-status
```

The `Witness (Sākṣī)` line should show a non-zero token count and
"set". You can also dump the exact system message:

```text
You: call get_sakshi and paste the system_message field verbatim
```

### Without the plugin

The witness would have been pasted into the user-message context at
turn 1 ("Project rules: ..."). By turn 30, that text is lost from the
attention budget — the model literally cannot see it any more. The
turn-50 answer would be `pip install httpx`, contradicting the project
contract. This is the classic G9 failure mode documented in the v0
retrospective.

---

## Case 3 — Long debugging session that crosses a phase boundary (boundary compaction)

**The problem.** You spend 30 turns deep-debugging a Django ORM N+1
query. You then switch to a totally unrelated task: "now let's review
the React component for the same model." Vanilla Claude Code carries
the entire ORM debugging context into the React phase — every
`select_related` claim, every `prefetch_related` failure mode — even
though none of it is relevant. The model's working window stays full
of stale precision-0.85 claims that aren't load-bearing for the new
task. The harness detects the **discourse boundary** by surprise
spike and scopes a compaction so old-phase low-precision claims drop
out, but the high-precision ones (the actual fix you found) remain.

### Run it

```text
You (turns 1..30):
  Debug a slow Django view at apps/users/views.py:UserListView. Use
  the harness as you go — type each finding via context_insert with
  qualificand "django_n_plus_1" and a precision based on how solid
  the evidence is.

You (turn 31, the boundary):
  OK that's settled. Switch topic — review apps/users/components/UserList.tsx
  for accessibility issues. Run /compact-now first so we don't carry
  stale ORM context into the new phase.
```

### What the harness does

1. During turns 1–30, the agent (or Buddhi) inserts ~12 typed claims
   under `qualificand: "django_n_plus_1"` with mixed precisions
   (0.4–0.95).
2. On turn 31 you invoke `/compact-now`. The slash command:
   - Calls `boundary_compact({text_window: <last 16 turns>,
     threshold_z: 2.0})`.
   - The surprise-spike detector sees the topic shift and confirms
     a real boundary at the right token index.
   - With the boundary confirmed, low-precision elements (precision <
     mean) under `django_n_plus_1` are compressed (precision → 0.0).
   - High-precision claims (the actual fix, precision ≥ 0.85) are
     kept retrievable.
3. The React phase then runs without those stale ORM claims polluting
   the agent's attention.

### Verify

```
/context-status
```

You should see `django_n_plus_1` element count drop, **mean precision
go up**, and the dropped elements appear in the audit log:

```bash
jq -c 'select(.tool == "boundary_compact")' \
  ~/.cache/pratyaksha/audit.jsonl
```

### Without the plugin

The next 20 turns about React would still drag the ORM context along.
Even with Claude's context-window auto-compaction, you have no control
over *what* gets dropped — it's a mechanical truncation, not a
precision- or scope-aware one. You frequently lose the *high*-precision
fix and keep the *low*-precision noise, because the noise is more
recent.

---

## Case 4 — Cheap-then-careful answer with hallucination guardrails (Manas → Buddhi → Khyātivāda)

**The problem.** "What's the right Django ORM call to eagerly load a
many-to-many relationship?" There is exactly one correct answer
(`prefetch_related`). The wrong answer (`select_related`) is in the
training data nearly as often, and the typo answers (`prefetch_relate`,
`prefetch_M2M`) appear too. A direct one-shot model call gets it right
~95% of the time. We want 100% on a code-generating turn. The harness
runs **Manas** (cheap Haiku draft) → **Buddhi** (Sonnet verifier with
fresh source read) → **Khyātivāda** classifier to *reject*
misidentified-method hallucinations before they ship.

### Run it

```text
You:
  In our Django repo, what is the correct ORM call to eagerly load a
  many-to-many relationship between User and Group? I want this to go
  through manas first; if manas is uncertain or the claim has any
  user-visible consequence (this will end up in code I commit),
  escalate to buddhi for verification with a fresh primary-source
  read. Reject any answer that classify_khyativada flags as
  anyathakhyati.
```

### What the harness does

1. `manas` runs:
   - `get_sakshi()` → reads the project rules.
   - `context_retrieve({qualificand: "django_m2m_eager_load"})` →
     empty (we've never recorded this).
   - Drafts: "Use `prefetch_related` for M2M; `select_related` is for
     ForeignKey/OneToOne."
   - `classify_khyativada({claim: ..., evidence: ...})` → `samyakhyati`
     (correct cognition) on the prefetch part.
   - But the draft has user-visible consequence (code-generating)
     → returns `needs_buddhi: true`.
2. `buddhi` runs:
   - `WebFetch https://docs.djangoproject.com/en/5.1/ref/models/querysets/#prefetch-related`
     → ratifies prefetch_related.
   - `context_insert({id: "django_m2m_v5_1", qualificand:
     "django_m2m_eager_load", qualifier: "method", condition:
     "django>=4.0", precision: 0.96, provenance: "<docs URL>",
     content: "Use QuerySet.prefetch_related(field) for M2M; for FK
     and OneToOne use select_related."})`.
   - `classify_khyativada` on a counter-claim "use select_related for
     M2M" → returns `anyathakhyati` (misidentification). Buddhi
     **rejects** that branch and emits the verified answer with the
     element id as a citation.

### Verify

After the turn, `/context-status` should show one new qualificand
`django_m2m_eager_load` with one element at precision 0.96. The audit
log will contain the `context_insert` and the rejection events:

```bash
jq -c 'select(.tool == "classify_khyativada")' \
  ~/.cache/pratyaksha/audit.jsonl | tail -5
```

### Without the plugin

You'd have a single Sonnet (or Opus) call answering directly. ~95%
correct in expectation, but with no audit trail, no precision
calibration, no citation, and no separation between the cheap-and-fast
intuition and the slow-and-careful verification.

---

## Case 5 — Three contradicting PR review comments (detect_conflict at scale)

**The problem.** You're the human resolver on a PR with three reviewers,
each leaving a different verdict on the same line:

- Reviewer A: "Use `Optional[Foo]`."
- Reviewer B: "Use `Foo | None` — it's the modern syntax."
- Reviewer C: "Don't allow None at all; refactor the caller."

A naive Claude Code session reads all three reviews into context and
answers the *next* question — "what should I do?" — by basically
flipping a coin weighted by which review came last. The harness types
each comment as a separate claim with provenance, runs
`detect_conflict` to surface the pair-wise disagreements, and lets you
*explicitly* sublate the losers with full audit.

### Run it

```text
You:
  I have three PR review comments to reconcile on apps/users/models.py
  line 42, where I currently have `def get(id: int) -> Foo`. Insert
  each into the context store as a typed claim under qualificand
  "user_get_signature", precision based on reviewer seniority
  (Reviewer A 0.7, Reviewer B 0.65, Reviewer C 0.85 — they're the
  module owner). Then run detect_conflict and walk me through
  sublation. Don't pick a winner without surfacing the conflict.

  - Reviewer A: "Use Optional[Foo] for backward compat."
  - Reviewer B: "Use Foo | None, modern Python."
  - Reviewer C: "Don't allow None — refactor the caller to never pass
    a missing id. The current API design is broken."
```

### What the harness does

1. Three `context_insert` calls under
   `qualificand: "user_get_signature"`, with provenances `pr#123/A`,
   `pr#123/B`, `pr#123/C` and precisions 0.70 / 0.65 / 0.85.
2. `detect_conflict({qualificand: "user_get_signature"})` returns
   three pairs (A-B, A-C, B-C) — every pair disagrees.
3. The agent applies the `sublate-on-conflict` decision procedure:
   - **Provenance:** all three are PR comments (same source class).
   - **Precision:** Reviewer C is +0.15 above the next, the configured
     "default winner" gap.
   - **Action:** sublate A by C's claim, sublate B by C's claim. Two
     `sublate_with_evidence` calls, both auditable.
4. `context_retrieve({qualificand: "user_get_signature"})` now returns
   exactly one element: Reviewer C's claim. The agent recommends
   refactoring the caller, with citations to the pr#123/A and pr#123/B
   sublations so the user knows what was overruled and why.

### Verify

```bash
# Two sublations should appear:
jq -c 'select(.tool == "sublate_with_evidence" and
              (.args.qualificand == "user_get_signature"))' \
  ~/.cache/pratyaksha/audit.jsonl
```

```
/context-status
```

`user_get_signature` should show count 1, mean precision 0.85.

### Without the plugin

The model would have answered "use `Foo | None`" or "use
`Optional[Foo]`" with high confidence and *no acknowledgement that
two other reviewers disagreed*, because all three comments were
indistinguishable text in the context. The user would have to manually
re-read the PR to discover they'd just been talked out of the most
senior reviewer's recommendation.

---

## 7. Troubleshooting

### "MCP server failed to start"

Confirm `uv` is on `PATH`:

```bash
uv --version
```

If missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

Then test the server boots in isolation:

```bash
cd ~/.claude/plugins/marketplaces/pratyaksha-context-eng-harness/pratyaksha-context-eng-harness
uv run --no-project mcp/server.py
```

You should see `MCP server started` within ~5 s. Ctrl-C to exit.

### "/context-status returns nothing"

The slash command works but the MCP server isn't connected. Restart
Claude Code. If the problem persists, list installed plugins:

```
/plugin list
```

`pratyaksha-context-eng-harness` should appear with status `enabled`.
If not: `/plugin install pratyaksha-context-eng-harness@pratyaksha-context-eng-harness`.

### "context_insert rejected with 'duplicate id'"

The store rejects re-insertion of an existing id without
`overwrite=true`. The correct response is **never** `overwrite=true` —
it's `sublate_with_evidence` with the new content. The harness is
deliberately stricter than a key-value store on this point because
silent overwrites destroy the audit trail.

### "set_sakshi rejected with 'over 500 tokens'"

The witness is a hard ≤500-token cap. Factor the invariant into a
short stable core (which goes in Sākṣī) and a longer elaboration
(which goes in `context_insert` with appropriate precision). See the
`witness-prefix` skill for the rationale.

### Auditing the audit log

```bash
# Tool call counts, by tool name
jq -r '.tool' ~/.cache/pratyaksha/audit.jsonl | sort | uniq -c | sort -rn

# All sublations in the last hour
jq -c 'select(.tool == "sublate_with_evidence" and
              (.ts | fromdateiso8601) > (now - 3600))' \
  ~/.cache/pratyaksha/audit.jsonl
```

---

## 8. What to read next

| Topic                                       | Where                                       |
|---------------------------------------------|---------------------------------------------|
| Tool reference (all 15 MCP tools)           | [`README.md`][readme] · [`mcp/server.py`][server] |
| Skills (decision procedures the agent follows) | [`skills/`][skills]                      |
| Agents (Manas / Buddhi / Sākṣī Keeper)      | [`agents/`][agents]                         |
| Slash commands                              | [`commands/`][commands]                     |
| Lifecycle hooks (SessionStart / PreToolUse / Stop) | [`hooks/`][hooks]                    |
| Validation against RULER, HELMET, SWE-bench, … | The [v2.0.0 release][release] PDF (92 pp) |
| Vedic epistemology background               | [`paper/sections/04_theory.md`][theory] in the parent research repo |

[readme]: README.md
[server]: mcp/server.py
[skills]: skills/
[agents]: agents/
[commands]: commands/
[hooks]: hooks/
[release]: https://github.com/SharathSPhD/pratyaksha-context-eng-harness/releases/tag/v2.0.0
[theory]: https://github.com/SharathSPhD/context-engineering-harness/blob/main/paper/sections/04_theory.md

---

**Got stuck or found a sharp edge?** File an issue on the [plugin
repo][issues]. Include the contents of `~/.cache/pratyaksha/audit.jsonl`
since the start of the failing session — it's the single most useful
debugging artifact.

[issues]: https://github.com/SharathSPhD/pratyaksha-context-eng-harness/issues
