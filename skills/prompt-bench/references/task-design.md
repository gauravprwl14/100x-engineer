# Task design: hidden ground truth without a ceiling

A bench is only as good as its tasks. Round 1 (four easy tasks) put every arm at 7–8.5 on the
first answer; the second pass "improved" everything and no wording separated. Round 2 (three
hard tasks) moved the baseline to ~5.9 and exposed what each arm actually did.

## What makes a task useful

| property | why | check |
|---|---|---|
| a trap a careful first answer usually misses | room to improve; otherwise ceiling | baseline mean < 8.5 (`aggregate` warns) |
| the trap is discoverable from the fixture alone | the arm can find it without the network | name the file/line that reveals it in `ground_truth` |
| ground truth lives only in the spec | runners must not see it | `init` writes it to `GROUND_TRUTH.md`, outside `runs/` |
| a decoy: something that looks wrong and is fine | catches arms that "fix" everything | list it in `ground_truth` as "Decoy: …" |
| an over-engineering bait | catches arms that add scope | state the scale (traffic, users) in the fixture |
| code tasks carry probes | reading code is not running it | each probe asserts the trap's behaviour, exit 0 = pass |

Aim for 3–5 tasks across kinds (review, plan, fix). One kind only measures one skill.

## Round-2 tasks as templates

**h1-review — coupon redemption PR (review).** `diff.patch` + `CONTEXT.md` (Prisma schema,
"once per user", 200 req/s). Hidden: read-then-write `usedCount + 1` race; `Date < string`
compare is always false so expiry is never enforced; coupon and order updates not in one
transaction; once-per-user rule unenforced with an unused `Redemption` model. Decoy: the
logging line.

**h2-migration — `events.tenant_id NOT NULL` on Postgres 11, 50M rows, 300 inserts/s (plan).**
Hidden: on PG 11 `SET NOT NULL` scans the table under ACCESS EXCLUSIVE; the validated-CHECK
shortcut exists only from PG 12. Right plan: nullable add, app writes new rows, batched
backfill, `CREATE INDEX CONCURRENTLY`, `CHECK … NOT VALID` then `VALIDATE`. Wrong: one big
UPDATE, `DEFAULT 0`, claiming PG 11 skips the scan. Bait: dual tables, logical replication.

**h3-fix — `parse_amount("1,234.50")` fails (code).** `money.py`, `test_money.py`,
`checkout.py`, `import_eu.py` (calls with `decimal_sep=","`). Hidden: stripping every comma
passes the test but breaks the EU caller, and stripping the "other" separator turns
previously-rejected input into silent 100× errors (`"12,50"` → 125000). Probes:

```python
from money import parse_amount as p; assert p("1,234.50") == 123450
from money import parse_amount as p; assert p("1.234,50", decimal_sep=",") == 123450
from money import parse_amount as p
try: v = p("12,50")
except ValueError: v = None
assert v != 125000, "silent 100-fold misparse"
```

0/8 first answers were safe; 7/8 were after any second pass, placebo included.

## Spec checklist

- `task_prompt` reads like a real request — no hint at the trap, no "be careful".
- `ground_truth` lists required findings, wrong answers, the decoy, and what counts as
  over-engineering, so the judge scores against a list, not taste.
- `reps` ≥ 2 and arms × reps × tasks gives ≥ 6 runs per arm (the sign test cannot reach
  p < 0.05 below 6 untied pairs).
- Run one pilot answer first; if it nails the trap, make the task harder before `init`.
