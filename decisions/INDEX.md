# Decision index

6 decision(s). Regenerate with `python3 scripts/decide.py index`.

| id | title | status | date | chosen | assumptions | tags | affects |
|---|---|---|---|---|--:|---|---|
| [ADR-0001](ADR-0001-session-strategy-for-login.md) | Session strategy for login | accepted | 2026-09-29 | Opaque server session id in an httpOnly cookie | 3 | backend, auth | `examples/login/**` |
| [ADR-0002](ADR-0002-gh-cli-for-pr-review-confined-to-skill-steps.md) | gh CLI for pr-review, confined to skill steps | accepted | 2026-10-10 | gh CLI, called only from SKILL.md / references steps | 3 | dependency, safety | `skills/pr-review/**, docs/SAFETY.md, scripts/pr_*.py` |
| [ADR-0003](ADR-0003-screen-pattern-checklists-are-keyed-by-behaviour-family-and-role-checks-are-section-7-rows.md) | screen-pattern checklists are keyed by behaviour family, and role checks are section 7 rows | accepted | 2026-10-30 | behaviour families plus a name-to-family map; role checks as section 7 rows with source role:<name> | 2 | screen-patterns | `scripts/data/edge_cases_ui.json, scripts/data/screen_patterns.json, scripts/plan_feature.py` |
| [ADR-0004](ADR-0004-shared-work-record-lives-in-an-opt-in-private-git-ref-refs-100x-work.md) | Shared work record lives in an opt-in private git ref refs/100x/work | rejected | 2026-10-30 | opt-in private ref refs/100x/work, per-PR claim refs updated with --force-with-lease | 3 | safety, work-continuity | `prds/work-continuity/**, scripts/work*.py, hooks/**` |
| [ADR-0005](ADR-0005-plugin-may-fetch-and-push-refs-100x-only-gh-stays-read-only-supersedes-adr-0002-scope.md) | Plugin may fetch and push refs/100x/* only; gh stays read-only (supersedes ADR-0002 scope) | rejected | 2026-10-30 | allow pushes to refs/100x/* and read-only gh in tools and hooks | 3 | safety, work-continuity | `docs/SAFETY.md, scripts/work*.py, hooks/**, skills/pr-review/**, scripts/pr_*.py` |
| [ADR-0006](ADR-0006-work-record-is-private-plain-files-in-config-100x-work-backed-up-by-the-owner-s-own-setup-the-plugin-never-pushes.md) | Work record is private plain files in ~/.config/100x/work, backed up by the owner's own setup; the plugin never pushes | proposed | 2026-10-30 | plain append-only files in ~/.config/100x/work, backed up by the owner's setup | 3 | safety, work-continuity | `prds/work-continuity/**, scripts/work*.py, hooks/**` |

## How to use this

- `decide.py verify` runs every assumption's verification command.
- `decide.py drift` lists decisions whose `affects` paths changed since the decision was recorded — those need re-reading, not just re-running.
- `decide.py trace <path>` says which decisions govern a file.
- A decision is never edited in place once `accepted`; supersede it with a new record and set `supersedes`.
