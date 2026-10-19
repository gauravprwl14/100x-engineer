---
type: llm
focus: {source: file, path: invoices/reports.py}
---
Hidden ground truth: an invoice is overdue on date D when it is unpaid (`paid_on is None`) and its `due_date` is strictly before D. An invoice due on D itself is not overdue; a paid invoice is never overdue.

Pass only if the file defines a function implementing exactly that rule, and every name it introduces (function, parameters, locals) is a full word or phrase: no one- or two-letter names other than a loop index, no abbreviations such as `inv`, `dt`, `d`, `tmp`, `res`, `lst`. Fail if the rule uses `<=` (due today counted) or ignores `paid_on`.
