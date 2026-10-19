# PR 9999 — feat(reset): cap password-reset mails at 3 per minute

> **In 10 seconds:** **Request changes.** The cap counts per sender IP, so an attacker with 2 IPs still sends 6 mails a minute to one inbox — the exact problem the PR is meant to stop. Post 4 comments to @dana (2 on lines, 2 general); ask someone else 1 thing. #1 blocks the merge; #2 must be answered before rollout.

## Who is who

| | |
|---|---|
| Reviewed by | PR reviewer (+ security pass) (claude-opus) |
| Requested by (you) | @sam |
| PR author (gets the comments) | @dana |
| PR | [widgets PR 9999](https://git.example.com/acme/widgets/pull/9999) · `main` · CI pass 2/2 · 4 commits behind |
| Commit reviewed | [`0a1b2c3d`](https://git.example.com/acme/widgets/commit/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567) (every link points here) |
| Date | 2030-01-15 |
| Recheck of | — (first review) |

## What the PR does

- Anyone could ask for unlimited password-reset mails to any address, so one inbox could be flooded.
- This PR counts reset requests and refuses the 4th within 60 seconds with `429 Try again later`.
- The count is kept in memory on each server.

## Recommendation: Request changes

The cap counts per sender IP, so an attacker with 2 IPs still sends 6 mails a minute to one inbox — the exact problem the PR is meant to stop.

| Blocks | Items |
|---|---|
| The merge | #1 |
| The rollout (before enabling for real users) | #2 |

## Your action items (in order)

| # | What | Type | Where to write it | Blocks? | Will post? | How we know | Text | ref |
|---|---|---|---|---|---|---|---|---|
| 1 | Cap is per sender IP, not per email address | issue (blocking) | Inline on [`limiter.ts` line 10](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/limiter.ts#L10) | **Yes — merge** | Yes | Ran it | [#1](2-comments-to-post.md#c1) | 9999-BUG-01 |
| 2 | How many API instances run in production? | question (before rollout) | Inline on [`limiter.ts` line 6](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/limiter.ts#L6) + ping Infra on-call on Slack #infra | Not the merge — **before rollout** | Yes | Inferred — not tested | [#2](2-comments-to-post.md#c2) | 9999-SEC-01 |
| 3 | Test the 4th call is refused | suggestion (non-blocking) | General PR comment (about [`reset.controller.spec.ts` L4](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/reset.controller.spec.ts#L4), not in this PR's diff) | No | Yes | Read in the code | [#3](2-comments-to-post.md#c3) | 9999-TST-01 |
| 4 | Name the 60000 and the 3 | nit (non-blocking) | General PR comment (one comment for all nits) | No | Yes | Read in the code | [#4](2-comments-to-post.md#c4) | 9999-CNV-01 |

Paste text for each row is in [2-comments-to-post.md](2-comments-to-post.md); open questions (who answers, where to ask) in [3-questions.md](3-questions.md).
Not happy with a comment? `/pr-review adjust <feature> <pr>` and say what to change (drop, reword, add, change blocking). Nothing is posted until `/pr-review post`.

## Things you don't need to raise

| Topic | Why it's fine |
|---|---|
| In-memory instead of Redis | Author's stated choice (no Redis in this service yet); the instance question covers the risk |
| UI message for a blocked user | Deferred to issue 9990 slice 2, on purpose |

## Read next

| File | Read it when |
|---|---|
| [1-context.md](1-context.md) | You are new to the PR: problem, before → after diagram, terms |
| [2-comments-to-post.md](2-comments-to-post.md) | You are ready to comment: exact text per row above |
| [3-questions.md](3-questions.md) | You need to know who answers what, and where to ask |
| [4-findings.md](4-findings.md) | You want the evidence behind a point |
| [5-security.md](5-security.md) | You want the attacks tried and what was verified safe |
