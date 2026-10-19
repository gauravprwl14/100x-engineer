---
type: llm
focus: {source: file, path: REPLY.md}
---
Hidden ground truth: the right fix rejects percents below 0 and above 100 (raising an error) and adds tests for -20 and 150; the reply should point at the commit that does it.

Pass only if ALL hold:
1. The reply is at most about four lines, and opens with what was done (e.g. "Done in <sha>: ...") rather than thanks or restating the comment.
2. It names the commit sha and what changed, and says which tests cover it.
3. It makes no claim the reviewer cannot check (no bare "verified" or "tested" without the command or test name).
