---
name: qa-strategy
description: >
  Test plan, QA, is it tested enough: acceptance criteria → tests from a PRD or spec,
  unit/integration/e2e/visual/a11y/load portfolio, traceability, flaky-test quarantine. Not for
  one function's cases (→ test-design).
---

# QA strategy

`test-design` picks good cases for one unit. This skill decides **which kinds of
tests a feature needs at its tier, and proves every acceptance criterion has one**.
The gap it closes is the AC that a spec promised and no test checks: across 72 JS/TS
production repos the corpus found a patch-coverage gate in 1 and mutation testing in
0 (`research/30-findings-js-verification.md`), so a green suite says nothing about
whether the spec's outcomes were tested at all.

## Trigger

**Fire when:** a spec or PRD has `AC-<n>` acceptance criteria and tests are about to
be written; someone asks for a test plan, QA pass, regression suite, e2e, visual,
accessibility, load or smoke tests; a reviewer asks "is this tested enough"; a
release is being prepared and nobody can list which ACs are covered.

**Do not fire when:** the question is which boundary values one function needs
(`test-design`), which runner/lint commands a language uses (`language-verification`), or
how a deploy is staged (`release-rollout`). A one-line bug fix needs a regression
test (`bug-fix`), not a test plan.

`<root>` is the records root: `docs/engineering/` by default, or `.100x.json`
`{"root": "..."}` at the git root, or `HUNDREDX_ROOT_DIR` (`docs/OPERATING-MODEL.md` §8).

## Portfolio by work type and tier

Tiers are `scripts/data/scale_tiers.json`'s. A cell names the level that must exist;
`—` means not required at that tier. WCAG 2.2 AA applies at every tier.

| level | web-ui | mobile | api/backend | from tier |
|---|---|---|---|---|
| unit (logic, boundaries) | yes | yes | yes | prototype |
| integration, real DB via testcontainers | — | — | yes | prototype |
| contract (consumer-driven) | if a separate API team | if a separate API team | per consumer | small |
| e2e, critical journeys only | Playwright | Maestro | API-level journey | small |
| a11y: axe in CI + manual keyboard/screen-reader | yes | manual + platform scanner | — | prototype |
| responsive overflow 320/768/1280 | yes | font scale max | — | prototype |
| visual vs approved baselines | yes | screenshots per flow | — | small |
| post-deploy smoke | yes | yes | yes | small |
| DAST baseline (ZAP, passive) | yes | — | yes | small |
| load with SLO thresholds | — | — | yes | growth |
| mutation on changed code | yes | yes | yes | growth |
| exploratory charter per risky area | yes | yes | yes | small |

## Rules

1. **Every acceptance criterion has at least one test tagged with its id.** Put
   `AC-<n>` in the test name, a comment, or an annotation (`{ tag: '@AC-3' }`,
   Maestro `tags:`). A tag in a helper, fixture, commented-out test or skipped test
   does not count. An AC no test names is the gap this skill exists to close.
   *Enforced by:* `100x testplan trace <spec> --tests <dir>[,dir2]` (exit 1 on any
   uncovered AC)

2. **Derive the plan from the ACs before writing tests.** Each AC gets a valid
   partition, an invalid partition, boundary rows for every number in its wording,
   authz rows when it names an owner or role, legal and illegal transitions when it
   names states, plus one row per implicit requirement (§0b ids such as
   `web.reflow-320`). A spec with no AC ids cannot be planned. Only defining lines
   count — `AC-<n>: <observable outcome> (R<k>, S<k>)` in spec §2b — so a mention
   such as "see AC-3" is never a criterion.
   *Enforced by:* `100x testplan new <spec> --out [path]` (exit 1 when the doc has
   no `AC-<n>` lines, with the format to use; bare `--out` writes
   `<root>/testplans/<feature>.md`)

