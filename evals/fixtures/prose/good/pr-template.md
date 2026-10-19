Part of #330

## Summary
Rate-limit the public share endpoint to 60 requests a minute per token (decision: #318).

## Changes
- Add a token-bucket middleware in `share/limits.py`.
- Return 429 with a `Retry-After` header when the bucket is empty.
- Does not limit signed-in users; that is tracked in #331.

## Testing
```
$ pytest tests/share -q
14 passed in 1.02s
```
