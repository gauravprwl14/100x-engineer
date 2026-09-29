---
name: distributed-correctness
description: >
  Use when designing or reviewing anything that crosses a network boundary more
  than once for one logical operation — a service calling another service, a DB
  write paired with an event/webhook/notification, a queue consumer, a retry, a
  timeout, a cache, a fan-out to multiple downstreams, or any code that compares
  timestamps from different machines. Covers idempotency, the dual-write/outbox
  problem, ordering, sagas, retry and timeout budgets, backpressure, clock
  hazards, consistency bounds, and cache correctness. Use PROACTIVELY before
  writing an integration, a queue consumer, a webhook sender/receiver, or a
  multi-step write, and during review of any diff that adds a retry, a timeout,
  or a second write derived from a first one.
---

# Distributed correctness

Every rule below exists because a single-machine mental model was applied to code
that runs across a network. `research/35-findings-security-reliability.md`
already covers the resilience mechanics in depth (Envoy's retry/circuit-breaking/
outlier-detection config, the timeout-budget rule, kestra's metrics-cardinality
rule) — this skill builds on that and does not repeat it; it adds the correctness
half: what makes a distributed write, delivery, or read actually right, not just
resilient.

## Trigger

**Fire when:** the change adds a call to another service or process, a DB write
alongside a publish/notify/webhook, a queue consumer, a cache, a retry or
timeout, a scheduled/batch job touching shared state, or any comparison of
timestamps from different machines.

**Do not fire when:** the change is entirely in-process with one durable store
and no network hop — there is no distribution to be incorrect about. For the
feature-kind edge cases this generates, scaffold with
`python3 scripts/plan_feature.py new <name> --kind <kinds>` — kinds `queue`,
`cache`, `webhook`, `third-party-api`, `cron`, `batch-job` in
`scripts/data/edge_cases_infra.json` seed the scenarios below automatically.

## Rules

1. **"Exactly-once" is marketing.** No transport guarantees a message is
   processed exactly once across an untrusted network — only *effectively*
   once, via at-least-once delivery plus an idempotent consumer. Say "at-least-
   once + idempotent" in the design, never "exactly-once".
   *Enforced by:* `grep -rniE "exactly.once" <spec-or-diff>` — a hit that isn't
   immediately followed by naming the dedup mechanism is rejected in review.

2. **Idempotency key covers the request body, not just the route.** Derive the
   key from a hash of method + route + body (or a client-supplied key stored
   alongside the result), store it with a TTL past the client's retry window,
   and on replay return the *original recorded response*, not reprocess. A
   route-only key collides two different bodies; a too-short TTL lets a slow
   retry reprocess.
   *Enforced by:* review — the audit's `payment`/`queue` edge cases in
   `scripts/data/edge_cases.json` and `edge_cases_infra.json` require a named
   test for this, which forces the design question.

3. **The dual-write problem: a DB write and a publish are not one transaction.**
   `db.save(x); bus.publish(x)` loses the event on a crash between the two
   calls, or publishes for a transaction that later rolls back. Three real
   fixes, pick one explicitly: (a) **outbox** — write the event row in the same
   DB transaction as the business write, relay it asynchronously; (b) **CDC** —
   stream the DB's own change log (e.g. a Debezium-style connector) so the
   event is derived from committed data, never authored separately; (c)
   **accept loss, add reconciliation** — publish best-effort, run a scheduled
   job that detects and repairs drift. "We'll just publish after the commit" is
   none of these and is the bug.
   *Enforced by:* review — reject a diff with a business write and a publish
   in different transactions and no reconciliation job named.

4. **Order per key, not globally.** Global ordering needs one partition/queue
   for everything, which caps throughput at one consumer's speed and creates a
   single point of contention nobody asked for. Order within a partition key
   (user id, order id, aggregate id) and design the rest of the system to not
   care about cross-key order. Partitioning buys parallelism; it costs hot-key
   skew when one key gets disproportionate traffic.
   *Enforced by:* review

5. **A saga's compensating action is itself fallible.** A distributed
   transaction across services doesn't exist; a saga — a sequence of local
   transactions each with a compensating action — does, and the compensation
   must be retried and made idempotent exactly like the forward action, not
   assumed to always succeed.
   *Enforced by:* `grep -rniE "compensat|rollback" <diff>` — a compensating
   function with no retry/error handling nearby is rejected.

6. **Retry discipline: classify, jitter, cap, budget.** Only retry errors that
   mean "the server didn't process this" (timeouts, 503, connection reset) —
   not errors that mean "it did, and rejected it" (400, most 409s). Apply
   jittered backoff, cap attempts, and declare a retry *budget* (a token bucket,
   not just a per-call cap) so a downstream blip can't be amplified into an
   outage by every caller retrying at once — see Sources for the concrete
   token-bucket parameters from grpc and AWS's SDKs.
   *Enforced by:* `grep -rnE "retry|backoff" <diff> -l | xargs grep -L "jitter"`
   flags retry code with no jitter for review.

