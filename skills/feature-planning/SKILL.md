---
name: feature-planning
description: >
  Use BEFORE writing code for any new feature, endpoint, screen, payment flow,
  upload, migration, or integration — scaffolds a spec that seeds the edge cases
  and decisions that feature kind always has, pre-answers each with a recommended
  default, and mechanically blocks implementation until gaps are resolved or
  explicitly accepted. Use PROACTIVELY when asked to build, implement, or add a
  feature. Not for fixing something broken (bug-fix) and not for choosing between
  competing implementation approaches inside an already-planned feature
  (approach-selection, called from within this skill's decision points).
---

# Feature planning

The goal is one-shot: the gaps are found before the code, not in review. That works
because the gaps are not novel. "Build login" has the same 31 edge cases every time,
and an agent that writes plausible code without enumerating them will miss roughly
the same ones every engineer misses.

## Trigger

**Fire when:** asked to build, implement, or add new behavior — a feature, an
endpoint, a screen, a flow — beyond a trivial edit.

**Do not fire when:** the change is a typo, a version bump, a rename, or a one-line
fix with an obvious blast radius of zero (planning overhead on a trivial change is
the fastest way to get planning abandoned); the work is *correcting* something
broken rather than adding new behavior — that's `bug-fix`, or `root-cause-analysis`
first if the cause isn't obvious; or the codebase already has a spec for this
feature and code has drifted from it — that's `codebase-comprehension` +
`design_drift.py` to re-establish ground truth before re-planning.

## How this avoids interrogating you

Three rules, because a process that asks twenty questions is worse than no process:

1. **Every decision ships a default.** 24 recurring decisions across 8 feature kinds
   are pre-answered with a recommendation and the factor that would change it. The
   agent proceeds on defaults and records that it did.
2. **A question only appears if its answer changes the design.** Anything else is a
   preference and gets a default instead.
3. **Every question carries a recommendation**, so work continues while it is
   unanswered rather than blocking on you.

## Rules

1. Scaffold the spec before writing code. The spec seeds the edge cases and decisions
   for the feature kind, so nothing has to be remembered.
   *Enforced by:* `python3 scripts/plan_feature.py new <name> --kind <kinds>`

2. Every edge case must end at `covered` with a named test, `accepted` with a reason,
   or `deferred` with a follow-up reference — `TODO` is not a terminal state — and
   implementation starts only once this audit passes. That gate is the whole
   mechanism: without it "we'll decide later" silently becomes "nobody decided".
   *Enforced by:* `python3 scripts/plan_feature.py audit specs/<name>` exits non-zero

3. State what is explicitly out of scope. Out-of-scope is what turns a gap into a
   decision — and it is where the edge cases you are deliberately not handling go.
   *Enforced by:* the audit rejects placeholder cells in the scope table

4. Any decision that departs from the recommended default needs an ADR. Accepting a
   default is also recorded, as `default`, so a later reader can tell "we chose this
   deliberately" from "nobody looked at it."
   *Enforced by:* `python3 scripts/decide.py new` + the audit's ADR-reference check

5. Generate a level-2 sequence diagram (≤30 nodes, implementer detail) of the planned
   flow before implementing, and keep it in the spec as the design of record — prose
   describing a multi-step flow hides exactly the branch that turns out to matter.
   *Enforced by:* `python3 scripts/diagram_from_code.py <analogous-existing-code> --kind sequence --level 2` for an existing analog to model the flow on, or a hand-authored `mermaid` block validated by `python3 scripts/check_diagrams.py specs/<name>/spec.md` when there is no code yet to generate from

6. Name the verification command per check, with the gate it runs at. A verification
   plan with no commands is a wish.
   *Enforced by:* the audit rejects verification rows with no command

7. State the rollback before the rollout. If you cannot say how to undo it, you do not
   understand the blast radius.
   *Enforced by:* review

## Verify

```bash
# 1. scaffold: seeds edge cases + pre-answered decisions for the feature kind
python3 scripts/plan_feature.py new login --kind auth,crud --stack nestjs
#    kinds: universal auth crud payment upload search realtime migration integration
#    combine them — a checkout feature is `payment,crud`

# 2. fill sections 1-4 and 8-9, resolve every edge case, then gate on it
python3 scripts/plan_feature.py audit specs/login      # exits 1 until complete

# 3. record decisions that depart from the default
python3 scripts/decide.py new "Session strategy" --affects "src/auth/**" --tag auth

# 3b. embed the level-2 flow diagram in the spec before writing code -- generate
#     from an analogous existing flow if one exists (there is no new code yet to
#     generate this feature's own diagram from); example login/auth flow:
python3 scripts/diagram_from_code.py examples/login/src --kind sequence --level 2
#     no analog: hand-author the mermaid block instead, then validate it
python3 scripts/check_diagrams.py specs/login/spec.md

# 4. during and after implementation
python3 scripts/design_drift.py specs/login/spec.md src/auth   # design vs code
python3 scripts/decide.py verify                                # assumptions still hold
python3 scripts/decide.py drift                                 # decisions gone stale
python3 scripts/bloat_check.py --base origin/main               # AI bloat in the diff

# 5. the indexes, regenerated not hand-maintained
python3 scripts/plan_feature.py index    # specs/INDEX.md
python3 scripts/decide.py index          # decisions/INDEX.md
```

A complete worked example is in `specs/login/` — 31 seeded edge cases resolved as
26 covered, 3 accepted, 2 deferred, with 10 decisions of which 7 accept the default.

## Failure modes

This skill rejects:

- **Code before a spec** for anything non-trivial.
- **An edge case left `TODO`.** The audit names the first one and exits non-zero.
- **"Covered" with no test reference** — a claim with no evidence.
- **"Deferred" with no follow-up** — that is a dropped requirement wearing a label.
- **A decision that departs from the default with no ADR**, so the reasoning is lost.
- **A verification plan with no commands.**
- **A placeholder left in any table cell**, which is how a spec looks finished while
  being empty.
- **A sequence diagram still containing template text.**

**Honest limitations:**
- The catalogue covers 9 feature kinds and 60 edge cases. A feature outside those
  kinds gets only the 10 universal cases — add to `scripts/data/edge_cases.json`
  rather than pretending coverage.
- The audit checks **structure, not judgement**. It cannot tell whether a test named
  in the `test` column actually exercises the edge case. That gap is real and is why
  rule 2 requires a *named* test a reviewer can open.
- Six defect classes are not detectable by any check here — see
  `python3 scripts/run_evals.py`, which lists them explicitly. Route those to a
  scoped review pass.

## Next

Once the audit passes: read `stack-reviewer` for the framework's failure modes
before writing code. While implementing, `bloat_check.py` and `design_drift.py` run
continuously (Verify step 4). Before opening the PR, run `scoped-review` on the
diff. Before commit, `verification-gate`.

## Scale

`solo` and up, and this is the skill that matters most at `solo`, where no reviewer
will catch a missed edge case. At `small-team` the spec becomes the review artifact,
which is cheaper to review than a diff. At `org` the decision log matters more than
the spec, because the expensive question becomes "why is it like this" years later.

## Sources
- Edge-case catalogue (60 cases, 9 kinds) and required-decision defaults (24
  decisions): `scripts/data/edge_cases.json`, `scripts/data/decisions_required.json` —
  `SOURCE: original`, assembled from the failure classes named across
  `research/23`, `research/33`, `research/35` and `research/36`.
- The "one named command proves it works" rule appears in 30+ of 48 surveyed
  production agent-instruction files: `research/21-findings-agent-instruction-corpus.md`.
- Expand/contract migration discipline and rollback-must-be-tested:
  `research/35-findings-security-reliability.md`.
- Per-schema-version migration tests as the most consistent mobile practice:
  `research/33-findings-mobile-verification.md`.
- Measured scope of what these checks catch and the six they do not:
  `scripts/run_evals.py`, `evals/seeded/`.
