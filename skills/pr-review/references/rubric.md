# Review rubric — the one home for every `review.json` rule

Reference for `pr-review` (loaded on demand). `../SKILL.md` orchestrates, `reviewer-prompt.md`
briefs agents; both link here. Rules tagged `G…` are enforced by `100x pr_review_gate`. Shape to
copy: `$(100x root)/evals/fixtures/pr-review/example-run/` (*Illustrative*: fictional PR 9999 on
`git.example.com`).

**Judgement is delegated, not restated.** Intent before critique, a concrete failure scenario per
finding, blast-radius ordering and "cite the convention before calling it blocking" are
`diff-review` rules 9–16 (`$(100x root)/skills/diff-review/SKILL.md`, detail in its
`references/others-diff.md`). Framework failure modes come from the matching
`$(100x root)/reviewers/<stack>.md` via `stack-reviewer`. This file adds only what those do not
own: the record format, the rendering and the gate.

## 1. Golden rules

| # | Rule |
|---|---|
| 1 | **Read-only.** No edit, commit, push, checkout, comment, review, reaction or resolve in any repo or on GitHub. Subagents never post; the orchestrator posts only in `post`, after an explicit yes. |
| 2 | **One source.** Every point is one item in `review.json`. README, file 2, file 3, the tables in file 4 and `github-review.json` are rendered by `100x pr_review render` — never hand-written (G11). |
| 3 | **Traceable.** Links = `<pr.url minus /pull/n>/blob/<40-hex head SHA>/<path>#L<n>`, built by the renderer. No host/owner/repo typed anywhere (G7). Other-repo evidence: `<repo>/<path>:<line> @ <sha>` as text + the SHA in `PINS.md`. |
| 4 | **Whole PR + impact.** Cumulative diff `<base>...<head>`, `git log` for reverts; grep callers of every changed shared symbol. |
| 5 | **Conventions win over taste.** Read `<CR>/CONTEXT.md` first; cite the repo's CLAUDE.md / AGENTS.md / docs, then `<CR>/_meta/focus.md` and `decisions.md`, then the reviewer profile (load order in `../SKILL.md`). |
| 6 | **Honest evidence.** `ran` = you executed it; `read` = you opened it at the pinned SHA; `inferred` = one link unseen; `assumption` = unchecked. Label the weakest link. `inferred`/`assumption` → `confirm_by` (G2). |
| 7 | **Example with every claim.** `comment` has a real value: code span, number or quoted text (G2). Words like "validate", "handle", "consider" are not a fix — show what the code becomes. |
| 8 | **Existing comments first.** Read PR comments, review threads and bot reviews before writing items; a point already raised → `dup_of_existing_comment` = its URL (renders as "reply / +1"). Record `run.existing_comments` (G4). |
| 9 | **Review, adjust, post — in that order.** A review run never posts. The user reads it, changes it with `adjust` (their decisions live in each item's `user` block and win over the reviewer's wording, also across re-reviews), then `post` sends only open, not-skipped, not-yet-posted items (G14). |

## 2. Folder

`<run-root>/PR-<num>__<area>-<short-title>__<author>/` (area = backend · frontend · spec · mixed).

| File | Rendered? | For | Holds |
|---|---|---|---|
| `review.json` | written by agents | machines | schema §3 |
| `README.md` | rendered | you, first | who reviewed, what the PR does, recommendation, blocks merge vs rollout, action table, not-to-raise, changes since last review |
| `1-context.md` | hand-written | anyone new | sections `## Problem` · `## Before → after` (1 diagram) · `## Terms` · `## Author's decisions` · `## Not in this PR` (G13) |
| `2-comments-to-post.md` | rendered | you → author | Quick index (every comment by priority, with theme and related comments) · A) line · B) general · C) ask someone else · D) reply in existing thread · E) praise; each: Why (for you) + Paste this |
| `3-questions.md` | rendered | you | every question / needs-decision / inferred / assumption item: what we don't know · why · how to confirm · who · where |
| `4-findings.md` | mixed | depth | rendered between `<!-- rendered:coverage\|findings START … -->` / `END` markers; hand-written `## Evidence notes` with `### <ID> — <title>` (IDs must exist, G13) |
| `5-security.md` | hand-written, optional | depth | threat model, request-path diagram, verified-safe table. Findings stay in review.json |
| `github-review.json` | rendered | `post` | `{commit_id, body, comments[]}` (no `event` = draft) |
| `suggestion-checks.json` | written by `100x pr_suggest` | gate | proof behind every "… ok" / "applies cleanly" claim (G5) |

