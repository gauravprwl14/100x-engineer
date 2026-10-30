# Workstream: album-comments (brief, 100x work)

Goal: ship album comments (backend, frontend, settings) as separate PRs.

| PR | branch | role | base | state |
|---|---|---|---|---|
| #1 | feat/comments-backend | backend API | main | open, CI green |
| #2 | feat/comments-frontend | frontend UI | feat/comments-backend | open, CI green |
| #3 | feat/comments-settings | settings toggle | main | open, CI green |

Merge order: #1, then #2, then #3.

Holds:
- #3: do not push (hold by gaurav, 2026-10-29: waiting for product sign-off on the default value).
- `integration` branch: merge-only; never commit feature changes there.

Decisions:
- D1 departed users are displayed as the constant `RETIRED_USER_LABEL` ("退会済みユーザー"), never null.
- D2 stamp list cache TTL is 1 hour.

Conventions: backend code lives under `api/`, frontend under `web/`, settings under `settings/`; every fix goes to the branch that owns the file.

Open questions: none.