7. **A timeout longer than the caller's own deadline is a bug.** Set connect,
   read, and total timeouts explicitly on every outbound call; the sum of a
   call chain's timeouts must fit inside the top-level caller's deadline, and a
   retry's backoff must come *out of* that budget, not add to it (Envoy's rule,
   `research/35-findings-security-reliability.md`: "the route timeout...
   includes all retries").
   *Enforced by:* `grep -rnE "(axios|fetch\(|http\.request|requests\.(get|post|put)|httpx\.)\(" <diff> | grep -v "timeout"`

8. **Backpressure and load shedding: queue depth is latency, not a buffer.**
   An unbounded queue in front of a slow consumer doesn't absorb load, it
   converts overload into unbounded latency for everyone behind the pile-up.
   Shed early (reject at the edge once a depth/age threshold is crossed) and
   deliberately (a named policy — reject newest, reject oldest, degrade), not
   "it'll drain eventually".
   *Enforced by:* review — a queue with no depth/age alarm and no shed policy
   is rejected.

9. **Never order events by wall-clock time across machines.** Two machines'
   clocks are never exactly in sync; a wall-clock tie-break silently picks the
   wrong winner under skew, and both DST transitions and leap seconds are real,
   recorded incident causes, not theoretical. Use a monotonic clock for
   duration measurement and a logical/hybrid-logical clock or a sequence number
   for cross-machine ordering (CockroachDB's HLC is the production reference —
   see Sources).
   *Enforced by:* `grep -rnE "(Date\.now\(\)|time\.time\(\)|System\.currentTimeMillis)" <diff>`
   used as a sort key or tie-break across services is rejected in review.

10. **Eventual consistency needs a stated bound, and the author always reads
    their own write.** "Eventually consistent" with no number is not a design,
    it's a shrug. Name the bound (seconds, or "read-through on the author's own
    session") so a caller can decide whether to wait, poll, or read-your-writes.
    *Enforced by:* review — a spec's consistency claim with no bound is
    rejected.

11. **Cache is never the source of truth.** Pick invalidate-on-write,
    TTL-with-a-stated-staleness-window, or write-through, explicitly — not by
    default. Guard against thundering herd (a jittered TTL or a single-flight
    lock around recompute) and stale-while-revalidate where staleness is
    acceptable. The classic error is a cache whose eviction under memory
    pressure loses data nothing else holds.
    *Enforced by:* `grep -rn "cache\.\(set\|put\)" <diff>` with no matching
    invalidation call nearby is flagged for review; see the `cache` kind in
    `scripts/data/edge_cases_infra.json` for the seeded scenarios.

12. **State what the caller sees on partial fan-out failure.** When a request
    triggers N downstream calls and M < N succeed, the caller-visible contract
    must be named: all-or-nothing (compensate the M), partial-success-with-a-
    per-item-status, or best-effort-with-reporting. A bare `200 OK` when 3 of 5
    succeeded is a silent data-loss bug wearing a success response.
    *Enforced by:* a named test asserting the partial-success response shape,
    required by the `queue`/`webhook`/`notification` edge cases in
    `edge_cases_infra.json`.

## Verify

```bash
# 1. does the design claim "exactly-once" without naming a dedup mechanism?
grep -rniE "exactly.once" specs/<name>/spec.md 2>/dev/null

# 2. every outbound client call sets an explicit timeout
grep -rnE "(axios|fetch\(|http\.request|requests\.(get|post|put)|httpx\.)\(" src/ \
  | grep -v "timeout"

# 3. retry code declares jitter, not a bare loop
grep -rlE "retry|backoff" src/ 2>/dev/null | xargs -r grep -L "jitter"

# 4. wall-clock time used as a cross-machine ordering/tie-break key
grep -rnE "(Date\.now\(\)|time\.time\(\)|System\.currentTimeMillis)" src/ | grep -i "sort\|order\|compare"

# 5. scaffold the spec for this domain -- seeds queue/cache/webhook/third-party
#    edge cases (idempotency, ordering, backpressure, outbox) before code exists
python3 scripts/plan_feature.py new order-events --kind queue,integration
python3 scripts/plan_feature.py audit specs/order-events   # exits 1 until every case resolves
```
Point greps at `git diff --name-only` output rather than the whole tree; each
runs in under a second. Step 5 is the one that actually gates.

## Failure modes

This skill rejects:

- **A design doc or PR description claiming "exactly-once delivery"** with no
  idempotency key named — the two most common resulting bugs are a duplicate
  charge/send, or (the less-caught direction) a key built from the route alone
  silently merging two different request bodies into one result.