Run root (`<CR>/<feature>/` on a first review; `<CR>/<feature>/runs/<date>[-2…]/` on every
re-review, chosen by `100x pr_review find` / `next-run`): `README.md` (rendered by `100x pr_review
feature`), `PINS.md` (from `100x pr_snapshot`), optional `feature.json` `{feature, source,
merge_order}`. `<CR>/INDEX.md` is rendered by `100x pr_review index <CR>` after every review,
adjust and post — never hand-edited.

Hand-written text never cites action numbers (`#3`) — they are assigned at render time (G13).
Diagrams only in `1-context.md`, `5-security.md` and the run-root README (G13); each followed by
`**Reading this diagram**` + 2–3 bullets; must render on GitHub (no `<tag>`, no `;` in sequence
diagrams, no `#123`).

## 3. `review.json` schema

| Key | Type / values | Rule |
|---|---|---|
| `pr` | `url, number, title, author, head_sha (40-hex), base, behind, ci` | `url` copied from `gh pr view` (G7) |
| `run` | `date, for (your gh login), agents[{role, model}], recheck_of (short sha or null), existing_comments{checked, count, note}` | G4 |
| `summary` | `what_it_does[1–3]` plain lines · `recommendation` · `reason` · `lang` en/ja · optional `review_intro` | G6, G8 |
| `items[]` | below | G1–G5, G9, G10 |
| `not_to_raise[]` | `{topic, why}` | plain, no IDs |
| `coverage[]` | `{dimension, checked, result}` — one row per §5 dimension, even "Nothing found" | G1 |

| Item field | Values | Rule |
|---|---|---|
| `id` | `<PR>-<DIM>-<NN>`; security agent `…-1NN`; cross-PR `<PR>-X-NN` | stable across re-reviews, never reused |
| `kind` | `issue` · `suggestion` · `question` · `nit` · `praise` | Conventional Comments label |
| `blocks` | `merge` · `rollout` (before enabling for real users) · `none` | nit/praise → `none` |
| `severity` | `critical` · `major` · `minor` · `trivial` | |
| `status` | `open` · `needs_decision` · `question` · `fixed:<sha>` · `accepted` · `wont_fix` | first three = actionable |
| `title` | ≤ 100 chars, plain | |
| `why` | for **you**, ≤ 2 lines / 300 chars, plain, no jargon | G2, G3 |
| `where` | `{path, line (end), start_line, in_diff}`; `path` null = whole PR | `in_diff` must match the diff (G10) |
| `ask` | `{who: "author" or a named owner/team, where}`; author → `line comment` (needs in_diff) or `PR comment` | G2 |
| `also_ask[]` | `{who, where, say}` — someone besides the author must answer too | renders in file 2 §C |
| `comment` | author-facing (or `who`-facing), polite, ≤ 900 chars, a real value, no IDs/emoji/jargon, in `summary.lang` | G2, G3, G8 |
| `change` | `{type: suggestion·diff·pseudo·none, body, checked, lang?}` | §4 |
| `evidence` | `{type: ran·read·inferred·assumption, detail}` — `detail` quotes the line or `command` → output | |
| `confirm_by` | exact command/test; required for inferred/assumption and anything in file 3 | G2 |
| `unknown` | what we don't know, one line; required for anything in file 3 | G2 |
| `dup_of_existing_comment` | URL into this PR, or null | G4 |
| `previous_status` | re-review only: status at `recheck_of` (null = new) | G9 |
| `theme` | optional, short plain label (e.g. `Failure handling`) | grouped in file 2's Quick index |
| `duplicate_of` | optional, another item id | Quick index shows "near-duplicate of #n" |
| `user` | set only by `adjust`: `{decision: post·skip, edited: [field…], original: {field: reviewer's value}, note, by (login), at (date)}` | G14 |
| `posted` | set only by `100x pr_review mark-posted`: `{at, mode: draft·submit, url}` | G14 |