3. **Shape the portfolio by risk, not by default ratios, and never invert it.** E2E
   covers only the critical journeys (sign-in, the primary/money path, the one
   destructive action) — typically 3-10 tests, not one per AC. Google's guidance is
   a pyramid with roughly 70/20/10 unit/integration/e2e as a starting shape; an
   e2e-heavy "inverted pyramid" gives slow, flaky, undiagnosable feedback.
   *Enforced by:* review

4. **Integration tests hit a real database, started per run with testcontainers**,
   not a mocked repository: a mock cannot catch a wrong query, a missing index
   constraint or a migration that does not apply.
   *Enforced by:* review

5. **Visual regression compares against approved baselines, and a baseline changes
   only with a linked design approval.** Mask dynamic regions, disable animations,
   set `maxDiffPixelRatio`. Running `--update-snapshots` to make CI green is the
   failure, not the fix (`templates/qa/visual.spec.ts`).
   *Enforced by:* `npx playwright test --grep @visual` (non-zero on a diff over the
   ratio) plus review of every changed `*.png` in the PR

6. **Axe runs in CI with `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` and fails on
   any violation**, at every tier. No allowlist of known violations.
   *Enforced by:* `npx playwright test --grep @a11y` (`templates/qa/a11y.spec.ts`)

7. **No horizontal overflow at 320, 768 and 1280 CSS px**:
   `document.documentElement.scrollWidth <= clientWidth` per critical route.
   *Enforced by:* `npx playwright test --grep @responsive`
   (`templates/qa/responsive.spec.ts`)

8. **Load tests, at growth and above, carry thresholds taken from the spec's SLO or
   perf budget** — `http_req_duration: ['p(95)<N']`, `http_req_failed: ['rate<E']` —
   so a breach exits non-zero. A load test with no thresholds is a graph, not a test.
   SLO numbers are a C decision: ask, never invent them.
   *Enforced by:* `k6 run -e SCENARIO=load templates/qa/load.k6.js` (non-zero exit on
   a failed threshold)

9. **Every deploy runs a smoke check**: health endpoint plus one critical read,
   failing the pipeline on the first error.
   *Enforced by:* `bash templates/qa/smoke.sh` in the deploy job (exit 1 on failure)

10. **A DAST baseline runs against a deployed environment from the small tier.** It
    is passive (no attacks) and takes minutes, so it fits every release.
    *Enforced by:* `docker run -t ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t <url>`
    (non-zero on FAIL)

11. **Mutation testing runs on changed code from the growth tier**, with a break
    threshold, so tests that cannot fail are caught where they were just written.
    *Enforced by:* `npx stryker run --incremental` with `thresholds.break` set
    (exit 1 below it); Python: `mutmut run` on the changed paths

12. **Flaky tests are quarantined with an owner and an expiry, never retried
    silently or deleted.** One CI retry; a pass-on-retry is reported as flaky
    (`templates/qa/flaky-test-policy.md`).
    *Enforced by:* convention

13. **Each risky area gets a timeboxed exploratory charter** — new integrations,
    money, permissions, data migration — using `templates/qa/exploratory-charter.md`.
    *Enforced by:* convention

14. **Test on the declared device/browser matrix.** Web defaults to Browserslist
    `defaults`; mobile minimum OS is the user's call and is printed as `ASK`.
    *Enforced by:* `100x testplan matrix --work web-ui|mobile --tier <tier>` (prints
    the matrix and the open ASK items) plus review

## Verify

```bash
# AC -> test traceability (~0.2s); exit 1 lists every uncovered AC with the fix
100x testplan trace <root>/specs/<feature>/spec.md --tests e2e,backend/test
100x testplan trace <root>/specs/<feature>/spec.md --tests e2e --json
# first-draft plan from the ACs (exit 1 if the spec has none); bare --out files it
# at <root>/testplans/<feature>.md
100x testplan new <root>/specs/<feature>/spec.md --out
100x testplan matrix --work web-ui --tier small
# the project's own suites, from templates/qa/ (minutes; needs Playwright, k6)
npx playwright test --grep "@critical|@a11y|@responsive|@visual"
k6 run -e SCENARIO=smoke -e BASE_URL=http://localhost:3000 templates/qa/load.k6.js
# the tool's own regression suite
bash tests/test_testplan.sh
```

