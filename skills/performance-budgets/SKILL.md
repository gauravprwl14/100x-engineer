---
name: performance-budgets
description: >
  Use before designing or reviewing anything with a request/response shape, a
  loop that touches a database or network, a new cache, a connection pool, or a
  capacity question — an endpoint, a query, a batch job, a fan-out call, a cache
  layer. Covers latency budgets split across a call chain, p95/p99 over
  averages, back-of-envelope estimation, the N+1 family, query cost and
  EXPLAIN, pagination as correctness, cache invalidation cost, capacity
  headroom, connection pools, and load/soak/spike testing. Not for bundle-byte
  or binary-byte budgets (see typescript-verification, mobile-release-safety)
  and not for choosing an implementation approach (see approach-selection).
  Use PROACTIVELY whenever asked "is this fast enough" or "will this scale."
---

# Performance and capacity

Bundle-byte and binary-byte budgets are owned elsewhere in this plugin
(`typescript-verification` rule 6, `mobile-release-safety` rule 7) and this skill
does not repeat them. What's missing across the corpus this plugin studied is the
other half of "will this survive production": **latency budgets, query cost, and
capacity arithmetic**. `research/30-findings-js-verification.md` found a bundle-size
budget in 2 of 72 JS repos; `research/33-findings-mobile-verification.md` found 0 of
31 mobile repos enforce a byte budget in CI at all. If bytes are this rare, latency
and capacity reasoning — which no CI check can even approximate — is rarer still,
and it's the harder half. This skill is a required *reasoning step*, not a metric to
budget, because most of it cannot be reduced to a number a script can check.

## Trigger

**Fire when:** designing or reviewing an endpoint, a query against a table with
real row counts, a loop that calls a DB/service per item, a new outbound HTTP/RPC
call, a cache, a connection pool, or a capacity/cost question ("is 400ms ok?",
"will this handle 10x traffic?"); setting up load/soak/spike testing.

**Do not fire when:** a pure refactor with no new I/O and no behavior change; a
UI-only change with no data fetching; doc/config edits with no runtime path.

## Rules

1. State a latency budget before writing code: one total user-visible number
   (state the percentile) split across every hop in the call chain, with each
   hop's share named. Without a total, "is 400ms ok?" is unanswerable and every
   hop silently assumes it owns the whole budget.
   *Enforced by:* review

2. Reason and report in percentiles — p95/p99 — never the mean. p50 lies at
   fan-out: one slow dependency in a 10-call fan-out makes most requests slow,
   not one in ten.
   *Enforced by:* review

3. Do the back-of-envelope arithmetic before a design is final — requests/sec,
   payload size, rows scanned, bytes egressed, storage growth per month — and
   write the numbers down where the design lives. A design whose arithmetic was
   never done is a guess wearing a diagram.
   *Enforced by:* convention

4. Never leave an `await`, a DB call, or an HTTP call running once per iteration
   of a loop with no batching, prefetching, or gathering. This is the N+1 family:
   an ORM's lazy relation and a hand-written `for x in items: call_service(x)`
   are the same bug.
   *Enforced by:* `python3 scripts/perf_check.py --only n-plus-one`

5. Run `EXPLAIN` on any new query against a table that isn't trivially small,
   before merge. A sequential scan is free at 10k rows (fits in cache) and an
   outage at 10M (real disk I/O, held locks, time scaling with row count).
   *Enforced by:* review

6. Bound every list query — `LIMIT`/`take`/`first` — and remember an index has a
   write cost, so don't add one to speed up a query nothing calls.
   *Enforced by:* `python3 scripts/perf_check.py --only unbounded-query`

7. Treat an endpoint with no pagination limit as a correctness bug, not a
   performance nit. It is a latent outage waiting for the table to grow, and
   "sort in application code after an unbounded fetch" is the same bug wearing
   a different hat.
   *Enforced by:* `python3 scripts/perf_check.py --only unbounded-query,hot-path-sort`

