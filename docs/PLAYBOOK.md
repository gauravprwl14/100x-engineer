# Playbook

What to run for each kind of task. Every row of every sequence either produces an
artifact you can read or a gate that blocks.

Conventions: `→` means the next step depends on the previous passing. **bold** steps
are gates that exit non-zero.

---

## 1. Build a feature

Greenfield or a new feature in an existing codebase.

```bash
# frame it (skip for a small change — a PRD for a two-day feature is overhead)
python3 scripts/prd.py new checkout --kind payment
python3 scripts/prd.py audit prds/checkout                    # GATE

# plan it: seeds the edge cases and decisions this feature type always has
python3 scripts/plan_feature.py new checkout --kind payment,crud --stack nestjs
python3 scripts/prd.py align prds/checkout specs/checkout      # PRD <-> spec divergence
python3 scripts/plan_feature.py audit specs/checkout           # GATE: blocks coding

# record the choices that departed from the recommended default
python3 scripts/decide.py new "Idempotency key strategy" --affects "src/checkout/**"
python3 scripts/decide.py lint                                 # GATE

# read the stack's failure modes BEFORE writing
python3 scripts/stack_audit.py .
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/nestjs.md

# --- implement ---

python3 scripts/bloat_check.py --base origin/main              # GATE
python3 scripts/design_drift.py specs/checkout/spec.md src/checkout   # GATE
python3 scripts/decide.py verify && python3 scripts/decide.py drift  # GATE
python3 scripts/review_scope.py --base origin/main             # answer every question
python3 scripts/verified.py --name test -- <your test command>
git commit                                                      # GATE: receipt required
python3 scripts/ledger.py check                                # GATE: linkage
```

**Artifacts:** `prds/checkout/prd.md`, `specs/checkout/spec.md` (edge cases resolved),
one or more ADRs, a verification receipt.

---

## 2. Feature into a codebase whose PRD, spec and code have diverged

The common real case. Establish ground truth before changing anything.

```bash
# what is actually here?
python3 scripts/repo_map.py . --top 20
python3 scripts/stack_audit.py .

# what does the code actually do, at the level you need?
python3 scripts/diagram_from_code.py src/checkout --kind sequence --level 1   # orient
python3 scripts/diagram_from_code.py src/checkout --kind sequence --level 2   # work

# where do the three disagree?
python3 scripts/prd.py align prds/checkout specs/checkout       # PRD vs spec
python3 scripts/design_drift.py specs/checkout/spec.md src/checkout  # spec vs code

# record the divergence as a decision rather than silently picking a winner
python3 scripts/decide.py new "Reconcile spec and code on partial refunds" \
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
python3 scripts/verified.py --name repro -- <the single failing test>   # expect non-zero

# is this bug a violated assumption? (a very common root cause)
python3 scripts/decide.py trace src/<file>
python3 scripts/decide.py verify

# --- fix the narrowest thing that makes the test pass ---

python3 scripts/bloat_check.py --base origin/main       # no drive-by changes
python3 scripts/verified.py --name test -- <the full suite>
git commit                                              # GATE
```

The permanent test is the deliverable; the fix is incidental. If the cause was a
violated assumption, supersede that decision — do not edit it.

---

## 4. Review your own code

```bash
python3 scripts/bloat_check.py --base origin/main       # mechanical first
python3 scripts/audit_ci_gates.py .                     # do your gates actually gate?
python3 scripts/decide.py check
python3 scripts/review_scope.py --base origin/main      # the 9 questions no tool answers
sed -n '/## Common AI failure modes/,/## Edge cases/p' reviewers/<stack>.md
python3 scripts/design_drift.py specs/<f>/spec.md <dir>
```

---

## 5. Review someone else's code

Different job: infer intent before critiquing, rank by blast radius, never lead with
style.

```bash
python3 scripts/repo_map.py . --symbol <TheThingTheyChanged>
python3 scripts/decide.py trace <changed-file>          # what governs this already?
python3 scripts/diagram_from_code.py <their-dir> --kind sequence --level 2
python3 scripts/review_scope.py --base <their-base>
python3 scripts/audit_agent_config.py .                 # if the PR is from outside
```

Label every finding **blocking / should-fix / optional / question**. Unlabelled
feedback reads as blocking.

---

## 6. Understand someone else's logic, or a past feature

```bash
python3 scripts/repo_map.py .                           # entry points, hot files
python3 scripts/ledger.py find "<feature name>"         # was it written down?
python3 scripts/decide.py trace <file>                  # why is it like this
python3 scripts/diagram_from_code.py <dir> --kind sequence --level 1     # orient
python3 scripts/diagram_from_code.py <dir> --kind sequence --level 2     # detail
python3 scripts/diagram_from_code.py <dir> --kind flow --level 3 --entry "Svc.method"
git log -S"<symbol>" --oneline | head             # why the code is shaped this way
```

**Stop condition:** you understand it when you can state the inputs, outputs, failure
modes and the one thing most likely to break — not when you have read everything.

---

## 7. Root cause analysis

```bash
python3 scripts/rca.py new "Sessions dropped after deploy" --affects "src/auth/**" --severity high
python3 scripts/decide.py drift                         # did an assumption silently lapse?
python3 scripts/decide.py verify
git log --oneline --since="3 days ago" | head
python3 scripts/diagram_from_code.py src/auth --kind sequence --level 3   # the real path
python3 scripts/rca.py lint                             # GATE
python3 scripts/rca.py link RCA-0001 --decision ADR-0001
```

`rca.py lint` rejects a root cause identical to the symptom, and rejects the record
entirely if it names no regression test.

---

## 8. Write a PRD or architecture proposal

```bash
python3 scripts/prd.py new <name> --kind <kinds>
# options analysis uses the approach-selection rubric:
#   reversibility x3, blast radius x3, moving parts x2, already-in-use x2,
#   exit cost x1, fit x1 — and always include "do nothing / smallest change"
python3 scripts/prd.py audit prds/<name>                # GATE
python3 scripts/check_diagrams.py prds/<name>/prd.md    # GATE
python3 scripts/decide.py new "<the architectural choice>" --affects "<glob>"
```

For an existing system with no PRD, reverse-engineer one: `repo_map.py` +
`diagram_from_code.py --level 1` give you the current state to write down.

---

## 9. Audit: is the reasoning recorded?

```bash
python3 scripts/ledger.py check      # index + traceability matrix + linkage gaps
cat ledger/MAP.md                    # feature x record-type grid
python3 scripts/ledger.py stats      # growth; when to shard
python3 scripts/ledger.py shard      # past 40 records per directory
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
questions. Run `python3 scripts/run_evals.py` for the current list; it is measured, not
asserted.
