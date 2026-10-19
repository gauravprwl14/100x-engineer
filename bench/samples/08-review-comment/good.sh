cat > REVIEW.md <<'MD'
[MUST] invoices/payments.py:20: `refund` never caps the amount, so it can refund more than was paid.
`refund(PAID, 20000)` → `refunded_cents == 20000` on a 10000 invoice.
Could you raise `PaymentError` when `amount_cents <= 0` or the total would exceed `amount_cents`?
MD
