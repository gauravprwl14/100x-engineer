# Anti-Bloat in Practice: How Production Repos Actually Configure and Enforce It

Scope: `research/00-signal-rubric.md` Part D2/G. `research/23-findings-antibloat-enforcement.md` tested the
TOOLING in isolation (knip, ruff, vulture, mutation testing, etc.) on planted-violation scratch repos. This
document does not repeat that testing. It answers a different question: **what do real production repos in
the corpus actually configure, and is it enforced or decorative?** 46 repos were read directly (git clone
`--depth 1 --filter=blob:none` or `raw.githubusercontent.com`, no `gh api`), drawn from `worklists/antibloat.txt`
(D2-ranked) and `worklists/tier1.txt`, cross-referenced. Every claim below is `owner/repo@sha:path`; SHAs are
full where captured, short where the source gave only a short form, `HEAD` where the researching pass did not
capture one (flagged inline — treat those citations as slightly weaker).

---

## Coverage

Repos read, by cluster: **JS/TS frameworks/infra** — nrwl/nx, QwikDev/qwik, nuxt/nuxt, vitejs/vite,
babel/babel, eslint/eslint, jestjs/jest, cypress-io/cypress, remix-run/react-router, typeorm/typeorm,
tailwindlabs/tailwindcss, chakra-ui/chakra-ui, heroui-inc/heroui, element-plus/element-plus,
react-hook-form/react-hook-form, refinedev/refine, ant-design/ant-design, ToolJet/ToolJet,
facebook/react, facebook/lexical, angular/angular, sveltejs/svelte, eclipse-theia/theia, nestjs/nest.
**JS/TS apps** — grafana/grafana, supabase/supabase, TryGhost/Ghost, calcom/cal.com, actualbudget/actual,
mui/material-ui, mermaid-js/mermaid, facebook/docusaurus (not deep-read this pass), payloadcms/payload,
TriliumNext/Trilium, better-auth/better-auth, danny-avila/LibreChat, ueberdosis/tiptap,
excalidraw/excalidraw, vercel/next.js, monkeytypegame/monkeytype, hoppscotch/hoppscotch,
AmruthPillai/Reactive-Resume, makeplane/plane, marmelab/react-admin, prisma/prisma,
renovatebot/renovate, pnpm/pnpm, backstage/backstage. **Go** — vitessio/vitess, gravitational/teleport.
**Python** — mlflow/mlflow, apache/superset. **Ruby** — discourse/discourse. **PHP** — nextcloud/server.
**Agentic-dev tooling (own-engineering test)** — CherryHQ/cherry-studio, QwenLM/qwen-code,
ComposioHQ/composio, promptfoo/promptfoo.

**Method note:** this pass leans JS/TS-heavy because the antibloat worklist is JS/TS-heavy (41 of 45 entries).
The Go/Python/Ruby/PHP/agentic-dev sample is a single broad sweep (11 repos, ~1 hour of agent time each) and
is directionally reliable but thinner than the JS/TS sample — flagged per-finding below, not smoothed over.

---

## Dead-code gates: verbatim, blocking vs advisory

| Repo | Tool | Config / invocation | Status |
|---|---|---|---|
| `better-auth/better-auth@5e6c8bcadee9e59b8e8b76beeebaba965ff6e159` | knip | `pnpm lint:dependencies` → `knip && knip --production`, inside the required `lint` job | **BLOCKING** |
| `promptfoo/promptfoo@HEAD` | knip (`~6.27.0`) | `npm run knip -- --no-progress --reporter github-actions`, labeled "Check dependencies, unused files, and exports"; separate lockfile-integrity check | **BLOCKING** |
| `nrwl/nx@b94bedeed454577ed311543d32395cc417056d6d` | `no-restricted-imports` (not knip) | per-package `.oxlintrc.json`, e.g. `packages/devkit` blocks deep `nx/src/*` imports except via `devkit-internals`; plus `scripts/check-imports.js` (`process.exit(1)` on disallowed Angular imports), invoked via `nx affected --targets=lint,oxlint,...` and `run-many -t check-imports check-lock-files check-codeowners` | **BLOCKING** |
| `monkeytypegame/monkeytype@4bd46c6` | knip | `knip.json` fully configured across backend/frontend/packages workspaces, `"knip": "knip"` script exists | **ABSENT FROM CI** — not in `turbo.json` tasks, not in any workflow; a config that runs zero times |
| `vitessio/vitess@HEAD` | staticcheck (`"all"` minus 9 excluded checks) + `unused`/`prealloc`/`errcheck` via golangci-lint, `default: none` + explicit `enable:` list | `.golangci.yml` | **BLOCKING** |
| `nextcloud/server@HEAD` | Psalm | `psalm.xml`: `errorLevel="4"`, `errorBaseline="build/psalm-baseline.xml"`, **`findUnusedCode="false"`** | **BLOCKING on everything except dead code** — dead-code detection is deliberately off in a 4-strictness-tier setup that gates almost everything else |
| `apache/superset@HEAD` | ruff, `flake8-tidy-imports` | `select = [B,C,E,F,G,I,N,PT,Q,S,T,TID,W]`; `TID251` bans raw `json`/`simplejson` imports repo-wide, "Use superset.utils.json instead" | **BLOCKING** (substitution gate, not classic dead-code) |
| `TriliumNext/Trilium@f1ce041` | none run in CI | `dev.yml` runs only `Typecheck`; **ESLint never executes in any workflow** | **ABSENT** — architecture/dead-code discipline lives only in `CLAUDE.md` prose, which itself admits: *"only ESLint checks that and it isn't run locally, so sort by hand"* |
| `payloadcms/payload@2abfb9e2a7b8d4eead4ec39fd19237526d5908d3` | `audit-dependencies.yml` | cron-triggered only | **ADVISORY** — never gates a PR |

