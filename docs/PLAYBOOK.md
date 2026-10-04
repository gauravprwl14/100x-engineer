# Playbook

What to run for each kind of task. Every row of every sequence either produces an
artifact you can read or a gate that blocks.

Conventions: `→` means the next step depends on the previous passing. **bold** steps
are gates that exit non-zero.

---

## Contents

| # | task | what it gives you | size |
|---|---|---|---|
| 1 | [1. Build a feature](#1-build-a-feature) | the full sequence from PRD to commit, with every gate named | 37 lines |
| 2 | [2. Feature into a codebase whose PRD, spec and code have diverged](#2-feature-into-a-codebase-whose-prd-spec-and-code-have-diverged) | **the common real case** — establish ground truth first, then record which of the three you treated as authoritative | 28 lines |
| 3 | [3. Fix a bug](#3-fix-a-bug) | repro-first; the permanent test is the deliverable, the fix is incidental | 22 lines |
| 4 | [4. Review your own code](#4-review-your-own-code) | mechanical checks, then the 9 questions no tool answers | 12 lines |
| 5 | [5. Review someone else's code](#5-review-someone-elses-code) | how this differs — infer intent, rank by blast radius, label every finding | 17 lines |
| 6 | [6. Understand someone else's logic, or a past feature](#6-understand-someone-elses-logic-or-a-past-feature) | the order of operations, and the stop condition so you don't read everything | 16 lines |
| 7 | [7. Root cause analysis](#7-root-cause-analysis) | timeline, hypotheses with falsifying evidence, and the regression test that would have caught it | 16 lines |
| 8 | [8. Write a PRD or architecture proposal](#8-write-a-prd-or-architecture-proposal) | options analysis with the scoring rubric, including the do-nothing option | 16 lines |
| 9 | [9. Audit: is the reasoning recorded?](#9-audit-is-the-reasoning-recorded) | the traceability matrix — which features have which records | 10 lines |
| 10 | [Diagram detail levels](#diagram-detail-levels) | which of the three levels to use, and their node budgets | 11 lines |
| 11 | [What still needs a human](#what-still-needs-a-human) | the six defect classes no tool detects anywhere | 7 lines |

## 1. Build a feature

Greenfield or a new feature in an existing codebase.

```bash
# frame it (skip for a small change — a PRD for a two-day feature is overhead)
100x prd new checkout --kind payment
100x prd audit prds/checkout                    # GATE

# plan it: seeds the edge cases and decisions this feature type always has
100x plan_feature new checkout --kind payment,crud --stack nestjs
100x prd align prds/checkout specs/checkout      # PRD <-> spec divergence
100x plan_feature audit specs/checkout           # GATE: blocks coding

# record the choices that departed from the recommended default
100x decide new "Idempotency key strategy" --affects "src/checkout/**"
100x decide lint                                 # GATE

# read the stack's failure modes BEFORE writing
100x stack_audit .
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/nestjs.md

# --- implement ---

100x bloat_check --base origin/main              # GATE
100x design_drift specs/checkout/spec.md src/checkout   # GATE
100x decide verify && 100x decide drift  # GATE
100x review_scope --base origin/main             # answer every question
100x verified --name test -- <your test command>
git commit                                                      # GATE: receipt required
100x ledger check                                # GATE: linkage
```

**Artifacts:** `prds/checkout/prd.md`, `specs/checkout/spec.md` (edge cases resolved),
one or more ADRs, a verification receipt.

---

## 2. Feature into a codebase whose PRD, spec and code have diverged

The common real case. Establish ground truth before changing anything.

```bash
# what is actually here?
100x repo_map . --top 20
100x stack_audit .

# what does the code actually do, at the level you need?
100x diagram_from_code src/checkout --kind sequence --level 1   # orient
100x diagram_from_code src/checkout --kind sequence --level 2   # work

# where do the three disagree?
100x prd align prds/checkout specs/checkout       # PRD vs spec
100x design_drift specs/checkout/spec.md src/checkout  # spec vs code

# record the divergence as a decision rather than silently picking a winner
100x decide new "Reconcile spec and code on partial refunds" \
  --affects "src/checkout/**"
```

Three-way divergence has three honest resolutions, and the decision record must say
which you chose: **code is right** (update the spec), **spec is right** (fix the code),
or **both are stale** (re-plan). Picking one silently is how the next person inherits
the same confusion.

---

## 3. Fix a bug

```bash
# reproduce FIRST — an unreproduced bug is a guess
# then commit the reproduction as a FAILING test and watch it fail
100x verified --name repro -- <the single failing test>   # expect non-zero

# is this bug a violated assumption? (a very common root cause)
100x decide trace src/<file>
100x decide verify

# --- fix the narrowest thing that makes the test pass ---

100x bloat_check --base origin/main       # no drive-by changes
100x verified --name test -- <the full suite>
git commit                                              # GATE
```

The permanent test is the deliverable; the fix is incidental. If the cause was a
violated assumption, supersede that decision — do not edit it.

---

## 4. Review your own code

```bash
100x bloat_check --base origin/main       # mechanical first
100x audit_ci_gates .                     # do your gates actually gate?
100x decide check
100x review_scope --base origin/main      # the 9 questions no tool answers
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/<stack>.md
100x design_drift specs/<f>/spec.md <dir>
```

---

## 5. Review someone else's code

Different job: infer intent before critiquing, rank by blast radius, never lead with
style.

```bash
100x repo_map . --symbol <TheThingTheyChanged>
100x decide trace <changed-file>          # what governs this already?
100x diagram_from_code <their-dir> --kind sequence --level 2
100x review_scope --base <their-base>
100x audit_agent_config .                 # if the PR is from outside
```

Label every finding **blocking / should-fix / optional / question**. Unlabelled
feedback reads as blocking.

---

## 6. Understand someone else's logic, or a past feature

```bash
100x repo_map .                           # entry points, hot files
100x ledger find "<feature name>"         # was it written down?
100x decide trace <file>                  # why is it like this
100x diagram_from_code <dir> --kind sequence --level 1     # orient
100x diagram_from_code <dir> --kind sequence --level 2     # detail
100x diagram_from_code <dir> --kind flow --level 3 --entry "Svc.method"
git log -S"<symbol>" --oneline | head             # why the code is shaped this way
```

**Stop condition:** you understand it when you can state the inputs, outputs, failure
modes and the one thing most likely to break — not when you have read everything.

---

## 7. Root cause analysis

```bash
100x rca new "Sessions dropped after deploy" --affects "src/auth/**" --severity high
100x decide drift                         # did an assumption silently lapse?
100x decide verify
git log --oneline --since="3 days ago" | head
100x diagram_from_code src/auth --kind sequence --level 3   # the real path
100x rca lint                             # GATE
100x rca link RCA-0001 --decision ADR-0001
```

`rca.py lint` rejects a root cause identical to the symptom, and rejects the record
entirely if it names no regression test.

---

## 8. Write a PRD or architecture proposal

```bash
100x prd new <name> --kind <kinds>
# options analysis uses the approach-selection rubric:
#   reversibility x3, blast radius x3, moving parts x2, already-in-use x2,
#   exit cost x1, fit x1 — and always include "do nothing / smallest change"
100x prd audit prds/<name>                # GATE
100x check_diagrams prds/<name>/prd.md    # GATE
100x decide new "<the architectural choice>" --affects "<glob>"
```

For an existing system with no PRD, reverse-engineer one: `repo_map.py` +
`diagram_from_code.py --level 1` give you the current state to write down.

---

## 9. Audit: is the reasoning recorded?

```bash
100x ledger check      # index + traceability matrix + linkage gaps
cat ledger/MAP.md                    # feature x record-type grid
100x ledger stats      # growth; when to shard
100x ledger shard      # past 40 records per directory
```

---

## Diagram detail levels

| level | nodes | audience | when |
|---|--:|---|---|
| 1 high | ≤ 12 | someone new, or a decision-maker | orientation, PRDs, "where does this sit" |
| 2 medium | ≤ 30 | implementers | the working diagram; specs |
| 3 detailed | — | debugging, review | every branch and error path, numbered steps + a step table |

`--level` on `diagram_from_code.py`; `check_diagrams.py` enforces the budgets.

---

## What still needs a human

Six defect classes have no mechanical detection anywhere — semantic duplication,
redundant comments, unnecessary dependencies, tests that assert the bug, missing
authorization, check-then-act races. `review_scope.py` turns them into nine attributed
questions. Run `100x run_evals` for the current list; it is measured, not
asserted.
