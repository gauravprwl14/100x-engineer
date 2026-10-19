---
type: llm
focus: {source: file, path: REPLY.md}
---
Hidden ground truth: the right fix rejects percents below 0 and above 100 by raising an error, and adds tests for values such as -20 and 150.

Pass if the reply says which tests cover the change (test names, or the inputs they exercise), and makes no claim the reviewer cannot check (a bare "verified" or "tested" with no test name or command fails).