**The Psalm/nextcloud and knip/monkeytype cases are the sharpest finding in this section:** a fully-configured
dead-code tool that nobody wired to CI is functionally identical to no tool at all. Presence of a config file
in the repo tree is not evidence of enforcement — this is checked separately for every mechanism below.

---

## Size budgets with real numbers

The headline result: **among 8 size-sensitive published UI/editor libraries checked (chakra-ui, heroui,
tailwindcss, lexical, tiptap, element-plus, monkeytype, refine), not one has a size-limit or bundlewatch byte
budget wired into required CI.**

| Repo | Mechanism | Number | Status |
|---|---|---|---|
| `react-hook-form/react-hook-form@d62c62b8132a329f382417bfbdde70e22f2ee3a1` | bundlewatch | `"bundlewatch": {"files":[{"path":"./dist/index.cjs.js","maxSize":"15.0 kB"}]}` | **BLOCKING** (`build-test.yml`, no `continue-on-error` anywhere in `.github`) |
| `facebook/lexical@b8cd393` | custom test, `scripts/__tests__/integration/tree-shaking.test.mjs` | `expect(size).toBeLessThan(2048)` (narrow `createCommand` import), `expect(size).toBeGreaterThan(100 * 1024)` (sanity floor) | **BLOCKING only when triggered** — the workflow (`call-integration-tests.yml`) runs only behind an `extended-tests` label or an approving review, not on every PR |
| `element-plus/element-plus@92d3e8f` | `preactjs/compressed-size-action` | posts a PR-comment size delta, **no threshold configured** | **ADVISORY** (informational only) |
| `heroui-inc/heroui@a29f473` | `measure-bundle-size.mjs` / `bundle-sizes.json` | scripts exist, produce numbers | **NOT WIRED TO CI AT ALL** — not even a workflow step, purely a local script |
| `chakra-ui/chakra-ui@9611614`, `tailwindlabs/tailwindcss@fa81d69`, `ueberdosis/tiptap@aef3880` | — | — | **ABSENT** entirely; zero grep hits for size/budget/KB/bytes in any workflow |

Contrast with the wider ecosystem examples already sourced in `research/23`:
`ai/nanoid@main:package.json` (`"nanoid"` import capped at **127 B**), `clerk/javascript@main` bundlewatch
(`554KB`/`81KB`/`124.5KB`/`7KB`, quarter-KB precision). Those are real and cited there — this pass confirms
they are the exception, not the norm, even among libraries where size is a stated selling point.

---

## API-surface control

**Universal absence in this sample:** none of the 8 libraries checked for API-surface control
(chakra-ui, heroui, tailwindcss, lexical, tiptap, element-plus, monkeytype, refine) has a committed `.api.md`
golden file or `@microsoft/api-extractor` configured. `research/23` cites `microsoft/fluentui` doing exactly
this (`apiReport.enabled: true`) — it remains a real but rare pattern, not found again in this independent
sample.

What exists instead is weaker: type/export-shape correctness, not surface-diff review.

- `refinedev/refine@2352eb5:package.json`: `"attw": "lerna run attw --scope @refinedev/*"`,
  `"publint": "lerna run publint --scope @refinedev/*"` (also per-package, e.g.
  `packages/core: "publint": "publint --strict=true --level=suggestion"`). `.github/workflows/pull-request.yml`
  runs both unconditionally in the required `build` job. **BLOCKING** — but attw/publint catch broken
  CJS/ESM export maps, not an accidentally-widened public surface.
- `ueberdosis/tiptap@aef3880:scripts/check-package-exports.mjs`, run as `vp run check:package-exports` in
  `build.yml`/`publish.yml`: verifies `main`/`module`/`types`/`exports` paths exist on disk. **BLOCKING**,
  same caveat — existence check, not a signature diff.
- `facebook/lexical@b8cd393:scripts/validate-tsc-types.mjs`: fails if published `.d.ts` leaks internal
  `shared/*`/`scripts/*` imports. Wired only into `call-release.yml` (`build-release`/`prepare-release`), **not
  standard PR CI** — a real API-leak check that only fires at publish time, after the surface has already
  shipped in main.
- `backstage/backstage@77ccaee`: `build:api-reports:only --ci` + `verify-api-reference.js` at
  `ci.yml:124-127`, **BLOCKING**, no `continue-on-error` — the strongest API-surface gate found in this whole
  survey, using api-extractor's underlying report mechanism per-package.

**Finding:** committed golden-file API diffing (the strongest known mechanism per `research/23`'s own
testing) is present in exactly one repo across 9 checked here (`backstage`). Export-shape linting (attw,
publint, check-package-exports) is more common and easier to adopt, but it is a different, weaker guarantee —
it cannot catch a new exported function that is perfectly well-typed and perfectly unwanted.

---

## Dependency-addition friction: policy text + enforcement

