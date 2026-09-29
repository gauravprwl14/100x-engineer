# Decision index

1 decision(s). Regenerate with `python3 scripts/decide.py index`.

| id | title | status | date | chosen | assumptions | tags | affects |
|---|---|---|---|---|--:|---|---|
| [ADR-0001](ADR-0001-session-strategy-for-login.md) | Session strategy for login | accepted | 2026-09-29 | Opaque server session id in an httpOnly cookie | 3 | backend, auth | `examples/login/**` |

## How to use this

- `decide.py verify` runs every assumption's verification command.
- `decide.py drift` lists decisions whose `affects` paths changed since the decision was recorded — those need re-reading, not just re-running.
- `decide.py trace <path>` says which decisions govern a file.
- A decision is never edited in place once `accepted`; supersede it with a new record and set `supersedes`.
