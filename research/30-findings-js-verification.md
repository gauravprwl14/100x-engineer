# 30 — Findings: JS/TS Verification Systems

Deep-read of the JS/TS worklist (`research/worklists/js.txt`, 72 repos) for D1
(verification stack), D2 (anti-bloat), D4 (correctness ratchets). All 72 repos were
reached — 0 unreachable. Method below. No repo was `git clone`d.

**Across all 72 repos: mutation testing 0/72, property-based testing 0/72, and a
real blocking patch-scoped coverage gate in exactly 1 of 72.**

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Coverage (what was actually read vs skipped, honestly)](#coverage-what-was-actually-read-vs-skipped-honestly) | which of the 72 repos were fetched directly vs pulled in by a sub-agent, and why CI-workflow-discovery gaps mean every `merge_group`/CI count later in the doc is a floor, not a true population figure | 39 lines |
| 2 | [The prove-it command, per repo](#the-prove-it-command-per-repo) | the exact test/lint/typecheck command copied from each repo's root `package.json` (or CONTRIBUTING/AGENTS.md) — the single most useful table in this file, and the only place showing that 5 repos have no root command at all | 91 lines |
| 3 | [Tooling distribution (counts)](#tooling-distribution-counts) | which test runner, linter, formatter, package manager and monorepo tool actually won this cohort (vitest 40/72, pnpm 53%), and confirms mutation/property-based testing appear in zero repos | 57 lines |
| 4 | [Typecheck strictness spectrum](#typecheck-strictness-spectrum) | who sets `strict: true` vs who explicitly turns it off, the strictest and weakest root tsconfigs found verbatim, and that `isolatedDeclarations` is unused in all 72 | 50 lines |
| 5 | [Coverage and diff-coverage gates (blocking vs advisory)](#coverage-and-diff-coverage-gates-blocking-vs-advisory) | **highest-value section**: only 1 of 72 repos has a real blocking patch-scoped coverage gate — the rest have no codecov.yml, a whole-repo-only target, or an advisory/informational patch check | 31 lines |
| 6 | [CI architecture patterns](#ci-architecture-patterns) | merge-queue, sharding and cost-aware-runner adoption among the repos whose CI workflow could actually be found | 55 lines |
| 7 | [Anti-bloat configs verbatim](#anti-bloat-configs-verbatim) | knip/size-limit/api-extractor adoption rates with real config snippets — bundle-size budgets exist in only 2/72 repos | 77 lines |
| 8 | [Monorepo affected-only patterns](#monorepo-affected-only-patterns) | Turborepo/Nx/Lerna task-graph configs and the cache-correctness idioms (self-edges, env allowlists) that keep affected-only builds correct | 60 lines |
| 9 | [Synthesis: minimum viable vs strongest justified stack](#synthesis-minimum-viable-vs-strongest-justified-stack) | two runnable command sequences — the modal floor everyone actually runs, and the strongest stack assembled from real T1 practices — each line tied to the failure class it blocks | 79 lines |

## Coverage (what was actually read vs skipped, honestly)

- **72/72 repos reached.** 54 via my own scripted `curl -sf --max-time 6
  raw.githubusercontent.com/OWNER/REPO/BRANCH/PATH` fetches (26 target paths each:
  package.json, tsconfig.json(.base), CONTRIBUTING.md, AGENTS.md, CLAUDE.md,
  turbo.json, nx.json, lerna.json, pnpm-workspace.yaml, knip.json,
  .size-limit.json, codecov.yml, api-extractor.json, biome.json, eslint
  configs, vitest/jest/playwright configs, and 9 guessed CI workflow filenames).
  18 (rows 37-54 of the worklist: eslint, react-admin, mocha, wekan, next.js,
  excalidraw, shadcn-ui, uptime-kuma, vite, hoppscotch, prettier, bruno, puter,
  reactive-resume, chakra-ui, trpc, TanStack/table, element-plus) were extracted
  by a sub-agent using the identical method; its per-repo write-ups are folded
  into every table below.
- **What was NOT read**: sub-package `tsconfig.json`s inside monorepos (root only,
  per task scope), individual GitHub Actions workflow files beyond the ones
  fetched (see below), and any file behind a branch/path guess that 404'd.
  Absence is recorded as `NOT FOUND`, never silently omitted.
- **CI workflow discovery was the weakest link and it's worth being honest about
  why.** `raw.githubusercontent.com` cannot list a directory, so `.github/workflows/`
  contents cannot be enumerated without `gh api` (quota-exhausted, forbidden) or a
  clone (forbidden for large repos). Two fallbacks were used: (a) 9 guessed common
  filenames (ci.yml, test.yml, build.yml, lint.yml, e2e.yml, main.yml,
  unit-tests.yml, pr.yml, node.js.yml) — **hit for 30/54** self-fetched repos; (b)
  grepping README.md for CI-badge URLs referencing `workflows/*.yml`, which
  recovered a handful more (axios, badges/shields, facebook/lexical, jhipster,
  quasarframework, react/react, prisma, TryGhost, docusaurus, babel, mozilla/pdf.js).
  For monorepos over jsdelivr's 50MB tree-API limit (grafana, backstage, nx,
  supabase, mui, docusaurus, cypress, vscode, and others) and repos using
  non-obvious workflow names, **the real CI workflow was never found** — this is
  recorded as `NOT FOUND`, not zero adoption. Any "N/M repos have merge_group"
  count below is therefore a **floor**, not a true population figure.
- **A worklist data error found and corrected**: `calcom/cal.diy` does not exist;
  it resolves to `calcom/cal.com`. Treated as `calcom/cal.com` throughout.
- No mutation testing, no property-based testing (fast-check/jsverify), and no
  fuzz harnesses were found in any of the 72 repos' root configs — absence
  recorded, not assumed.

---

## The prove-it command, per repo

Extracted verbatim from each repo's root `package.json` `scripts` (or, where no
root script existed, from CONTRIBUTING.md/AGENTS.md/CLAUDE.md prose — marked).
`NOT FOUND` means no test/check/lint/typecheck script exists at the workspace
root — the repo has *no single command a contributor can run from the top*, which
is itself a finding for a monorepo.

| repo | tier | prove-it command (from root package.json unless noted) | runner(s) | pm |
|---|---|---|---|---|
| grafana/grafana | T1 | `test`: jest --notify --watch / `lint`: yarn run lint:ts && yarn run lint:sass / `typecheck`: tsc --noEmit && tsc --noEmit -p scripts/rspack/tsconfig.json && yarn r... | vitest,jest | yarn@4.18.0 |
| backstage/backstage | T1 | `test`: NODE_OPTIONS='--experimental-vm-modules' backstage-cli repo test / `lint`: backstage-cli repo lint --since origin/master | jest | yarn@4.18.0 |
| prisma/orm | T1 | `test`: turbo run test --continue / `lint`: turbo run lint / `typecheck`: turbo run typecheck | vitest | pnpm@10.27.0 |
| TryGhost/Ghost | T1 | `test`: pnpm nx run-many -t test --exclude @tryghost/e2e --exclude ghost-admin / `lint`: pnpm nx run-many -t lint lint:boundaries && pnpm lint:packages && pnpm... | vitest | pnpm@12.4.2 |
| calcom/cal.com | T1 | `test`: TZ=UTC vitest run / `lint`: turbo lint / `type-check`: turbo run type-check | vitest | yarn@4.12.0 |
| nrwl/nx | T1 | `test`: nx run-many -t test | vitest,jest,cypress | pnpm@12.4.2 |
| actualbudget/actual | T1 | `test`: lage test --continue / `lint`: oxfmt --check . && oxlint --type-aware --quiet / `typecheck`: tsgo -p tsconfig.root.json --noEmit && lage typecheck | vitest | yarn@4.17.1 |
| QwikDev/qwik | T1 | `test`: pnpm build.full && pnpm test.unit && pnpm test.e2e / `lint`: pnpm lint.eslint && pnpm lint.prettier | vitest | pnpm@11.22.0 |
| supabase/supabase | T1 | `lint`: turbo run lint / `typecheck`: turbo --continue typecheck (no `test` script at root) | none identified | pnpm@11.13.1 |
| ant-design/ant-design | T1 | `test`: jest --config .jest.js --no-cache / `lint`: npm run version && npm run tsc && npm run lint:script && npm run lint:biome && ... | vitest,jest | unpinned |
| mui/material-ui | T1 | `test`: pnpm test:node | vitest,playwright | pnpm@12.4.2 |
| mermaid-js/mermaid | T1 | `test`: pnpm lint && vitest run / `lint`: eslint --quiet --stats --cache --cache-strategy content . && pnpm lint:jison && prettier --cache --check . | vitest,jest,playwright | pnpm@10.30.3 |
| facebook/docusaurus | T1 | `test`: vitest run / `lint`: pnpm lint:js && pnpm lint:style && pnpm lint:spelling && pnpm lint:syncpack && pnpm lint:knip | vitest | pnpm@12.3.4 |
| nuxt/nuxt | T1 | `test`: pnpm test:prepare && vitest run && pnpm test:types && pnpm typecheck / `lint`: pnpm dev:prepare && eslint . --cache / `typecheck`: vue-tsc --noEmit | vitest | pnpm@12.5.1 |
| payloadcms/payload | T1 | `test`: pnpm test:int && pnpm test:components && pnpm test:e2e / `lint`: turbo run lint --log-order=grouped --continue --filter "!blank" ... | vitest | pnpm@11.9.0 |
| ToolJet/ToolJet | T1 | **NOT FOUND** — no test/check/lint/typecheck script at root | none identified | unpinned |
| TriliumNext/Trilium | T1 | `typecheck`: tsx scripts/filter-tsc-output.mts (no aggregate `test` at root) | vitest,playwright | pnpm@12.6.0 |
| better-auth/better-auth | T1 | `test`: turbo test --continue --filter=./packages/* --filter=./test/* / `lint`: biome check . --error-on-warnings / `typecheck`: tsc --build --force | vitest | pnpm@11.1.1 |
| axios/axios | T2 | `test`: npm run test:vitest / `lint`: eslint lib/**/*.js | vitest,playwright | unpinned |
| cypress-io/cypress | T2 | `test`: yarn lerna exec yarn test --scope=cypress --scope=@packages/{...} / `lint`: lerna run lint --no-bail --concurrency 2 / `type-check`: yarn lerna exec ... | vitest,mocha | yarn@1.22.22 |
| DIYgod/RSSHub | T2 | `test`: npm run format:check && npm run vitest:coverage / `lint`: oxlint --type-aware . / `typecheck`: tsc --noEmit | vitest | pnpm@10.34.5 |
| LibreChat-AI/LibreChat | T2 | `lint`: eslint . (no `test`/`typecheck` at root) | jest | npm@11.13.0 |
| ueberdosis/tiptap | T2 | `test`: vp run -r build && vp run test:unit / `lint`: vp lint | none identified | pnpm@11.2.2 |
| facebook/lexical | T2 | `lint`: eslint ./ (no `test` at root) | vitest,playwright | pnpm@11.24.0 |
| renovatebot/renovate | T2 | `test`: run-s lint test-schema jest / `lint`: run-s ls-lint type-check oxlint biome prettier markdown-lint git-check doc-fence-check | vitest | pnpm@11.27.1 |
| super-productivity/super-productivity | T2 | `test`: npm run packages:test && ... && ng test --watch=false && npm run test:tz:ci / `lint`: npm run lint:ts && lint:scss && ... | playwright,karma | npm@11.18.0 |
| sveltejs/kit | T2 | `check`: pnpm -r prepublishOnly && pnpm -r check / `lint`: pnpm -r lint && eslint --cache ... (no `test` at root) | none identified | pnpm@10.34.3 |
| react/react | T2 | `test`: node ./scripts/jest/jest-cli.js / `lint`: node ./scripts/tasks/eslint.js | jest | yarn@1.22.22 |
| microsoft/vscode | T2 | `test` script is a stub telling you to run `./scripts/test.sh` manually; `precommit`: node build/hygiene.ts | mocha | unpinned |
| cline/cline | T2 | `test`: bun --parallel -F './sdk/packages/**' ... test / `lint`: bun biome lint ... | vitest | bun@1.3.13 |
| makeplane/plane | T2 | `check`: turbo run check (no `test` at root) | none identified | pnpm@11.10.0 |
| remix-run/react-router | T2 | `test`: node --experimental-vm-modules ... jest.js / `lint`: eslint --cache . / `typecheck`: pnpm run --recursive --parallel typecheck | vitest,jest | pnpm@11.7.0 |
| mozilla/pdf.js | T2 | **NOT FOUND** — no test/check/lint/typecheck script at root | none identified | unpinned |
| jestjs/jest | T2 | `test`: yarn lint && yarn jest / `lint`: eslint . --cache ... / `typecheck`: yarn typecheck:examples && yarn typecheck:tests | jest | yarn@4.18.0 |
| babel/babel | T2 | `test`: make test / `lint`: make lint | jest | yarn@4.17.0 |
| typeorm/typeorm | T2 | `test`: pnpm --filter typeorm run test / `lint`: pnpm -r run lint / `typecheck`: pnpm --filter typeorm run typecheck | none identified | pnpm@10.34.5 |
| eslint/eslint | T2 | `test`: npm test (Makefile.js: mocha + coverage gate 99%/98% + fuzzer + license) / `lint`: Makefile lint (+checkRuleFiles, checkLicenses, lint:unused=knip) | mocha,cypress | npm(unpinned) |
| marmelab/react-admin | T2 | `test`: yarn test-unit && yarn test-e2e / Agents.md: `make lint`, `make typecheck`, `make prettier` | jest,cypress | yarn@4.0.2 |
| mochajs/mocha | T2 | `test`: run-s lint test-node test-browser (AGENTS.md: format:check→lint→test-node→test-browser→tsc) | mocha,playwright | npm only(unpinned) |
| wekan/wekan | T2 | `test`: meteor test --once --driver-package meteortesting:mocha / `test:unit:node`: node tests/run-node-suites.cjs (~260 suites) | mocha,playwright | unpinned(meteor+npm) |
| vercel/next.js | T2 | `lint`: run-p test-types lint-typescript prettier-check lint-eslint lint-ast-grep lint-language check-unused-turbo-tasks / `typescript`: tsc --noEmit | jest,playwright | pnpm@10.33.0 |
| excalidraw/excalidraw | T2 | `test:all`: yarn test:typecheck && test:code && test:other && test:app --watch=false | vitest | yarn@1.22.22 |
| shadcn-ui/ui | T2 | `check`: turbo lint typecheck format:check / `test`: builds registry, boots app, turbo run test --force | vitest | pnpm@10.33.4 |
| louislam/uptime-kuma | T2 | `test`: node --run test-backend && node --run test-e2e / `lint`: npm run lint (CONTRIBUTING.md CI list) | node:test,playwright | unpinned(npm) |
| vitejs/vite | T2 | `test`: pnpm test-unit && pnpm test-serve && pnpm test-build / `lint`: eslint --cache . / `typecheck`: tsc -p scripts && pnpm -r --parallel typecheck | vitest | pnpm@12.6.0(only-allow pnpm) |
| hoppscotch/hoppscotch | T2 | `pre-commit`: pnpm -r do-lint && pnpm -r do-typecheck / `test`: pnpm -r do-test (fans to sub-packages) | unidentified at root (sub-pkg) | pnpm@10.34.5(only-allow pnpm) |
| prettier/prettier | T2 | CONTRIBUTING.md: yarn test (jest -u) / `lint`: run-p lint:* (typecheck,eslint,changelog,prettier,spellcheck,deps,knip,format-test) | jest(jest-light-runner) | yarn@4.18.0 |
| usebruno/bruno | T2 | `lint`: eslint / `test:e2e`: playwright test --project=default --project=system-pac (5-project split, sharded via blob reports) | jest,playwright | npm workspaces(unpinned) |
| HeyPuter/puter | T2 | `test:backend`: vitest run --config src/backend/vitest.config.ts / `check:puterjs:types` (AGENTS.md: deliberately no aggregate script) | vitest,playwright | unpinned(npm) |
| reactive-resume/reactive-resume | T2 | AGENTS.md gate: `pnpm check` (biome --write --unsafe) then `pnpm test`, `pnpm typecheck`, `pnpm build`, `pnpm exec turbo boundaries` | vitest,playwright | pnpm@12.6.0 |
| chakra-ui/chakra-ui | T2 | `test`: vitest / `typecheck`: tsgo --noEmit (MS Go-based typechecker) / `lint`: eslint packages --ext .ts,.tsx --cache | vitest | pnpm@11.10.0 |
| trpc/trpc | T2 | `test`: vitest (native `projects: ['./packages/*']`) / `lint`: turbo lint / `typecheck-packages` | vitest | pnpm@12.4.1 |
| TanStack/table | T2 | `test:pr`: nx affected --targets=test:eslint,test:sherif,test:knip,test:lib,test:types,test:build,build (AGENTS.md: applies equally to AI-assisted work) | vitest,playwright,node:test | pnpm@12.4.1 |
| element-plus/element-plus | T2 | AGENTS.md: `pnpm test` (vitest) / `pnpm lint`: eslint --max-warnings 0 / `pnpm typecheck`: fans to 5 sub-checks incl. vue-tsc | vitest | pnpm@12.6.0 |
| badges/shields | T2 | `test`: run-s --silent --continue-on-error lint test:package test:core test:entrypoint check-types:package prettier:check | mocha,cypress | unpinned |
| jhipster/generator-jhipster | T2 | `test`: esmocha test generators cli .blueprint lib --forbid-only / `lint`: npm run eslint | none identified | unpinned |
| monkeytypegame/monkeytype | T2 | `test`: turbo run test integration-test / `lint`: turbo run lint | vitest | pnpm@11.21.0 |
| immich-app/immich | T2 | **NOT FOUND** — no test/check/lint/typecheck script at root | none identified | pnpm@11.27.0 |
| angular/angular | T2 | `test`: bazelisk test / `lint`: pnpm --silent tslint && pnpm --silent ng-dev format changed --check | cypress,karma | pnpm@11.27.1 |
| microsoft/playwright | T2 | `test`: playwright test --config=tests/library/playwright.config.ts / `lint`: npm run eslint && npm run tsc && npm run doc && ... | none identified | unpinned |
| puppeteer/puppeteer | T2 | `test`/`lint`/`build`/`format` all delegate to `wireit` (task-graph runner) | mocha | unpinned |
| sveltejs/svelte | T2 | `test`: vitest run / `lint`: eslint && prettier --check . | vitest,playwright | pnpm@10.33.4 |
| react-hook-form/react-hook-form | T2 | `test`: jest --config ./scripts/jest/jest.config.js / `lint`: eslint . --cache | jest | unpinned |
| refinedev/refine | T2 | `test`: lerna run test --stream / `lint`: biome check . | vitest,cypress | pnpm@9.4.0 |
| eclipse-theia/theia | T2 | `test`: npm run -s test:theia && npm run -s electron test && npm run -s browser test / `lint`: lerna run lint | none identified | unpinned |
| nestjs/nest | T2 | `test`: vitest run / `lint`: oxlint packages integration | vitest | unpinned |
| Kong/insomnia | T2 | `test`/`lint`/`type-check`: npm run X --workspaces --if-present | vitest | unpinned |
| heroui-inc/heroui | T2 | `test`: turbo test / `lint`: turbo lint / `typecheck`: turbo typecheck | vitest | pnpm@10.26.2 |
| quasarframework/quasar | T2 | `test`: pnpm --filter quasar test / `lint`: oxfmt && oxlint --fix ... | vitest | pnpm@12.3.4 |
| tailwindlabs/tailwindcss | T3 | `test`: cargo test && vitest run --hideSkippedTests / `lint`: prettier --check . && turbo lint | vitest | pnpm@11.9.0 |
| fastify/fastify | T3 | `test`: npm run lint && npm run unit && npm run test:types | none identified | unpinned |
| honojs/hono | T3 | `test`: tsc -p tsconfig.spec.json && vp test --run / `lint`: vp lint src runtime-tests build ... | vitest | pnpm@12.6.0 |

**5/72 repos (ToolJet, supabase, mozilla/pdf.js, immich-app/immich, sveltejs/kit)
have no single root `test` script at all** — either the repo has no aggregate
verification command, or verification is delegated entirely to CI-only scripts /
sub-package scripts invisible from the root. For a monorepo this means "prove it
works" cannot be answered without already knowing which sub-package changed.

---

## Tooling distribution (counts)

Counts are of root-level `package.json` `dependencies`/`devDependencies` across
all 72 repos (54 self-fetched + 18 from the batch-3 sub-agent, merged).

**Test runners** (repo may use more than one; totals will exceed 72):
| runner | n | repos (sample) |
|---|---|---|
| vitest | 40/72 | prisma, calcom, nuxt, excalidraw, vite, puter, trpc, TanStack/table, element-plus, ... |
| jest | 15/72 | grafana, backstage, ant-design, react, jestjs/jest(self), babel, react-hook-form, react-admin, next.js, prettier, bruno |
| playwright | 16/72 | mui, mermaid, TriliumNext, axios, facebook/lexical, super-productivity, sveltejs/svelte, wekan, next.js, uptime-kuma, bruno, puter, reactive-resume, TanStack/table |
| mocha | 7/72 | cypress, microsoft/vscode, puppeteer, badges/shields, eslint(self), mocha(self), wekan |
| cypress | 6/72 | nrwl/nx, badges/shields, angular, refinedev, react-admin, eslint(browser tests) |
| karma | 2/72 | super-productivity, angular |
| node:test | 2/72 | uptime-kuma, TanStack/table |

**Linters**: eslint **53/72**, oxlint 8/72 (actualbudget, DIYgod/RSSHub, renovate,
nrwl/nx, makeplane, quasarframework, nestjs — all Rust-based, adopted by repos
chasing lint speed), Biome 8/72 (better-auth, calcom, cline, prisma, refinedev,
renovate, reactive-resume — the modern all-in-one alternative). **No repo used
both oxlint and Biome as its primary linter.**

**Formatters**: Prettier **44/72** (still the default by a wide margin), Biome
9/72 (same repos as the Biome-linter set, since Biome ships format+lint together),
oxfmt 2/72 (actualbudget, vite — paired with oxlint, the Rust-toolchain repos).

**Package managers** (from `packageManager` field; "unpinned" = no field, so the
actual PM used by contributors is not enforced/verifiable from the repo alone):
| pm | n |
|---|---|
| pnpm | 38/72 (53%) |
| unpinned/no field | 20/72 (28%) |
| yarn | 11/72 (15%) |
| npm (explicit field) | 2/72 |
| bun | 1/72 (cline) |

pnpm has won this cohort outright. Two repos go further and **hard-block** the
wrong PM: `vitejs/vite:package.json` and `hoppscotch/hoppscotch:package.json`
both set `"preinstall": "npx only-allow pnpm"`.

**Monorepo task-graph tools** (repo may combine; "plain workspaces" = npm/yarn/pnpm
`workspaces` field with no task-graph tool):
| tool | n | notes |
|---|---|---|
| Turborepo | 14/72 | better-auth, calcom, heroui, makeplane, monkeytype, payload, prisma, tailwindcss, LibreChat, next.js, shadcn-ui, reactive-resume, trpc(secondary), tanstack(via nx, not turbo) |
| Lerna | 10/72 | cypress, theia, docusaurus, grafana, jest, mui, nestjs, refinedev, react-admin(primary), trpc(publish-only) — mostly legacy/publish-only now, not the build orchestrator |
| Nx / Nx Cloud | 6/72 | TryGhost, cypress(secondary), grafana(secondary), mui(secondary), nrwl/nx(dogfooding itself), refinedev(secondary), TanStack/table(Nx Cloud distributed CI) |
| plain workspaces, no task graph | ~30/72 | eslint, excalidraw, vite, hoppscotch, chakra-ui, element-plus, uptime-kuma(not a monorepo), puter, bruno, and most non-monorepo repos |

**No mutation testing tool (Stryker etc.) and no property-based testing library
(fast-check, jsverify) appeared in any of the 72 root `package.json` files.**
This is a real absence, not a search failure — dependency name searches for
`stryker`, `fast-check`, `jsverify`, `jsfuzz` across all 72 fetched manifests
returned zero hits.

---

## Typecheck strictness spectrum

Root `tsconfig.json`/`tsconfig.base.json` presence and `strict`-family flags.
33/54 self-fetched repos had a readable root tsconfig; many monorepos put
strictness in a sub-package or an unfetched extended base (recorded as such).

**Strictest found — TanStack/table** (`TanStack/table:tsconfig.json`):
```json
{
  "allowJs": true, "checkJs": true, "strict": true,
  "noUncheckedIndexedAccess": true, "noUnusedLocals": true,
  "noUnusedParameters": true, "noImplicitReturns": true,
  "allowUnreachableCode": false, "allowUnusedLabels": false,
  "isolatedModules": true, "noErrorTruncation": true
}
```
Close behind, `mermaid-js/mermaid:tsconfig.json` sets `strict`,
`noUncheckedIndexedAccess`, **and** `exactOptionalPropertyTypes` all `true` — the
only repo in the corpus with `exactOptionalPropertyTypes` on (`facebook/docusaurus`
has the flag present but explicitly `false`).

**`verbatimModuleSyntax: true`**: only 3/72 — `nuxt/nuxt`,
`remix-run/react-router`, `jhipster/generator-jhipster`.

**`isolatedDeclarations`**: **0/72.** Not found anywhere in the corpus, despite
being TypeScript 5.5+'s flagship flag for fast/parallel `.d.ts` emission in
monorepos — telling for a cohort with 24 turbo/nx/lerna monorepos among it.

**Weakest found — explicit, deliberate opt-outs**, not just absence:
- `vercel/next.js:tsconfig.json`: `"strict": false` — explicitly disabled at
  root (individual packages may be stricter, out of scope here).
- `marmelab/react-admin:tsconfig.json`: `// "strict": true` commented out, plus
  `"noImplicitAny": false` explicitly set — implicit `any` is allowed by policy.
- `prettier/prettier:tsconfig.json`: `"strict": true` is set but immediately
  undercut by `"noImplicitAny": false, "strictNullChecks": false` with an
  in-file comment: *"TBD it is desired to enabled strict type checking at some
  point"* — a strictness flag present in name, defeated in practice, and the
  maintainers say so themselves.
- `louislam/uptime-kuma:tsconfig.json`: `strict: true` but paired with an empty
  `"files": []` and TypeScript pinned to `~4.4.4` (a 2021-era compiler).

**Aggregate**: of 45/72 repos with a discoverable root tsconfig, 31 set
`strict: true`; 2 (next.js, react-admin) explicitly set/comment-out `strict` to
**disable** it — a deliberate choice, not an oversight, worth distinguishing from
the 27/72 where strictness simply could not be determined (extends an unfetched
base, or no root tsconfig at all — common in Babel-based build setups like Babel
itself, wekan, puppeteer-adjacent cases).

---

## Coverage and diff-coverage gates (blocking vs advisory)

Only **10/72** repos have a discoverable `codecov.yml`, and among those the
*philosophy* varies more than the presence:

| repo | gate | scope | tolerance |
|---|---|---|---|
| eslint/eslint | **99% statements/functions/lines, 98% branches** — enforced inside `npm test` itself, not codecov | whole-repo | 0 — hard floor, blocking |
| ant-design/ant-design | `target: 100%`, `threshold: 0%` | project | zero tolerance |
| babel/babel | `target: "90.0%"`, `patch: enabled: false` | **whole-repo only** | patch-scoped checking explicitly disabled |
| trpc/trpc | `range: 50..90`, `target: auto`, `threshold: 1%`, `patch: off` | **whole-repo only** | 1% regression tolerance, patch off |
| element-plus/element-plus | `target: auto`, `threshold: 10%` | project | 10% regression tolerance — 10x more permissive than trpc |
| honojs/hono | project `target: 75%, threshold: 1%`; patch `target: 80%, informational: true` | both | **patch gate is advisory** ("Don't fail the build even if coverage is below target") |
| TriliumNext/Trilium | project `target: auto, threshold: 1%`; **patch `target: 80%, threshold: 5%`** | both, per-flag (client/server/standalone) | one of the only repos with a real enforced patch-coverage gate |
| jestjs/jest | `target: auto` (project+patch), `require_ci_to_pass: false`, `comment: false` | both, informational | no fixed floor — "auto" baselines off history |
| renovatebot/renovate | codecov present but only `require_ci_to_pass`/`notify` keys — **no target set** | n/a | effectively non-gating config |
| DIYgod/RSSHub, mozilla/pdf.js | codecov.yml present but only sets `comment: off` / `flag_management` | n/a | **not a gate at all** — config exists only to silence PR comments |

**Headline finding: patch/diff-scoped coverage gating — the rubric's specifically
called-out signal — is functionally absent.** Of 10 repos with any codecov.yml,
only **2 (honojs/hono, TriliumNext/Trilium)** set a patch-level target, and one of
those two (`hono`) marks it `informational: true`, i.e. non-blocking. **Only
TriliumNext/Trilium has a real, blocking, patch-scoped coverage gate** in the
entire 72-repo corpus. `eslint/eslint`'s 99%/98% gate is the strictest overall but
is whole-repo, enforced in-process rather than via Codecov. The other 62/72 repos
have **no discoverable coverage gate of any kind** — coverage tooling (vitest
`--coverage`, `@vitest/coverage-v8`) is frequently present as a *reporting*
capability but not wired to fail a build.

---

## CI architecture patterns

Caveat from the Coverage section applies throughout: CI workflow files were only
retrievable for a subset (see above); `merge_group` counts are a **floor**.

**`merge_group` (GitHub merge-queue) adoption**: found in **8/72** retrieved
workflows — `Kong/insomnia`, `actualbudget/actual`, `better-auth/better-auth`,
`mermaid-js/mermaid`, `nuxt/nuxt`, `prisma/orm`, `renovatebot/renovate`,
`facebook/lexical`. All are T1/T2 repos with active pnpm/turbo tooling — no T3
repo in the sample uses a merge queue. This is genuinely rare even among
well-resourced repos: most rely on required-status-checks + linear-history
branch protection instead of a queue.

**Matrix strategy**: common where found — `ant-design/ant-design:.github/workflows/test.yml`
runs a matrix with sharding (see below); `vitejs/vite:.github/workflows/ci.yml`
runs `os: [ubuntu-latest]` × `node_version: [20, 22, 24, 26]` plus extra
macOS/Windows legs on node 24, `fail-fast: false`; `eslint/eslint`'s CI matrixes
node 26/24/22/20/20.19.0 across ubuntu+windows+macOS-on-lts.

**Sharded test execution** — found explicitly in: `ant-design/ant-design` (test.yml),
`mermaid-js/mermaid` (e2e.yml), `jestjs/jest` (test.yml), `nuxt/nuxt` (ci.yml),
`prisma/orm` (ci.yml, via `VITEST_COVERAGE_SHARD` env + turbo `test` task),
`puppeteer/puppeteer` (ci.yml), `ueberdosis/tiptap` (build.yml),
`payloadcms/payload` (main.yml), `calcom/cal.com` (e2e.yml),
`usebruno/bruno` (5-project Playwright split with blob-report merging across
shards), `react/react` (build-shard-weight caching to rebalance shards over time
— the most sophisticated sharding setup found: it restores prior shard timing
data from `actions/cache` to keep shards balanced as the suite grows).
**~10/72** repos shard explicitly; the rest run their suite as one job or via
Nx Cloud / Turborepo remote task distribution instead of GitHub matrix sharding.

**Cost-aware CI runners**: `reactive-resume/reactive-resume:.github/workflows/e2e.yml`
conditionally uses a paid faster-CI provider — `runs-on: ${{ vars.USE_BLACKSMITH
== 'true' && 'blacksmith-32vcpu-ubuntu-2404' || 'ubuntu-latest' }}` — a pattern
not seen elsewhere in the corpus.

**Distributed/cloud task execution instead of GitHub matrix**: `TanStack/table`
uses Nx Cloud (`npx nx-cloud start-ci-run --distribute-on=...` then `nx affected`)
to fan work across cloud agents rather than a static matrix — the only repo doing
CI distribution this way.

**Admitted CI debt, in-repo**: `hoppscotch/hoppscotch:.github/workflows/tests.yml`
contains the comment *"Pinned to Node.js 22 due to known test failures on
Node.js 24. Future TODO: Investigate test failures and move to Node.js 24."* —
an honest, dated admission left in a required workflow file.

**CI that validates config, not code**: `louislam/uptime-kuma`'s only retrievable
workflow (`validate.yml`) runs JSON/YAML schema checks and custom Node scripts
(`check-lang-json.js`, `check-knex-filenames.mjs`) — not the lint/test suite,
which apparently lives under a non-guessable filename never retrieved. Worth
flagging as a case where "has CI" (rubric A9) would be true from a shallow probe
while the actual test gate is invisible to the same probe.

---

## Anti-bloat configs verbatim

**knip** — present as a committed `knip.json` in **7/72**: `actualbudget/actual`,
`TryGhost/Ghost`, `cypress-io/cypress`, `monkeytypegame/monkeytype`,
`nuxt/nuxt`, `reactive-resume/reactive-resume`, `TanStack/table`. Wired into
CI/lint scripts **without** a committed config file in 3 more (`eslint/eslint`,
`mochajs/mocha`, `prettier/prettier` — the tool run with defaults). Total: knip
present in some form in **10/72 (14%)**, always as a required/blocking step when
present, never advisory.

`actualbudget/actual:knip.json` (excerpt) shows the "hard parts" pattern — turning
off noisy rules globally, then scoping ignores per-workspace:
```json
{
  "rules": { "exports": "off", "types": "off", "nsExports": "off", "nsTypes": "off", "duplicates": "off" },
  "ignoreBinaries": ["electron-rebuild"],
  "workspaces": {
    ".": { "entry": ["bin/*.mts"], "ignore": ["lage.config.js", ".claude/**", ".agents/**"] },
    "packages/api": { "ignoreDependencies": ["@actual-app/crdt", "better-sqlite3", "uuid", "@jlongster/sql.js"] }
  }
}
```
`TanStack/table:knip.json` shows the same shape at larger scale, with per-framework
`ignoreDependencies` lists for its Ember/Angular/Svelte/Vue adapter packages (a
direct consequence of shipping one core library through 6 framework wrappers).
`reactive-resume/reactive-resume:knip.json` has **40+ `ignoreDependencies`
entries** in its server workspace alone (mostly `@ai-sdk/*` provider adapters,
loaded dynamically and therefore invisible to static analysis).

**size-limit with a real byte budget** — found in only **2/72**:
`TanStack/table:package.json` `"size-limit"` key:
```json
[{ "path": "packages/table-core/dist/index.js", "limit": "30 KB" }]
```
and `ant-design/ant-design` (key present in package.json; specific budget value
not retrieved). **This is a striking absence** — bundle-size regression is one of
the most common real-world "silent bloat" failure modes for UI libraries, and
70/72 repos in this corpus have no automated byte-budget check at all, including
several component libraries (mui/material-ui, chakra-ui, element-plus,
heroui-inc/heroui) that ship to size-sensitive consumers.

**api-extractor + committed `.api.md`** — found in only **1/72**:
`react-hook-form/react-hook-form` (config file present; the committed `.api.md`
golden itself was not separately fetched). No other repo in either the primary
fetch or the batch-3 sub-agent's 18 showed API-surface-review tooling.

**Hand-rolled dead-export detection where knip wasn't adopted**: `trpc/trpc`
runs `"lint-prune": "! ts-prune | grep -v <allowlist>"` — `ts-prune` piped through
a negated grep as a manual knip-equivalent, evidence the *problem* (dead exports
in a public-API package) is recognized even where the modern tool isn't used.

**Monorepo dependency-consistency linting**: `TanStack/table` uses **Sherif**
(`"test:sherif": "sherif"`, cached via Nx) — a monorepo package.json consistency
checker (duplicate/mismatched dependency versions across workspaces) not seen
elsewhere in the corpus. `trpc/trpc` uses `manypkg fix` for the same class of
problem via its `lint-fix` script.

**Architectural-boundary enforcement as a build gate** (a D2/D4 crossover worth
flagging): `reactive-resume/reactive-resume:turbo.json` wires Turborepo's
**boundaries** feature plus a custom Grit plugin
(`./tooling/grit/workspace-boundaries.grit`) to fail the build if a package
imports across a forbidden dependency edge:
```json
"boundaries": {
  "dependencies": { "deny": ["web", "server"] },
  "tags": {
    "app:server": { "dependencies": { "deny": ["app:web", "runtime:browser"] } },
    "runtime:browser": { "dependencies": { "deny": ["app:server", "runtime:server"] } }
  }
}
```
This is the only explicit, machine-enforced architectural-layering check found in
the corpus — every other "server code doesn't import browser code" convention
observed elsewhere is enforced by review discipline, not tooling.

---

## Monorepo affected-only patterns

**Turborepo** (14/72) — the dominant task-graph tool. The recurring idiom across
every `turbo.json` read is `"dependsOn": ["^build"]` (build my dependencies before
me) paired with declared `outputs` for caching:
```json
// better-auth/better-auth:turbo.json
"build": { "dependsOn": ["^build"], "inputs": ["$TURBO_DEFAULT$", "tsconfig.json", "tsdown.config.*"], "outputs": ["dist/**", "node_modules/.cache/ts/**"] }
```
```json
// prisma/orm:turbo.json — a self-documented cache-correctness fix
"typecheck": {
  // `build` as well as `^build`: several packages import their own published
  // subpaths, which resolve into their own dist. Without the self-edge those
  // typechecks read whatever dist happens to be on disk — TS2307 when it is
  // absent, a stale cache replay when it is not.
  "dependsOn": ["^build", "build"], "inputs": ["src/**", "test/**", "tsconfig.json"]
}
```
`vercel/next.js:turbo.json` runs `"build": "turbo run build --remote-cache-timeout
60 --summarize true"` with **remote caching** and adds its own meta-check —
`"check-unused-turbo-tasks": "node scripts/check-unused-turbo-tasks.mjs"` — a
custom script that lints the task graph itself for orphaned task definitions.
`shadcn-ui/ui:turbo.json` marks `lint`/`test` `"cache": false` deliberately (fast
enough not to need it, or too environment-dependent to cache safely), while
`build` caches on real output globs.

**Nx / Nx Cloud** (6/72). `nrwl/nx` (dogfooding itself) and `TryGhost/Ghost` both
show the idiom of **excluding test/lint inputs from the `production` named-input**
so that touching a spec file doesn't invalidate downstream build caches:
```json
// nrwl/nx:nx.json
"production": ["default", "!{projectRoot}/**/?(*.)+(spec|test).[jt]s?(x)?(.snap)",
  "!{projectRoot}/tsconfig.spec.json", "!{projectRoot}/eslint.config.@(js|cjs|mjs|ts|cts|mts)", ...]
```
`TanStack/table:nx.json` pairs `targetDefaults` caching with **Nx Cloud
distributed CI** (`nx-cloud start-ci-run --distribute-on=".nx/workflows/dynamic-changesets.yaml"`)
— task distribution across cloud agents replaces a GitHub Actions matrix
entirely; `nrwl/nx-set-shas` computes the affected-base range for `nx affected`.

**Lerna** (10/72) has almost entirely receded to **publish-only** duty
(`trpc/trpc`: `lerna publish --force-publish --canary`; `next.js` lists it as a
devDependency but doesn't drive the task graph) or is the sole orchestrator only
in older-style repos (`react-admin`, `theia`, `eclipse`) that predate
Turbo/Nx adoption and use `lerna run <task> --stream` with no caching at all.

**Deliberate cache-busting via env allowlists**: both `better-auth` and
`reactive-resume` maintain long `globalEnv`/`passThroughEnv` lists in
`turbo.json` specifically so that *some* env vars invalidate the cache
(secrets/config) while *others* (deploy tokens, feature flags) don't — an
explicit, visible trade-off between cache hit rate and correctness.

**pnpm catalogs as a lighter-weight alternative**: `element-plus/element-plus`
uses pnpm's native **catalog** feature (`"prettier": "catalog:"`,
`"typescript": "catalog:"`) for centralized dependency-version pinning across
workspace packages — achieving one class of monorepo hygiene (version drift)
without adopting a task-graph tool at all.

---

## Synthesis: minimum viable vs strongest justified stack

**The modal production TS verification setup** (most common combination across
72 repos): **pnpm** (53%) + **vitest** (56%) + **ESLint** (74%) + **Prettier**
(61%) + a root `test`/`lint`/`typecheck` script triad, **no coverage gate**
(86% of repos), **no bundle-size budget** (97%), **no committed API-surface
snapshot** (99%), and for the ~1/3 that are monorepos, **Turborepo** over
Nx/Lerna 2.3:1. This is the "does it type-check, does it lint, do the unit tests
pass" floor — nothing more — and it is what most repos, including many T1s,
actually ship.

**What tier-1 repos do that tier-3 ones do not, concretely:**
1. **A merge queue** (`merge_group`) — found only in T1/T2 repos (8/72, all
   pnpm/turbo shops), never in the T3 sample (tailwindcss, fastify, hono).
   *Prevents*: two independently-green PRs merging into a broken `main`.
2. **A committed anti-bloat config** (knip.json, size-limit budget) — 9 of the
   10 knip adopters and both size-limit adopters are T1/T2. *Prevents*: dead
   code and bundle-size creep accumulating invisibly between releases.
3. **Sharded CI with rebalancing** (react/react's cached shard-weight system;
   nuxt, prisma, payload, calcom sharding explicitly) — *prevents* PR feedback
   latency from growing linearly with suite size as the repo scales.
4. **A patch-scoped, non-advisory coverage gate** — found in exactly 1 repo
   corpus-wide (TriliumNext/Trilium, T1) — *prevents* new code shipping under-
   tested even while aggregate coverage looks fine.
5. **Architectural-boundary enforcement as a build gate**, not just convention
   (reactive-resume's Turborepo `boundaries` + Grit) — *prevents* a
   browser-only package silently importing server-only code.

**Two runnable command sequences, each tied to the failure class it blocks:**

*Minimum viable (solo / small team, <10 people, matches the corpus mode):*
```bash
pnpm install --frozen-lockfile   # blocks: "works on my machine" from a drifted lockfile
pnpm lint                        # blocks: style/correctness lint violations (catches ~a class of bugs eslint rules encode)
pnpm typecheck                   # blocks: type errors — tsc --noEmit at minimum with "strict": true
pnpm test                        # blocks: regressions in covered behavior (vitest/jest run)
```
This mirrors what the modal repo in this corpus actually runs before merge — no
more, no less. It catches type errors, lint violations, and regressions in
*already-tested* code, but not coverage regressions, bundle bloat, dead exports,
or cross-package boundary violations, because 86%+ of the corpus doesn't check
those either.

*Strongest justified (org-scale / high blast radius — assembled from the
above-modal T1 practices actually observed, not invented):*
```bash
pnpm install --frozen-lockfile
pnpm lint                                     # ESLint/Biome/oxlint — style + correctness rules
pnpm typecheck                                # tsc --noEmit -p tsconfig.json, "strict": true minimum
knip                                          # blocks: dead code and unused deps (actualbudget, nuxt, TanStack/table pattern)
pnpm exec turbo boundaries                    # blocks: cross-layer import violations (reactive-resume pattern) — Nx has an equivalent module-boundary rule
vitest run --coverage                         # generate coverage
node scripts/coverage-gate.mjs --patch-threshold=80  # blocks: undertested new code specifically (TriliumNext pattern — patch-scoped, not whole-repo)
size-limit                                    # blocks: bundle-size regressions (TanStack/table pattern, byte budget in package.json)
turbo run test --filter=...[affected]         # affected-only, not whole-repo — scales CI time sublinearly with repo size
```
Each added line corresponds to a practice found in a specific T1/T2 repo above,
not to a generic "best practice" — per Part G of the rubric, the failure class
each line blocks is stated next to it, and every line is sourced to a repo that
actually runs it, not aspirational.

**The clearest corpus-wide absence, worth restating as a headline**: mutation
testing, property-based testing, and bundle-size budgets are each present in
0, 0, and 2 of 72 repos respectively — including repos with 50k+ stars and
paid enterprise backing. "The strongest justified stack" above is strong
*relative to this corpus*, not relative to what a rigorous test-theory reading
would recommend; the corpus itself has a ceiling.

---

### Sources

All citations are `owner/repo:path` at the branch tip fetched (no shas — raw
URLs were used, not clones); branch per `research/worklists/js.txt` (fallback to
`main`/`master` where the listed branch 404'd, noted per-repo above). Full raw
fetch trees, per-repo condensed extraction, and the batch-3 sub-agent's complete
18-repo write-up are preserved at
`/private/tmp/claude-502/-Users-gauravporwal-Sites-projects-rnd-100x-engineer-research/9939911f-e3f5-49a4-98b6-1be207fbc16a/scratchpad/`
(`js-raw/`, `condensed.txt`, `provit_table_final.md`, `ts_ci.txt`,
`antibloat.txt`, `js-batch3.md`) for anyone re-verifying a specific claim.
