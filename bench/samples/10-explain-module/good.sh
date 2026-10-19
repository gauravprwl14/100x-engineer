cat > "$BENCH_TEXT" <<'MD'
`send_with_retry` makes at most 4 attempts, retrying only safe requests on 429/502/503/504 or a connection error, and waits with jittered backoff or the server's `Retry-After`.

- **Which requests:** GET, HEAD, PUT, DELETE, or any method with an `Idempotency-Key` header. A plain POST is sent once.
- **Which failures:** status 429, 502, 503, 504, `ConnectionError`, `TimeoutError`. A 500 is returned at once.
- **How long it waits:** a random time between 0 and `min(0.5 s × 2^(attempt-1), 8 s)` (full jitter).
- **Retry-After:** a numeric header replaces the backoff, capped at 30 s.
- **When it gives up:** after attempt 4 it returns the last response or re-raises the error.
MD