8. Never `SELECT *` in application code or a migration. It fetches columns
   nobody asked for and breaks silently when a column is added or renamed.
   *Enforced by:* `python3 scripts/perf_check.py --only select-star`

9. Give every outbound HTTP/RPC call an explicit timeout. An unstated timeout is
   a contract the client library invents for you — Envoy's own default is 5s;
   yours might not be.
   *Enforced by:* `python3 scripts/perf_check.py --only no-timeout`

10. Cap concurrency on any fan-out (`Promise.all`/`asyncio.gather`) and cap any
    in-memory accumulation over a query-result loop. Unbounded either one turns
    one large input into an outage, not a slow response.
    *Enforced by:* `python3 scripts/perf_check.py --only unbounded-concurrency,unbounded-accumulation`

11. Treat caching as a decision with an invalidation cost, not a default. State
    the hit-rate assumption, and state what happens at 0% hit rate — cold start,
    right after a deploy, every cache is empty and the backend eats full load.
    *Enforced by:* convention

12. Before load-testing, know which resource saturates first as load grows 10x
    — CPU, memory, connections, IOPS, file descriptors, or a thread pool — and
    name it. "It got slow" is not a finding; "the connection pool hit its ceiling
    at 40 req/s" is.
    *Enforced by:* convention

13. Size connection pools deliberately; they are a common invisible ceiling.
    Bigger is not safer — a real benchmark reducing an oversized pool cut
    response time 50x (see `reviewers/_latency-numbers.md`) with no other change,
    because contention past the DB's real parallelism costs more than it buys.
    *Enforced by:* review

14. Run load, soak, and spike tests for different reasons and don't substitute
    one for another. Load = sustained target throughput. Soak = the same load
    held for hours, to catch leaks and slow degradation a short run can't show.
    Spike = a sudden multiple of normal traffic, to see what saturates first and
    whether it recovers.
    *Enforced by:* review

15. Put cost-per-request next to latency in any capacity review, and check
    observability spend specifically — logs, traces, and metrics cardinality are
    often a top-3 cloud line item on their own, not a rounding error.
    *Enforced by:* review

16. Don't optimise without a measurement, a stated budget, and a position on the
    critical path. Profile first, then fix the thing the profile names — a
    hot-path micro-optimisation applied on a hunch, to code nothing measured, is
    the same failure mode as skipping performance work entirely: effort spent
    with no evidence it mattered.
    *Enforced by:* review

## Verify

Diff-scoped; runs in well under a second on a typical PR.

```bash
# the mechanical half -- structural shapes only a script can reliably catch
python3 scripts/perf_check.py --list
python3 scripts/perf_check.py --base origin/main
python3 scripts/perf_check.py --base origin/main --strict   # treat advisories as failures too

# just the blocking checks (N+1, missing timeouts)
python3 scripts/perf_check.py --only n-plus-one,no-timeout

# the reasoning half -- no command exists for this by design; the numbers below
# are what "is this ok" gets checked against
cat reviewers/_latency-numbers.md
```

`perf_check.py` is heuristic, not exhaustive, and says so in its own docstring:
**Python checks parse the real syntax tree (`ast`)**; **TS/JS checks are regex plus
brace/paren-balancing** (no stdlib JS parser exists). Both discard any match whose
line the current diff didn't actually touch, so a pre-existing pattern elsewhere in
the file never surfaces. `n-plus-one` and `no-timeout` are blocking; the rest are
advisory because they need a human to confirm the call site is actually a hot path.

## Failure modes

This skill rejects:

- **"Is 400ms ok?" with no stated total or hop split.** Unanswerable without rule 1;
  every hop will assume it owns the whole budget and the sum will blow it.
- **A latency claim that's secretly p50.** "It's fast, 90ms average" while p99 is
  2s is the canonical way a fan-out service looks healthy in a dashboard and isn't.
