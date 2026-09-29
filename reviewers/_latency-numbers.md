# Latency numbers every engineer should reason from

The back-of-envelope table every senior engineer has half-memorized. It exists so
"is 400ms ok?" gets answered with arithmetic instead of a vibe. Labels follow
`reviewers/_evidence-labels.md`: `Verified` means read directly in a cited source
(file:line or quoted text); `Inferred` means derived from a verified figure, not
itself measured; `Added` means a standard, checkable fact (a protocol spec, a
well-known convention) not pulled from the repos studied here; `Uncertain` means a
real number exists but this session could not pin a citable current source for it
— stated rather than invented. Used by `skills/performance-budgets/SKILL.md`.

## Hardware, memory, storage

Values below are computed from the year-parameterized model in
`colin-scott/interactive_latencies@master:interactive_latency.html`, itself an
extrapolation of Jeff Dean's original figures as republished in Peter Norvig's
"Teach Yourself Programming in Ten Years" (the file's own header credits this
lineage). Snapshot year: **2024**, stated because most of these move.

| operation | latency | basis | label |
|---|---|---|---|
| L1 cache reference | ~1 ns | 3 cycles at 3GHz (clock speed plateaued ~2005) | `Verified` |
| Branch mispredict | ~3 ns | 10 cycles | `Verified` |
| L2 cache reference | ~4 ns | 13 cycles | `Verified` |
| Mutex lock/unlock | ~17 ns | 50 cycles | `Verified` |
| Main memory reference | 100 ns | plateaued since ~2000 | `Verified` |
| SSD random read | ~16 µs | plateaued since ~2014 | `Verified` |
| Disk seek (spinning disk) | ~1.9 ms | halves every ~10 yrs from a 10ms/2000 baseline | `Verified` |

**Deliberately excluded**: the same model's *sequential-transfer* (bandwidth)
figures for SSD/disk/NIC in 1MB-per-request terms. Checked directly: extrapolating
2012-era SSD bandwidth (3GB/s, doubling every 3 years) forward to 2024 predicts
~48GB/s sequential SSD throughput — well above real 2024 NVMe hardware (commonly
~2–7GB/s). The exponential-doubling assumption held for CPU/memory *latency* far
longer than it held for *bandwidth*. This is the clearest illustration in this
table of why these numbers age badly: the formula didn't break, its assumption did.
For a real order-of-magnitude figure instead: a modern NVMe SSD reads 1MB
sequentially in roughly 150µs–500µs, and a datacenter NIC (10–100Gbps) moves 1MB
in tens of microseconds — both `Added`, common-knowledge figures, not derived from
the model above.

## Network

| operation | latency | basis | label |
|---|---|---|---|
| Round trip, same datacenter | ~0.5 ms | held constant in the model since ~2012 | `Verified` |
| Round trip, cross-region / WAN | ~150 ms | held constant; bounded by speed of light | `Verified` |
| TLS 1.3 full handshake | 1 network RTT (0-RTT if resumed) | protocol spec, RFC 8446 | `Added` |
| TLS 1.2 full handshake | 2 network RTTs | protocol spec, RFC 5246 | `Added` |
| Cache hit (same-DC, e.g. Redis GET) | ~0.5–1 ms | dominated by the same-DC RTT above + microsecond-scale lookup | `Inferred` |
| "Reasonable" HTTP request-duration range | 5 ms – 10 s | Prometheus client's default histogram buckets — a convention for what's worth distinguishing, not a measured p50/p99 | `Verified` |
| Cold serverless function start | tens of ms (light runtime) to several seconds (JVM/large image, VPC-attached) | widely reported, highly variable by runtime/memory/network config | `Uncertain` — no citable primary benchmark source located this session |

Sources for the two `Verified` network rows and the histogram-bucket row:
`colin-scott/interactive_latencies@master:interactive_latency.html` (`getDCRTT`,
`getWanRTT`) and `prometheus/client_golang@main:prometheus/histogram.go:271`
(`DefBuckets = []float64{.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10}`).

## Database

| claim | mechanism | label |
|---|---|---|
| Indexed lookup vs. full table scan | index lookup is ~O(log n) plus a constant; a scan without a matching index is O(n) rows read | `Verified` — `cockroachdb/docs@main:src/current/v24.1/sql-tuning-with-explain.md` (`EXPLAIN` shows `spans: FULL SCAN` vs. an index join) |
| "Fine at 10k rows, fatal at 10M" | same O(n) scan: 10k rows likely fits in cache/memory (sub-ms to low-ms); 10M rows means real disk I/O, held locks, and query time scaling roughly linearly with row count | `Inferred` — no absolute-ms figure is published anywhere citable; this is the scaling argument, not a benchmark number |
| An index has a write cost | every insert/update maintains every index on the row, not just the table | `Added` — standard relational-database fact |

