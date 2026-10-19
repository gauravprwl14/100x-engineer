---
type: llm
focus: {source: file, path: invoices/reports.py}
---
Hidden ground truth: an invoice is overdue on date D when its `due_date` is strictly before D and it was unpaid on D: `paid_on is None`, or (also correct) `paid_on` is after D. An invoice due on D itself is not overdue; an invoice paid on or before D is not overdue on D.

Pass only if the file defines a function implementing that rule, and every name it introduces (function, parameters, locals) is a full word or phrase: no one- or two-letter names other than a loop index, no abbreviations such as `inv`, `dt`, `d`, `tmp`, `res`, `lst`. A noun-phrase function name that says what it returns (`overdue_invoices`) is fine. Fail if the rule uses `<=` (due today counted) or ignores `paid_on`.
