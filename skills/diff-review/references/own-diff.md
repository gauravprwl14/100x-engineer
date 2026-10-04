# Reviewing your own diff — detail

Reference for `diff-review` (loaded on demand). The numbered rules and the Verify block live in `../SKILL.md`; rule numbers below refer to that file.

Mechanical checks settle the objectively checkable part. A short list of defect classes
has **no mechanical coverage in any production repository surveyed** across two
independent research passes. Those need a reader — but a reader asked *only* those
questions, not asked to re-derive what the tools already decided.

Running `scripts/run_evals.py` prints the current list, so the scope of this skill is
measured rather than asserted.

The R1–R9 question table is in `../SKILL.md`.

## Failure modes

This skill rejects:

- **"Looks good to me"** on a diff with in-scope questions unanswered.
- **An interface with one implementation** shipped as an extension point nobody asked for.
- **A test whose expected value was copied from the implementation output** — it will
  pass forever and prove nothing.
- **A data-access call with no caller-based authorization check**, which reads as
  complete code because the defect is an absence.
- **`if exists() then insert()`** with no unique constraint behind it.
- **A new dependency** that duplicates something already in the lockfile or the stdlib.
- **A review that re-reports what `bloat_check` already found**, which wastes the one
  resource this process is trying to conserve.

**Honest limitations:**
- The scoping is heuristic. R6 fires on any data-access-shaped line, so it will ask
  about authorization on code where it does not apply — answer `n-a` and move on. A
  false question is much cheaper than a missed one, so the bias is deliberate.
- Nothing verifies that the answers are *true*. This produces a finite, attributed
  checklist; it does not produce diligence.
- The nine questions come from defect classes measured as uncovered in this research.
  They are not a complete taxonomy of what tools miss.

## Next

If every question passes: `verification-gate` before commit. If any `no` needed an
accepted gap recorded (rule 4), that record lives under `decision-records` (record mode) from
here on. If the diff touches a known framework: run `stack-reviewer` alongside this,
not after — the nine questions here are generic and miss what's framework-specific.

## Scale

`solo` and up. At `solo` this is the only review that happens, which makes it the
highest-value item in the plugin after the verification gate. At `small-team` it
becomes the PR checklist. At `org` it is what stops review degenerating into
style commentary, because the expensive questions are pre-named.

## Sources
- The uncovered-defect classification, from two independent passes (tool isolation, then
  production configs across ~46 repos): `research/23-findings-antibloat-enforcement.md`,
  `research/36-findings-antibloat-in-practice.md`.
- Semantic duplication with renamed variables scoring 0% on clone detectors: measured
  directly in `research/23`.
- Mutation testing absent in 0/50 Python and 0/72 JS repos, so "can this test fail" has
  no industry answer: `research/31`, `research/30`.
- The mechanical-narrows-then-human-review architecture: the conclusion both research
  passes reached independently.
- `scripts/review_scope.py` and the nine questions: `SOURCE: original`.
