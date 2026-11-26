---
name: pr-description
description: >
  PR description, pull request body, commit message or review reply: summary table, root cause,
  a diagram when logic changes, before/after images for UI, real output under Verified, no
  process noise. Not for reviewing a PR (→ pr-review).
---

# PR description

A reviewer reads the body before the diff, so a body longer than the change or a "verified"
with no proof costs every reviewer time. The shared rules and templates are in
[`docs/WRITING.md`](../../docs/WRITING.md); this skill is the procedure that applies them and
the check that measures the draft.

## Trigger

**Fire when:** writing or editing a PR description or pull request body (`gh pr create`,
`gh pr edit`), a commit message, or a reply to a review comment on your own PR.

**Do not fire when:** reviewing someone else's PR (→ `pr-review`) or your own diff before
pushing (→ `diff-review`); designing the repo's PR template or merge checks
(→ `review-gates`); proving work is done before commit (→ `verification-gate`).

## Steps

| # | step |
|---|---|
| 1 | Read the repo's PR template if one exists (`.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE/`, `docs/`); its headings win |
| 2 | Compute the diff size: `git diff --shortstat <base>...HEAD`, insertions + deletions = N |
| 3 | Draft from the PR template in `docs/WRITING.md`: Refs/Closes #N, Summary table, Root cause, How it works (diagram), What changed, Before / after, Verified, Not verified |
| 4 | Run `100x prose_check --kind pr --diff-lines N body.md` (commits: `--kind commit`; replies: `--kind reply`) |
| 5 | Fix what it reports, or keep a finding only with a reason you can state |
| 6 | Under Verified, paste the commands you ran and their output lines; never tick a test box you did not run |

## Rules

1. The repo's own PR template wins on headings; fill its sections with the WRITING.md content
   rather than adding a second set of headings.
   *Enforced by:* review
   `SOURCE: original (private-repo PR communication survey: 120 human PRs, 251 inline review comments)`: default AI headings in place of the
   team's template broke the team's reading habit.

2. The body is at most max(2500, 12 × diff lines) chars; image lines are not counted. Cut
   process notes, history, timelines and restated diff first.
   *Enforced by:* `100x prose_check --kind pr --diff-lines N` (`body-budget`, `history-section`)
   `SOURCE: original (private-repo PR communication survey: 120 human PRs, 251 inline review comments)`: best bodies ran a median 812 chars for
   315 diff lines, worst ones 4,420 chars for 107.

3. The first line closes or links the issue. The Summary says what the PR does and why in at
   most 3 sentences, with a 2–5 row table (Adds, Changes, Removes, Does not touch) when the
   change spans several parts. A fix or refactor adds a Root cause of 1–3 sentences: what was
   wrong and why, not the symptom.
   *Enforced by:* `100x prose_check --kind pr` (`missing-issue-link`), review
   The description must stand on its own for a future reader
   (google/eng-practices@master:review/developer/cl-descriptions.md).

4. Every "verified", "tested", "confirmed" or "passed" sits next to the command and its output,
   a sha, a link or a file:line. No ticked boxes the agent did not run.
   *Enforced by:* `100x prose_check --kind pr` (`claim-without-evidence`, `self-ticked-box`)
   `SOURCE: original (private-repo PR communication survey: 120 human PRs, 251 inline review comments)`: an unbacked "verified" was in 56% of
   the worst bodies and 3% of the best.

5. A commit subject follows Conventional Commits, `<type>(<scope>): <summary>`, and the body says
   why in 1–3 lines.
   *Enforced by:* `100x prose_check --kind commit`; the type prefix by review
   conventional-commits/conventionalcommits.org@master:content/v1.0.0/index.md

6. A reply to a review comment says `Done in <sha>: <what changed>` or `Kept: <measured reason>
   (<evidence>)`.
   *Enforced by:* `100x prose_check --kind reply` (`reply-fixed-no-sha`)
   `SOURCE: original (private-repo PR communication survey: 120 human PRs, 251 inline review comments)`: 42% of the 238 author replies cited a
   commit.

7. PR text is always English, whatever language the conversation is in.
   *Enforced by:* convention
   `SOURCE: original` (a user decision for this plugin).

8. When the change alters logic, a request flow, a data path, state or module structure, show it
   in one mermaid diagram of how it works now: a flowchart for decisions, a sequence for calls
   between services, at most 10 nodes, plain-word labels. A pure copy, style or rename change
   gets no diagram. A stack of 3+ PRs gets a table: position, PR, concern.
   *Enforced by:* review
   `SOURCE: original` (a user decision, 2026-11-26, from a review of recent PR bodies).

9. Show structure instead of telling it: a table for 3+ items across 2+ attributes, a diagram
   for a flow, at most 6 bullets otherwise, no paragraph over 3 lines.
   *Enforced by:* `100x prose_check --kind pr` (`long-paragraph`, `long-bullet`), review
   `SOURCE: original` (a user decision, 2026-11-26).

10. Leave out process noise: audit or review-round counts and severity tallies, head and run
    shas beyond the one commit Verified names, "same warnings as main" counts, runner or timeout
    notes, "screenshots to follow". Keep only what changes a reviewer's decision: a failing
    check, a path not verified, a deferred item with its issue link.
    *Enforced by:* review
    `SOURCE: original` (a user decision, 2026-11-26, from a review of recent PR bodies).

11. A change a user can see gets a Before / after table of images in the body: same page, state
    and width, desktop and phone. Drag the images into the PR description box so GitHub hosts
    them; never commit them or push a screenshots branch. Say so when they come from a fixture
    page and not the real app. A minor or invisible change writes "No UI change".
    *Enforced by:* review
    `SOURCE: original` (a user decision, 2026-11-26).

## Verify

```bash
git diff --shortstat origin/main...HEAD
100x prose_check --kind pr --diff-lines 40 body.md
100x prose_check --kind pr --diff-lines 40 --strict body.md   # exit 1 while findings remain
bash "$(100x root)/tests/test_prose_check.sh"
```

## Failure modes

This skill rejects:

- **The 4,000-char body for a 40-line diff** with Summary, Background, Timeline and Risks
  headings → rule 2; the history goes, the link to the decision stays.
- **"Five audit rounds, last found 0 critical"**, head shas and lint-warning counts → rule 10;
  they do not help a reviewer decide.
- **A UI change with "screenshots to follow"** → rule 11; add the table before opening the PR.
- **"Verified everything works"** with nothing run → rule 4; paste the command and its output.
- **`- [x] Tests pass` ticked by the agent** → rule 4; the box becomes a command and its output.
- **"Fixed, thanks"** on a review thread → rule 6; name the sha.
- **Overriding the team's template** with generic headings → rule 1.

Known limits: `prose_check` measures size and proof, not truth; a pasted output line can still
come from another commit. `verification-gate` binds results to the code.

## Scale

`solo` and up. On a solo project the reader is you in six months; on a team, every reviewer.

## Sources

- Shared rules, templates and the vocabulary map: `docs/WRITING.md`.
- CL descriptions: google/eng-practices@master:review/developer/cl-descriptions.md
- Review comments and replies: google/eng-practices@master:review/reviewer/comments.md
- Commit subjects: conventional-commits/conventionalcommits.org@master:content/v1.0.0/index.md
- Length, proof and reply numbers:
  `SOURCE: original (private-repo PR communication survey: 120 human PRs, 251 inline review comments)`.
