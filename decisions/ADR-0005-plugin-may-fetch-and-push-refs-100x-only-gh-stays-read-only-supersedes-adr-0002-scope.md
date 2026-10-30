# ADR-0005: Plugin may fetch and push refs/100x/* only; gh stays read-only (supersedes ADR-0002 scope)

```json meta
{
  "id": "ADR-0005",
  "title": "Plugin may fetch and push refs/100x/* only; gh stays read-only (supersedes ADR-0002 scope)",
  "status": "rejected",
  "date": "2026-10-30",
  "decided_by": "gaurav",
  "tags": [
    "safety",
    "work-continuity"
  ],
  "affects": [
    "docs/SAFETY.md",
    "scripts/work*.py",
    "hooks/**",
    "skills/pr-review/**",
    "scripts/pr_*.py"
  ],
  "commit": "ff58242",
  "assumptions": [
    {
      "id": "A1",
      "claim": "Every git push in plugin tools and hooks targets refs/100x/* only",
      "verify": "! (grep -rnE '\\[\"git\"[^]]*\"push\"' scripts/[a-z]*.py hooks/*.py | grep -v 'refs/100x/')",
      "revisit_when": "a tool needs to push anything outside refs/100x/*",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "gh calls in tools and hooks are read-only (no POST/PATCH/PUT/DELETE, no pr comment/review/merge/edit)",
      "verify": "! grep -rnE '\\[\"gh\"[^]]*(\"-X\", *\"(POST|PATCH|PUT|DELETE)\"|\"(comment|review|merge|edit|create|ready)\")' scripts/[a-z]*.py hooks/*.py",
      "revisit_when": "a request for a tool or hook to write to GitHub",
      "confidence": "high"
    },
    {
      "id": "A3",
      "claim": "pr-review still writes to GitHub only in post, after an explicit yes (carried over from ADR-0002 A2)",
      "verify": "! grep -nE 'gh (api[^|]*-X (POST|PATCH|PUT|DELETE)|pr (comment|review|merge|edit))' skills/pr-review/references/workflow.md && grep -q 'Anything but an explicit yes = post nothing' skills/pr-review/references/adjust-and-post.md",
      "revisit_when": "a request to post automatically is accepted",
      "confidence": "high"
    }
  ],
  "options": [
    {
      "name": "keep ADR-0002: no push and no gh in tools; all syncing in skill steps with an explicit yes",
      "fit": "fail",
      "chosen": false,
      "why_not": "every resume, claim and note would need a manual approval, which recreates the decision fatigue the work-continuity PRD exists to remove"
    },
    {
      "name": "allow pushes to refs/100x/* and read-only gh in tools and hooks",
      "fit": "pass",
      "chosen": true,
      "why": "the smallest widening that lets hooks sync the work record and read live PR facts, with both limits checkable by grep"
    },
    {
      "name": "allow general git push and gh writes in tools",
      "fit": "pass",
      "chosen": false,
      "why_not": "widens the blast radius to branches and GitHub state for no requirement in the PRD"
    }
  ],
  "supersedes": "ADR-0002",
  "revisit_by": "2027-04-01"
}
```

## Context

**Rejected 2026-10-30:** the owner requires that nothing about the work record reaches a team repository. Superseded by ADR-0006.


`docs/SAFETY.md` promises the plugin never runs `git push` and no tool sends anything off the
machine; ADR-0002 kept `gh` inside the pr-review skill's steps. The work-continuity PRD needs hooks
to fetch and push the shared work record (ADR-0004) and to read live PR facts. The owner agreed on
2026-10-30 to widen the promise narrowly.

## Options considered

### Option A — keep ADR-0002 as is
Fails fit: syncing would need a yes on every step.

### Option B — push only `refs/100x/*`, `gh` read-only (chosen)
Downside: tools now touch the network; `gh` becomes a runtime dependency of the work commands, so
they must degrade to local mode when `gh` is missing or unauthenticated.

### Option C — general push and `gh` writes
Rejected: no requirement needs it.

## Decision

Option B. Tools and hooks may `git fetch`/`git push` only `refs/100x/*` and may call `gh` only for
reads. Everything else from ADR-0002 stands: pr-review posts only in `post`, as a draft, after an
explicit yes.

## Consequences

Easy: automatic sync and live PR facts. Status stays `proposed` until the phase 0 spike passes; ADR-0002 is marked `superseded` in the same PR that ships the first push or `gh` call. Hard: `docs/SAFETY.md` must be revised in the same PR that
first adds a push or `gh` call to a tool (contract task); tests need a temporary bare remote and a
`gh` stub; hooks must time out and fail open on network trouble.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| `docs/SAFETY.md` still states the old promise until the first implementation PR | docs and decision disagree for a while | accepted | contract task in the work-continuity spec |
| grep checks see single-line argv lists only (`["git", …, "push"`) | a push or gh write built across lines or from variables escapes A1/A2 | accepted | review, plus a unit test that the push helper rejects other refs |
