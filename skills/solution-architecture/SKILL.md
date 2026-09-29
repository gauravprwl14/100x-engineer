---
name: solution-architecture
description: >
  Use when asked to write a PRD, a solution proposal, or "the implementation
  approach" for something bigger than one feature — a new system, a build-vs-buy
  call, a migration, or any request to "think like a solution architect" before
  a spec exists. Sits ABOVE feature-planning: this frames the problem, weighs
  options at the system level, and recommends; feature-planning then turns the
  recommendation into edge cases and a diagram for a single feature. Not for
  scoring a single already-framed technical choice — that's approach-selection,
  which this skill calls for its own options table rather than re-deriving it.
  Also use to reverse-engineer a PRD from code that already exists and was never
  documented.
---

# Solution architecture

A spec (`skills/feature-planning`) assumes the "what" is already decided and finds
the edge cases in the "how". This skill is what decides the "what" — and, in a
codebase that already exists, what to do about the gap between what the PRD
promised, what the spec described, and what actually shipped. That three-way
divergence is normal, not a failure, and it is undetectable if nobody wrote the
PRD down in a form that can be checked against the other two.

## Trigger

**Fire when:** asked for a PRD, a solution proposal, a build-vs-buy recommendation,
a migration plan, or "the implementation approach" for something spanning multiple
features or components; asked to evaluate whether to rewrite something; handed
existing code with no PRD and asked to change it.

**Do not fire when:** the solution is already decided and the ask is "write the
spec" — go straight to `feature-planning`. Re-litigating a settled choice at the
PRD altitude for a one-file change is the same overhead problem `feature-planning`
warns about, one layer up.

## Rules

1. Frame the problem before proposing solutions: name who has it, what they do
   today, and give "better" a number and a way to measure it. A PRD nobody can
   evaluate in six months was decoration.
   *Enforced by:* `python3 scripts/prd.py audit prds/<name>`

2. State constraints — team size and skills, existing stack, deadline, budget,
   compliance, what cannot change — before scoring options, not after picking one
   and rationalizing it.
   *Enforced by:* `python3 scripts/prd.py audit prds/<name>` (rejects placeholder
   constraint cells)

3. Score every option, **always including do-nothing / the smallest possible
   change**, on the `approach-selection` rubric (reversibility x3, blast radius x3,
   moving parts x2, already-in-use x2, exit cost x1, fit x1). Cross-reference that
   skill's weights and tie-breaks rather than re-deriving them here.
   *Enforced by:* `python3 scripts/prd.py audit prds/<name>` (>=2 options, every
   option — including the winner — needs a genuine con)

4. Name the recommendation's single deciding factor, and the observation that
   would change it. "Best overall" is not a deciding factor; it means the options
   were not actually compared.
   *Enforced by:* `python3 scripts/prd.py audit prds/<name>`

5. Score every risk likelihood x impact and give it a mitigation. A risk with no
   mitigation is a worry someone wrote down, not a plan.
   *Enforced by:* `python3 scripts/prd.py audit prds/<name>`

6. Phase the plan: what ships first, what risky assumption it proves, and the kill
   criteria if it fails. Phase 1 is the smallest slice that tests the riskiest
   assumption — not the smallest slice of the full feature.
   *Enforced by:* review — `prd.py audit` checks the table is filled, not that the
   phase is actually the risky slice

6b. Include a level-1 diagram (≤12 nodes) of the recommended system shape — a
   reviewer deciding whether to approve the PRD was not in the room when the
   options were scored, and a paragraph describing three boxes and two arrows is
   slower to check than the picture.
   *Enforced by:* `python3 scripts/check_diagrams.py prds/<name>/prd.md`

7. State what is explicitly out of scope, same discipline as `feature-planning`
   rule 3: out-of-scope is what turns a gap into a decision.
   *Enforced by:* `python3 scripts/prd.py audit prds/<name>`

