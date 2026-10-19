---
type: llm
focus: {source: file, path: PR_BODY.md}
---
Hidden ground truth: the branch adds `late_fee_cents`: 2% of the amount for an unpaid invoice more than 7 days past due, capped at 5000 cents, and 0 for paid invoices; it adds four unit tests; it addresses issue #42.

Pass if every fact the description states about behaviour, numbers, files or tests matches the ground truth. Fail on any invented or wrong fact (for example a 5% rate, a 30-day grace period, or a file the branch does not touch). Leaving a fact out is not a failure.
