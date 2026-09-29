---
name: scoped-review
description: >
  Use when reviewing a diff, before opening a PR, or after implementing a feature —
  to audit the defect classes no tool detects: speculative abstractions, semantically
  duplicated logic, comments that restate code, unnecessary dependencies, tests that
  assert the bug, missing authorization checks, and check-then-act races. Use
  PROACTIVELY after the mechanical checks pass, because passing them is not the same
  as being correct.
---

# Scoped review

Mechanical checks settle the objectively checkable part. A short list of defect classes
has **no mechanical coverage in any production repository surveyed** across two
independent research passes. Those need a reader — but a reader asked *only* those
questions, not asked to re-derive what the tools already decided.

Running `scripts/run_evals.py` prints the current list, so the scope of this skill is
measured rather than asserted.

## Trigger

**Fire when:** a diff is ready for review; before opening a PR; after implementing from
a spec. Run it **after** the mechanical checks, not instead of them.

**Do not fire when:** the mechanical checks are still failing — fix those first, or this
review is spent re-finding what a tool already reported.

## The questions nothing else answers

| id | question | why no tool catches it |
|---|---|---|
| R1 | Is every new abstraction used by more than one caller? | single-dependent counts are a signal, not a verdict; only a human knows if a seam is deliberate |
| R2 | Does added logic duplicate existing logic under different names? | copy-paste detectors score renamed-variable duplication at 0% — verified directly |
| R3 | Does every comment explain why, not what? | needs semantic understanding of both the comment's claim and the code |
| R4 | Was each new dependency checked against stdlib and existing deps? | tools make an addition visible and blockable; they cannot judge necessity |
| R5 | Do tests assert the *intended* behaviour, not the implemented behaviour? | a test written from the code passes and locks the bug in |
| R6 | Is authorization checked against the caller, not just the record id? | the code looks complete; the missing check is an absence |
| R7 | Is every check-then-act sequence race-safe? | correctness depends on concurrency the diff does not show |
| R8 | Does every new file earn its existence? | file necessity is a judgement about alternatives not in the diff |
| R9 | Are the spec's `accepted`/`deferred` edge cases still the right call? | requires comparing intent to what implementation revealed |

## Rules

1. Generate the checklist from the diff rather than reviewing from memory. It names
   which files each question applies to.
   *Enforced by:* `python3 scripts/review_scope.py --base origin/main`

2. Answer every in-scope question explicitly `yes`, `no`, or `n-a` with a reason. An
   unanswered question is not a pass.
   *Enforced by:* review — the generated table has an `answer` column per row

3. Run the mechanical checks first, so this review is not spent on what they settle.
   *Enforced by:* `python3 scripts/bloat_check.py --base origin/main && python3 scripts/decide.py check`

4. For every `no`, apply the stated remedy or record why you are not, as an accepted gap.
   *Enforced by:* `python3 scripts/decide.py new` for the accepted-gap case

5. Check the stack-specific reviewer too — each carries the failure modes particular to
   that framework, which these nine generic questions do not cover.
   *Enforced by:* `ls reviewers/` and read the one matching the diff

6. For R5 specifically, derive the expected value from the spec before reading the
   implementation. Reading the code first is how a test ends up asserting the bug.
   *Enforced by:* review

7. Re-check the spec's edge-case table after implementing. Implementation reveals cases
   planning missed.
   *Enforced by:* `python3 scripts/plan_feature.py audit specs/<name>`

## Verify

```bash
# 1. mechanical first — do not spend a human pass on these
python3 scripts/bloat_check.py --base origin/main
python3 scripts/decide.py check
python3 scripts/audit_ci_gates.py .

# 2. generate the scoped checklist (names the files per question)
python3 scripts/review_scope.py --base origin/main

# 3. the stack-specific failure modes
ls reviewers/
grep -A20 "Common AI failure modes" reviewers/<stack>.md

# 4. after implementing, re-audit the spec
python3 scripts/plan_feature.py audit specs/<feature>
python3 scripts/design_drift.py specs/<feature>/spec.md <code-dir>

# 5. confirm the uncovered list has not changed under you
python3 scripts/run_evals.py | sed -n '/KNOWN GAPS/,$p'
```

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
- The mechanical-narrows-then-scoped-review architecture: the conclusion both research
  passes reached independently.
- `scripts/review_scope.py` and the nine questions: `SOURCE: original`.
