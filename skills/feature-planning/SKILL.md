---
name: feature-planning
description: >
  Build, implement or add a feature, endpoint, screen, payment flow, upload or integration:
  scaffold a spec with the edge cases and decisions it always has, before code. Not for a bug (→
  bug-fix).
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
| feature kind | `--kind auth,crud` (optional, default `universal`) | edge cases + 24 pre-answered decisions |
| work type | `--work web-ui,api` | implicit requirements (`scripts/data/baseline.json`) |
| load tier + risk | `--tier small --risk elevated` | what is required and what is not |

1. **Every decision ships a default.** Class A/B baseline items are applied silently and
   listed; decisions carry a recommendation. The agent proceeds and records it.
2. **Only class C items are asked** — residency, retention, compliance regime, cost,
   SLO numbers, unusual targets. At most five questions, each tagged `must-ask` or
   `default`, each with a recommendation. `plan_feature new` seeds §6 with at most five
   of the applicable C asks, blocking first, then one-way doors; the rest are listed as
   "Deferred to next batch" and stay `ASK` rows in §0b.
3. **An unanswered C item may proceed as `ASSUMED(<recommendation>)`**, except
   residency, retention, compliance regime and cost, which block `ready`.

`<root>` below is the records root: `docs/engineering/` by default, or `.100x.json`
`{"root": "..."}` at the git root, or `HUNDREDX_ROOT_DIR` (`docs/OPERATING-MODEL.md` §8).
This plugin's own repo pins `{"root": "."}`, so its worked example is `specs/login/`.
A feature's spec, `plan.json`, `testplan.md` and `reports/` live together in
`<root>/specs/<feature>/`. A generated `spec.md` keeps its fixed sections and needs no
Contents table (`AGENTS.md` rule 17).

## Acceptance criteria — the one id from PRD to test

Spec §2b holds one line per criterion, `AC-<n>: <observable outcome> (R<k>, S<k>)`;
the header's `| prd |` field names the PRD, and the §8 verification plan's `covers`
column lists the ACs each row proves. `plan_feature audit` requires: at least one AC,
every AC on its own canonical line, ids unique and never renumbered, an outcome a test
can observe, every in-scope `S<k>` row mapped to an AC, `R<k>` links that exist when a
PRD is linked, and every AC covered by a verification row. It also runs `prd audit` on
the linked PRD (the `| prd |` field, else `<root>/prds/<feature>/`): its failures are
errors from the `growth` tier, where a PRD is required, and warnings below;
`| prd | none |` unlinks it. `plan_dag lint` and `testplan trace` read the same parser, so only ACs defined in §2b count. Tests tag them
`<feature>/AC-<n>` (`test('login/AC-1 …')`), because AC ids repeat across specs.

The spec header pins the baseline version it was written against, `| baseline | <n> |`.
The audit requires the items that existed at that version and only warns about items
added later, so a finished spec does not fail when the catalogue grows. Baseline ids are
never deleted; a retired item is marked `deprecated`.

## Rules

1. Scaffold the spec before writing code, declaring the load tier (no default exists),
   the risk level and the work types. `auth`, `payment` and `pii-compliance` raise risk
   to at least `elevated`.
   *Enforced by:* `100x plan_feature new <name> --work <types> --tier <tier> [--kind <kinds>]`
   exits 2 without `--tier`

1b. Resolve every §0b implicit requirement with an allowlisted status: `covered` or
   `applied` with evidence, `accepted`, `deferred` with a follow-up, `waived(<reason>)`
   (only if waivable), `n/a(<reason>)`, or for class C `ASK(<answer>)` /
   `ASSUMED(<recommendation>)`. Evidence for `covered`/`applied` (and a covered edge
   case's reference) must be proof: a test or file path, a `<feature>/AC-<n>` tag, a
   runnable command, an ADR id or a §8 `V<n>` row. The seeded suggestion copied as-is is
   an error; `review` alone passes but is counted unverified in the audit summary.
   *Enforced by:* `100x plan_feature audit <root>/specs/<name>`

2. Every edge case must end at `covered` with a named test, `accepted` with a reason,
   or `deferred` with a follow-up reference — `TODO` is not a terminal state — and
   implementation starts only once this audit passes. That gate is the whole
   mechanism: without it "we'll decide later" silently becomes "nobody decided".
   A seeded edge-case (§7) or decision (§5) row is answered, never deleted.
   *Enforced by:* `100x plan_feature audit <root>/specs/<name>` exits non-zero, also on a
   deleted seeded row

3. State what is explicitly out of scope. Out-of-scope is what turns a gap into a
   decision — and it is where the edge cases you are deliberately not handling go.
   *Enforced by:* the audit rejects a template placeholder anywhere in the spec

3b. Write the design-doc sections — Security (threat model), Privacy, Observability,
   Migration, Cost. `N/A because <reason>` is fine; blank is not.
   *Enforced by:* `100x plan_feature audit <root>/specs/<name>`

4. Any decision that departs from the recommended default needs an ADR. Accepting a
   default is also recorded, as `default`, so a later reader can tell "we chose this
   deliberately" from "nobody looked at it." When a decision has no default, or
   the default's deciding factor does not hold here, hand off to
   `approach-selection` to compare the options, then record its result as the ADR.
   *Enforced by:* `100x decide new` + the audit's ADR-reference check

5. Generate a level-2 sequence diagram (≤30 nodes, implementer detail) of the planned
   flow before implementing, and keep it in the spec as the design of record — prose
   describing a multi-step flow hides exactly the branch that turns out to matter.
   *Enforced by:* `100x diagram_from_code <analogous-existing-code> --kind sequence --level 2` for an existing analog to model the flow on, or a hand-authored `mermaid` block validated by `100x check_diagrams <root>/specs/<name>/spec.md` when there is no code yet to generate from

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
100x plan_feature audit <root>/specs/login      # exits 1 until complete

# 3. record decisions that depart from the default
100x decide new "Session strategy" --affects "src/auth/**" --tag auth

# 3b. embed the level-2 flow diagram in the spec before writing code -- generate
#     from an analogous existing flow if one exists (there is no new code yet to
#     generate this feature's own diagram from); example login/auth flow:
100x diagram_from_code examples/login/src --kind sequence --level 2
#     no analog: hand-author the mermaid block instead, then validate it
100x check_diagrams <root>/specs/login/spec.md

# 4. during and after implementation
100x design_drift <root>/specs/login/spec.md src/auth   # design vs code
100x decide verify                                # assumptions still hold
100x decide drift                                 # decisions gone stale
100x bloat_check --base origin/main               # AI bloat in the diff

# 5. the indexes, regenerated not hand-maintained
100x plan_feature index    # <root>/specs/INDEX.md
100x decide index          # <root>/decisions/INDEX.md
```

A complete worked example is in this repo's `specs/login/` (its `<root>` is `.`) — tier `small`, risk `elevated`, 29
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
- **A seeded edge case or decision deleted** instead of answered with `n/a(<reason>)`,
  `waived(<reason>)` or a chosen option.
- **"Covered" with no test reference** — a claim with no evidence — or with the seeded
  suggestion pasted back, or prose that names nothing a reviewer can open or run.
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
continuously (Verify step 4). Before opening the PR, run `diff-review` on the
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