**Universal absence, stated first because it is the headline:** across 8 repos checked specifically for this
(nrwl/nx, prisma, grafana, mui, better-auth, payloadcms, renovate, pnpm), **not one `CONTRIBUTING.md` contains
prose policy text on when adding a new dependency is or isn't acceptable**, and no generic
`.allowed-deps`-style allowlist file exists anywhere. `research/23` already found and cited the one prose
exception in the wider ecosystem (`ProjectMirador/mirador@master:CONTRIBUTING.md`, "Careful consideration
should be given..."); this independent sample of 8 found zero more examples. **Dependency friction, where it
exists at all, is expressed exclusively as mechanical config — never as reviewable prose.**

**`grafana/grafana@a00056576a4d0eea5c2b102fdd3a6827a3136d11` — the strongest, most unusual gate found in the
whole survey: per-dependency ownership, not an allowlist.** `go.mod` header: `// Direct requirements -- every
entry needs an owner`, every direct require carries a team comment, e.g.
`dario.cat/mergo v1.0.2 // @grafana/grafana-app-platform-squad`. `scripts/modowners/modowners.go:77-92` fails
on any new direct dependency with no assigned owner:
`errors.New("one or more newly added dependencies do not have an assigned owner - please assign a team as an owner")`.
Wired as **BLOCKING** at `.github/workflows/backend-code-checks.yml:77-78`
(`run: go run scripts/modowners/modowners.go check go.mod`). A second job,
`.github/workflows/modowners-reviewers.yml`, diffs base vs. PR `go.mod` to auto-request the owning squads as
reviewers — **ADVISORY** (review routing, not a build gate). Deliberately, `.github/CODEOWNERS:70-72` leaves
`/go.mod` and `/go.sum` *without* a CODEOWNERS entry: `# Empty owners so GitHub does not request a squad` — the
ownership signal lives in the file itself, not in GitHub's review-request mechanism, because a single
CODEOWNERS team can't express "this specific line is owned by this specific team." `/package.json`,
`/yarn.lock` *are* CODEOWNERS-gated to `@grafana/grafana-frontend-platform`.

**`gravitational/teleport@HEAD:.golangci.yml` — the most aggressive dependency denylist found, explicitly
tied to binary size.** 10+ named `depguard` rulesets. Binary-size-driven denials: `lib/auth`, `lib/cloud`,
`lib/web` are banned from client-tools code paths "to prevent increasing binary size." `logrus`,
`aws-sdk-go` v1, and `text/template`/`html/template` ("prevents DCE") are denied with forced replacements.
`testify`/`testing` denied outside `_test.go`. Enterprise (`/e/`) package imports denied outside `/e/`.
`forbidigo` separately bans specific unsafe call patterns (`rsa.GenerateKey`, raw `ssh.Dial`) repo-wide.
`issues.max-issues-per-linter: 0` — no cap, fully blocking. CODEOWNERS requires named reviewers on every
`go.mod` and `pnpm-lock.yaml` change. **The intent is there (protect binary size via import bans) but there is
no actual binary-size *measurement* gate anywhere in the repo** — the policy is enforced upstream of the
metric it's trying to protect, never checked against the metric itself.

**Independently converging on the same Go pattern** (already cited in `research/23` for Traefik/Prometheus):
`vitessio/vitess@HEAD:.golangci.yml` uses per-directory `depguard` to keep library packages
(`go/mysql`, `go/vt/sqlparser`, `go/vt/schemadiff`) importable without server infrastructure — denying them
`vitess.io/vitess/go/vt/servenv` and `github.com/spf13/pflag`, with the comment "component should be usable as
a library without server infrastructure." Four unrelated major Go repos (traefik, prometheus, teleport,
vitess) now converge on `depguard` as the real, running, CI-enforced answer to "stop this dependency from
creeping back in" — it is the single most production-proven mechanism in this entire document.

**Changesets as a forced-disclosure gate (JS monorepos):**
- `better-auth/better-auth@5e6c8bcadee9e59b8e8b76beeebaba965ff6e159:.github/workflows/verify-changesets.yml`
  fails any PR touching `packages/**` with no changeset:
  `echo "::error::Missing changeset. Add one with 'pnpm changeset' or add the 'skip-changeset' label."; exit 1`
  — **BLOCKING, with a label escape hatch.**
- `pnpm/pnpm@15a5da5864020375be4c46c905807364f0e941b2:CONTRIBUTING.md:287` requires `pnpm change` per patch;
  content (not just presence) is validated by `pn lint` in the required TS CI job — **BLOCKING on content**.
  Separately, `CONTRIBUTING.md:72`: the Cargo source-replacement block "changes only when a git-sourced
  dependency moves to a new revision... Rust CI fails if the two drift apart" — a drift check, not a
  dependency-addition gate per se, but the same mechanical family.

**A real allowlist, though narrowly scoped:** `payloadcms/payload@2abfb9e2a7b8d4eead4ec39fd19237526d5908d3:pnpm-workspace.yaml`
`allowBuilds:` restricts which dependencies may run postinstall scripts (`sharp: true`), enforced by the
`check-template-build-approvals` job in `main.yml`, triggered specifically by `pnpm-lock.yaml` diffs —
**BLOCKING**. This is a supply-chain-safety allowlist (which deps may execute code at install time), not a
"should this dependency exist" allowlist — no repo in the sample has the latter.

**Notable near-misses / absences:** `prisma/prisma@23ae73844ecc46da6607b41fb8d248c84f6e6fcb` has no dependency
gate at all (only an indirect size-limit required check). `mui/material-ui@22773ae0b2b6646faae2a5e6132a0de15bf7a600`
has **no CODEOWNERS file whatsoever**. `renovatebot/renovate@c94897829ce70369357da1a4b1755a4525758d4d` — the
bot whose entire product is dependency management — has no CODEOWNERS, no changesets, no lockfile-diff job,
and no import bans on its own repo; its only relevant PR-template line is an AI-usage disclosure requirement
(advisory). `apache/superset@HEAD:pyproject.toml` runs `tool.liccheck` — an allowed-*license* list for every
dependency (not a necessity check), with a `# TODO REMOVE THESE DEPS` GPL-exception list — license friction as
an anti-bloat proxy, a mechanism not seen anywhere else in this survey.

---

## Architectural boundary rules (verbatim)

**`eslint-plugin-boundaries` has essentially zero flagship adoption.** Zero hits across the 8 repos checked
specifically for it (Ghost, backstage, nx, nuxt, ant-design, qwik, mermaid, Trilium) — matching `research/23`'s
own gap note. Real boundary enforcement in production is almost entirely **hand-rolled**: custom ESLint rules,
`dependency-cruiser`, `no-restricted-imports`/`no-restricted-paths`, or Go's `depguard` repurposed for
in-repo layering (see previous section) — not the purpose-built plugin.