## Connections, concurrency, capacity

| claim | number | label |
|---|---|---|
| Connection pool sizing (starting point) | `connections = (core_count * 2) + effective_spindle_count` | `Verified` — `brettwooldridge/HikariCP.wiki:About-Pool-Sizing.md` |
| Oversized pool cost, measured | reducing an oversized pool alone took response time from ~100ms to ~2ms — a 50x improvement, no other change | `Verified` — same doc, describing a public Oracle demo |
| Deadlock-avoidance pool floor | `pool size = T_n × (C_m − 1) + 1` for `T_n` threads each needing `C_m` connections | `Verified` — same doc |
| Per-cluster connection/request ceiling, a real default | `max_connections`, `max_pending_requests`, `max_requests` each default to **1024**; `max_retries` defaults to **3** | `Verified` — `envoyproxy/envoy@main:api/envoy/config/cluster/v3/circuit_breaker.proto` |
| Connect timeout, a real default | **5s** if unset | `Verified` — `envoyproxy/envoy@main:api/envoy/config/cluster/v3/cluster.proto:902` |
| Retry backoff, a real default | fully-jittered exponential, 25ms base, capped at 250ms (10x base) | `Verified` — `envoyproxy/envoy@main:docs/root/configuration/http/http_filters/router_filter.rst` |
| Retry budget is a subset of the deadline, not additive | "the route timeout... includes all retries" | `Verified` — same doc; this is the transferable rule, not just the number |
| SQL async query timeout, a real default | 6 hours (`SQLLAB_ASYNC_TIME_LIMIT_SEC`); dashboard client-side timeout 60s | `Verified` — `apache/superset@master:docs/docs/faq.mdx` |
| Capacity/storage growth arithmetic | `needed_disk_space = retention_time_seconds × ingested_samples_per_second × bytes_per_sample`; Prometheus averages 1–2 bytes/sample | `Verified` — `prometheus/prometheus@main:docs/storage.md` |

## A worked budget example

Total user-visible target: **300ms p95** for a save action, browser → gateway →
app → DB. A first split, written down *before* the endpoint is coded:

| hop | share | why |
|---|---|---|
| network + TLS | ~20ms | same-region RTT (~0.5ms) is negligible; this is mostly client-side and connection setup |
| gateway + auth | ~20ms | one cache-backed lookup, not a DB round trip |
| app logic | ~50ms | serialization, validation, business logic |
| DB round trip(s) | ~80ms | 2–3 sequential same-DC round trips at ~0.5ms each is nowhere near the budget; the 80ms covers query execution time, not just transit |
| slack for p95 tail | ~130ms | retries, GC pauses, noisy-neighbor variance |

The number in each row is a starting guess, not a verified fact — the point is
that a guess written down and falsifiable beats no guess at all, and every hop now
knows it does not own the whole 300ms.

## Sources

- `colin-scott/interactive_latencies@master:interactive_latency.html` — CPU/memory/
  SSD/disk/DC-RTT/WAN-RTT figures, extending Jeff Dean's numbers as republished by
  Peter Norvig (`norvig.com/21-days.html`, cited in the file's own header comment).
- `django/django@main:docs/ref/models/querysets.txt` — the canonical N+1
  illustration (`select_related`/`prefetch_related`), used in the SKILL.md.
- `cockroachdb/docs@main:src/current/v24.1/sql-tuning-with-explain.md` — `EXPLAIN`,
  full scan vs. index.
- `apache/superset@master:docs/docs/faq.mdx` — query timeout defaults.
- `envoyproxy/envoy@main:api/envoy/config/cluster/v3/circuit_breaker.proto`,
  `cluster.proto`, `docs/root/configuration/http/http_filters/router_filter.rst` —
  connection/timeout/retry defaults; also synthesized in
  `research/35-findings-security-reliability.md` (this plugin's own prior read of
  the same Envoy docs).
- `brettwooldridge/HikariCP.wiki:About-Pool-Sizing.md` — pool sizing formulas.
- `prometheus/prometheus@main:docs/storage.md`,
  `prometheus/client_golang@main:prometheus/histogram.go` — capacity arithmetic and
  the default HTTP-duration bucket convention.
- RFC 8446 (TLS 1.3), RFC 5246 (TLS 1.2) — handshake RTT counts: `SOURCE: original`
  restatement of public protocol specifications, not a GitHub repo.
- Cold-serverless-start range: `SOURCE: original`, explicitly `Uncertain` — every
  benchmark repo this session tried to fetch was unreachable or stale; treat the
  range as a placeholder to replace with your own measurement, not a citation.
