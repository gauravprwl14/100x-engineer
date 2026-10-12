# Focus checklists — generic

Reference for `pr-review` (loaded on demand). Paste the matching block(s) into the reviewer
prompt's `{{FOCUS}}`, together with:

| Source | What it adds | Who owns it |
|---|---|---|
| this file | stack-neutral lines that apply to any repo | the plugin |
| `$(100x root)/reviewers/<stack>.md` (routing in `stack-reviewer`) | framework failure modes — NestJS, Next.js/React, React Native, Flutter, native mobile, Kubernetes, IaC | the plugin |
| `<CR>/_meta/focus.md` | this repo's own lines: its tenancy key, its upstream clients, its folder conventions, its generated code | the user; grown from misses |

When a review finds a bug class none of these name, add one line to `<CR>/_meta/focus.md` (a
repo-specific class) after the report — never to this file, which an update replaces.

## Backend (any stack)

- Migration: real timestamp/version (no round numbers), order vs sibling branches, foreign keys and
  cascade rules for every parent (including parents created in another PR), the tenant key in
  indexes, `down()` reverses `up()`.
- Tenancy: every query (reads AND writes) scoped by the tenant key; access checked against the
  caller, not just the record id; cross-tenant → 404, not 403; ids taken from the verified token,
  never the body.
- Upserts: the same key twice in one statement fails on most databases — dedupe the input.
- Client IP from `X-Forwarded-For`: the trusted hop count matches the real proxy chain; the "no IP"
  path fails closed or logs.
- Removed log or context fields: grep the issue, spec and runbooks for anything that planned to
  read them.
- Calls to another service: only through the repo's client layer; pass page size explicitly;
  timeouts; what happens when the call fails AFTER our own DB write (duplicate on retry?).
- Rich/JSON input: schema-validated server-side; allowed node types/attrs/URL schemes; size limits.
- Guard order: feature flag before auth; the flag's config line is actually present.
- Response shape changes on an existing endpoint: every endpoint returning that type fills the new
  fields; the API description (OpenAPI etc.) is updated.
- Tests: at least one test against the real database engine; populated (non-empty) data paths;
  concurrency.

## Frontend (any framework)

- Spec states: empty / loading / error / no-permission (hide controls for view-only) / deleted user
  / limits.
- Data hooks: stale-response guard, fetch on open not on mount, refresh sibling instances after a
  modal closes, optimistic update + rollback, pagination by cursor not local length.
- Rendering user content: raw-HTML injection, `<img src>` from content, link `href` schemes, paste
  handling.
- IME (CJK input) + Enter-to-send; keyboard navigation; focus trap; aria; mobile modal shape.
- Portals / z-index inside nested views.
- Is the component actually mounted on a page in THIS PR?
- Duplicated components vs sibling branches — diff the copies, list one-sided fixes.
- Generated clients not hand-edited; the API description matches the backend it sits on; CI green.
- Bundle: heavy libraries (editors, charts) lazy-loaded.

## Spec / PRD

- Same rule stated in several docs (PRD, translations, spec, API reference, open questions) → all
  agree?
- Every "decided"/"resolved" item matches code; old wording grepped and removed everywhere.
- Edge cases: deleted/deactivated users, permission revoked, cascades, notifications, moderation,
  limits, i18n, mobile, a11y, rollout flag.
- Each requirement testable (acceptance criteria, numbers).

## PR hygiene (every PR)

- `git log` for merges of other feature branches, revert-of-merge, revert-and-reapply churn.
- Branch behind its base? `git merge-tree` against sibling PRs for conflicts.
- Backend and frontend in separate PRs when the repo does that; the PR description is still true.
- Tracker rows claiming "fixed" → verify in code.
- Evals/tests that count any non-zero exit as "detected" — a crash passes. Assert the message.
- Gates/linters that read policy from a copy the checked agent can edit, or fail open when a helper
  (git, parser) errors.
- The same parser (status, glob, argv screen) copied across files → feed one input to every copy
  and diff.