**`TryGhost/Ghost@7c30676:.dependency-cruiser.cjs` — the cleanest ruleset found, with rationale inline.**
Header: `"Architectural boundary rules for the monorepo, enforced on the resolved module graph (require AND
import)."` 11 rules at `severity: 'error'`, including:
```js
// frontend-to-server-via-proxy-only
// pathNot allowlist carries: "Adding files to this list is an anti-pattern"
//                             "Goal: Work down until only proxy.js remains"
```
and `admin-domains-cross-via-api-only`: *"may import a different domain only through that domain's public
surface (its api.ts)"*. **BLOCKING** — `ci.yml:434`: `run: pnpm nx run ghost-monorepo:lint:boundaries` inside
`job_lint`, a dependency of `job_required_tests`. The repo's own lint policy states the rationale for
error-only severity: `configs/eslint/index.mjs:10`: *"Every rule is 'error' or 'off' — never 'warn'. Warnings
get ignored by humans."* Ghost's Nx project **tags exist but constrain nothing** — the taxonomy
(`public-app`/`playwright`/`i18n`) is used only as a CI matrix selector; zero `depConstraints` reference them.

**`backstage/backstage@77ccaee` — a custom role-based layer plugin, escalated in-repo.**
`packages/eslint-plugin/rules/no-mixed-plugin-imports.js` encodes a role matrix verbatim:
`roleRules = [{ sourceRole: ['frontend-plugin','web-library'], targetRole: ['backend-plugin','node-library','backend-plugin-module','frontend-plugin'] }, …]`.
A second rule, `no-forbidden-package-imports`, enforces package `exports` maps — the JS/TS analogue of Go's
`internal/`. Shipped-to-users severity is `'warn'`
(`packages/eslint-plugin/index.js`), but the repo **escalates its own dogfood config to `'error'`** with a
named debt list: `.eslintrc.js:26`:
`'@backstage/no-mixed-plugin-imports': ['error', { /* TODO: Fix these… */ excludedTargetPackages: [...] }]`.
**BLOCKING and diff-scoped**: `ci.yml:308`: `yarn backstage-cli repo lint --since origin/master --success-cache`.
Notable dead lever: `lint:circular-deps` (`madge --circular .`) exists in `package.json` but **is never called
by any workflow** — configured, unenforced, identical to the knip/monkeytype pattern above.

**`nuxt/nuxt@7758942:eslint.config.mjs:177` — real named zone rules:**
```js
'import-x/no-restricted-paths': ['error', { zones: [
  { from: 'packages/nuxt/src/!(core)/runtime/*', target: 'packages/nuxt/src/core',
    message: 'core should not directly import from modules.' },
  { from: 'packages/nuxt/src/app/**/index.ts', target: 'packages/nuxt/src',
    message: 'should not import from barrel/index files' },
  { from: 'packages/nitro', target: 'packages/!(nitro)/**/*',
    message: 'nitro should not directly import other packages.' },
]}]
```
**BLOCKING**, no `continue-on-error`; diff-scoped via `dorny/paths-filter` gating jobs on `needs.changes.outputs.src`.

**`ant-design/ant-design@7ad6408` — a build-level cycle gate, not just lint-level:**
`webpack.config.js:67`: `new CircularDependencyPlugin({ failOnError: true })` — **BLOCKING** through the `ut
dist` build step, distinct from and stronger than the more common ESLint-only cycle check (contrast:
`test-vitest` in the same CI is explicitly labeled `(non-blocking)` with `continue-on-error: true`, a rare
case of a repo naming its own advisory gates in the job name itself).

**`CherryHQ/cherry-studio@HEAD` — the most sophisticated boundary system found in the entire survey, in an
AI-agent-tooling repo (see agentic-dev section below).** `eslint.config.mjs` implements
`import-x/no-restricted-paths` rules **generated dynamically from the filesystem**: sibling pages can't import
each other, `services/<topic>/` directories must be entered only through their `index.ts` barrel, and
main/renderer/preload Electron process boundaries are enforced — each rule carries an inline comment citing
an architecture doc or GitHub issue number. Wired into `ci:basic-check` alongside `oxlint --deny-warnings`.

**Nothing at all:** `QwikDev/qwik@0bad0c6` (one `no-restricted-imports` rule for a single directory, no
cross-package or cycle enforcement), `mermaid-js/mermaid@4e6427b` (a single banned-module rule, nothing
architectural), `nrwl/nx@b94bedeed454577ed311543d32395cc417056d6d` (tags exist in ~46 `project.json` files with
`depConstraints: [{ "sourceTag": "*", "onlyDependOnLibsWithTags": ["*"] }]` — a **wildcard no-op**; the real
enforcement is `no-restricted-imports` + a custom `check-imports.js` script instead of the tag system).
**`TriliumNext/Trilium@f1ce041` — the clearest negative case:** no dependency-cruiser, no boundaries plugin,
no Nx, and ESLint itself never runs in CI. Layer rules exist only as prose in `CLAUDE.md` written for AI
coding agents (*"apps/client has zero @triliumnext/core imports"*, *"No Node built-ins in core"*), and the
document itself admits this is unchecked outside human/agent discipline.

---

## Diff hygiene mechanisms

**`.git-blame-ignore-revs`: present in 6 of 8 repos checked, always advisory, mechanized (not just
documented) in only 2.**

