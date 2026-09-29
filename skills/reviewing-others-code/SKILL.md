---
name: reviewing-others-code
description: >
  Use when reviewing a pull request, diff, or change someone else wrote — a teammate,
  an external contributor, or another agent's output you did not produce. Covers what
  is genuinely different about reviewing someone else's work versus your own: infer
  intent before critiquing, rank findings by blast radius, label every finding
  blocking/should-fix/optional/question, and respect the target codebase's own
  conventions over your preferences. Use PROACTIVELY when asked to review a PR, before
  approving a change you did not write, or when reviewing code an AI agent produced.
---

# Reviewing others' code

Reviewing your own diff and reviewing someone else's are different tasks wearing the
same verb. Your own diff comes with intent already in your head — you know what you
were trying to do, so `scoped-review` can go straight to defect classes. Someone
else's diff comes with *no* intent attached, and the single most common way a review
goes wrong is skipping straight to critique on a guessed intent. A review that
misunderstands the goal is noise, however sharp its individual comments are.

This is not a rerun of `scoped-review` (the nine defect classes no tool catches) or
`stack-reviewer` (framework-specific failure modes) with different words. Read those
first if the diff has either kind of surface — this skill is about the interpersonal
and judgement layer that sits above both: whose code is this, what were they trying
to do, what's actually at stake if it's wrong, and how do you say so without either
rubber-stamping or triggering a rewrite nobody asked for.

## Trigger

**Fire when:** reviewing a PR, diff, or patch someone else authored — a teammate, an
external contributor, or an agent whose output you did not write yourself.

**Do not fire when:** reviewing your own diff before opening a PR — that is
`scoped-review`, which skips intent-inference because you already have the intent.
Don't fire for framework-specific mechanics alone — route those through
`stack-reviewer` first, then come back here for the judgement layer. Understanding
unfamiliar code with no review pending is `codebase-comprehension`.

## Rules

1. State the author's intent in one sentence, from the PR description, linked
   ticket, or commit message, before writing a single critique. If none exists, infer
   it from the diff and say explicitly that it is inferred, not confirmed.
   *Enforced by:* review

2. For each finding, name the concrete failure scenario in production — who hits it,
   under what input or load, and what breaks — not "I would have written this
   differently." A finding with no failure scenario is a preference, not a review
   comment, and does not block. (Same discipline `scoped-review` uses for its own
   findings: a claim needs the specific failure class, not "this feels risky.")
   *Enforced by:* review

3. Rank findings by blast radius (data loss, auth bypass, outage, silent wrong
   answer > everything else), and lead with the highest one. A review that opens with
   a naming nit and buries an authz gap in comment #9 has mis-prioritized regardless
   of how correct comment #9 is.
   *Enforced by:* review

4. Label every finding **blocking**, **should-fix**, **optional**, or **question**.
   An unlabelled finding is read as blocking by default, and a pile of unlabelled
   nits reads as obstruction — this is the single most common cause of review
   friction that has nothing to do with the code.
   *Enforced by:* `grep -c "blocking\|should-fix\|optional\|question" <review-notes>`
   should equal the number of findings raised — an unlabelled finding fails this count

5. Before marking anything blocking, check the target repo's own conventions —
   existing similar code, its linter config, its style guide, its `AGENTS.md` — and
   cite where the convention is established. Your preference is not their convention.
   *Enforced by:* `python3 scripts/repo_map.py <root> --symbol <PatternName>` (find an
   existing precedent before asserting one should exist)

6. Assume a constraint you cannot see before assuming incompetence — a deadline, a
   platform limitation, an earlier decision. Ask ("is there a reason X over Y?")
   rather than assert ("this should be Y") when the alternative is plausible and you
   have not confirmed the constraint is absent.
   *Enforced by:* review

7. Check what no static tool catches: authorization against the caller (not just the
   record id), races in check-then-act sequences, missing error paths, silent
   behavior changes (a return type, a default, an error being swallowed), and whether
   the tests would actually fail if the code were wrong.
   *Enforced by:* `python3 scripts/review_scope.py --base <ref>` generates R6/R7-style
   questions scoped to the diff — run it even on someone else's diff; the questions
   are the same, only the intent-inference step around them differs

