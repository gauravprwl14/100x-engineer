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

Baseline ids as `plan_feature new` writes them. The evidence column names tools on
purpose (axe, k6, web-vitals, screenshots) that are NOT how the row is tested:
`testplan new` must take each level from the requirement, never from the evidence.

| id | default | status | evidence |
|---|---|---|---|
| web-ui.reflow-320 | content reflows at a 320 CSS px wide viewport with no two-dimensional scrolling | covered | e2e/responsive.spec.ts |
| web-ui.contrast-and-targets | text contrast >= 4.5:1, UI component contrast >= 3:1, pointer targets >= 24x24 CSS px | covered | e2e/a11y.spec.ts |
| web-ui.analytics-consent | non-essential analytics and tracking load only after opt-in consent | covered | k6 run shows no tracker request before consent |
| api.health-graceful-shutdown | separate liveness and readiness endpoints; SIGTERM drains in-flight work before exit | covered | axe scan of the status page is clean too |
| api.boundary-validation | every input is validated at the trust boundary for type, range, length and format, with explicit size limits | covered | web-vitals unaffected by the validation layer |
| all.tests-in-same-change | tests ship in the same change as the code, and they are deterministic (no sleeps, no wall-clock, no network) | covered | visual snapshots updated in the same PR |
| api.authz-every-endpoint | every endpoint checks the actor's tenant | covered | api/test_tag_delete.py |
| api.p95-budget | p95 latency under 300 ms at the declared tier | accepted | measured in staging |
| api.rate-limit | per-client rate limiting at the gateway, returning 429 with Retry-After | n/a(internal API behind the gateway's own limit) | — |
| web-ui.seo-meta | public, indexable pages carry a unique title, a meta description and a canonical URL | waived(album pages are private) | — |
| ask.data-residency | ASK: In which country or region must personal data be stored and processed? | ASSUMED(Tokyo region) | — |
