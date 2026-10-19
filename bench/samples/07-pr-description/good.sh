cat > PR_BODY.md <<'MD'
closes #42

## Why
Overdue invoices cost nothing today, so customers have no reason to pay on time.

## What
- `late_fee_cents`: 2% of the amount once an unpaid invoice is more than 7 days late
- capped at 5000 cents; paid invoices never get a fee

## Verified
`python3 -m unittest -q` → `Ran 5 tests ... OK`
MD
