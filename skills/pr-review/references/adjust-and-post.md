# `adjust` and `post`

Reference for `pr-review` (loaded on demand). The numbered rules live in `../SKILL.md`; the
`user` and `posted` blocks are specified in `rubric.md` §3.

## Finding the review

Both accept a PR link (`/pr-review adjust <pr-url>`) or a folder + PR number
(`/pr-review adjust <folder> <n>`). `CR=$(100x pr_review out-dir --url <pr-url>)`, then
`100x pr_review find "$CR" <pr-url>` or `find "$CR" <folder> <n>` → the newest line is the PR
folder; its run root is the folder above it. Exit 1 → stop: "this PR has no review yet — run
`/pr-review <pr-url>` first".

## `adjust <pr-url>`

The user says, in plain words, what to change ("drop #7", "shorter and friendlier #3", "make #5
blocking", "add a comment on `api-client.ts:14`: …", "undo my change to #3"). Numbers are the README
action-table numbers. Edit `review.json` only, never the rendered files.

| # | Step | Action |
|---|---|---|
| 1 | Find | see above; copy `review.json` to `<scratch>/review-<n>.before.json`. If the PR head moved since that review, say so and suggest re-reviewing first (adjusting old comments is still allowed) |
| 2 | Map | no request given yet → show the README action table (`#`, what, type, will post?) and ask what to change, then continue. Resolve each request to item IDs via the README table; anything ambiguous (which #, what wording, which line) → ask with AskUserQuestion, never guess |
| 3 | Edit | skip → `user: {decision: "skip", note, by, at}` · edit → change the field(s), list them in `user.edited`, keep the reviewer's value in `user.original` · add → new item `<PR>-U-NN`, `evidence: {type: "user", detail: "added by @<login>"}`, `user.decision: "post"`; a new line comment must sit on a diff line (`where.in_diff` from `<snap>/<n>.diff`), else it becomes a general comment · undo → restore from `user.original`, drop the `user` block. An item already `posted` cannot be skipped or edited — say so |
| 4 | Recheck changes | any `change` body edited or added → run workflow step 9 (`100x pr_suggest`) again |
| 5 | Render + gate | workflow step 11 (including `100x pr_review index "$CR"`); fix until exit 0 |
| 6 | Show | per touched item: `#n` · before → after (comment text, kind, blocks) or "skipped"; then the totals: "Will post: N (A line, B general) · by hand: C · skipped: S". `100x pr_review preview <pr-dir>` prints the full text that would be posted |

## `post <pr-url> [draft|submit]`

Default `draft` (a pending review only the user sees until they submit it in the UI), or
`post_mode` from `<CR>/_meta/settings.json` when no mode is given — still one explicit yes. `submit` =
`event: COMMENT`. Never `APPROVE` / `REQUEST_CHANGES` unless the user asks for that event by name.
This is the only place the skill writes to GitHub.

| Step | Action |
|---|---|
| 0 Sync earlier drafts | for each `run.posts` entry with `mode: draft`: `gh api --hostname HOST repos/OWNER/REPO/pulls/<n>/reviews/<id>` (id = the number after `#pullrequestreview-`). Still `PENDING` → stop: "you have an unsubmitted draft — submit or delete it on GitHub first" (GitHub allows one per user). Submitted with an empty `body` while the entry has `summary_items` → GitHub dropped the summary (the Finish-review box replaces it): show `100x pr_review followup-text <pr-dir> <url>`, ask, and on yes `gh pr comment <n> -R … -F <file>`; record it (a second `run.posts` entry with the comment URL, those items' `posted.url`/`mode: submit`) |
| 0b Own comments | `gh api --hostname HOST --paginate repos/OWNER/REPO/pulls/<n>/comments` and `.../issues/<n>/comments`, keep the user's own (`gh api --hostname HOST user -q .login`). One already says what an unposted item says → show both and ask whether to skip the item |
| 1 Find | see above |
| 2 Gate | `100x pr_review_gate <run-root> --snap <snap>` (re-run `100x pr_snapshot` if the scratchpad is gone) |
| 3 SHA guard | `gh pr view <n> -R HOST/OWNER/REPO --json headRefOid -q .headRefOid` must equal `review.json` `pr.head_sha`, else stop: "head moved — run `/pr-review <pr-url>` again to re-review" |
| 4 Build | `100x pr_review emit <pr-dir> <draft\|submit> [--body-max N] > <scratch>/review-<n>.json` (preview on stderr; `body_max` from `settings.json`). A `WARN body is over` line → offer to post the general comments as separate PR comments instead. Exit 3 = nothing new to post (all skipped / already posted / by hand) → tell the user and stop. Skipped and already-posted items are never included |
| 5 Show | mode, every inline `path:line` + first line, the general comments, and what is NOT posted (file 2 sections C and D — the user does those by hand) |
| 6 Ask | AskUserQuestion once per PR naming `OWNER/REPO#n` and the mode. Anything but an explicit yes = post nothing |
| 7 Post | `gh api --hostname HOST -X POST repos/OWNER/REPO/pulls/<n>/reviews --input <scratch>/review-<n>.json` |
| 8 Record | `100x pr_review mark-posted <pr-dir> <html_url> <draft\|submit>`, then render + gate (workflow step 11, including `index`). README gains "Posted to GitHub"; posted items show "Posted" and are never sent again |
| 9 Report | the review `html_url`; draft → "pending: submit it in Files changed", **plus, when the draft has general comments, this warning with the text**: "GitHub's *Finish your review* box starts empty and replaces the summary when you submit. Paste the text below into it (or leave it and run `/pr-review post <pr-url>` again after submitting — it will offer to post the general comments as a PR comment)." Print the `followup-text` output for them. If GitHub says a pending review already exists, stop and tell the user |
