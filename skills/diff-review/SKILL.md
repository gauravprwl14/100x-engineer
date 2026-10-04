---
name: diff-review
description: >
  Review a diff, PR or pull request — your own changes before you push, or a teammate's or
  agent's before you approve: authz gaps, races, speculative abstraction, tests asserting the
  bug. Not for merge policy (→ review-gates).
---

# Diff review

Mechanical checks settle the objectively checkable part. A short list of defect classes has **no
mechanical coverage in any production repository surveyed**, across two independent research passes;
those need a reader asked *only* those questions. Reviewing your own diff and someone else's share
those questions but differ in one thing: your own diff comes with intent already in your head;
someone else's comes with none, and the most common way a review goes wrong is critiquing a guessed
intent. Formerly `scoped-review` (own diff) and `reviewing-others-code` (someone else's).

| mode | when | rules | detail |
|---|---|---|---|
| **own diff** | before opening your PR, or right after implementing from a spec | 1–8 | `references/own-diff.md` |
| **someone else's diff** | a teammate's PR, an external contribution, another agent's output | 1–3, 5, 7 + 9–16 | `references/others-diff.md` |

## Trigger

**Fire when:** a diff is ready for review; before opening a PR; after implementing from a spec;
reviewing a PR, diff or patch someone else authored — a teammate, an external contributor, or an
agent whose output you did not write. Run it **after** the mechanical checks, not instead of them.

**Do not fire when:** the mechanical checks are still failing — fix those first; the question is
merge machinery (PR templates, CODEOWNERS, required checks — `review-gates`); framework mechanics
alone (`stack-reviewer` first, then back here); understanding unfamiliar code with no review
pending (`codebase-comprehension`).

## The questions nothing else answers

| id | question | why no tool catches it |
|---|---|---|
| R1 | Is every new abstraction used by more than one caller? | single-dependent counts are a signal, not a verdict |
| R2 | Does added logic duplicate existing logic under different names? | clone detectors score renamed-variable duplication at 0% |
| R3 | Does every comment explain why, not what? | needs semantic understanding of claim and code |
| R4 | Was each new dependency checked against stdlib and existing deps? | tools make an addition visible, not necessary |
| R5 | Do tests assert the *intended* behaviour, not the implemented one? | a test written from the code locks the bug in |
| R6 | Is authorization checked against the caller, not just the record id? | the missing check is an absence |
| R7 | Is every check-then-act sequence race-safe? | depends on concurrency the diff does not show |
| R8 | Does every new file earn its existence? | a judgement about alternatives not in the diff |
| R9 | Are the spec's `accepted`/`deferred` edge cases still the right call? | compares intent to what implementation revealed |

## Rules

### Both modes (own diff: all of 1–8)

1. Generate the checklist from the diff rather than reviewing from memory; it names the files per question.
   *Enforced by:* `100x review_scope --base origin/main`
2. Answer every in-scope question `yes`, `no` or `n-a` with a reason; unanswered is not a pass.
   *Enforced by:* review — the generated table has an `answer` column per row
3. Run the mechanical checks first, so the review is not spent on what they settle.
   *Enforced by:* `100x bloat_check --base origin/main && 100x decide check`
4. For every `no`, apply the remedy or record why not, as an accepted gap.
   *Enforced by:* `100x decide new` for the accepted-gap case
5. Check the stack-specific reviewer too; the nine generic questions miss framework failure modes.
   *Enforced by:* `ls reviewers/` and read the one matching the diff
6. For R5, derive the expected value from the spec before reading the implementation.
   *Enforced by:* review
7. For R6/R7 on a multi-step flow, draw a level-3 sequence diagram instead of tracing concurrency in
   your head; skip it for a single-function diff.
   *Enforced by:* `100x diagram_from_code <dir> --kind sequence --level 3`
8. Re-check the spec's edge-case table after implementing; implementation reveals missed cases.
   *Enforced by:* `100x plan_feature audit specs/<name>`

### Someone else's diff

9. State the author's intent in one sentence (PR description, ticket, commit) before any critique;
   if inferred, say it is inferred.
   *Enforced by:* review
10. Every finding names a concrete production failure scenario — who hits it, what input, what
    breaks. No scenario means a preference, and a preference does not block.
    *Enforced by:* review
11. Rank findings by blast radius (data loss, auth bypass, outage, silent wrong answer first) and
    lead with the highest.
    *Enforced by:* review
12. Label every finding **blocking**, **should-fix**, **optional** or **question**.
    *Enforced by:* `grep -c '\*\*blocking\*\*\|\*\*should-fix\*\*\|\*\*optional\*\*\|\*\*question\*\*' <notes>` equals the finding count
13. Before marking anything blocking, cite where the target repo establishes the convention.
    *Enforced by:* `100x repo_map <root> --symbol <PatternName>`
14. Assume a constraint you cannot see before assuming incompetence; ask rather than assert.
    *Enforced by:* review
15. Check what no static tool catches: caller authorization, check-then-act races, missing error
    paths, silent behaviour changes, and whether the tests would fail if the code were wrong.
    *Enforced by:* `100x review_scope --base <ref>`
15a. For a new multi-step or multi-component flow, draw a level-2 sequence diagram first; a mismatch
    with the PR description is often the finding.
    *Enforced by:* `100x diagram_from_code <their-dir> --kind sequence --level 2`
16. For AI-generated code, check plausible-but-wrong logic, one-implementation abstractions, and
    tests that assert current rather than intended behaviour.
    *Enforced by:* `100x bloat_check --base <ref>`

## Verify

```bash
# 1. mechanical first (diff-scoped, under 30s total)
100x bloat_check --base origin/main        # <ref> for someone else's branch
100x decide check
100x audit_ci_gates .

# 2. the scoped checklist (names the files per question)
100x review_scope --base origin/main

# 3. stack-specific failure modes
100x stack_audit .
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/<stack>.md

# 4. own diff, after implementing: re-audit the spec
100x plan_feature audit specs/<feature>
100x design_drift specs/<feature>/spec.md <code-dir>

# 5. someone else's diff: precedent and recorded decisions before asserting a convention
100x repo_map . --symbol <PatternOrClassName>
100x decide trace <path>

# 6. multi-step/concurrent flow only (level 3 own diff, level 2 theirs)
100x diagram_from_code <code-dir> --kind sequence --level 3

# 7. the uncovered list has not changed under you
100x run_evals | sed -n '/KNOWN GAPS/,$p'
```

## Failure modes

This skill rejects:

- **"Looks good to me"** on a diff with in-scope questions unanswered.
- **An interface with one implementation** shipped as an extension point nobody asked for.
- **A test whose expected value was copied from the implementation output.**
- **A data-access call with no caller-based authorization check**; **`if exists() then insert()`**
  with no unique constraint behind it; **a new dependency** duplicating the lockfile or stdlib.
- **A review that re-reports what `bloat_check` already found.**
- **Critiquing before stating intent**, or **"I would have done this differently"** with no scenario.
- **Leading with style** when an authorization gap sits three comments down.
- **An unlabelled pile of comments** — every one gets read as blocking.
- **Imposing your style over their established convention** without citing where it is established.
- **Approving AI-generated code because it reads fluently.**

**Honest limitations:** scoping is heuristic — R6 fires on any data-access-shaped line, so answer
`n-a` where it does not apply; a false question is cheaper than a missed one. Nothing verifies the
answers are *true*, or that a stated failure scenario actually holds. Intent inferred from a diff with
no ticket is uncertain — say so. The nine questions are measured gaps, not a complete taxonomy.

## Next

Every question passes: `verification-gate` before commit. An accepted gap or an undocumented decision
the PR changes goes to `decision-records` before merge. A known framework: run `stack-reviewer`
alongside, not after. A blocking fix in code you did not write: `codebase-comprehension` first.

## Scale

`solo` and up. At `solo` the own-diff pass is the only review that happens, and reviewing an agent's
output is where intent inference pays. At `small-team` this is the PR checklist and the
blocking/should-fix/optional split keeps review from becoming resentment. At `org` blast-radius
ranking and convention citation matter most, because reviewers are unfamiliar with local norms.

## Sources

- The uncovered-defect classification, from two independent passes (tool isolation, then production
  configs across ~46 repos): `research/23-findings-antibloat-enforcement.md`,
  `research/36-findings-antibloat-in-practice.md`; renamed-variable duplication at 0% measured in `research/23`.
- Mutation testing absent in 0/50 Python and 0/72 JS repos: `research/31`, `research/30`.
- Plausible-but-wrong, over-abstraction and tests-assert-current-behaviour as AI-diff failure modes:
  `research/23-findings-antibloat-enforcement.md`, `research/36-findings-antibloat-in-practice.md`.
- `scripts/review_scope.py`, the nine questions, blocking/should-fix/optional/question labelling,
  blast-radius ordering and intent-before-critique: `SOURCE: original`.
