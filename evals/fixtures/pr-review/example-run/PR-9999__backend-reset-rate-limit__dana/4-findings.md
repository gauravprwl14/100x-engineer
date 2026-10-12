<!-- ILLUSTRATIVE ONLY — PR 9999 is fictional. Tables between the rendered:* markers come from review.json; the rest is hand-written. -->
# PR 9999 — findings (depth)

> **In 10 seconds:** Every review dimension with what was checked, and every point with its evidence. Internal IDs are used in this file only.

## Coverage

<!-- rendered:coverage START — edit review.json, then re-run 100x pr_review render -->
| Dimension | What was checked | Result |
|---|---|---|
| Product / spec | Issue 9990 vs code: 3 per address per 60 s | 9999-BUG-01, 9999-PRD-02 (accepted) |
| Correctness | Window math at t = 0, 59 999, 60 000 ms | 9999-BUG-01 |
| Security / data | Key choice, multi-instance counting, header spoofing | 9999-SEC-01 |
| Conventions | Repo CLAUDE.md: constants, file placement | 9999-CNV-01 |
| Tests | `reset.controller.spec.ts` | 9999-TST-01 |
| Performance | Map growth: one entry per key, never evicted | Nothing found at today's traffic (≈ 200 resets/day) |
| Impact | Callers of `ResetLimiter.allow` (1) | Nothing found |
| Existing PR comments | 1 bot thread | Not duplicated |
<!-- rendered:coverage END -->

## All points

<!-- rendered:findings START — edit review.json, then re-run 100x pr_review render -->
| # | ID | Kind | Blocks | Sev | Status | Finding | Evidence | Where | Change |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 9999-BUG-01 | issue | merge | major | open | Cap is per sender IP, not per email address | Ran it: `node scripts/try-reset.js user@acme.test --ips 2` → 6 mails in 60 s | [`limiter.ts` L10](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/limiter.ts#L10) | suggestion (applies cleanly — typecheck not run (no node_modules in the snapshot)) |
| 2 | 9999-SEC-01 | question | rollout | major | question open | How many API instances run in production? | Inferred — not tested: `private readonly hits = new Map<string, number[]>()` — per process; replica count not visible in this repo | [`limiter.ts` L6](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/limiter.ts#L6) | none |
| 3 | 9999-TST-01 | suggestion | none | minor | open | Test the 4th call is refused | Read in the code: `expect(l.allow('198.51.100.7', 'user@acme.test', 0)).toBe(true);` is the only assertion | [`reset.controller.spec.ts` L4](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/reset.controller.spec.ts#L4) | diff (applies cleanly — typecheck not run (no node_modules in the snapshot)) |
| 4 | 9999-CNV-01 | nit | none | trivial | open | Name the 60000 and the 3 | Read in the code: `filter((t) => now - t < 60000)` and `recent.length >= 3` | [`limiter.ts` L11](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/limiter.ts#L11) | diff (applies cleanly — typecheck not run (no node_modules in the snapshot)) |
| — | 9999-PRD-01 | praise | none | trivial | open | Clear 429 answer | Read in the code: PR body: "answers 429 Try again later" | whole PR | none |
| — | 9999-PRD-02 | suggestion | none | minor | accepted | UI shows no wait time yet | Read in the code: PR body "Not in this PR: UI message (issue 9990 slice 2)" | whole PR | pseudo |
<!-- rendered:findings END -->

## Evidence notes

<!-- Hand-written. One `### <ID> — <title>` per point that needs more than the table row: quoted lines, command + output, the example scenario. -->

### 9999-BUG-01 — Cap is per sender IP, not per email address

```text
$ node scripts/try-reset.js user@acme.test --ips 198.51.100.7,203.0.113.9
sent 1..6 OK  (6 mails in 60 s; issue 9990 wants 3)
```
Same run after the suggestion → 3 sent, the 4th gets `429`.