- **`db.save(x); bus.publish(x)`** in two separate transactions/connections
  with no outbox table, no CDC, and no reconciliation job — the event is lost
  on any crash between the two lines and nothing ever notices.
- **A saga step with a compensating action that has no retry or error path** —
  "undo the charge" written as a single best-effort call that, if it fails,
  leaves the system in the half-completed state the saga existed to prevent.
- **A timeout that is absent, or longer than the caller's own deadline** — the
  request hangs past when the caller already gave up, holding a connection/
  thread the whole time.
- **An unbounded queue with no depth alarm** — "the consumer will catch up" is
  what's said right before the queue-depth graph goes vertical.
- **A cache with no stated invalidation strategy** that becomes the de facto
  source of truth — delete the underlying row and the UI still shows it forever.
- **`200 OK` from a fan-out where 3 of 5 downstream calls actually failed** —
  the caller has no way to know which two didn't happen.

## Scale

`solo`: rules 2, 7 (idempotency key, explicit timeouts) — cheap even alone.
`small-team (2-10)`: add 3 (outbox once any publish sits next to a DB write),
6 (retry classification + budget), 11 (named cache invalidation strategy).
`org (10+)`: add 5 (cross-team sagas), 4 (deliberate partition-key ordering),
9 (clock/ordering-hazard review before multi-region).
`high-blast-radius`: 10's bound becomes a published SLA; 8's shed policy is
load-tested, not assumed; rule 3's three fixes are enforced in design review,
never a two-phase commit across services.

## Sources
- Retry/timeout-budget mechanics (jittered backoff, "route timeout includes
  all retries", circuit breaking as a count limiter not a state machine,
  active vs passive outlier detection) and the kestra cardinality convention
  used in the companion skill: `research/35-findings-security-reliability.md`
  ("Resilience patterns", "Observability conventions") — built on, not repeated.
- Retry policy fields (`maxAttempts`, `initialBackoff`, `maxBackoff`,
  `backoffMultiplier`), ±0.2 jitter, deadline spans every attempt, retry
  throttling as a token bucket (`maxTokens`/`tokenRatio`), and "it is up to the
  service owner to pick the correct set of retryable status codes... gRPC
  retries do not provide a mechanism to specifically mark a method as
  idempotent": `grpc/proposal@master:A6-client-retries.md`.
- Retry token-bucket defaults (`DefaultMaxAttempts=3`, `DefaultMaxBackoff=20s`,
  `DefaultRetryRateTokens=500`, `DefaultRetryCost=5`,
  `DefaultRetryableHTTPStatusCodes={500,502,503,504}` — AWS treats 500 as
  retryable where gRPC's own example treats only `UNAVAILABLE`, underscoring
  rule 6: the retryable set is a judgement call, not a universal list):
  `aws/aws-sdk-go-v2@main:aws/retry/standard.go`.
- Idempotency-key-at-scale in production: Temporal's Workflow ID *is* the
  idempotency key; `WorkflowIdReusePolicy` (`ALLOW_DUPLICATE` /
  `ALLOW_DUPLICATE_FAILED_ONLY` / `REJECT_DUPLICATE`) is literally "what a
  replay returns": `temporalio/api@master:temporal/api/enums/v1/workflow.proto`.
- The outbox pattern realized in production: Temporal's history-service state
  transition appends to durable History **and** creates the next Transfer/
  Timer Task in one transition, with a monotonic `RangeID` fencing token
  against a stale former shard-owner: `temporalio/temporal@main:docs/architecture/history-service.md`.
  **Absence, per the rubric:** Saga/compensation is documented at the
  SDK/samples layer, not in the server repo — cited here for the
  durable-execution substrate sagas run on, not the saga pattern itself.
- Clock hazards: an HLC with an explicit `toleratedOffset` beyond which the
  node self-terminates, and a `monotonicityErrorsCount` for backward jumps:
  `cockroachdb/cockroach@master:pkg/util/hlc/hlc.go`.
- Cache-key scoping (a `Vary`-header allowlist controls what varies the cached
  entry, at insertion and lookup) as production shape for "the key must cover
  everything that changes the value": `envoyproxy/envoy@main:api/envoy/extensions/filters/http/cache/v3/cache.proto`.
- `realtime`/`integration`/`payment` already cover reconnect-ordering-
  backpressure-authz, outage-retry-secret-rotation-contract-drift, and charge-
  idempotency-webhook-refund — referenced, not restated: `scripts/data/edge_cases.json`.
  Component-keyed additions (`queue`, `cache`, `webhook`, `third-party-api`,
  `cron`, `batch-job`, `multi-tenancy`, `pii-compliance`, `file-storage`,
  `notification`): `scripts/data/edge_cases_infra.json`, `SOURCE: original`.
