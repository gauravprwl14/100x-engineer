# Playbook

What to run for each kind of task. Every row of every sequence either produces an
artifact you can read or a gate that blocks.

Conventions: `→` means the next step depends on the previous passing. Comments marked
`GATE` are steps that exit non-zero. `<root>` is the records root: `docs/engineering/` by
default, or what `.100x.json` `{"root": "..."}` at the git root or `HUNDREDX_ROOT_DIR`
names (`docs/OPERATING-MODEL.md` §8). This plugin's own repo uses `{"root": "."}`, which is
why its examples live at `specs/login`, `decisions/` and `ledger/`.

---

## Contents

| # | task | what it gives you | size |
|---|---|---|---|
| 0 | [0. Start here: say it in plain English](#0-start-here-say-it-in-plain-english) | the one command a newcomer needs; the router picks everything below | 15 lines |
| 1 | [1. Turn a vague request into requirements](#1-turn-a-vague-request-into-requirements) | intake: defaults applied silently, at most five questions | 15 lines |
| 2 | [2. Build a feature](#2-build-a-feature) | the full sequence from PRD to commit, with every gate named | 45 lines |
| 3 | [3. Split the work across agents](#3-split-the-work-across-agents) | orchestrate: task graph, parallel waves, agent reports, replay | 25 lines |
| 4 | [4. Feature into a codebase whose PRD, spec and code have diverged](#4-feature-into-a-codebase-whose-prd-spec-and-code-have-diverged) | **the common real case**: establish ground truth first, then record which of the three you treated as authoritative | 28 lines |
| 5 | [5. Fix a bug](#5-fix-a-bug) | repro-first, and how to prove the test fails without the fix | 28 lines |
| 6 | [6. Review your own code](#6-review-your-own-code) | mechanical checks, then the 9 questions no tool answers | 12 lines |
| 7 | [7. Review someone else's code](#7-review-someone-elses-code) | how this differs: infer intent, rank by blast radius, label every finding | 17 lines |
| 8 | [8. Understand someone else's logic, or a past feature](#8-understand-someone-elses-logic-or-a-past-feature) | the order of operations, and the stop condition so you don't read everything | 16 lines |
| 9 | [9. Root cause analysis](#9-root-cause-analysis) | timeline, hypotheses with falsifying evidence, and the regression test that would have caught it | 16 lines |
| 10 | [10. Write a PRD or architecture proposal](#10-write-a-prd-or-architecture-proposal) | options analysis: fit as a pass/fail filter, then weighted scores, always with a do-nothing option | 18 lines |
| 11 | [11. QA: test plan and coverage](#11-qa-test-plan-and-coverage) | a plan generated from AC ids, and proof every AC has a test | 15 lines |
| 12 | [12. Audit: is the reasoning recorded?](#12-audit-is-the-reasoning-recorded) | the traceability matrix: which features have which records | 10 lines |
| 13 | [Diagram detail levels](#diagram-detail-levels) | which of the three levels to use, and their node budgets | 11 lines |
| 14 | [What still needs a human](#what-still-needs-a-human) | the six defect classes no tool detects anywhere | 7 lines |

## 0. Start here: say it in plain English

```text
/100x-engineer:100x Add tagging to albums so users can find photos by tag
```

| the router does | you do |
|---|---|
| names the intent (build, fix, incident, understand, review, plan, QA, ship) and the tier | read one line |
| applies the defaults for that work type and tier, and lists them | correct any you disagree with |
| asks at most five questions, each with a recommendation | answer, or say "go with your recommendations" |
| runs the matching sequence below, with agents where the work splits | approve one-way decisions when asked |

Everything else on this page is what the router runs for you. Use it directly when you
want one step, not the whole pipeline.

---

## 1. Turn a vague request into requirements

```bash
100x baseline show --work api,web-ui --tier small    # the defaults applied without asking
```

| class | meaning | what happens |
|---|---|---|
| A | a default any senior engineer applies (authz, input validation, 320px reflow) | applied silently, listed as an assumption |
| B | on from a tier (rate limiting at `growth`, multi-region at `scale`) | applied per tier, listed |
| C | genuinely your call (residency, retention, compliance, SLO numbers, cost) | asked; residency, compliance, retention and money block `ready` |

The output is requirements with sources, assumptions, and at most five questions
(`requirements-intake`). They become the PRD's `R<k>` rows or the spec's in-scope rows.

---

## 2. Build a feature

Greenfield or a new feature in an existing codebase.

```bash
# frame it (skip for a small change: a PRD for a two-day feature is overhead)
100x prd new checkout --kind payment --tier small
100x prd audit <root>/prds/checkout                       # GATE

# plan it: --tier is required; --work selects the implicit-requirement baseline
100x plan_feature new checkout --kind payment,crud --stack nestjs --tier small --work api,web-ui
100x prd align <root>/prds/checkout <root>/specs/checkout  # R <-> AC <-> S trace
100x plan_feature audit <root>/specs/checkout              # GATE: blocks coding

# record the choices that departed from the recommended default
100x decide new "Idempotency key strategy" --affects "src/checkout/**"
100x decide lint                                           # GATE

# read the stack's failure modes BEFORE writing
100x stack_audit .
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/nestjs.md

# --- implement ---

100x bloat_check --base origin/main                        # GATE
100x design_drift <root>/specs/checkout/spec.md src/checkout   # GATE
100x decide verify && 100x decide drift                    # GATE
100x review_scope --base origin/main                       # answer every question
100x verified --name test -- <your test command>
git commit                                                 # GATE: receipt required
100x ledger check                                          # GATE: linkage
```

Acceptance criteria are the join key from PRD to test. The spec's `## 2b` holds one line
per criterion, and the verification plan's `covers` column names the criteria each row
proves:

```text
AC-1: A returning user with a correct password gets a 204 and an httpOnly session cookie. (R1, S1)
```

| `plan_feature audit` rejects | because |
|---|---|
| no `AC-<n>` line, or one not in the canonical form | every later tool parses the same lines |
| a duplicate or reused id | tests and `plan.json` reference ids; they are never renumbered |
| an outcome a test cannot observe | "use a service class" is a step, not an outcome |
| an in-scope row with no AC | scope with nothing that proves it shipped |
| a missing or unknown `R<k>` when a PRD exists (header `prd` field, or `<root>/prds/<feature>/`) | the requirement has no trace |
| an AC no verification row `covers` | a criterion nothing checks |

`prd align` traces by id (R ↔ AC ↔ S, and each metric to the `V<k>` row that measures it).
**A declared link proves the trace exists, not that the AC satisfies the requirement**; read
the wording.

**Artifacts:** `<root>/prds/checkout/prd.md`, `<root>/specs/checkout/spec.md` (edge cases
resolved), one or more ADRs in `<root>/decisions/`, a verification receipt.

---

## 3. Split the work across agents

For two or more specialists, or tasks that can run in parallel (`orchestrate`).

```bash
100x plan_dag lint plan.json --spec <root>/specs/checkout/spec.md   # GATE
100x plan_dag waves plan.json          # which tasks run together
100x plan_dag next plan.json           # what can start now
# per task: git worktree add ../wt-T1 -b wt/checkout-T1, then dispatch its agent
100x agent_report extract msg.md -o T1.json
100x agent_report lint T1.json --graph plan.json                    # GATE
100x agent_report replay T1.json --cwd ../wt-T1 --yes               # GATE: re-runs evidence
100x agent_report summary *.json       # every open question, one message to the user
```

| rule | why |
|---|---|
| `--spec` counts only **defined** ACs, and fails a spec with none | a mention like "see AC-3" is not a criterion |
| tasks with no dependency path own disjoint files | two agents never edit the same file |
| shared contracts are `contract: true` tasks others `consume` | the API shape is settled before both sides build on it |
| a report merges only after it lints and replays | "tests pass" is a claim until the main session re-runs it |
| a `needs-decision` task pauses only its dependents | independent work keeps moving |

---

## 4. Feature into a codebase whose PRD, spec and code have diverged

The common real case. Establish ground truth before changing anything.

```bash
# what is actually here?
100x repo_map . --top 20
100x stack_audit .

# what does the code actually do, at the level you need?
100x diagram_from_code src/checkout --kind sequence --level 1   # orient
100x diagram_from_code src/checkout --kind sequence --level 2   # work

# where do the three disagree?
100x prd align <root>/prds/checkout <root>/specs/checkout       # PRD vs spec
100x design_drift <root>/specs/checkout/spec.md src/checkout    # spec vs code

# record the divergence as a decision rather than silently picking a winner
100x decide new "Reconcile spec and code on partial refunds" \
  --affects "src/checkout/**"
```

Three-way divergence has three honest resolutions, and the decision record must say
which you chose: **code is right** (update the spec), **spec is right** (fix the code),
or **both are stale** (re-plan). Picking one silently is how the next person inherits
the same confusion.

---

## 5. Fix a bug

```bash
# 1. reproduce FIRST: an unreproduced bug is a guess
#    write the reproduction as a test, watch it fail, and commit it on its own
git add <test file> && git commit -m "test: reproduce <bug>"

# is this bug a violated assumption? (a very common root cause)
100x decide trace src/<file>
100x decide verify

# 2. fix the narrowest thing that makes the test pass

# 3. prove the test fails without the fix and passes with it
git stash push -- <src paths of the fix>
<the single test>                                  # must fail
git stash pop
<the single test>                                  # must pass

100x bloat_check --base origin/main                # no drive-by changes
100x verified --name test -- <the full suite>
git commit                                         # GATE
```

The permanent test is the deliverable; the fix is incidental. Stashing only the source
paths keeps the committed test in place, so the red run is the real test against the
unfixed code. If the cause was a violated assumption, supersede that decision; do not
edit it.

---

## 6. Review your own code

```bash
100x bloat_check --base origin/main       # mechanical first
100x audit_ci_gates .                     # do your gates actually gate?
100x decide check
100x review_scope --base origin/main      # the 9 questions no tool answers
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/<stack>.md
100x design_drift <root>/specs/<f>/spec.md <dir>
```

---

## 7. Review someone else's code

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

## 8. Understand someone else's logic, or a past feature

```bash
100x repo_map .                           # entry points, hot files
100x ledger find "<feature name>"         # was it written down?
100x decide trace <file>                  # why is it like this
100x diagram_from_code <dir> --kind sequence --level 1     # orient
100x diagram_from_code <dir> --kind sequence --level 2     # detail
100x diagram_from_code <dir> --kind flow --level 3 --entry "Svc.method"
git log -S"<symbol>" --oneline | head             # why the code is shaped this way
100x check_index --register <root>/architecture/<area>.md  # file the note in <root>/INDEX.md
```

**Stop condition:** you understand it when you can state the inputs, outputs, failure
modes and the one thing most likely to break, not when you have read everything.

---

## 9. Root cause analysis

```bash
100x rca new "Sessions dropped after deploy" --affects "src/auth/**" --severity SEV2
100x decide drift                         # did an assumption silently lapse?
100x decide verify
git log --oneline --since="3 days ago" | head
100x diagram_from_code src/auth --kind sequence --level 3   # the real path
100x rca lint                             # GATE
100x rca link RCA-0001 --decision ADR-0001
```

`--severity` takes `SEV1`–`SEV4` (`critical`/`high`/`medium`/`low` still map to them).
`rca lint` rejects a root cause identical to the symptom, and rejects the record
entirely if it names no regression test.

---

## 10. Write a PRD or architecture proposal

```bash
100x prd new <name> --kind <kinds> --tier <tier>
100x prd audit <root>/prds/<name>                # GATE
100x check_diagrams <root>/prds/<name>/prd.md    # GATE
100x decide new "<the architectural choice>" --affects "<glob>"
100x decide lint                                 # GATE
```

Options analysis uses the approach-selection rubric, in two steps:

| step | rule | enforced by |
|---|---|---|
| 1. fit | every option is `"fit": "pass"` or `"fail"`; at least one passes; the chosen one must pass | `decide lint` |
| 2. score (optional) | 1–5 on reversibility ×3, blast radius ×3, moving parts ×2, already-in-use ×2, exit cost ×1; the chosen option holds the top fit-passing score or records `override_reason` | `decide lint` |

Always include "do nothing / smallest change" as an option. For an existing system with
no PRD, reverse-engineer one: `repo_map` + `diagram_from_code --level 1` give you the
current state to write down.

---

## 11. QA: test plan and coverage

```bash
100x testplan new <root>/specs/checkout/spec.md --out   # writes <root>/testplans/checkout.md
100x testplan trace <root>/specs/checkout/spec.md --tests tests/,e2e/   # AC covered / uncovered
100x testplan matrix --work web-ui --tier small         # default devices and browsers
100x test_design_check --base origin/main
```

`trace` finds tests tagged with an AC id; an AC with no tagged test is reported uncovered.
The plan's cases come from the spec's `AC-<n>` lines and its implicit-requirements table.

---

## 12. Audit: is the reasoning recorded?

```bash
100x ledger check      # index + traceability matrix + linkage gaps
cat <root>/ledger/MAP.md                       # feature x record-type grid
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

`--level` on `diagram_from_code`; `check_diagrams` enforces the budgets.

---

## What still needs a human

Six defect classes have no mechanical detection anywhere: semantic duplication,
redundant comments, unnecessary dependencies, tests that assert the bug, missing
authorization, check-then-act races. `review_scope` turns them into nine attributed
questions. Run `100x run_evals` for the current list; it is measured, not
asserted.
