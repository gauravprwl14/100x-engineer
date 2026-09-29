---
name: legacy-change
description: >
  Use when changing code that has no tests, or where the tests that exist don't
  cover the part you're about to touch — most real work, not the exception.
  Covers characterization tests (capture what the code DOES, bugs included, as
  the safety net), finding a seam to change behaviour without editing the thing
  under test, sprout/wrap to avoid touching a large unsafe function directly,
  branch by abstraction and the strangler fig for larger replacements, the
  single highest-value rule (never refactor and change behaviour in one
  commit), the approval-testing trap, and a stop rule for cleanup scope. Use
  PROACTIVELY before editing any function or module with no test covering it.
---

# Legacy change

Most real engineering work is not "add a feature to a clean codebase" — it is
"change something inside code nobody currently has a safety net for." `bug-fix`
assumes a reproducible failure and a test-writing loop already works there.
`test-design` assumes tests exist to extend. Neither says what to do first when
neither is true, which is most of the job. This skill is that first step.

## Trigger

**Fire when:** about to edit a function, class, or module with no test covering
the specific behaviour you're about to touch — regardless of whether the repo
has tests elsewhere. Changing a well-tested area is `feature-planning` or
`bug-fix`; this skill is specifically for the untested seam.

**Do not fire when:** the code you're touching is already covered by a test
that exercises the exact behaviour changing — write the change and let that
test fail red first (`bug-fix` rule 2 covers that loop). Also do not fire for
code you are about to delete outright — see the last rule.

## Rules

1. **Write a characterization test before anything else.** It captures what the
   code currently DOES — including its bugs — not what it should do. This is
   the safety net: a change that keeps this test green did not alter observable
   behaviour, whatever else it did internally. Michael Feathers names this
   technique explicitly in *Working Effectively with Legacy Code* (2004):
   pin current behaviour first, decide separately whether that behaviour is
   correct.
   *Enforced by:* `python3 scripts/test_design_check.py --only assert-count,test-name`
   run on the new characterization test itself — it must be a real, well-named,
   assertive test, not a placeholder

2. **Find the seam before editing the thing under test.** A seam is a place you
   can change behaviour without editing the code that needs it — Feathers names
   five kinds: **object seam** (dependency injection — pass the collaborator
   in), **parameter seam** (add a parameter so a test can supply a fake),
   **subclass-and-override** (override the one method that reaches outside),
   **link-time seam** (swap the linked implementation, common in Go/C), and
   **environment seam** (an env var or config flag that changes runtime wiring
   without changing source). If no seam exists, making one *is* the first
   change — and that change itself must not alter behaviour (rule 4).
   *Enforced by:* review

3. **Sprout, don't edit in place, when adding new behaviour to an unsafe
   function.** Write the new behaviour as a new, independently-testable
   method or class ("sprout method" / "sprout class"), and call it from one
   inserted line in the untested function, rather than threading new logic
   through 900 existing untested lines. **Wrap**, don't edit, when adding
   behaviour *around* a call you can't safely touch — wrap it in a new method
   that calls the old one and adds the new behaviour before or after. Both are
   Feathers' terms for the same idea: put the new, testable code outside the
   untested code, not inside it.
   *Enforced by:* review

