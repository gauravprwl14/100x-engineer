**Reviewer** on `invoices/pricing.py` line 9:

> [SHOULD] `apply_discount` accepts any percent. `apply_discount(1000, -20)` → 1200, so a bad coupon raises the price, and `apply_discount(1000, 150)` → -500, a negative total. Could you reject percents outside 0–100?
