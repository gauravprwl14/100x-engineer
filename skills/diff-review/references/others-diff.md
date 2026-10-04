# Reviewing someone else's diff — detail

Reference for `diff-review` (loaded on demand). The numbered rules and the Verify block live in `../SKILL.md`; rule numbers below refer to that file.

Reviewing your own diff and reviewing someone else's are different tasks wearing the
same verb. Your own diff comes with intent already in your head — you know what you
were trying to do, so own-diff mode can go straight to defect classes. Someone
else's diff comes with *no* intent attached, and the single most common way a review
goes wrong is skipping straight to critique on a guessed intent. A review that
misunderstands the goal is noise, however sharp its individual comments are.

This is not a rerun of own-diff mode (the nine defect classes no tool catches) or
`stack-reviewer` (framework-specific failure modes) with different words. Read those
first if the diff has either kind of surface — this skill is about the interpersonal
and judgement layer that sits above both: whose code is this, what were they trying
to do, what's actually at stake if it's wrong, and how do you say so without either
rubber-stamping or triggering a rewrite nobody asked for.

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
- The failure-scenario requirement (rule 10) cannot be mechanically checked; nothing
  stops a reviewer from writing a scenario that does not actually hold. It forces the
  form of justified feedback, not its truth.
- `bloat_check`/`review_scope` are the same tools own-diff mode runs — this skill
  does not duplicate their detection logic, only adds the intent/authorship/ranking
  layer around them.

## Next

Post the labelled findings. If any is blocking and the fix requires you to
understand code you didn't write, `codebase-comprehension` first. If the PR reveals
an undocumented decision it's now changing, that decision needs `decision-records`
before merge, not after.

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
  (R1-R9, `bloat_check.py`, `review_scope.py`): own-diff mode (`references/own-diff.md`), grounded in
  `research/23-findings-antibloat-enforcement.md` and
  `research/36-findings-antibloat-in-practice.md`.
- Framework-specific routing: `skills/stack-reviewer`, `reviewers/*.md`.
- Blocking/should-fix/optional/question labeling and blast-radius-first ordering as
  the mechanism that prevents unlabelled-feedback resentment, and intent-before-
  critique: `SOURCE: original` — the interpersonal-review gap neither own-diff mode
  nor `stack-reviewer` covers, since both assume the reviewer already has intent.
- Plausible-but-wrong, over-abstraction, and tests-assert-current-behavior as the
  distinguishing failure modes of AI-generated diffs specifically:
  `research/23-findings-antibloat-enforcement.md`,
  `research/36-findings-antibloat-in-practice.md` (the same corpus `bloat_check.py`
  is built from).
