---
name: observability-design
description: >
  Use when adding a metric, a log line, a trace span, an alert rule, or an SLO —
  or when designing a new service/endpoint/job and deciding what it should emit
  before it ships. Covers choosing metrics vs traces vs logs, cardinality
  budgets for labels, structured-logging field conventions, what to log at a
  service boundary, SLI/SLO/error-budget mechanics, symptom-based alert design,
  and observability cost/sampling as a design decision. Not for debugging a
  live incident with existing telemetry — this is about what gets instrumented
  before the incident, not how to read a dashboard during one. Use PROACTIVELY
  before merging a new endpoint, job, or service, and when writing an alert
  rule.
---

# Observability by design

Instrumentation added after an incident is always late — the code path that
paged you didn't have the field you needed at 3am, and now everyone adds it,
everywhere, defensively, which is how cardinality problems are born. Decide what
this code needs to answer *before* it ships, not after it fails once.
`research/35-findings-security-reliability.md` records that **no repo in a
33-repo corpus has a numeric SLO/error-budget document as a first-class file**
and that only one (`kestra-io/kestra`) has a dedicated metrics-naming
convention — this skill is that convention, generalized and sourced, because
the corpus shows almost nobody writes it down.

## Trigger

**Fire when:** adding or changing a metric, log statement, trace span, alert
rule, or SLO; designing a new endpoint, job, or service (instrument at design
time, not after); reviewing a diff that adds a label to an existing metric.

**Do not fire when:** debugging with telemetry that already exists — that's
incident response, not design. Not for choosing a vendor/backend (Datadog vs
Grafana vs...) — this is about what to emit, not where it's stored.

## Rules

1. **Pick the signal for the question, not out of habit.** Metrics are for
   aggregates you'll alert on (cheap, lossy, no per-request detail — bad at
   "why did *this* request fail"). Traces are for causality across services
   (show the call graph and where time went — bad at aggregate trends, and
   expensive if you keep 100% of them). Logs are for the detail of one event
   (richest, but unindexed free text is bad at "how many of these happened" at
   scale). Reaching for a log grep to answer an aggregate question, or a metric
   to answer a causal one, is the mismatch this rule catches.
   *Enforced by:* review

2. **Cardinality budget: no unbounded value in a metric label.** A user id,
   request id, raw URL, or email in a label turns one metric into millions of
   time series and can take down the metrics backend — this is the exact
   mechanism `kestra-io/kestra` names as the reason its guideline exists (see
   Sources). OpenTelemetry's own registry states the same constraint on
   `error.type`: "SHOULD have low cardinality... SHOULD be predictable."
   Concrete budget: a label's value set should be enumerable and stable —
   status codes, error classes, route *templates* (`/users/{id}`, never the
   raw path), tenant tier, region. Never a raw id, raw URL, or free-text input.
   *Enforced by:* `grep -rnE "\.(label|tag|with_label)s?\(" <diff> | grep -iE "user.?id|email|request.?id|session.?id|raw.?url"`

3. **Structured logging: one JSON event per line, stable field names, no PII,
   correlation id always present.** This is a naming convention, not a
   suggestion — follow OTel's attribute-naming rules: lowercase, dot-namespaced
   (`http.response.status_code`, not `httpStatus`), snake_case within a
   namespace segment, and never reuse a name for a different meaning once
   shipped. Propagate the trace/correlation id from the inbound request through
   every log line the request touches — a log line with no correlation id is
   unfindable the moment there's more than one request in flight.
   *Enforced by:* `grep -rnE "console\.log\(|print\(" <diff>` for unstructured
   log calls in a codebase with a structured logger available is flagged for
   review; PII in a log line is checked by rule 5.

4. **At a service boundary, log the decision — not the payload.** On every
   inbound/outbound boundary crossing, log: a request id, the caller (service
   or user, not raw credentials), the outcome, the duration, and *the decision
   taken* (which branch, which fallback, which cache path) — not the full
   request/response body. The decision is what a future reader needs; the body
   is what makes the log line a PII/size liability.
   *Enforced by:* review — a boundary log call passing a whole request/response
   object is rejected.

