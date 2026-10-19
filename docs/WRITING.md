# Writing standard

**Answer:** lead with the answer, size the text to the change, and put proof next to every
claim. This covers PR bodies, commits, review comments, replies, docs, specs, READMEs, reports,
chat answers and code comments. `100x prose_check` lints it; it warns and never blocks.

Good and bad PR bodies use the same links, tables and code blocks. Proportion and proof are
what separate them: best bodies ran a median 812 chars for 315 diff lines, worst ones 4,420
for 107. `SOURCE: original (private-repo PR communication survey: 120 human PRs, 251 inline review comments)`

## Core rules

| # | rule | enforced by |
|---|---|---|
| 1 | Lead with the answer: the first lines say what changed or what is true | `summary-first`, review |
| 2 | Size fits the change: a PR body is at most max(600, 8 × diff lines) chars | `body-budget` |
| 3 | A paragraph is at most 3 lines and 300 chars; past that, use bullets | `long-paragraph` |
| 4 | Why is 1 sentence with a link to the issue or decision | `missing-issue-link`, review |
| 5 | What is bullets of behaviour, including what is NOT done; a bullet is ≤ 160 chars | `long-bullet` |
| 6 | "verified/tested/confirmed/passed" only next to a command and its output, a sha, a link or a file:line | `claim-without-evidence` |
| 7 | No self-ticked boxes, no "This PR…" or "Successfully" filler | `self-ticked-box`, `filler-phrase` |
| 8 | No history or timeline narration and no restating the diff; link the decision | `history-section`, `heading-overload`, review |
| 9 | A table only to compare 3+ items across 2+ attributes | review |
| 10 | Links over prose: point at the issue, file:line or doc instead of retelling it | review |

Rules 2 and 8 come from the survey: history sections appeared in 24% of the worst bodies and 0%
of the best; an unbacked "verified" in 56% and 3%. Google asks for a first line that stands alone
and a body that says what and why (google/eng-practices@master:review/developer/cl-descriptions.md).

## Per output

**PR description.** The repo's own PR template wins on headings; fill its sections with this
content. PR text is always English. Do not tick a test box you did not run.

```text
closes #<issue>                      (or: part of #<epic>)
## Why
<one sentence: the problem and a link to the decision>
## What
- <behaviour change>
- <scope limit: "does not X">
## Verified
<env>: `<command>` → <result line>
## Out of scope
- <deferred item> → #<issue>
```

**Review comment.** One comment, one ask. Tag severity first, show what breaks, then the fix.
Explain the reasoning and label severity (google/eng-practices@master:review/reviewer/comments.md).

````text
[MUST|SHOULD|NIT|ASK] <one-line claim>
<input> → <failure> (<file>:<line>)
<evidence: command + 1–3 output lines, or a doc link>
```suggestion
<fix>
```
<one question, or "ignore if intended">
````

Enforced by `review-comment-no-severity`, `review-comment-no-scenario` (MUST/SHOULD) and
`review-comment-multi-ask`. A failure scenario was in 31% of threads that got a fix and 0% of
threads that ended in a clarification request (survey above).

| output | shape | enforced by |
|---|---|---|
| commit message | Conventional Commits `<type>(<scope>): <imperative summary>`; body says why in 1–3 lines, then `Closes #N` (conventional-commits/conventionalcommits.org@master:content/v1.0.0/index.md) | `long-paragraph`, review |
| reply to a review comment | `Done in <sha>: <what changed>; covered by <test>.` or `Kept: <measured reason> (<evidence>). Follow-up: #<issue>.` | `reply-fixed-no-sha` |
| docs, specs, READMEs, reports | a 2–5 line answer or summary table first; long-doc index rules are OPERATING-MODEL §9 | `summary-first` |
| chat answer | the answer in the first sentence, then only what the reader acts on | `long-paragraph`, `filler-phrase` |
| inline code comment | why, not what, in 1–2 lines; link the issue or decision instead of narrating (`code-craft` rule 10) | `code-comment-narration` |

## One vocabulary map

Each tool keeps its own terms; these rows say which ones mean the same thing.

| meaning | `_evidence-labels` | comprehension | pr-review `evidence.type` | §3 `confidence` | learn |
|---|---|---|---|---|---|
| opened or ran it, with file:line or command | `Verified` | `verified` | `ran`, `read` | `definite` | `Verified` |
| deduced from names or structure | `Inferred` | `inferred` | `inferred` | `probable` | `Inferred` |
| unchecked or unresolved | `Uncertain` | `inferred` | `assumption` | `possible` | `Uncertain` |
| a source's opinion, not a fact | — | — | — | — | `Speaker's view` |

| meaning | comment tag | `diff-review` | pr-review `review.json` | §3 findings | Conventional Comments |
|---|---|---|---|---|---|
| must change before merge | `[MUST]` | blocking | `issue`, `blocks: merge` or `rollout` | `blocking: true` | `issue (blocking)` |
| should change, not blocking | `[SHOULD]` | should-fix | `issue`/`suggestion`, `blocks: none`, `major`/`minor` | `blocking: false`, `major`/`minor` | `suggestion` |
| take it or leave it | `[NIT]` | optional | `suggestion`/`nit`, `blocks: none` | `minor`/`trivial` | `nitpick` |
| needs an answer | `[ASK]` | question | `question`, `status: question` | a `questions[]` entry | `question` |

Labels: https://conventionalcomments.org; Google's `Nit:` and `Optional:` map to `[NIT]`.
