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

Three axes feed the spec, so the gaps are generated rather than remembered:

| axis | flag | catalogue |
|---|---|---|
| feature kind | `--kind auth,crud` | edge cases + 24 pre-answered decisions |
| work type | `--work web-ui,api` | implicit requirements (`scripts/data/baseline.json`) |
| load tier + risk | `--tier small --risk elevated` | what is required and what is not |

1. **Every decision ships a default.** Class A/B baseline items are applied silently and
   listed; decisions carry a recommendation. The agent proceeds and records it.
2. **Only class C items are asked** — residency, retention, compliance regime, cost,
   SLO numbers, unusual targets. At most five questions, each tagged `must-ask` or
   `default`, each with a recommendation.
3. **An unanswered C item may proceed as `ASSUMED(<recommendation>)`**, except
   residency, retention, compliance regime and cost, which block `ready`.

## Rules

1. Scaffold the spec before writing code, declaring the load tier (no default exists),
   the risk level and the work types. `auth`, `payment` and `pii-compliance` raise risk
   to at least `elevated`.
   *Enforced by:* `100x plan_feature new <name> --kind <kinds> --work <types> --tier <tier>`
   exits 2 without `--tier`

1b. Resolve every §0b implicit requirement with an allowlisted status: `covered` or
   `applied` with evidence, `accepted`, `deferred` with a follow-up, `waived(<reason>)`
   (only if waivable), `n/a(<reason>)`, or for class C `ASK(<answer>)` /
   `ASSUMED(<recommendation>)`.
   *Enforced by:* `100x plan_feature audit specs/<name>`

2. Every edge case must end at `covered` with a named test, `accepted` with a reason,
   or `deferred` with a follow-up reference — `TODO` is not a terminal state — and
   implementation starts only once this audit passes. That gate is the whole
   mechanism: without it "we'll decide later" silently becomes "nobody decided".
   *Enforced by:* `100x plan_feature audit specs/<name>` exits non-zero

3. State what is explicitly out of scope. Out-of-scope is what turns a gap into a
   decision — and it is where the edge cases you are deliberately not handling go.
   *Enforced by:* the audit rejects a template placeholder anywhere in the spec

3b. Write the design-doc sections — Security (threat model), Privacy, Observability,
   Migration, Cost. `N/A because <reason>` is fine; blank is not.
   *Enforced by:* `100x plan_feature audit specs/<name>`

4. Any decision that departs from the recommended default needs an ADR. Accepting a
   default is also recorded, as `default`, so a later reader can tell "we chose this
   deliberately" from "nobody looked at it." When a decision has no default, or
   the default's deciding factor does not hold here, hand off to
   `approach-selection` to compare the options, then record its result as the ADR.
   *Enforced by:* `100x decide new` + the audit's ADR-reference check

5. Generate a level-2 sequence diagram (≤30 nodes, implementer detail) of the planned
   flow before implementing, and keep it in the spec as the design of record — prose
   describing a multi-step flow hides exactly the branch that turns out to matter.
   *Enforced by:* `100x diagram_from_code <analogous-existing-code> --kind sequence --level 2` for an existing analog to model the flow on, or a hand-authored `mermaid` block validated by `100x check_diagrams specs/<name>/spec.md` when there is no code yet to generate from

6. Name the verification command per check, with the gate it runs at. A verification
   plan with no commands is a wish.
   *Enforced by:* the audit rejects verification rows with no command

7. State the rollback before the rollout. If you cannot say how to undo it, you do not
   understand the blast radius.
   *Enforced by:* review

## Verify

```bash
# 0. what does this work type inherit at this tier and risk?
100x baseline show --work api --tier small --risk elevated

# 1. scaffold: seeds §0b baseline, edge cases + pre-answered decisions
100x plan_feature new login --kind auth,crud --work api --tier small --stack nestjs
#    work: web-ui mobile api worker data-pipeline cli iac (public-api = api, public)
#    kinds: universal auth crud payment upload search realtime migration integration
#    + infra: cache queue cron webhook third-party-api multi-tenancy pii-compliance
#      batch-job file-storage notification
#    combine them — a checkout feature is `payment,crud`

# 2. fill §0b and sections 1-14, resolve every edge case, then gate on it
100x plan_feature audit specs/login      # exits 1 until complete

# 3. record decisions that depart from the default
100x decide new "Session strategy" --affects "src/auth/**" --tag auth

# 3b. embed the level-2 flow diagram in the spec before writing code -- generate
#     from an analogous existing flow if one exists (there is no new code yet to
#     generate this feature's own diagram from); example login/auth flow:
100x diagram_from_code examples/login/src --kind sequence --level 2
#     no analog: hand-author the mermaid block instead, then validate it
100x check_diagrams specs/login/spec.md

# 4. during and after implementation
100x design_drift specs/login/spec.md src/auth   # design vs code
100x decide verify                                # assumptions still hold
100x decide drift                                 # decisions gone stale
100x bloat_check --base origin/main               # AI bloat in the diff

# 5. the indexes, regenerated not hand-maintained
100x plan_feature index    # specs/INDEX.md
100x decide index          # decisions/INDEX.md
```

A complete worked example is in `specs/login/` — tier `small`, risk `elevated`, 29
baseline items resolved, 31 edge cases (26 covered, 3 accepted, 2 deferred), 10
decisions of which 7 accept the default.

## Failure modes

This skill rejects:

- **Code before a spec** for anything non-trivial.
- **A spec with no declared tier**, or a risk below the floor its kind implies.
- **A §0b status outside the allowlist** — `n/a` with no reason, `done?`, `TODO`.
- **Residency, retention, compliance regime or cost left `ASSUMED`.**
- **More than five open questions**, or one not tagged `must-ask` / `default`.
- **A blank Security, Privacy, Observability, Migration or Cost section.**
- **An edge case left `TODO`.** The audit names the first one and exits non-zero.
- **"Covered" with no test reference** — a claim with no evidence.
- **"Deferred" with no follow-up** — that is a dropped requirement wearing a label.
- **A decision that departs from the default with no ADR**, so the reasoning is lost.
- **A verification plan with no commands.**
- **A template placeholder anywhere** — table, prose or diagram — which is how a spec
  looks finished while being empty.

**Honest limitations:**
- The catalogue covers 19 kinds and 140 edge cases: 9 kinds (including `universal`)
  and 60 cases in `edge_cases.json`, 10 kinds and 80 cases in `edge_cases_infra.json`.
  A feature outside those gets only the 10 universal cases — add to the catalogue
  rather than pretending coverage.
- The audit checks **structure, not judgement**. It cannot tell whether a test named
  in the `test` column actually exercises the edge case. That gap is real and is why
  rule 2 requires a *named* test a reviewer can open.
- Six defect classes are not detectable by any check here — see
  `100x run_evals`, which lists them explicitly. Route those to a
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
- Implicit-requirements baseline, each item citing its standard (WCAG 2.2, OWASP ASVS
  5.0.0, OWASP API Top 10 2023, Google SRE book, NIST SSDF v1.1, Android vitals):
  `scripts/data/baseline.json`; question classes A/B/C: `docs/OPERATING-MODEL.md` §5.
- Edge-case catalogue (140 cases, 19 kinds) and required-decision defaults (24
  decisions, 8 kinds): `scripts/data/edge_cases.json`, `edge_cases_infra.json`,
  `scripts/data/decisions_required.json` —
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
