# Decision index

2 decision(s). Regenerate with `python3 scripts/decide.py index`.

| id | title | status | date | chosen | assumptions | tags | affects |
|---|---|---|---|---|--:|---|---|
| [ADR-0001](ADR-0001-session-strategy-for-login.md) | Session strategy for login | accepted | 2026-09-29 | Opaque server session id in an httpOnly cookie | 3 | backend, auth | `examples/login/**` |
| [ADR-0002](ADR-0002-gh-cli-for-pr-review-confined-to-skill-steps.md) | gh CLI for pr-review, confined to skill steps | accepted | 2026-10-10 | gh CLI, called only from SKILL.md / references steps | 3 | dependency, safety | `skills/pr-review/**, docs/SAFETY.md, scripts/pr_*.py` |

## How to use this

- `decide.py verify` runs every assumption's verification command.
- `decide.py drift` lists decisions whose `affects` paths changed since the decision was recorded — those need re-reading, not just re-running.
- `decide.py trace <path>` says which decisions govern a file.
- A decision is never edited in place once `accepted`; supersede it with a new record and set `supersedes`.