5. **No PII in logs, metrics labels, or trace attributes, ever.** Same
   catalogue as `pii-compliance` in `scripts/data/edge_cases_infra.json`
   (plaintext PII in logs is its first entry) — referenced, not restated here.
   *Enforced by:* `grep -rniE "(email|phone|ssn|password|token)\s*[:=]" <diff>`
   inside a log/metric/span call is flagged for review.

6. **Choose the SLI from the user's experience, not the server's internals.**
   "P99 request latency at the load balancer" beats "average handler execution
   time" — the second hides queueing, retries, and everything upstream of the
   handler that the user actually waits through. Use percentiles, never
   averages: an average of {10ms × 999, 10000ms × 1} is ~20ms and hides the one
   user who waited 10 seconds; p99 does not. p50 lies for the same reason in
   the other direction — it describes the median user, not the one filing the
   complaint. Percentile math requires a histogram, not a summary of individual
   samples, because only a bucketed histogram can be aggregated across
   instances after the fact (`prometheus_quantile()` operates on `_bucket`
   series for exactly this reason — see Sources).
   *Enforced by:* `grep -rniE "\bavg\(|average" <diff>` on anything named as an
   SLI is flagged for review.

7. **Alert on symptoms, not causes, and every alert names its action.** Page
   on "checkout error rate > 1% for 5m" (a symptom the user feels), not on "CPU
   > 80%" (a cause that may or may not matter). If an alert fires and there is
   no documented next step, it is not an alert, it is noise that trains people
   to ignore the pager — a non-actionable alert is measurably worse than no
   alert, because it burns the signal budget the real page needs.
   *Enforced by:* review — an alert rule with no linked runbook/action is
   rejected.

8. **The two-minute debuggability test.** Given one failed request, can you
   answer "which request, which user, which version" in under two minutes
   using only what's already instrumented? If the answer requires SSHing into
   a box or guessing at a deploy timestamp, the boundary logging (rule 4) and
   correlation-id propagation (rule 3) are incomplete. Run this test at design
   time, before the code that would need it ships.
   *Enforced by:* review — a new endpoint/job with no way to answer this from
   its own logs/traces fails design review.

9. **Sampling and retention are design decisions, sized to a real budget.**
   Observability is routinely a top-3 cloud line item; "keep 100% of traces
   forever" is not a default, it's an unbudgeted decision. Decide the sampling
   rate (and whether errors/slow requests are always kept regardless of the
   base rate) and the retention window explicitly, and record it like any
   other decision that departs from "just turn everything on".
   *Enforced by:* `python3 scripts/decide.py new "Sampling/retention policy" --affects "<glob>" --tag observability`

## Verify

```bash
# 1. metric/log calls with a high-cardinality label (user id, email, raw url)
grep -rnE "\.(label|tag|with_label)s?\(" src/ 2>/dev/null \
  | grep -iE "user.?id|email|request.?id|session.?id|raw.?url"

# 2. unstructured logging where a structured logger is already in use
grep -rnE "console\.log\(|print\(" src/ 2>/dev/null

# 3. PII-shaped fields going into a log/metric/span call
grep -rniE "(email|phone|ssn|password|token)\s*[:=]" src/ 2>/dev/null

# 4. an SLI defined as an average instead of a percentile
grep -rniE "\bavg\(|average" src/ docs/ specs/ 2>/dev/null | grep -i "sli\|latency\|slo"

# 5. record the sampling/retention decision once it's made
python3 scripts/decide.py new "Sampling/retention policy" --affects "src/telemetry/**" --tag observability
python3 scripts/decide.py verify   # confirms the assumption still holds later
```
Each grep is diff-scoped in practice (point at `git diff --name-only`) and runs
in under a second; step 5 is a few seconds and is what makes the sampling
decision reviewable later instead of forgotten.

## Failure modes

This skill rejects:

- **A metric labeled with a user id, email, session id, or raw URL** — the
  exact mechanism `kestra-io/kestra`'s guideline exists to prevent: "every
  unique label-value combination is a separate time series."
- **An SLI reported as an average** — hides the tail the SLO is supposed to
  protect; a 1-in-1000 ten-second request disappears into a 20ms average.
- **A cause-based alert with no user-facing symptom and no linked action** —
  "CPU high" pages someone who then has to reverse-engineer whether it matters.
