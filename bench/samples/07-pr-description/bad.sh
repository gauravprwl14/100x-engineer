cat > PR_BODY.md <<'MD'
## Summary

This PR adds a late fee feature to the invoices module. I have implemented a new function called late_fee_cents in invoices/late_fees.py which takes an invoice and today's date and calculates the late fee for the invoice based on how many days late it is, applying a grace period of seven days and a rate of two percent, with a cap so that very large invoices do not get enormous fees applied to them.

## History
Invoices were added first, then outstanding totals.

## Checklist
- [x] Tests pass
- [x] Verified everything works
MD