| Repo | SHAs | What they are | Setup |
|---|---|---|---|
| `vitejs/vite@afaf48b7327e09564048821b2e7eb772d59e7f80` | 3 | prettier/oxfmt mass-reformats | **Documented** — `CONTRIBUTING.md:23-29`: *"We have a `.git-blame-ignore-revs` file... `git config --local blame.ignoreRevsFile .git-blame-ignore-revs`"* |
| `angular/angular@319a3c4f3268f4f96ac4acdbb118737d2261e0be` | 43 | 3 groups: prettier migration ×22, relative-imports refactor ×20, clang reformat ×1 (e.g. `fd544159e "ci: complete migration to prettier formatting (#55580)"`) | **Mechanized** — committed `.vscode/recommended-settings.json`: `"gitlens.advanced.blame.customArguments": ["--ignore-revs-file .git-blame-ignore-revs"]` |
| `vercel/next.js@ed2c6b9bd8897355d761a51ec967437a8c47b110` | 15 | prettier bumps + 11× "Turbopack: Make `<crate>` Rust 2024" mass rustfmt migrations | **Mechanized** — committed `.vscode/settings.json:118-121`, same gitlens pattern |
| `babel/babel@d5d57cbc5a56d01b38e40b808f036f46cae1b73e` | 2 | prettier adoption / v2 bump | Documented in the file's own header, not in CONTRIBUTING |
| `eslint/eslint@93de066d4125f8df013d40305e8009f4634a5cba` | 3 | prettier version bumps | Undocumented |
| `facebook/react@d083ec1da1e5252abd3ddfdde6dfbc09701a2c51` | 2 | prettier/compiler config unforking | Undocumented |
| `sveltejs/svelte`, `typeorm/typeorm` | 0 | — | Does not exist |

All 6 instances are **editor-level (GitLens `blame.customArguments`), never CI-enforced** — nothing fails a
build if the setting isn't applied; it purely changes what a human sees while reading blame.