- **A boundary log call that dumps the full request/response body** instead of
  outcome + duration + decision — a PII liability and a needle-in-a-haystack
  for the reader who actually needed one field.
- **A trace/log with no correlation id**, making "which request was this" an
  unanswerable question the moment there's concurrent traffic.
- **"We'll add the metric/log/trace once we see what breaks"** — the thesis
  this whole skill exists to reject; the two-minute debuggability test (rule 8)
  is failed at design time, deliberately, before it's failed in an incident.
- **100%-sample, forever-retention as an unexamined default** — an unbudgeted
  cost decision wearing the shape of "just being thorough".

## Scale

`solo`: rules 3 (structured logs with a correlation id) and 5 (no PII) — cheap
from the first line of code, and the two-minute test (rule 8) still applies
even with one engineer, because that engineer is asleep half the time too.
`small-team (2-10)`: add 2 (cardinality budget before the first label-heavy
metric ships), 4 (boundary logging convention as a team-wide pattern, not
per-service taste), 7 (symptom-based alerts before the pager rotation starts).
`org (10+)`: add 6 (a written SLI/SLO per user-facing surface — the corpus
finding is that essentially nobody does this in-repo, so writing it down is
already ahead of median) and 9 (sampling/retention as a reviewed budget line,
not an ops afterthought).
`high-blast-radius`: full OTel semantic-convention adherence across every
service so traces correlate cross-team without a translation layer, and an
error-budget policy with a defined consequence (feature freeze, rollback
trigger) when it's spent — not just a number nobody acts on.

## Sources
- The cardinality-collapse mechanism and the `.total`-suffix metric-naming
  convention ("Every Counter — without exception — MUST end in `.total`...
  Keep cardinality bounded. Every unique label-value combination is a separate
  time series. Avoid labels that take user-controlled or unbounded values"):
  `kestra-io/kestra@c30e361:docs/architecture/METRICS_GUIDELINES.md`, via
  `research/35-findings-security-reliability.md` ("Observability conventions").
  **Also recorded there as an absence**: no repo in the 33-repo corpus has a
  numeric SLO/error-budget document as a first-class file, and no deep-read
  repo has an explicit OTel adoption/naming document — this skill exists
  because that gap is real, not assumed.
- Attribute naming rules (lowercase, dot-namespaced, snake_case per segment,
  no name reuse) and `error.type`'s explicit cardinality requirement ("SHOULD
  be predictable, and SHOULD have low cardinality"):
  `open-telemetry/semantic-conventions@main:docs/general/naming.md`,
  `docs/registry/attributes/error.md`. Concrete attribute names for boundary
  logging/tracing (`server.address`, `server.port`, `messaging.destination.name`,
  `messaging.message.id`, `messaging.consumer.group.name`):
  `docs/general/attributes.md`, `docs/registry/attributes/messaging.md`.
  **Tension worth noting:** OTel's own metric-naming guidance says counters
  "SHOULD NOT append `_total`" (confusing in delta backends), the opposite of
  kestra's Prometheus-context rule above — both are correct in their own
  ecosystem; the transferable idea is *pick one suffix convention and enforce
  it*, not which suffix. (Note: the semantic conventions moved out of
  `open-telemetry/opentelemetry-specification`, which now 404s for these paths,
  into `open-telemetry/semantic-conventions` — cited at its current location,
  and the move itself is recorded as a finding.)
- Percentile aggregation requiring a bucketed histogram, not an average or a
  per-instance summary: `histogram_quantile()` operates on `_bucket` series
  with an `le` label and requires `sum by (...)` across instances before
  quantile computation — averages and per-node summaries cannot be recombined
  this way: `prometheus/prometheus@main:docs/querying/functions.md`.
  `google/sre-book` was checked and is not resolvable as a GitHub repo (404) —
  recorded as an absence per the rubric rather than cited from memory.
- Timeout/retry/circuit-breaking material referenced, not repeated, from
  `research/35-findings-security-reliability.md` ("Resilience patterns");
  companion skill `distributed-correctness` covers the correctness side of the
  same boundary.
- `pii-compliance`, `notification`, `webhook`, `third-party-api` kinds (log/
  metric/trace-visible failure scenarios): `scripts/data/edge_cases_infra.json`,
  `SOURCE: original`.
