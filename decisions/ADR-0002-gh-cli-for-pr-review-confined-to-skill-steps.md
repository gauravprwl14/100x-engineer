# ADR-0002: gh CLI for pr-review, confined to skill steps

```json meta
{
  "id": "ADR-0002",
  "title": "gh CLI for pr-review, confined to skill steps",
  "status": "accepted",
  "date": "2026-10-10",
  "decided_by": "gaurav",
  "tags": [
    "dependency",
    "safety"
  ],
  "affects": [
    "skills/pr-review/**",
    "docs/SAFETY.md",
    "scripts/pr_*.py"
  ],
  "commit": "38a47f5",
  "assumptions": [
    {
      "id": "A1",
      "claim": "No user-facing tool under scripts/ runs gh; every gh call lives in the pr-review skill's steps",
      "verify": "! grep -lE '\\[\"gh\",' scripts/[a-z]*.py",
      "revisit_when": "a tool needs GitHub data that a skill step cannot pass it as a file or argument",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "The review and adjust steps contain no gh command that writes to GitHub; the only write is in post, after an explicit yes",
      "verify": "! grep -nE 'gh (api[^|]*-X (POST|PATCH|PUT|DELETE)|pr (comment|review|merge|edit))' skills/pr-review/references/workflow.md && grep -q 'Anything but an explicit yes = post nothing' skills/pr-review/references/adjust-and-post.md",
      "revisit_when": "a request to post automatically, or to resolve or react to threads, is accepted",
      "confidence": "high"
    },
    {
      "id": "A3",
      "claim": "gh is already installed and authenticated per host by the people who review PRs on GitHub or GitHub Enterprise",
      "verify": "",
      "revisit_when": "users report the skill unusable without gh, or a host gh cannot log in to",
      "confidence": "medium"
    }
  ],
  "options": [
    {
      "name": "gh CLI, called only from SKILL.md / references steps",
      "fit": "pass",
      "chosen": true,
      "why": "scripts stay Python stdlib + git and never touch the network beyond git fetch; gh already owns per-host auth, so GitHub Enterprise needs no token handling here"
    },
    {
      "name": "urllib calls to the GitHub REST API inside scripts/",
      "fit": "pass",
      "chosen": false,
      "why_not": "needs a token store and per-host API base derivation reimplemented in this plugin, and puts a network-writing code path inside scripts/, which docs/SAFETY.md promises never sends anything"
    },
    {
      "name": "gh invoked via subprocess inside scripts/",
      "fit": "pass",
      "chosen": false,
      "why_not": "adds a non-stdlib runtime dependency to tools that must run anywhere (AGENTS.md rule 12) and makes every pr_* test need a gh mock"
    },
    {
      "name": "no posting: the user pastes comments by hand",
      "fit": "fail",
      "chosen": false,
      "why_not": "drops the draft-review post and the lost-summary recovery the workflow exists for"
    }
  ],
  "supersedes": null,
  "revisit_by": "2027-04-01"
}
```

## Context

`pr-review` reads PR metadata, issues, existing comments and review threads, and posts a draft
review. All of that is GitHub API traffic, per host (github.com and GitHub Enterprise). This plugin
promises that its tools use only the Python standard library and git and that nothing it runs
sends data off the machine (AGENTS.md rule 12, `docs/SAFETY.md`). A dependency on `gh` and one
network write had to be admitted somewhere, deliberately, rather than leak into `scripts/`.

## Options considered

### Option A — `gh` from skill steps only (chosen)
The agent runs `gh` exactly as written in `skills/pr-review/` and passes results to the tools as
files and arguments. Downside: the skill is unusable without `gh` and a login per host, and no
script can check that the agent followed the post rule; that rests on review and on the steps
being written as one explicit-yes gate.

### Option B — urllib in `scripts/`
Stdlib, so technically within rule 12. Rejected: it reimplements auth and GHE base URLs, and puts
a network-writing path inside the tools whose read-only boundary `safety_audit` enforces.

### Option C — subprocess `gh` in `scripts/`
Rejected: a hidden runtime dependency in tools that must run anywhere, and every test needs a mock.

### Option D — never post
Fails fit: posting the adjusted review as a draft is the end of the workflow.

## Decision

Option A. `gh` is an allowed dependency of the `pr-review` skill's steps and of nothing else;
`scripts/pr_*.py` stay stdlib + git (their only network use is `git fetch` in `pr_snapshot`).
The plugin writes to GitHub in exactly one place: `post`, after the user has seen the exact
payload and answered yes; the default is a draft review, never `APPROVE`/`REQUEST_CHANGES` unless
named.

## Consequences

Easy: GHE works through `gh auth login --hostname`; tools stay testable offline. Hard: the post
boundary is a skill instruction, not code — `safety_audit` cannot see it, and the PreToolUse gate
does not intercept `gh api … /reviews`. `docs/SAFETY.md` states this exception so nobody reads
"never sends anything" as covering it.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| no mechanical check that `gh api -X POST` runs only after a yes | an agent ignoring the skill could post without asking | accepted, not planned | the draft default limits the damage: a draft is visible only to its author until submitted |
| `gh` version differences (`-q`, `--input`) | a step fails on an old `gh` | accepted | `gh auth status` in Verify surfaces a missing or broken install |