8. Before treating a PRD as final, check it against the spec it feeds: a PRD
   requirement with no spec section is a dropped requirement; a spec section
   implementing nothing in the PRD is undocumented scope creep; a success metric
   with no verification step is a promise nobody wired a check for.
   *Enforced by:* `python3 scripts/prd.py align prds/<name> specs/<name>`

9. Fit the design to the codebase that exists. A rewrite is justified only when
   **all** of: the current design provably cannot meet a stated constraint (not
   "feels dated"), the cost of extending it exceeds the cost of rebuilding *and
   re-proving* it, and the team can absorb the cutover risk in the stated deadline.
   Two of three is a large refactor, not a rewrite — say so and pick the refactor.
   *Enforced by:* review

10. When code exists in production with no PRD, reverse-engineer one from the code
    and its spec before proposing changes to it — you cannot know what to preserve
    without first writing down what the code is currently for.
    *Enforced by:* convention

## Working with an existing codebase

Default to fitting the recommendation to what already runs, not proposing a clean
slate:

- Read the constraints table (rule 2) against the actual stack before scoring
  options — "already-in-use" in the rubric is not a preference, it is a fact
  about this repo, checkable with `grep` and `decide.py trace`.
- An option that requires touching working, untested-but-load-bearing code scores
  worse on blast radius even if it is architecturally cleaner. The rubric already
  weights this at x3; do not override it with taste.
- If the existing code already made this class of choice (`decide.py trace
  <path>`), a new PRD proposing something else needs an ADR that supersedes the
  old one, not a silent second way of doing the same thing.

## Reverse-engineering a PRD from existing code

Common, and genuinely useful — not a fallback for when "real" PRD work was skipped.
Code in production is evidence of a decision even when nobody wrote the decision
down:

1. Read the code's actual behavior and any spec/ADRs that exist for it — those are
   the "what they do today" and "constraints" rows; do not invent them.
2. Write Requirements (`prd.py new` §5) as what the code *currently* does, not what
   it was probably meant to do — a requirement with no code and no stated reason
   behind it is speculation, not reverse-engineering.
3. Success metrics are usually the gap: shipped code frequently has no instrumented
   metric at all. Recording that gap explicitly (proposed, not measured) is itself
   the finding — see `examples/login/prd.md` §11 for a worked instance.
4. Run `prd.py align` against the real spec once both exist. A reverse-engineered
   PRD that fails its own alignment check found a real divergence, not a bug in
   the tool.

## Verify

```bash
# scaffold: pre-answers the do-nothing option, seeds 3 universal risks
python3 scripts/prd.py new login --kind auth --stack nestjs

# fill sections 1-7, 9-10, then gate on completeness (~10s)
python3 scripts/prd.py audit prds/login

# the PRD's requirements and metrics must trace into the spec that implements them
python3 scripts/plan_feature.py new login --kind auth,crud --stack nestjs
python3 scripts/prd.py align prds/login specs/login       # both directions, ~5s

# a level-1 diagram (<=12 nodes) of the recommended shape — orientation for a
# reviewer who was not in the room when the options were scored
test -f scripts/diagram_from_code.py \
  && python3 scripts/diagram_from_code.py <closest-existing-analog> --kind deps --level 1 \
  || echo "not built in this checkout yet -- hand-sketch the system boundary and say so"

# gate: does the PRD actually contain that diagram, not just describe one in prose
python3 scripts/check_diagrams.py prds/login/prd.md

# feature-level choices inside the recommendation still need their own record
python3 scripts/decide.py new "Session strategy" --affects "src/auth/**" --tag auth

python3 scripts/prd.py index    # prds/INDEX.md
```

Reverse-engineering an existing system: `repo_map.py` plus
`diagram_from_code.py --level 1` (same guard as above) give you the current-state
picture to write down, before proposing what changes.

A complete worked example is `examples/login/prd.md`, audited clean and aligned
0/0/0 against `specs/login/spec.md`.

## Failure modes