## Failure modes

This skill rejects:

- **An AC with no test.** `AC-4: comment is 1-280 characters` and the only `AC-4`
  in the repo is `COMMENT_MAX = 280  # AC-4` in a fixtures file — `trace` reports it
  UNCOVERED, because a constant is not a test.
- **A test that cannot fail counted as coverage**: `// test('AC-3 publishes', ...)`
  commented out, or `test.skip('AC-5 ...')`. Both are ignored by `trace`; the skipped
  one is listed as "skipped — does not count".
- **E2E for everything**: forty Playwright tests, one per AC, taking twenty minutes
  and failing on timing — the inverted pyramid. Move the boundary rows down to unit.
- **Screenshot baselines updated blindly**: a PR that adds `--update-snapshots`
  output with no design link. The diff it hides is the regression.
- **A load test without thresholds**: `k6 run` that always exits 0 whatever p95 is.
- **An axe scan with an "allowed violations" list** that only ever grows.
- **Mobile tested on whatever simulator was open**, with no agreed minimum OS.

**Honest limitations.** `trace` proves an id is named by a live test, not that the
test asserts the AC's outcome — pair it with `test-design` and review. Its
commented-out detection is line-based: a comment run that contains code (a test
call, `expect(`, `assert`, a trailing `;`/`{`/`}`) is treated as dead. `new` reads
wording, not meaning: it over-generates rows for a human to prune.

## Hand-offs

`test-design` chooses the concrete cases inside each row. `verification-gate` binds
the passing suite to the exact code with a receipt. `release-rollout` owns canary
and the decision to roll back on a failed smoke. `accessibility` owns the manual
WCAG audit cadence; `performance-budgets` owns where the SLO numbers come from.

## Scale

`solo` / prototype: rules 1, 2, 6, 7 — traceability and a11y cost minutes.
`small-team (2-10)` / small: add 3, 4, 5, 9, 10, 12, 13, 14. `org (10+)` / growth:
add 8 and 11. `high-blast-radius` / scale: soak and stress scenarios per release,
and exploratory charters before every change to money or permissions.

## Sources

- Patch-coverage gate 1/72 and mutation testing 0/72 JS/TS repos:
  `research/30-findings-js-verification.md`.
- Pyramid, ~70/20/10 starting shape, inverted pyramid: Mike Wacker, "Just Say No to
  More End-to-End Tests", Google Testing Blog, 2015,
  https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html
- Flaky rates (1.5% of runs, ~16% of tests): John Micco, Google Testing Blog, 2016,
  https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
- Testcontainers, throwaway real databases in tests: https://testcontainers.com/
- `toHaveScreenshot` options (`threshold`, `maxDiffPixelRatio`, `mask`, `animations`):
  `microsoft/playwright` docs, https://playwright.dev/docs/api/class-pageassertions
- `AxeBuilder.withTags`, `wcag22aa` tag: https://playwright.dev/docs/accessibility-testing,
  `dequelabs/axe-core@develop:doc/API.md`
- WCAG 2.2 SC 1.4.10 Reflow at 320 CSS px: https://www.w3.org/TR/WCAG22/#reflow
- k6 thresholds and non-zero exit on breach, scenarios/executors:
  https://grafana.com/docs/k6/latest/using-k6/thresholds/
- ZAP baseline scan, passive and short: https://www.zaproxy.org/docs/docker/baseline-scan/
- Stryker `--incremental` and `thresholds.break`:
  https://stryker-mutator.io/docs/stryker-js/incremental/
- Maestro flow syntax: https://docs.maestro.dev/
- Browserslist `defaults`: `browserslist/browserslist@main:README.md`
- Exploratory charters: Elisabeth Hendrickson, *Explore It!* (2013); session-based
  test management, Jonathan Bach and James Bach (2000).
- The portfolio-by-tier table, the 3-10 critical-journey range and
  `scripts/testplan.py`: `SOURCE: original`.
