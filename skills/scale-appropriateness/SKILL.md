---
name: scale-appropriateness
description: >
  Use BEFORE designing anything, to state the expected scale tier and derive what the
  design must and must not include — user and request volume, data growth, latency
  budget, availability target. Prevents both over-engineering for scale nobody asked
  for and shipping a design that cannot survive the stated load. Use PROACTIVELY at the
  start of a spec or PRD, and whenever a decision invokes scale as its justification.
  Not for measuring or fixing performance after the fact — see performance-budgets.
---

# Scale appropriateness

An agent asked to "build login" will either add a Redis cluster, a queue and a read
replica, or assume a hundred users forever. Both are wrong, both look reasonable in a
diff, and neither states which it assumed. That assumption is the most consequential
undocumented decision in most designs.

One declared tier fixes it. Not a questionnaire — a default you override.

## Trigger

**Fire when:** starting a spec or PRD; a decision cites scale as its reason; someone
proposes caching, sharding, a queue, or a replica.

**Do not fire when:** the change is local and scale-invariant — a copy fix, a lint
rule, a rename. Declaring a tier for a typo is ceremony.

## The four tiers

| tier | volume | p95 | availability |
|---|---|--:|---|
| `prototype` | <100 users, <1 req/s | 1000ms | best-effort, no SLA |
| `small` *(default)* | <10k users, low tens req/s | 300ms | single-region, manual failover |
| `growth` | <1M users, hundreds–low thousands req/s | 250ms | automatic in-region failover, stated number |
| `scale` | >1M users, **or any regulated data** | 150ms | numeric SLO with an error budget |

Note that `scale` is reached by **blast radius**, not only by volume. Regulated or
financial data puts a 500-user system in the top tier.

Full definitions, including the required and not-required lists per tier, are in
`scripts/data/scale_tiers.json`.

## The half that matters

Each tier carries a **`not_required`** list, and that is the more useful half. It is
what licenses an agent to keep things simple without arguing:

- `prototype` does not require a caching layer
- `small` does not require multi-region
- `growth` does not require active-active
- `scale` does not require adopting a larger company's practice with no named failure class

Without that list, "we might need it later" wins every argument.

## Rules

1. Declare the tier before designing. It is recorded in the spec's section 0, not held
   in someone's head.
   *Enforced by:* `python3 scripts/plan_feature.py new <name> --scale <tier>`

2. An unfilled or invalid non-functional-requirements table blocks implementation.
   *Enforced by:* `python3 scripts/plan_feature.py audit specs/<name>`

3. Derive requirements from the tier, never from imagination. If a design element is not
   in the tier's `required` list, name the specific failure it prevents or drop it.
   *Enforced by:* review, against `scripts/data/scale_tiers.json`

4. Do not add anything in the tier's `not_required` list without an ADR that says why
   this case is the exception.
   *Enforced by:* `python3 scripts/decide.py lint` (the ADR needs options and a
   deciding factor)

5. Keep the PRD's tier and the spec's tier the same. A silent mismatch means two
   documents describe different systems.
   *Enforced by:* `python3 scripts/prd.py align prds/<name> specs/<name>`

6. A tier change is a re-plan, not a patch. Moving up invalidates decisions made under
   the old tier — supersede them rather than editing them.
   *Enforced by:* `python3 scripts/decide.py drift` after changing the tier

7. State the p95 budget as a number and split it across the call chain. An unstated
   budget means every hop assumes it has the whole thing.
   *Enforced by:* the NFR table's `p95_budget_ms` row; see `performance-budgets` for
   the split

## Verify

```bash
# declare the tier; `small` is the default if you say nothing
python3 scripts/plan_feature.py new checkout --kind payment --scale growth
python3 scripts/plan_feature.py audit specs/checkout          # blocks on an unfilled NFR table

# what does this tier require, and explicitly not require?
python3 -c "import json;t=json.load(open('scripts/data/scale_tiers.json'))['growth'];\
print('REQUIRED:');[print(' -',x) for x in t['required']];\
print('NOT REQUIRED:');[print(' -',x) for x in t['not_required']]"

# PRD and spec must agree on the tier
python3 scripts/prd.py align prds/checkout specs/checkout

# after a tier change, decisions made under the old tier are stale
python3 scripts/decide.py drift
```

## Failure modes

This skill rejects:

- **A spec with no declared tier**, where the reader cannot tell whether 100 or 10
  million users were assumed.
- **A Redis cluster in a `prototype`** — caching is in that tier's `not_required` list,
  so it needs an ADR naming the failure it prevents.
- **A `scale`-tier design with a single instance and no stated SLO.**
- **A PRD and spec that disagree on the tier**, which means the options analysis was
  done against different constraints than the implementation.
- **"We might need it later"** as a justification. Later is a tier change, and a tier
  change is a re-plan with a recorded decision.
- **Treating a 500-user regulated system as `small`** — blast radius, not volume, puts it
  in `scale`.

**Honest limitations:**
- The tier boundaries are conventions, not physics. A write-heavy 5,000-user system can
  be harder than a read-heavy 50,000-user one. The tier is a starting point that must be
  stated, not a measurement.
- Nothing verifies the declared tier is *true*. An optimistic tier produces an
  optimistic design, and only production corrects it.
- The p95 numbers are defaults for a typical web request. A batch job or an interactive
  editor needs its own budget, set deliberately.

## Scale

Every tier, including `prototype` — the whole point is that a prototype gets to stay
simple, on the record, instead of accumulating infrastructure defensively.

## Sources
- Tier definitions and their required / not-required lists:
  `scripts/data/scale_tiers.json`.
- The security baseline by scale (solo / small-team / org / high-blast-radius) these
  tiers are aligned with: `research/35-findings-security-reliability.md`.
- The anti-cargo-culting rule that a practice must name the failure class it prevents:
  `research/00-signal-rubric.md` Part G.
- Latency budget splitting and percentile discipline: `skills/performance-budgets`,
  `reviewers/_latency-numbers.md`.
