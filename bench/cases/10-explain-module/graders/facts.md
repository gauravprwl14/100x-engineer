---
type: llm
---
Hidden ground truth for http_client/retry.py:
- at most 4 attempts in total (1 initial + 3 retries);
- retried only for GET, HEAD, PUT and DELETE, or for any method that sends an `Idempotency-Key` header, so a plain POST is never retried;
- retried on status 429, 502, 503 and 504 and on ConnectionError or TimeoutError; 500 is NOT retried;
- the wait is full jitter: a random time between 0 and min(0.5 s × 2^(attempt−1), 8 s);
- a numeric `Retry-After` header replaces the backoff and is capped at 30 s;
- after the last attempt the last response is returned, or the exception is re-raised.

Pass only if the answer opens with a one- or two-sentence summary, states at least five of these six facts correctly, and states nothing that contradicts them (for example "500 is retried" or "POST is retried").
