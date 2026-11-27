# ADR-0010: pr-review runs a structure pass inside the PR reviewer, switchable per repo

```json meta
{
  "id": "ADR-0010",
  "title": "pr-review runs a structure pass inside the PR reviewer, switchable per repo",
  "status": "accepted",
  "date": "2026-11-27",
  "decided_by": "gaurav",
  "tags": [
    "pr-review"
  ],
  "affects": [
    "skills/pr-review/**"
  ],
  "commit": "a25cb79",
  "assumptions": [
    {
      "id": "A1",
      "claim": "The PR reviewer prompt loads the structure pass, so a review run can apply it",
      "verify": "grep -q structure-pass.md skills/pr-review/references/reviewer-prompt.md",
      "revisit_when": "the reviewer prompt is restructured",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "The gate accepts STR items and the two new coverage rows, so the pass needs no gate change",
      "verify": "bash tests/test_pr_review.sh",
      "revisit_when": "the gate starts whitelisting item prefixes or coverage dimensions",
      "confidence": "high"
    },
    {
      "id": "A3",
      "claim": "The pass names the diff-review questions it relies on, so a reader can trace each check to its source",
      "verify": "grep -q 'R1, R2, R8' skills/pr-review/references/structure-pass.md",
      "revisit_when": "diff-review renumbers its R-questions",
      "confidence": "high"
    }
  ],
  "options": [
    {
      "name": "New Structure lens (a separate agent, like Design and Scenario)",
      "fit": "pass",
      "chosen": false,
      "why_not": "Adds an agent against the 10-agent cap, its own fragment, merge, cap and gate rules; the PR reviewer already reads every changed file."
    },
    {
      "name": "Structure pass inside the PR reviewer, off switch in settings.json",
      "fit": "pass",
      "chosen": true,
      "why": "One reference file and four pointers; no code, gate or schema change; reverting is one commit or one settings key."
    },
    {
      "name": "Do nothing and keep adding the points by hand on GitHub",
      "fit": "fail",
      "why_not": "Four sampled PRs show the same structure, naming and placement comments added by hand; the cost recurs on every review."
    }
  ],
  "supersedes": null,
  "revisit_by": null
}
```

## Context

Reviewing the reviews of PRs 1836, 1504, 1479 and 1707 in the tunag-albums review folder showed the same pattern: the points added by hand on GitHub were about approach, naming, placement and readability (one subclass instead of four wrappers, a file named after a UI term, a helper with no caller). The reviewer prompt pointed only at diff-review rules 9-16 (process), so R1, R2, R8 and code-craft were never loaded, the coverage table had no row for structure, and the Design lens challenged only one-way doors.

## Options considered

### Option A — New Structure lens
A fourth agent next to Design and Scenario. Not chosen: it costs an agent slot and needs fragment, merge, cap and gate changes for a check the PR reviewer can do while it already reads every file.

### Option B — Structure pass inside the PR reviewer
Chosen. Described in `skills/pr-review/references/structure-pass.md`: how this repo would build it, closest analog, a shape table, at most five `STR` items.

### Option C — Do nothing
Not chosen: the hand-added comments recur on every review.

## Decision

Option B. The deciding factor is reversibility: it is additive text plus one settings key (`"structure_pass": false`), so a bad result is undone without touching the gate or the schema.

## Consequences

Reviews gain up to five structure items and two coverage rows; the Design lens also asks why a cheap-to-undo choice with a simpler alternative was not made now. Structure comments depend on the reviewer finding the closest analog by grep, so a repo with few siblings gets fewer. No recall measurement exists yet: the bench runs plain reviews, not `/pr-review`, and a billed run was not made.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| Whether earlier misses were a prompt gap or a model limit is not tested | the pass may change little | accepted, not planned | compare `STR` items with the hand comments on the next real PRs |
| No recall eval for structure findings | a regression in the pass is not caught offline; only wiring and gate acceptance are tested | accepted, not planned | measure on the next real PRs by comparing posted hand comments with `STR` items |
| Hand comments are not fed back into `_meta/focus.md` | the same miss can recur in a repo-specific form | accepted, not planned | a `learn` command was proposed and left out |
