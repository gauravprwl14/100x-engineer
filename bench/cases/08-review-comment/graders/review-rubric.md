---
type: llm
focus: {source: file, path: REVIEW.md}
---
Hidden ground truth: `refund` never checks the amount. A refund larger than what was paid (`refunded_cents + amount_cents > amount_cents`), repeated refunds that add up past the paid amount, and zero or negative amounts are all accepted. The tests do not cover any of these. Everything else in the diff is fine.

Pass only if ALL hold:
1. A comment identifies the missing upper bound (over-refund), states its severity as blocking or must-fix, and gives a concrete failing input, e.g. `refund(PAID, 20000)` → refunded_cents 20000 on a 10000 invoice.
2. Each comment opens with a severity tag and makes one ask.
3. No comment is invented praise filler or a style nit presented as blocking.
4. The review is shorter than about 1500 characters in total.