4. **Never refactor and change behaviour in the same commit.** This is the
   single highest-value rule here. A refactor that also changes behaviour
   cannot be reviewed as "safe, mechanical, behaviour-preserved" — the reviewer
   has to re-derive which parts were the refactor and which were the change,
   and usually can't. Split it: refactor first (characterization test stays
   green throughout), commit, *then* change behaviour (a different test now
   goes red, then green).
   *Enforced by:* `python3 scripts/test_design_check.py --only refactor-behavior`
   (advisory — flags a diff over `--max-files` (default 15) where a *modified*
   test file's expected value changed alongside production logic; see Verify)

5. **Use approval/snapshot testing for output too complex to hand-assert on**
   (a large JSON payload, rendered HTML, a generated file) — but read every
   snapshot before accepting it. `home-assistant/core` runs 1,961 `.ambr`
   snapshot files via `syrupy`, the largest snapshot suite found across 50
   production Python repos surveyed for this project
   (`research/31-findings-python-verification.md`). The trap: a snapshot
   regenerated and committed without being read is **worse than no test** — it
   looks like coverage, asserts nothing about correctness, and will silently
   re-approve the next regression too.
   *Enforced by:* `python3 scripts/test_design_check.py --only snapshot-same-diff`
   (advisory — flags a snapshot file changed in the same diff as the production
   code it approves, the shape most likely to mean "regenerated, not reviewed")

6. **For a replacement too large for one PR, use branch by abstraction or the
   strangler fig — and price in the real cost.** Branch by abstraction: put an
   interface in front of the old implementation, build the new one behind the
   same interface, flip a flag, delete the old path
   (`martinfowler.com/bliki/BranchByAbstraction.html`). Strangler fig: route an
   increasing share of traffic to the new implementation at a boundary (a
   proxy, a router) until the old one gets no traffic and can be deleted
   (`martinfowler.com/bliki/StranglerFigApplication.html`). Both cost the same
   thing, stated honestly: **two live code paths that must be kept
   behaviourally reconciled for the duration of the migration** — every bug fix
   during that window needs applying to both, or the two paths silently
   diverge and the cutover ships a regression.
   *Enforced by:* review

7. **Stop cleanup at the seam you actually needed.** The campsite rule ("leave
   it cleaner than you found it") has a real boundary: clean up what you
   touched to make the change safely, not everything nearby that also looks
   bad. Unbounded cleanup is exactly how a one-line fix becomes a 40-file diff
   — `minimal-diff` owns diff-size discipline generally; this rule is the
   legacy-specific version of it, because "I'm already in here, might as well"
   is strongest exactly where the code is worst.
   *Enforced by:* `python3 scripts/bloat_check.py --only file-creation-ratio`
   (advisory) — a real hard number on scope creep beyond a stated intent

8. **Do not touch code that is stable, understood, and scheduled for deletion.**
   A characterization test on code being deleted next sprint is wasted safety
   net; a seam introduced for a "cleaner" untested path nobody will read again
   is speculative work with no payoff. The single most valuable thing this
   skill can tell you is sometimes: leave it alone.
   *Enforced by:* review

## Verify

```bash
# characterization test exists, is real, and is well-named (~1s)
python3 scripts/test_design_check.py --only assert-count,test-name

# refactor/behaviour-change conflation + unreviewed snapshot approval (~1-2s)
python3 scripts/test_design_check.py --only refactor-behavior,snapshot-same-diff
python3 scripts/test_design_check.py --strict --max-files 15   # org-scale: treat both as blocking

# scope creep beyond the seam you needed (~1-3s, diff-scoped)
python3 scripts/bloat_check.py --only file-creation-ratio,commented-code

# the characterization test must fail if you revert your change and only your
# change -- proves it actually pins behaviour, not just "runs"
git stash && <single-test-runner> <new-characterization-test> ; echo "expect non-zero: $?" ; git stash pop
```

## Failure modes

This skill rejects:

- **A "refactor" PR that also changes an API response shape** — reviewed and
  merged as "just moving code around" because nobody could tell from the diff
  that behaviour moved too. `refactor-behavior` catches the mechanical
  signature: large diff, a modified test's expected value changed alongside
  production logic.
- **A snapshot file regenerated and committed in the same PR as the code that
  produces it**, with no comment on what changed and why the new output is
  correct — `snapshot-same-diff` flags exactly this pairing.
- **"I added a test" that asserts the code doesn't throw**, with no assertion
  on the actual output — not a characterization test, just a smoke test with a
  test-shaped name; `test_design_check.py --only assert-count,test-name` and
  `bloat_check.py --only assertionless` both apply to it.
- **A 900-line function edited in five places to add one new behaviour**,
  instead of sprouting a new, separately-testable method called from one
  inserted line — no mechanical check catches this shape, which is why rule 3
  is `review`, honestly.
- **A branch-by-abstraction flag flipped and the old path deleted the same
  day**, with no window where both paths ran and were reconciled — defeats the
  entire point of the technique, which is a *reversible*, *observed* cutover.
- **Cleanup that outgrew the change** — a one-line bug fix that also
  reformatted, renamed, and reorganized the file it lived in;
  `file-creation-ratio` gives this a number instead of a feeling.

## Scale

`solo`: rules 1, 4, 8 — the three that cost the least and prevent the worst
outcome (a change that silently broke something with no way to notice).
`small-team (2-10)`: add 3, 5, 7 — sprout/wrap and stop-rule discipline start
mattering once a reviewer other than the author has to understand the diff.
`org (10+)` / `high-blast-radius`: add 2, 6 — seam-finding as a first-class
skill and branch-by-abstraction/strangler-fig for anything that can't ship as
one PR, because the blast radius of getting rule 4 wrong scales with how many
callers depend on the code being changed.

## Sources

- Characterization tests, the five seam types (object, parameter,
  subclass-and-override, link-time, environment), and sprout/wrap as named
  techniques: Michael Feathers, *Working Effectively with Legacy Code*
  (Prentice Hall, 2004) — the origin of this vocabulary, cited by name per
  this project's research brief (`research/00-signal-rubric.md` Part G).
- Branch by abstraction: `martinfowler.com/bliki/BranchByAbstraction.html`.
- Strangler fig application: `martinfowler.com/bliki/StranglerFigApplication.html`.
- Largest snapshot-testing adopter found in the 50-repo Python survey (1,961
  `.ambr` files, `syrupy`), used here as the approval-testing example:
  `home-assistant/core@3b2a141`, `research/31-findings-python-verification.md`.
- Mutation testing 0/72 JS/TS and 0/50 Python — cited here as the reason a
  green characterization test is evidence of "behaviour pinned," never proof
  the pin would catch a mutation: `research/30-findings-js-verification.md`,
  `research/31-findings-python-verification.md`.
- `scripts/test_design_check.py`'s `refactor-behavior` and `snapshot-same-diff`
  checks: `SOURCE: original` — built for this skill because the corpus survey
  found no tool that detects refactor/behaviour-change conflation in a diff.
- Diff-size and scope-creep discipline this skill defers to rather than
  reimplementing: `skills/minimal-diff/SKILL.md`.
