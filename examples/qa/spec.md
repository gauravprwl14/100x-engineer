# Photo tagging — spec

| field | value |
|---|---|
| feature | photo-tagging |

Fixture for `100x testplan`: five acceptance criteria, an implicit-requirements
table, and a `tests/` tree that covers only AC-1 and AC-2 on purpose. Tests tag
`photo-tagging/AC-<n>`. AC-4 is named only in a fixtures file, which `trace` must not
count, and AC-3 only by a bare `AC-3` tag, which it reports as not counted.

## Acceptance criteria

AC-1: A member can tag up to 10 people on a photo from the photo page.
AC-2: Only the album owner can delete a tag.
AC-3: A draft album moves to published once the owner confirms.
AC-4: A tag comment must be between 1 and 280 characters.
AC-5: Tagged people receive a notification within 60 seconds.

AC-2 depends on AC-1 (a tag must exist before it can be deleted); this line
mentions ids but defines nothing.

## 0b. Implicit requirements

| id | requirement | class |
|---|---|---|
| `web.reflow-320` | no horizontal scroll at 320 CSS px | A |
| `a11y.wcag22-aa` | WCAG 2.2 AA, axe-clean | A |
| `api.p95-budget` | p95 latency under 300 ms at the declared tier | B |
| `api.authz-every-endpoint` | every endpoint checks the actor's tenant | A |