User-added items: id `<PR>-U-NN`, `evidence: {type: "user", detail: "added by @<login>"}`,
`user.decision: "post"`. They skip the "real value", `change none` and `confirm_by` rules (it is
the user's own text) but keep every other rule. `run.posts[]` = `{at, mode, url, items[ids]}` per
post.

### Mapping to `diff-review` labels

`diff-review` labels, comment tags and `review.json` `kind`/`blocks`/`severity` are mapped in one
table in `$(100x root)/docs/WRITING.md` ("One vocabulary map"), which also holds the shared
writing rules; the length and wording limits G2/G3 enforce stay in the tables above.

A `blocks: merge` item with no failure scenario in `why` is a preference (`diff-review` rule 10):
downgrade it.

## 4. Rendering rules and the gate

| Topic | Rule |
|---|---|
| Recommendation (G6) | any actionable `blocks: merge` → `request_changes`; else any actionable `issue`/`question` → `comment`; else `approve`. Rollout items never block the merge; README lists them separately |
| Numbering | posting order: section A → B → C → D, then merge → rollout → none, then severity, then json order. All author nits share one number = one general comment |
| File 2 sections | D if `dup_of_existing_comment`; C if `ask.who` ≠ author; A if in_diff + `line comment`; else B. `post` sends A (inline) + B + praise (review body). C and D are for the user to do by hand |
| Change types | `suggestion` = exact replacement for `start_line..line`, only when in_diff (G10), never on a nit. `diff` = unified, `--- a/` `+++ b/`, `-` lines copied from the file (G10). `pseudo` = doc, infra, decision, or anything not opened at the pinned SHA. `none` = question/praise only (G2) |
| Checked (G5) | suggestion/diff: `typecheck ok` · `lint ok` · `applies cleanly — typecheck not run (<why>)` · `not checked — <why>`. Any "ok/applies" claim needs a matching `suggestion-checks.json` entry (same body hash). Fails to apply or typecheck → downgraded to `pseudo` |
| Language (G8) | `why`, titles, README text: the user's language (English default). `comment`: `summary.lang`; `ja` needs Japanese text in every actionable comment + `review_intro` |
| Re-review (G9) | carry IDs; set `previous_status`; README shows "Changed since the last review". Never write "merged into"/"kept as" in reader text (G3). Copy `user` and `posted` forward unchanged |
| Adjust / post | skipped items get no number and are listed under "Skipped by you"; edited items show "edited by you"; README "Will post?" = Yes · Yes — edited by you · You, by hand · You, reply in thread · Posted (draft/submitted, date). `100x pr_review emit` leaves out skipped + posted items and exits 3 when nothing is new |

| Gate tag | Fails when |
|---|---|
| G0-files | a required file is missing (review.json, README, 1–4, github-review.json; run root: PINS.md, README.md) |
| G1-schema | key missing, bad enum, id not `<PR>-…`, duplicate id, empty coverage |
| G2-item | why/title/comment/ask missing or too long; no real value; `change none` on issue/suggestion/nit; inferred without `confirm_by`; file-3 item without `unknown`; nit blocks or uses suggestion; `line comment` not in diff |
| G3-clean | an internal ID, status emoji or rubric jargon in item text, summary, not_to_raise, README (above the action table), file 2 or file 3 |
| G4-existing | `run.existing_comments` missing; dup URL not in this PR |
| G5-checked | checked value outside the vocabulary, or an ok-claim without its `suggestion-checks.json` proof |
| G6-recommendation | `summary.recommendation` ≠ the computed one |
| G7-links | `pr.url` not `https://<host>/<owner>/<repo>/pull/<n>` matching `pr.number`; head SHA not 40-hex; a blob link off this repo or off the pinned SHA |
| G8-lang | `ja` without Japanese in comments or without `review_intro` |
| G9-recheck | `previous_status` without `recheck_of`, or outside the status vocabulary |
| G10-snapshot (`--snap`) | path/line missing at head; in_diff wrong either way; suggestion off-diff or identical to current lines; diff `-` line not in the file |
| G11-rendered | a rendered file or 4-findings region differs from a fresh render |
| G12-readme | "who reviewed" rows missing; action-table refs ≠ actionable, not-skipped items |
| G13-handwritten | 1-context sections/diagram missing; diagram without "Reading this diagram"; evidence note for an unknown ID; mermaid in 4-findings; `#n` in hand-written text |
| G14-user | bad `user` block (decision, edited fields without `original`, missing by/at); `evidence: user` on a non-`U` id or without a user block; bad `posted` record; a posted item marked skip |
| mermaid | parse error or GitHub-unsafe syntax (rendered with `npx` mermaid-cli when present; otherwise a stdlib syntax check and a WARN, never a FAIL) |

## 5. Coverage dimensions

| PR type | Dimensions (one `coverage` row each) |
|---|---|
| Code | Product / spec · Correctness · Security / data · Conventions · Tests · Performance · Impact · Prior findings · Existing PR comments |
| Spec | Completeness · Internal consistency · Ambiguity & testability · Technical feasibility · Spec vs implementation · Prior findings |
| Cross-PR (≥ 2 PRs) | Coverage matrix · Consistency · Stack & merge risks · Shared-code duplication · Product gaps |

"Prior findings" = `<CR>/_meta/decisions.md` and the prior run of this PR, when either exists.

## 6. Size tiers

| Changed lines (`additions + deletions`) | Agents | `5-security.md` |
|---|---|---|
| ≤ 300, no `--security` | 1 PR reviewer, which also does a security pass | only if something security-relevant was found |
| ≤ 300 with `--security` | PR reviewer + Security | yes |
| > 300 | PR reviewer; + Security when `--security` or the PR touches auth, session, IP, ACL, tokens, uploads | when Security ran |
| ≥ 2 PRs | + 1 Cross-PR agent | — |

Cap 10 agents per run (group small PRs above that).