**Generated-file discipline — real but rare.** `vercel/next.js@ed2c6b9bd8897355d761a51ec967437a8c47b110:.gitattributes`:
`packages/next/bundles/** -text linguist-vendored`, `packages/next/compiled/** -text linguist-vendored`,
`build/** linguist-generated=false` (an explicit opt-*out*, to keep a directory searchable/diffable despite
looking generated). Real header marker, mirrored across two languages:
`packages/next/src/build/browser-variant-modules.ts:1-2`:
```
// This file is @generated by `pnpm generate-browser-variant-aliases`.
// Do not edit by hand.
```
(and the identical comment in the Rust source that produces it, `crates/next-core/src/browser_variant_modules.rs`).
next.js also runs the freshness check that makes the marker meaningful, not just decorative:
`.github/workflows/build_and_test.yml:240-263`, comment *"Regenerate the browser-variant lists and fail if
they changed"* — regenerates, then `git diff --exit-code`. **BLOCKING.** `babel/babel` has the same pattern at
smaller scale (`.gitattributes` marks `/.yarn/** linguist-vendored`; a generated-typings marker exists at
`scripts/generators/archived-libs-typings.ts`'s output). `react`, `eslint`, `angular`, `svelte`, `vite`,
`typeorm` have **no** linguist-generated/vendored markers and **no** generated-file freshness check — only EOL
normalization rules in `.gitattributes`.

**CODEOWNERS: sparse, and never differentiates generated paths.** Real per-directory rules found only at
`eslint/eslint@93de066d4125f8df013d40305e8009f4634a5cba:.github/CODEOWNERS`
(`/docs/ @eslint/website-team @eslint/eslint-team`, `* @eslint/eslint-team`). `vercel/next.js`'s CODEOWNERS
exists but is **comments-only, zero actual rules**. `react`, `babel`, `angular`, `svelte`, `vite`, `typeorm`
have no CODEOWNERS at all. None of the 8 gives generated directories a different (or no) review requirement.

**Format-only-changed-files: the single rarest and most valuable gate in this whole document, found in
exactly 1 of 8 repos surveyed for it.** `angular/angular@319a3c4f3268f4f96ac4acdbb118737d2261e0be:.github/workflows/pr.yml:39-40`:
`run: pnpm ng-dev format changed --check ${{ github.event.pull_request.base.sha }}` — fails the PR if files
changed since the base SHA aren't formatted, **scoped only to the diff**, not the whole repo. Documented:
*"If the source code is not properly formatted, the CI will fail and the PR cannot be merged"*
(`contributing-docs/building-and-testing-angular.md`). Every other repo in the sample either runs full-repo
`prettier --check` (react, vite, svelte, typeorm — blocking for correctness, but blind to an agent reformatting
untouched lines as long as the end state is still correctly formatted) or relies on bypassable
`lint-staged`/husky pre-commit hooks (`--no-verify` defeats all of them, and none are re-checked in CI). A
related but distinct gate: `vercel/next.js@ed2c6b9bd8897355d761a51ec967437a8c47b110:AGENTS.md:450-453`
explicitly instructs AI coding agents to scope formatters manually —
`pnpm prettier ... --write <files>` / `npx eslint ... --fix <files>` — the same discipline written as an
**agent instruction with no mechanical enforcement**, rather than a CI gate.

**Codemod discipline: exists as tooling, not as process.** `babel/babel`'s `codemods/`,
`vercel/next.js`'s `packages/next-codemod`, and `typeorm/typeorm`'s `packages/codemod` are all **user-facing
migration CLIs for consumers' code**, not internal mechanical-refactor policy. No repo in the sample documents
isolating a large internal codemod/reformat PR from a logic-change PR.

---

## Complexity thresholds actually used (numbers)

**The dominant finding: real production repos overwhelmingly do not configure a numeric complexity
threshold — and several explicitly turn the rule off rather than leaving it at default.**

- `jestjs/jest@202dd8a14777c270607c2416bd5034c3c0abc984:eslint.config.mjs` (lines 68, 126, 128-129):
  `complexity: 'off'`, `'max-depth': 'off'`, `'max-params': 'off'`, `'max-statements': 'off'` — a deliberate,
  explicit disable, not an absence.
- `cypress-io/cypress`, `excalidraw/excalidraw`, `remix-run/react-router`, `react-hook-form/react-hook-form`,
  `eclipse-theia/theia@58615ba63666141a727ba99a44f13a1e559b2f4c` — zero complexity-rule matches anywhere in
  config (not even set to `off`; the rule is simply never referenced).
- `nestjs/nest@9feedffde8ef8c86f0cd521153740575dc579d88` uses `oxlint`, whose complexity rules live in the
  `pedantic`/`restriction` categories; `.oxlintrc.json` enables only `"correctness": "error"` — complexity
  checking is **genuinely not running**, not defaulted.
- `apache/superset@HEAD:pyproject.toml` selects a broad ruff ruleset but its own comment notes *"Ruff doesn't
  enable... McCabe complexity (C901) by default"* and does not opt in.
- `mlflow/mlflow@HEAD:pyproject.toml` hand-curates ~30 specific ruff rule codes (B006, PLR0402, PT*, FURB*)
  and includes none from the complexity families.
- `vitessio/vitess@HEAD`, `gravitational/teleport@HEAD`, `discourse/discourse@HEAD` — no gocognit/gocyclo or
  `Metrics/CyclomaticComplexity` override found in any of the three.

Where numeric thresholds *are* set, they were already sourced in `research/23` and remain the only real
examples in the whole corpus: `litestar-org/litestar@main:pyproject.toml` mccabe `max-complexity = 12`,
`traefik/traefik@master:.golangci.yml` `gocyclo: min-complexity: 14`, and
`aws-powertools/powertools-lambda-python@develop:Makefile` `xenon --max-absolute C --max-modules A --max-average A`.
This pass adds no new numeric example — it adds 10 confirmed absences (7 JS/TS repos here, plus superset,
mlflow, vitess, teleport, discourse in the broad sweep) to the denominator, which sharpens rather than
contradicts `research/23`'s original observation that PLR0913/complexity families are widely judged too noisy
to gate on.

---

## Test-quality gates

**No repo in the 7-repo JS/TS test-tooling sample (jest, cypress, excalidraw, react-router, react-hook-form,
theia, nestjs) runs mutation testing**, checked directly against `package.json` deps, `stryker.conf.*`, and
every CI workflow file. The broad Go/Python/Ruby/PHP/agentic-dev sweep (11 more repos) found the same: zero
hits for `mutmut`, `go-mutesting`, or `mutant`. Across 18 repos checked specifically for this, the count is 0.

**No repo has a patch/diff-coverage gate.** Codecov `codecov.yml` `patch:` targets are either absent entirely
or present with no number
(`jestjs/jest@202dd8a14777c270607c2416bd5034c3c0abc984:.codecov.yml`: `patch: default: target: auto`,
`require_ci_to_pass: false` — **advisory**, cannot fail CI even in principle).

**One real project-level coverage floor, and it is the only one found:**
`excalidraw/excalidraw@2d3707b816100ee2734bae2b9efc3f7641ab427b:vitest.config.mts`:
```
thresholds: { lines: 60, branches: 70, functions: 63, statements: 60 }
```
enforced by `.github/workflows/test-coverage-pr.yml` on every pull request (`yarn test:coverage`, no
`continue-on-error`) — **BLOCKING**. Important caveat: this is a whole-project floor, not scoped to the diff —
it cannot catch a single badly-tested new file if the rest of the codebase carries the average.

**The one gate that is nearly universal is a ban on focused tests, not a test-quality gate per se:**
- `jestjs/jest`: `'jest/no-focused-tests': 'error'` (`eslint.config.mjs:453`), via the required `static-checks`
  job — **BLOCKING**.
- `cypress-io/cypress@08ec143f851da73c533204141ac4ba33315cdd32`: `'mocha/no-exclusive-tests': 'error'`
  (`packages/eslint-config/src/baseConfig.ts:219`) bans `.only`; `.skip` is explicitly *allowed*
  (`'mocha/no-skipped-tests': 'off'`) but requires a justification comment via a custom rule,
  `'@cypress/dev/skip-comment': 'error'` (`baseConfig.ts:117`) — both **BLOCKING**, via the repo's documented
  single required check: *"the only required GitHub status check for PRs"*
  (`.circleci/src/pipeline/workflows/pull-request.yml:425`).
- `remix-run/react-router@291a913bf132aa0507fabf33bd8e82c4a71e5f12:integration/playwright.config.ts`:
  `forbidOnly: !!process.env.CI` — **BLOCKING** in CI only. Contrast: `jest/expect-expect` is present only via
  the default preset on `**/__tests__/**`, and the repo's `"lint": "eslint --cache ."` has **no
  `--max-warnings`**, so anything at `warn` severity (including expect-expect where it applies) cannot fail
  the build — **advisory in practice**, despite the rule technically being configured.

**The plainest statement of the gap, found verbatim in a repo's own CI:**
`nestjs/nest@9feedffde8ef8c86f0cd521153740575dc579d88` makes coverage collection explicitly non-blocking on
both scripts — `"coverage": "vitest run --coverage ... || true"` and `"test:cov": "... || true"` — plus
`vitest.config.coverage.mts` sets `passWithNoTests: true` with the comment
*"Allow tests to fail — we only want the coverage data."* The repo's only mechanical check on diff *shape* is
`.github/workflows/pr-content-guard.yml`, which blocks added lines matching `[ \t]{100,}` or length > 2000 — a
disguised-malware/supply-chain guard, unrelated to test quality. The requirement that a change actually be
tested is stated only in prose: `CONTRIBUTING.md:217`: *"All features or bug fixes **must be tested** by one
or more specs (unit tests)"* — with no automated check behind it. This sentence, or something functionally
identical to it, is the *only* mechanism found for "a test must exist" across all 7 repos in this cluster —
"the test can actually fail" (mutation testing's job) has no mechanism at all, anywhere in the sample.

---

## Blocking vs advisory: the counts

Tallied across every mechanism found in this document (dead-code, size, API-surface, dependency friction,
architecture, diff hygiene, complexity, test-quality — not double-counting the same job cited twice):

| | Count | Share |
|---|---|---|
| **CI-blocking** (required check, no `continue-on-error`, fails the build/merge) | 42 | ~69% |
| **Advisory** (warn-only, cron-only, PR-comment-only, never wired to a workflow, or bypassable pre-commit hook) | 19 | ~31% |

This ratio is more encouraging than it looks, and the encouragement is misleading. It counts *mechanisms that
were found at all* — it says nothing about the much larger set of anti-bloat questions (dependency necessity,
single-use abstractions, comment quality, semantic duplication, file-creation-vs-edit) for which **zero
mechanism of either kind exists** in any repo surveyed. See the next section. Within the "found" set, the
pattern is consistent: **dead-code and architecture-boundary gates skew heavily blocking** (once a team builds
the rule at all, they wire it to CI — the fixed cost of writing a `dependency-cruiser` config is paid once, so
teams also pay the smaller cost of gating on it); **size-budget and API-surface gates skew heavily advisory or
unwired** (`heroui`'s size scripts, `monkeytype`'s knip config, `element-plus`'s compressed-size-action,
`backstage`'s madge circular-deps check — all configured, none enforced); and **test-quality mechanisms are
almost entirely absent rather than either blocking or advisory** — there is no gate to classify because no
repo built one.

The single most common "advisory that looks like a gate but isn't": a **bypassable pre-commit hook**
(`lint-staged` + `husky`, present in `react`, `babel`, `eslint`, `vite`, `svelte`, `typeorm`, and implied by
convention elsewhere) that runs a real check but is defeated by `git commit --no-verify` and is never
re-checked by CI. Counted as advisory here because it fails to meet the bar this document uses throughout: a
gate that a determined (or merely fast-moving) agent can silently skip is not a gate.

---

## Coverage of the 12 AI-bloat failure modes: what real repos catch, what NOTHING catches

Referencing the 12 failure modes named in `research/23-findings-antibloat-enforcement.md`. For each: whether
*any* repo read in this pass has a real, running mechanism against it (not a tool that could theoretically be
pointed at it — an actual configured, wired instance).

| # | Failure mode | Real production coverage found | Strength |
|---|---|---|---|
| 1 | Agent creates a new file instead of editing an existing one | **NONE mechanical.** Closest analogue: `calcom/cal.com@54343aa:AGENTS.md:32` — *"Never create large PRs (>500 lines or >10 files) - split them instead"*, mirrored as a self-attested PR-template checkbox. This is a size proxy, not a file-necessity check, and it is unenforced (nothing greps the diff to verify the claim). | Convention only |
| 2 | Agent adds a dependency stdlib/existing deps already cover | **PARTIAL, and real.** `depguard` denylists (`teleport`, `vitess`, plus `research/23`'s `traefik`/`prometheus` citations of `github.com/pkg/errors`) and `TID251`-style banned-import lists (`superset` banning raw `json`) convert *known-bad, named* additions into a blocked PR. None of these judge a *novel* unnecessary dependency — they only catch re-adding something already on a blocklist. | Blocking, narrow scope |
| 3 | Agent writes a single-use abstraction/interface | **NONE found anywhere in this sample.** No repo runs `dependency-cruiser --output-type metrics` or an equivalent single-dependent-count check in CI. | Uncovered |
| 4 | Dead code, unused imports, commented-out blocks | **Best-covered mode.** knip (better-auth, promptfoo, both blocking), staticcheck (vitess), TID-style bans (superset) — real, blocking, in production. Counter-finding: two configured-but-unwired instances (monkeytype's knip, nextcloud's `findUnusedCode=false`) show configuration without enforcement is common even here. | Blocking, where wired |
| 5 | Agent duplicates near-identical logic (esp. with renamed variables) | **NONE found.** No repo in this sample runs jscpd/PMD-CPD as a CI gate. `ant-design`'s `CircularDependencyPlugin` and Ghost's dependency-cruiser catch *cycles*, not *duplication* — a different failure mode entirely. Matches `research/23`'s own finding that token-based clone detection misses renamed-variable duplication even when configured. | Uncovered |
| 6 | Redundant comments restating the code | **NONE found**, confirmed again in a much larger sample. No lint rule, no ratio-based heuristic, in any repo read. | Uncovered |
| 7 | Agent adds a README/doc nobody asked for | **Weakest-covered mode with any partial signal at all.** No repo gates file *necessity* mechanically. The only real friction is a review gate, not an automated check: `hoppscotch/hoppscotch@a9ffa29:CODEOWNERS`: blanket `*.md @liyasthomas` — every markdown file in the repo requires one named person's approval, a genuine but manual bottleneck. `supabase/supabase@8e20712:.github/CODEOWNERS`: `/apps/docs/ @supabase/docs` — same pattern, scoped. `danny-avila/LibreChat@c8c5478` structurally prevents *some* docs sprawl by redirecting all doc PRs to a separate repository. No repo has a CI check on `.md` file count or a doc-directory manifest. | Human review gate only, not mechanical |
| 8 | Agent silently widens a public API surface | **THIN.** Real golden-file diffing (`api-extractor` + committed `.api.md`) found in exactly 1 of 9 repos checked (`backstage`, via `verify-api-reference.js`, blocking). Export-shape linting (`attw`/`publint` at `refinedev`, `check-package-exports.mjs` at `tiptap`) is more common but only catches broken packaging, not an unwanted new export. `lexical`'s `.d.ts`-leak check runs only at release time, after the surface has already merged to main. | Rare, and often too late |
| 9 | Agent grows the bundle/binary/install size | **RARE.** One real blocking budget (`react-hook-form`, 15.0 kB), one budget that's blocking-but-gated-behind-a-label (`lexical`), one advisory PR-comment-only (`element-plus`), everything else absent — including in libraries where size is a stated concern. | Rare and inconsistent |
| 10 | Agent writes tests that assert nothing / mock everything | **NONE mechanical, confirmed at scale.** Zero mutation testing across 18 repos checked. `jest/expect-expect`-family rules exist in config in a few repos but are either absent, default-`warn`-with-no-`--max-warnings` (react-router), or simply not configured. "Tests must exist" is prose-only even in the repo that states it most explicitly (`nestjs` `CONTRIBUTING.md:217`). | Uncovered |
| 11 | Agent reformats untouched lines, inflating the diff | **RARE but real, and this pass found the cleanest example in the whole survey.** `angular/angular`'s `ng-dev format changed --check <base-sha>` is diff-scoped and CI-blocking — 1 of 8 repos checked for this specific mechanism. Everyone else either runs full-repo formatting checks (blind to this failure mode by construction) or relies on a bypassable pre-commit hook. | Rare, 1 strong example |
| 12 | Agent introduces an import cycle or crosses a layer boundary | **Best-covered architectural mode.** Real, diverse, blocking implementations: `Ghost` (dependency-cruiser), `ant-design` (webpack `CircularDependencyPlugin failOnError`), `backstage` (custom eslint-plugin), `nuxt` (`no-restricted-paths` zones), `cherry-studio` (filesystem-generated path rules), `vitess`/`teleport` (`depguard` repurposed for layering), `discourse` (custom rubocop cops scoped to `plugins/**`). | Blocking, in most large repos that bother |

**Net read: 4 of 12 failure modes (#4 dead code, #2 banned-dep re-adds, #12 cycles/layers, and #9 size — only
weakly) have real, blocking, production-proven mechanisms.** #7 (unwanted docs) and #8 (API widening) have
partial, mostly-manual coverage. **#1 (new file vs. edit), #3 (single-use abstraction), #5 (semantic
duplication), #6 (redundant comments), and #10 (assertion-free tests) have no mechanical coverage in any repo
read across two independent research passes now (`research/23`'s tool-isolation testing and this document's
production-config reading).** These five are where a plugin must invent, not adapt — there is no production
config to imitate, only the negative finding that nobody has solved it either.

---

## Recommended tiered stack for a small team

Built from what this document actually found running in production, not from what tools theoretically offer.
Every item below has a cited, running example above; nothing here is aspirational.

**Pre-commit (<5s, local, blocks the commit — but remember every hook here is `--no-verify`-bypassable and
none of the surveyed repos re-check it in CI, so treat this tier as a courtesy, not a gate):**
```bash
# diff-scoped formatter + linter, the pattern used by react/babel/eslint/vite/svelte/typeorm's lint-staged
npx eslint --fix $(git diff --cached --name-only --diff-filter=ACM -- '*.ts' '*.tsx')
npx prettier --write $(git diff --cached --name-only --diff-filter=ACM -- '*.ts' '*.tsx')
```

**Pre-PR / CI on every push (<2min, diff-scoped where possible — this tier is where the real, blocking,
cited-above mechanisms live):**
```bash
# dead code — knip, wired the way better-auth/promptfoo actually wire it (not the way monkeytype configured
# but never ran it)
npx knip                                    # BLOCKING, add to required checks, not just package.json scripts

# architecture — hand-write the rules; no off-the-shelf plugin has real adoption (Ghost/nuxt/backstage pattern)
npx dependency-cruiser --config .dependency-cruiser.cjs --output-type err src

# focused-test ban — the one test-quality gate every serious JS repo in this sample actually has
# (jest/no-focused-tests, mocha/no-exclusive-tests, playwright forbidOnly)
npx eslint --rule 'jest/no-focused-tests: error' .

# diff-scoped format check — angular's ng-dev pattern, the rarest and most valuable gate found; reimplement
# with whatever formatter you use, scoped to files changed since base SHA
prettier --check $(git diff --name-only $(git merge-base HEAD origin/main))

# dependency addition — grafana's owner-per-dependency pattern is the strongest found; a small team's
# version is a CODEOWNERS entry on the manifest plus a required review from that owner
```

**Nightly / weekly (expensive, whole-repo, trend-tracked — everything this document found NO team running
per-PR, because it's genuinely too slow, not because it's unimportant):**
```bash
mutmut run                    # or stryker — zero repos in this survey run this in CI at all; a small team
                               # adopting it nightly would be ahead of every repo in this document
npx knip                      # full whole-repo run
git-sizer --threshold 10MiB   # repo-object bloat
```

**What no tier above solves, because nothing in production solves it either** (see the failure-mode table):
single-use abstractions, semantic (renamed-variable) duplication, redundant comments, unnecessary new files,
and assertion-free tests. For a small team, the honest recommendation is not "buy a tool for this" — none
exists in working form anywhere in this corpus — it is: **route these five specifically to a human or
LLM-reviewer pass that is told exactly these five questions and nothing else**, the same conclusion
`research/23` reached from the tooling side. The two documents converge independently, which is itself
evidence: this isn't a gap in this research, it's a gap in the industry.

**Scale note:** the `depguard`/CODEOWNERS-on-manifest pattern (grafana, teleport, vitess) starts paying for
itself as soon as a repo has more than one team touching the dependency tree — for a genuinely small team (2-5
engineers, one dependency decision-maker) it is overkill; a lighter version — a single required reviewer on
`package.json`/`go.mod` via CODEOWNERS, no custom ownership-comment tooling — captures most of the value at a
fraction of the setup cost. The diff-scoped-format-check and focused-test-ban gates, by contrast, cost almost
nothing to add at any team size and were found running even in single-maintainer-adjacent projects in this
sample (`react-hook-form`) — there is no scale threshold below which they don't pay for themselves.
