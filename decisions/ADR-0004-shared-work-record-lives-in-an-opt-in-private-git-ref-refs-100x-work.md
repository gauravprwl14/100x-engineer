# ADR-0004: Shared work record lives in an opt-in private git ref refs/100x/work

```json meta
{
  "id": "ADR-0004",
  "title": "Shared work record lives in an opt-in private git ref refs/100x/work",
  "status": "rejected",
  "date": "2026-10-30",
  "decided_by": "gaurav",
  "tags": [
    "safety",
    "work-continuity"
  ],
  "affects": [
    "prds/work-continuity/**",
    "scripts/work*.py",
    "hooks/**"
  ],
  "commit": "ff58242",
  "assumptions": [
    {
      "id": "A1",
      "claim": "No plugin code writes the work record to a branch (refs/heads/*); it uses only refs/100x/*",
      "verify": "! grep -rnE 'refs/heads/100x|\"100x/work\"' scripts hooks --include=*.py",
      "revisit_when": "a host (GitHub, GHE, a git proxy) refuses pushes to refs outside refs/heads and refs/tags",
      "confidence": "medium"
    },
    {
      "id": "A2",
      "claim": "Shared mode is off unless a repo turns it on; the shipped default work.mode is not 'shared'",
      "verify": "! grep -rnE 'DEFAULT_MODE *= *.shared.' scripts --include=*.py",
      "revisit_when": "a request to make shared mode the default",
      "confidence": "high"
    },
    {
      "id": "A3",
      "claim": "A claude --cloud session loads the plugin's hooks, has gh auth, and may push refs/100x/*",
      "verify": "",
      "revisit_when": "the PRD's phase 0 cloud spike reports any of the three false",
      "confidence": "low"
    }
  ],
  "options": [
    {
      "name": "branch 100x/work",
      "fit": "pass",
      "chosen": false,
      "why_not": "a pushed branch can trigger on:push CI in teammates' repos, shows in branch lists, is touched by stale-branch bots, and is public on public repos"
    },
    {
      "name": "local files only (~/.100x/work)",
      "fit": "fail",
      "chosen": false,
      "why_not": "cloud sessions and teammates cannot read it, which is the core requirement (PRD R2)"
    },
    {
      "name": "GitHub tracking issue",
      "fit": "pass",
      "chosen": false,
      "why_not": "every note is visible to anyone with read access, body edits race (last writer wins), API rate limits; kept as the fallback if refs/100x/* is refused"
    },
    {
      "name": "opt-in private ref refs/100x/work, per-PR claim refs updated with --force-with-lease",
      "fit": "pass",
      "chosen": true,
      "why": "readable by every kind of session through git, does not trigger branch CI or appear in branch lists, and the per-PR ref gives a real compare-and-swap for claims"
    }
  ],
  "supersedes": null,
  "revisit_by": "2027-04-01"
}
```

## Context

**Rejected 2026-10-30:** the owner requires that nothing about the work record reaches a team repository. Superseded by ADR-0006.


The work-continuity PRD (`prds/work-continuity/prd.md`) needs state that outlives a session and is
readable from local, background, cloud and teammate sessions. The first draft put it on a branch;
the solution-architect review showed a branch triggers CI, is public on public repos, cannot be
withdrawn once fetched, and that one-file-per-event gives no real lock for claims. The owner
agreed on 2026-10-30 to an opt-in private ref instead.

## Options considered

### Option A — branch `100x/work`
Simple to inspect. Rejected: CI on every push, branch-list noise, stale-branch bots, public exposure.

### Option B — local files only
Private and simplest. Fails fit: cloud sessions and teammates cannot see it. Stays as the fallback
mode when the remote is unreachable.

### Option C — GitHub tracking issue
Human-readable on github.com. Rejected as primary: visibility, races on the body, rate limits.
Kept as the fallback store if a host refuses custom refs.

### Option D — opt-in private ref (chosen)
Events under `refs/100x/work`; one ref per claimed PR under `refs/100x/claims/<repo>/<n>`, updated
with `git push --force-with-lease` so only one claimant wins. Downside: custom refs are unfamiliar,
not shown in GitHub's UI, and need `git fetch origin 'refs/100x/*:refs/100x/*'` to be seen.

## Decision

Option D, off by default and turned on per repo (`.100x.json` `work.mode: shared`). Deciding
factor: it is the only option every kind of session can read through git without side effects on
teammates' CI or branch lists.

## Consequences

Easy: no CI cost, no branch noise, a real lock per PR, history in git. Hard: humans cannot browse
it on github.com (needs `100x work show`); a leaked secret needs a ref rewrite; hosts or proxies that
reject non-branch refs force the issue fallback.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| cloud sessions untested (A3) | the design does not work from the cloud | accepted until spike | PRD phase 0 |
| record is readable by anyone with repo read access | private notes are not private | accepted | `--private` keeps an event local (PRD Q2) |
| erasing a leaked secret needs a ref rewrite and teammates refetching | secret stays in clones already fetched | accepted | document the rewrite procedure in the spec |
