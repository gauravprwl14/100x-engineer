---
name: scale-appropriateness
description: >
  Scale tier and over-engineering check at the start of a spec, or before adding caching,
  sharding or a queue: users, traffic, data growth, latency, availability, compliance — what the
  design must and must not include.
---

# Scale appropriateness

An agent asked to "build login" will either add a Redis cluster, a queue and a read
replica, or assume a hundred users forever. Both are wrong, both look reasonable in a
diff, and neither states which it assumed. That assumption is the most consequential
undocumented decision in most designs.

Two declared axes fix it. Not a questionnaire, and not a silent default: the tier is
required, because a defaulted tier is the undocumented assumption this skill exists to
remove.

## Trigger

**Fire when:** starting a spec or PRD; a decision cites scale as its reason; someone
proposes caching, sharding, a queue, or a replica.

**Do not fire when:** the change is local and scale-invariant — a copy fix, a lint
rule, a rename. Declaring a tier for a typo is ceremony.

## Axis 1: load tier

| tier | volume | p95 starting point | availability |
|---|---|--:|---|
| `prototype` | <100 users, <1 req/s | 1000ms | best-effort, no SLA |
| `small` | <10k users, low tens req/s | 300ms | single-region, manual failover |
| `growth` | <1M users, hundreds–low thousands req/s | 300ms | automatic in-region failover |
| `scale` | >1M users | 300ms same-region | numeric SLO with an error budget |

The p95 numbers are **starting points with a basis**, not SLOs: 1000ms from Nielsen's
1-second flow limit, 300ms from the worked budget in `reviewers/_latency-numbers.md`.
The user-facing budget does not tighten with tier — more hops shrink each hop's
*share* of it. The committed SLO is a class C question (`ask.slo-numbers`).

## Axis 2: risk

| risk | when | adds |
|---|---|---|
| `none` | no auth, no personal data, no money | nothing |
| `elevated` | auth, personal data, money; implied by kinds `auth`, `payment`, `pii-compliance` | PII out of logs, encryption in transit, residency / retention / compliance questions |
| `regulated` | a named regime (GDPR special category, HIPAA, PCI DSS, APPI sensitive data) | audit trail, privacy impact assessment |

Risk **never adds capacity items**. A 500-user regulated app is `small` + `regulated`:
it gets the compliance controls and does not get multi-region or sharding. Full
definitions: `scripts/data/scale_tiers.json` (`_risk`) and `scripts/data/baseline.json`.

## The half that matters

Each tier carries a **`not_required`** list, and that is the more useful half. It is
what licenses an agent to keep things simple without arguing:

- `prototype` does not require a caching layer
- `small` does not require multi-region
- `growth` does not require active-active
- `scale` does not require adopting a larger company's practice with no named failure class

Without that list, "we might need it later" wins every argument.

## Rules

1. Declare the tier and risk before designing. They are recorded in the spec's section
   0, not held in someone's head; there is no default tier.
   *Enforced by:* `100x plan_feature new <name> --kind <k> --tier <tier> --risk <risk>`
   exits 2 without `--tier`

1b. Never let risk buy capacity. A regulated or financial system at low volume keeps its
   load tier; only the risk axis rises.
   *Enforced by:* review — the baseline puts no capacity item on the risk axis, which
   `tests/test_baseline.sh` asserts for a regulated `small` app

2. A missing tier, an invalid risk, a risk below its kind's floor, or an unfilled
   non-functional-requirements table blocks implementation.
   *Enforced by:* `100x plan_feature audit specs/<name>`

3. Derive requirements from the tier, never from imagination. If a design element is not
   in the tier's `required` list, name the specific failure it prevents or drop it.
   *Enforced by:* review, against `scripts/data/scale_tiers.json`

4. Do not add anything in the tier's `not_required` list without an ADR that says why
   this case is the exception.
   *Enforced by:* review — no tool detects a `not_required` item that arrived
   without an ADR; once the ADR exists, `decide.py lint` checks it has options
   and a deciding factor

5. Keep the PRD's tier and the spec's tier the same. A silent mismatch means two
   documents describe different systems.
   *Enforced by:* `100x prd align prds/<name> specs/<name>`

6. A tier change is a re-plan, not a patch. Moving up invalidates decisions made under
   the old tier — supersede them rather than editing them.
   *Enforced by:* review — `decide.py drift` flags only decisions whose `affects`
   files changed since recording; it does not watch the tier field

7. State the p95 budget as a number and split it across the call chain. An unstated
   budget means every hop assumes it has the whole thing. It is a starting point; the
   committed number is the product's SLO answer.
   *Enforced by:* the NFR table's `p95_budget_ms` row; see `performance-budgets` for
   the split

## Verify

```bash
# declare tier and risk; payment raises risk to at least `elevated` (~1s)
100x plan_feature new checkout --kind payment --work api --tier growth --risk regulated
100x plan_feature audit specs/checkout          # blocks on tier, risk, NFR, baseline

# what do this tier and risk add, by work type?
100x baseline show --work api,iac --tier small --risk regulated

# PRD and spec must agree on the tier
100x prd align prds/checkout specs/checkout

# decisions whose `affects` files changed since they were recorded (a lead for
# rule 6, not a tier-change detector: it never reads the tier)
100x decide drift
```

## Failure modes

This skill rejects:

- **A spec with no declared tier**, where the reader cannot tell whether 100 or 10
  million users were assumed — `plan_feature new` refuses to scaffold one.
- **An `auth` or `payment` spec declared `risk: none`.**
- **A Redis cluster in a `prototype`** — caching is in that tier's `not_required` list,
  so it needs an ADR naming the failure it prevents.
- **A `scale`-tier design with a single instance and no stated SLO.**
- **A PRD and spec that disagree on the tier**, which means the options analysis was
  done against different constraints than the implementation.
- **"We might need it later"** as a justification. Later is a tier change, and a tier
  change is a re-plan with a recorded decision.
- **Pushing a 500-user regulated system into `scale`** to get its compliance controls.
  It is `small` + `regulated`: compliance from the risk axis, no multi-region.

**Honest limitations:**
- The tier boundaries are conventions, not physics. A write-heavy 5,000-user system can
  be harder than a read-heavy 50,000-user one. The tier is a starting point that must be
  stated, not a measurement.
- Nothing verifies the declared tier is *true*. An optimistic tier produces an
  optimistic design, and only production corrects it.
- The p95 numbers are starting points for a typical web request. A batch job or an interactive
  editor needs its own budget, set deliberately.

## Scale

Every tier, including `prototype` — the whole point is that a prototype gets to stay
simple, on the record, instead of accumulating infrastructure defensively.

## Sources
- Tier definitions, required / not-required lists and the risk axis:
  `scripts/data/scale_tiers.json`; work-type items per tier and risk:
  `scripts/data/baseline.json`.
- Prototype p95 basis: Jakob Nielsen, "Response Times: The 3 Important Limits", NN/g,
  1993 (1.0s keeps the flow of thought).
- The security baseline by scale (solo / small-team / org / high-blast-radius) these
  tiers are aligned with: `research/35-findings-security-reliability.md`.
- The anti-cargo-culting rule that a practice must name the failure class it prevents:
  `research/00-signal-rubric.md` Part G.
- Latency budget splitting and percentile discipline: `skills/performance-budgets`,
  `reviewers/_latency-numbers.md`.
