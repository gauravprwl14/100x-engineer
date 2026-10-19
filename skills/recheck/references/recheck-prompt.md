# Re-check prompt

Reference for `recheck` (loaded on demand). This file is the single source of the prompt:
`hooks/recheck_gate.py` reads the block between the two markers verbatim and sends it as its
Stop `reason`, and `/100x:recheck` applies the same text. Edit it here only; the hook test
(`tests/test_hooks_recheck.sh`) fails if the two drift.

The wording combines arm B's "assume a mistake, name 3 ways it is wrong, check against the
files" (fewest wrong claims, the only arm that made answers shorter) with the user's quality bar
and arm A's staleness check, and asks for the answer only plus one `Re-check:` line, because
graders marked down a "changes vs v1" section. Measurements: [evidence.md](evidence.md).

<!-- recheck-prompt:start -->
```text
Before you finish: assume this answer still has at least one mistake.
Audit it as a skeptical senior reviewer — highest confidence, no gaps,
no over-engineering, surgical, least risk of negative impact.
1. Name the 3 most likely ways it is wrong, incomplete, or over-built,
   and check each against the actual files and facts, not memory
   (callers, edge cases, concurrency, version-specific behaviour).
2. Fix what is real, keep what holds, cut what isn't needed for it to
   work, and mark anything you could not verify.
3. Check assumptions for drift or staleness (docs vs code, versions, defaults).
Then give the final answer only, followed by one line:
"Re-check: <what changed>" or "Re-check: no changes — verified <what> (<file:line or command>)".
```
<!-- recheck-prompt:end -->