This skill rejects:

- **A success metric with no number** ("increase engagement") or **no measurement
  method** — unfalsifiable in six months, same failure `research/00` Part G names
  for the whole research process.
- **An options table with one option**, or a winning option with no stated
  con — a choice "considered" with no downside listed was not actually compared,
  just picked.
- **A recommendation with no deciding factor** — "the team liked it" is not
  reproducible reasoning.
- **A risk recorded with no mitigation.**
- **"Do nothing" missing from the options table.** It is frequently the correct
  answer and it is the option every PRD template omits by default.
- **A rewrite recommended on "the code is old" alone** — rule 9's three criteria
  are conjunctive on purpose; a rewrite that only clears one or two is a refactor
  wearing a bigger word.
- **A PRD nobody checked against its spec** — `align` catches a requirement like
  "supports hardware security keys" that never made it into the spec's in-scope
  table, and a spec route that implements something the PRD never asked for.
- **A recommendation described only in prose**, with no diagram a reviewer who
  wasn't in the room can check the options table against.

**Honest limitations:**
- `prd.py align` is **name-level, not semantic** — it matches shared significant
  words between the PRD and the spec. A real match phrased in different words is
  missed; an accidental shared word can produce a false "OK". Treat every finding
  as a lead for a human to check, not proof either way. It says this in its own
  output every time it runs.
- Nothing here checks whether a success metric is actually being measured in
  production, only whether the spec names a verification step for it. A metric can
  pass `align` and still have no real telemetry behind it — see
  `examples/login/prd.md` §11, which records exactly that gap rather than hiding it.
- Rule 9's rewrite criteria are a judgement call codified as a checklist, not a
  formula. The check forces the criteria to be named; it cannot verify they are
  true.

## Next

Once the PRD audits clean and aligns with a spec (or there isn't one yet): hand the
recommendation to `feature-planning` to scaffold that spec. Record the recommendation
itself with `decision-log` if it departs from an existing choice
(`decide.py trace` first). Implementation then follows the normal path through
`stack-reviewer`, `scoped-review`, and `verification-gate`.

## Scale

`solo` and up for the reverse-engineering half — the only person who will ever ask
"why does this code do this" is future-you, and the code alone will not tell you.
The forward half (writing a PRD before building) starts paying for itself at
`small-team`, where the PRD is the thing a non-implementer can actually review, and
matters most at `org`, where the PRD is what survives when everyone who remembers
the original context has moved to a different team.

## Sources
- `## Context / Decision / Consequences` as the minimum viable decision record, and
  "all consequences, not just the positive ones": `backstage/backstage@master:docs/
  architecture-decisions/adr000-template.md`.
- Motivation stated as user problems, not features; explicit Goals/Non-Goals; a
  dedicated Risks and Mitigations section; Graduation Criteria as phased,
  falsifiable proof before wider rollout: `kubernetes/enhancements@master:keps/
  NNNN-kep-template/README.md`.
- "Drawbacks" and "Rationale and alternatives" as required sections — a proposal
  with no stated downside or rejected alternative is not reviewable:
  `rust-lang/rfcs@master:0000-template.md`.
- The approach-selection rubric this cross-references rather than re-deriving:
  `skills/approach-selection/SKILL.md`.
- The pre-answered-defaults, table-driven, mechanically-gated philosophy this
  applies one layer up: `skills/feature-planning/SKILL.md`, `scripts/plan_feature.py`.
- The weighted rubric applied to options, the do-nothing default bias, and the PRD
  <-> spec alignment check as a distinct mechanism from spec <-> code drift
  (`scripts/design_drift.py`) or decision staleness (`scripts/decide.py drift`):
  `SOURCE: original`.
- `diagram_from_code.py`/`check_diagrams.py` and the level-1/2/3 detail scale:
  built by a sibling effort in this plugin, referenced here rather than duplicated
  — same convention `skills/codebase-comprehension/SKILL.md` uses.
