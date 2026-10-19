---
type: llm
focus: {source: file, path: PR_BODY.md}
---
Hidden ground truth: the branch adds `late_fee_cents`: 2% of the amount for an unpaid invoice more than 7 days past due, capped at 5000 cents, and 0 for paid invoices; four unit tests; it references issue #42.

Pass only if ALL hold:
1. The reason for the change is given in one or two sentences near the top, and #42 is linked.
2. What changed is a short bulleted list of behaviour (grace period, rate, cap, paid invoices), not a restatement of the code line by line.
3. Any claim that tests pass sits next to the command that was run and its result.
4. No checkbox is pre-ticked (`- [x]`), no "This PR" filler, no history or timeline section.
5. The body is proportionate: under about 600 characters of prose for this ~45-line diff, with no paragraph over three lines.
6. Every fact matches the ground truth (no invented behaviour, numbers or files).