- **A design merged with no back-of-envelope math** for a system taking real
  traffic — no requests/sec, no row-count estimate, no storage-growth number.
- **A loop making one DB or HTTP call per row** — Django's `entry.blog` lazy
  relation and a hand-rolled `for id in ids: requests.get(...)` are the same bug;
  see `django/django:docs/ref/models/querysets.txt` for the canonical illustration.
- **A new query on a large table merged with no `EXPLAIN`.**
- **An endpoint that returns "all rows."** It works in dev with 12 rows and pages
  the on-call engineer in production with 12 million.
- **`SELECT *`** in a migration or application code.
- **A new `requests.get(url)` / `fetch(url)` with no timeout argument.**
- **`Promise.all(items.map(...))` over a collection with no size bound.**
- **A cache added with no stated hit-rate assumption and no answer for 0%.**
- **Micro-optimising code nobody profiled**, off the critical path, with no
  measurement — this skill rejects premature optimisation exactly as hard as it
  rejects skipping performance work; both spend effort with no evidence attached.

**Honest limitations:** `perf_check.py` cannot tell a hot path from a cold one, so
several checks are advisory by design and need a human to confirm blast radius.
It also cannot verify rule 1, 2, 3, 11, 12, 14, or 15 mechanically — no script can
read a PR description and confirm a budget was actually reasoned about, only that
one is present. That gap is real; it is why this skill leans on `review` more than
most others in this plugin.

## Scale

`solo`: rules 1, 2, 4, 6, 8, 9 — free or near-free, and rules 4/6/8/9 are fully
mechanical via `perf_check.py`.
`small-team (2-10)`: add 3, 5, 10, 13 — back-of-envelope math and `EXPLAIN` start
paying for themselves once more than one person touches the query layer.
`org` / `high-blast-radius`: add 7, 11, 12, 14, 15, 16 and a numeric capacity/soak
regime. DuckDuckGo Android's canary is 0.0001% before a wider rollout
(`mobile-release-safety` Sources) — that's the shape of org-scale caution, applied
here to capacity headroom instead of a mobile rollout ladder.

## Sources

- Latency/capacity numbers and full citations: `reviewers/_latency-numbers.md`.
- N+1 canonical illustration: `django/django@main:docs/ref/models/querysets.txt`
  (`select_related`/`prefetch_related`, "Hits the database again to get the
  related Blog object").
- `EXPLAIN`, full scan vs. index:
  `cockroachdb/docs@main:src/current/v24.1/sql-tuning-with-explain.md`.
- Query timeout defaults: `apache/superset@master:docs/docs/faq.mdx`.
- Connection/timeout/retry defaults and "retry budget is a subset of the deadline,
  not additive": `envoyproxy/envoy@main:api/envoy/config/cluster/v3/circuit_breaker.proto`,
  `cluster.proto`, `docs/root/configuration/http/http_filters/router_filter.rst` —
  also read previously in `research/35-findings-security-reliability.md`.
- Connection pool sizing formula and the 50x oversized-pool measurement:
  `brettwooldridge/HikariCP.wiki:About-Pool-Sizing.md`.
- Capacity/storage-growth arithmetic: `prometheus/prometheus@main:docs/storage.md`.
- Bundle-byte and binary-byte budgets, owned elsewhere and not duplicated here:
  `skills/typescript-verification/SKILL.md` rule 6 (`TanStack/table` 30KB
  `size-limit` on `table-core` — 2 of 72 JS repos have any budget at all) and
  `skills/mobile-release-safety/SKILL.md` rule 7 (0 of 31 mobile repos have a hard
  byte gate).
- `perf_check.py`'s check shapes: `SOURCE: original`, built to detect the failure
  classes named in this skill's Rules and Failure modes, informed by the AI-agent
  bloat patterns catalogued in `research/23-findings-antibloat-enforcement.md` and
  `research/36-findings-antibloat-in-practice.md`.