8. For AI-generated code specifically, check for plausible-but-wrong output (the code
   reads as correct and compiles but the logic is subtly off), over-abstraction
   (interfaces and factories with one implementation), and tests that assert the
   implementation's current behavior rather than the intended one.
   *Enforced by:* `python3 scripts/bloat_check.py --base <ref>`

## Verify

```bash
# 1. the shared mechanical + defect-class layer (same tools scoped-review uses)
python3 scripts/bloat_check.py --base <ref>
python3 scripts/review_scope.py --base <ref>

# 2. framework-specific failure modes, if the diff touches a known stack
python3 scripts/stack_audit.py .
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/<stack>.md

# 3. precedent check before asserting a convention -- find it, don't guess it
python3 scripts/repo_map.py . --symbol <PatternOrClassName>
git log --follow --oneline <file changed in the diff>

# 4. is there a decision on record explaining why it's shaped this way
python3 scripts/decide.py trace <path>

# 5. self-check before posting: every finding labelled, highest blast-radius first
grep -c '\*\*blocking\*\*\|\*\*should-fix\*\*\|\*\*optional\*\*\|\*\*question\*\*' <notes>
```

Expected runtime: under 30s total (`bloat_check` and `review_scope` are diff-scoped,
not whole-repo).

## Failure modes

This skill rejects:

- **Critiquing before stating intent.** "This should use a factory here" on a diff
  whose actual goal was a one-off script is a review of the wrong thing.
- **"I would have done this differently"** with no failure scenario attached. That is
  a preference wearing a review comment's clothes, and it does not block.
- **Leading with style** when the diff has an authorization gap three comments down.
  Blast radius sets order, not file order or line order.
- **An unlabelled pile of comments.** Every one of them gets read as blocking, which
  is how a two-line fix accumulates a week of back-and-forth over nits nobody flagged
  as optional.
- **Requesting a change with no scenario that breaks without it** — "this could be
  cleaner" is not a scenario.
- **Imposing your style over an established convention in their codebase** without
  citing where that convention is established (a similar file, a lint rule, their
  `AGENTS.md`).
- **Approving AI-generated code because it reads fluently**, without checking whether
  the logic is actually right, whether new abstractions have more than one caller, or
  whether the tests would catch a regression.
- **Asserting a missing constraint ("there's no reason not to do X") instead of
  asking**, when a plausible reason exists that the diff does not show.

**Honest limitations:**
- Intent inference from a diff with no ticket or description is genuinely uncertain —
  say so, do not present a guess as confirmed intent.
- The failure-scenario requirement (rule 2) cannot be mechanically checked; nothing
  stops a reviewer from writing a scenario that does not actually hold. It forces the
  form of justified feedback, not its truth.
- `bloat_check`/`review_scope` are the same tools `scoped-review` runs — this skill
  does not duplicate their detection logic, only adds the intent/authorship/ranking
  layer around them.

## Scale

`solo`: mostly applies to reviewing an agent's output before accepting it — intent
inference matters even when the "author" is a model, because a plausible-looking diff
from a fast agent is exactly where this skill's checks pay for themselves.
`small-team (2-10)`: this is the PR review process. The blocking/should-fix/optional
split is what keeps review from becoming a source of resentment as volume grows.
`org (10+)`: blast-radius ranking and convention-citation matter most here, where a
reviewer is routinely unfamiliar with the target codebase's local norms.

## Sources
- Failure-scenario discipline for findings, and the shared defect-class layer
  (R1-R9, `bloat_check.py`, `review_scope.py`): `skills/scoped-review`, grounded in
  `research/23-findings-antibloat-enforcement.md` and
  `research/36-findings-antibloat-in-practice.md`.
- Framework-specific routing: `skills/stack-reviewer`, `reviewers/*.md`.
- Blocking/should-fix/optional/question labeling and blast-radius-first ordering as
  the mechanism that prevents unlabelled-feedback resentment, and intent-before-
  critique: `SOURCE: original` — the interpersonal-review gap neither `scoped-review`
  nor `stack-reviewer` covers, since both assume the reviewer already has intent.
- Plausible-but-wrong, over-abstraction, and tests-assert-current-behavior as the
  distinguishing failure modes of AI-generated diffs specifically:
  `research/23-findings-antibloat-enforcement.md`,
  `research/36-findings-antibloat-in-practice.md` (the same corpus `bloat_check.py`
  is built from).
