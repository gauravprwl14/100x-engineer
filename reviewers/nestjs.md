# NestJS reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

## Applies when
- `package.json` has `@nestjs/core` as a direct dependency.
- `nest-cli.json` or `.nest-cli.json` exists at the workspace root.
- Files matching `*.module.ts` with an `@Module(` decorator exist under `src/`.

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | Global `ValidationPipe` exists and sets `whitelist: true` (and ideally `forbidNonWhitelisted: true`) at bootstrap, not per-route | `grep -n "new ValidationPipe(" src/main.ts \| grep "whitelist"` exits non-zero if missing | mass-assignment: extra body fields silently reach the handler/entity |
| 2 | Every `@Controller` route handler's body/query param is typed with a DTO class, never `any`/`Record<string, unknown>`/`object` | `grep -rn "@Body() .*: \(any\|object\|Record\)" src/**/*.controller.ts` — must return empty | DTO validation bypassed by construction |
| 3 | A global exception filter (`@Catch()` + `APP_FILTER` or `app.useGlobalFilters`) is registered | `grep -rln "APP_FILTER\|useGlobalFilters" src/*.module.ts src/main.ts` — must be non-empty | unhandled exceptions leak stack traces / internal messages as 500 responses |
| 4 | `forwardRef()` usage has an inline comment explaining why, or a tracked ticket link | `grep -rn "forwardRef(" src --include=*.ts -B2 \| grep -c "//"` compared to `grep -rc "forwardRef("` — mismatch is a finding, not auto-fail | circular imports papering over a real layering mistake |
| 5 | `tsc --noEmit` passes with the repo's own `tsconfig.json` (no widening of `strict`) | `npx tsc --noEmit -p tsconfig.json` exits 0 | type errors an LLM introduced silently pass `nest build`'s transpile-only mode |
| 6 | No `catch` block that only logs and rethrows the original error without an `HttpException`/filter translation | review question: "does every `catch` either rethrow as an `HttpException` subtype, add context, or get handled by the global filter?" | 500s with framework-internal error shapes reaching clients |

## Common AI failure modes in this stack
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | Generates a full `xModule` + `xController` + `xService` + `xModule.ts` registration for a single utility function (e.g. "format a phone number") | Nest's own CLI (`nest g resource`) scaffolds exactly this shape, so the pattern is "idiomatic" even when the unit of work doesn't need DI at all | `git diff --stat` on the PR shows 4 new files for 1 real function; ask "is this ever injected into more than one place, or could it be a plain exported function?" | plain exported function/module until a second consumer or a mocking need exists; promote to a provider only then |
| 2 | Puts validation/business rules in the controller (`if (dto.role === 'admin') throw ...`) or on the TypeORM entity class instead of the service layer | Controllers "own" the request in tutorials, and NestJS entities are classes, which invites methods on them | `grep -rn "if (" src/**/*.controller.ts \| wc -l` — nonzero conditional/business logic in controllers is a smell; controllers should be arg-marshal + call-service only | move logic to the service; controller stays thin (auth guard + DTO + one service call + response shape) |
| 3 | Adds `@Injectable()` to every class "just in case," producing providers nobody lists in any `providers:` array or injects via constructor | `@Injectable()` is the first decorator shown in every Nest example, so it's applied reflexively | `grep -rl "@Injectable()" src \| xargs -I{} basename {} .ts` cross-referenced against `grep -rn "providers:" src/**/*.module.ts` — a class decorated but never in a `providers` array or constructor param is dead weight (immich-app/immich has 113 `@Injectable()` classes, all registered via a single `services` barrel array — `immich-app/immich@HEAD:server/src/services/index.ts` + `server/src/app.module.ts:44` `const common = [...repositories, ...services, ...]` — the registration is centralized and auditable, not ad hoc) | delete the decorator and the class, or register it; a provider with zero injectors is dead code |
| 4 | Omits `whitelist: true` / `forbidNonWhitelisted: true` from the global `ValidationPipe`, so a DTO with 3 declared fields silently accepts a 4th attacker-controlled field | `class-validator` DTOs look fully guarded because *declared* fields ARE validated — the gap (undeclared fields passing through) is invisible in a code read | `grep -n "new ValidationPipe(" src/main.ts` then check for `whitelist` — **this is a real production gap, not hypothetical**: `novuhq/novu@HEAD:apps/api/src/bootstrap.ts:109-113` registers the global pipe as `new ValidationPipe({ transform: true, forbidUnknownValues: false })` with no `whitelist` — three individual controllers (`novuhq/novu@HEAD:apps/api/src/app/inbox/inbox.controller.ts:681`, `app/human/human-interactions.controller.ts:64`, `app/step-resolvers/step-resolvers.controller.ts:126`) locally override with `whitelist: true` and a comment explaining why, meaning every *other* route in that app does not strip extra fields | set `whitelist: true` once, globally, at bootstrap; per-route overrides should only ever be more permissive with a documented reason, never the only place strictness exists |
| 5 | Types a request body as `@Body() body: any` or `@Body() body: Record<string, unknown>` "to unblock" a route, defeating the DTO entirely | Compiles instantly, no class-validator decorator errors to fight, looks like a temporary shortcut that never gets revisited | `grep -rn "@Body() .*: any\b" src/**/*.controller.ts` | write the DTO; if the shape is genuinely dynamic, use a discriminated union or `class-validator`'s `@ValidateIf`/polymorphic decorators, not `any` |
| 6 | Resolves a circular module dependency with `forwardRef(() => OtherModule)` on both sides instead of extracting the shared piece into a third module | `forwardRef` is Nest's documented, sanctioned escape hatch, so it reads as "the framework's way," not a workaround | count real usage: 28 `forwardRef(` call sites across `novuhq/novu@HEAD:apps/api/src` (mongoose/usecase-heavy app) vs. 0 across `immich-app/immich@HEAD:server/src` (strict layered repository/service/controller split, no module re-imports each other) — the same problem class, two very different outcomes, is direct evidence the boundary, not the tool, is the variable | extract the shared provider/interface into its own module both sides import; reach for `forwardRef` only as a last resort with a comment naming what would need to move to remove it |
| 7 | Does multi-row writes (create order + decrement stock + write ledger entry) as sequential `await repo.save()` calls with no transaction wrapper | Each call awaits and returns successfully in the happy path, and Nest doesn't force transaction boundaries the way some ORMs' unit-of-work patterns do | `grep -rn "async .*(" src/**/*.service.ts` where the body has >=2 `.save(`/`.insert(`/`.update(`/`.delete(` calls to different repositories and no `runTransaction`/`manager.transaction`/`dataSource.transaction`/`@Transactional()` wrapping them | wrap in `dataSource.transaction(async (manager) => {...})` (TypeORM) or the driver's transaction API; partial failure must roll back all writes, not just log and continue |
| 8 | Declares a TypeORM relation `eager: true` so every `find()` on the owning entity joins in the related table, or conversely leaves relations lazy and loops over results calling `.find()`/`.load()` per row | `eager: true` "just works" in the one screen the model was asked to build, and lazy-loop code passes tests against a 3-row fixture | grep for `eager:\s*true` in entity files and flag if the entity is used on hot list/search endpoints; for N+1, grep for `for (const \w+ of \w+)` blocks that contain an `await \w+Repository\.` call inside the loop — **real instance**: `ever-co/ever-gauzy@develop:packages/core/src/lib/organization/organization.entity.ts:590-598` sets `eager: true` on the `ImageAsset` `@ManyToOne`, with the framework's own doc comment on the line above admitting "Eager relations are always loaded automatically... using find* methods" — every `Organization` query now joins `image_asset` whether or not the caller needs it | use explicit `relations: [...]` or query-builder `leftJoinAndSelect` per call site instead of `eager: true`; batch related rows with `In(ids)` or a DataLoader instead of per-row awaits inside a loop |
| 9 | Catches an exception, logs it, and rethrows the raw `Error` (or a generic `InternalServerErrorException`) instead of letting the exception filter map it, so the client gets a 500 with an internal message | Looks defensive — "at least we logged it" — and still compiles/returns *a* response | review question: "for this catch block, does the rethrown/returned error carry a stable client-facing shape (`HttpException` subclass with a defined `statusCode`+`message` contract), or does it leak `error.message`/`error.stack` verbatim?" — compare against `immich-app/immich@HEAD:server/src/middleware/global-exception.filter.ts`, which explicitly strips the framework-injected `error` and `statusCode` duplicate fields before responding, and both `immich` and `novuhq/novu@HEAD:apps/api/src/exception-filter.ts` route every uncaught exception through one `@Catch()` filter that builds a stable `{message, ...}` DTO | let a single global filter own response shaping; a local `catch` should only add context (`throw new BadRequestException('...', { cause: error })`) or handle a specific recoverable case, never re-log-and-rethrow raw |
| 10 | Writes `async someMethod() { doSomethingAsync(); }` — forgets `await`, or fires a promise in a loop with `.forEach(async ...)` | TypeScript does not error on an unawaited promise by default; the method "runs" and returns before the async work finishes, and it's invisible until a race condition or an unhandled rejection crashes the process | `@typescript-eslint/no-floating-promises` and `@typescript-eslint/no-misused-promises` (catches `.forEach(async ...)` specifically, since `forEach` ignores the returned promise) — confirmed set to `'error'` in a real production config: `immich-app/immich@HEAD:server/eslint.config.mjs` (`'@typescript-eslint/no-floating-promises': 'error'`, `'@typescript-eslint/no-misused-promises': 'error'`, `'@typescript-eslint/require-await': 'error'`) | `await` every promise or explicitly mark fire-and-forget with `void promise.catch(handler)` (see the correct pattern below) |
| 11 | Reaches for `@Global()` on a module to make a provider available everywhere, instead of importing the specific module where it's needed | Removes a whole class of "forgot to import the module" errors in one line, so it feels like it "fixed" a DI error | `grep -rn "@Global()" src/**/*.module.ts` — every hit is a review point: "does this genuinely need to be available to every module in the app, or does it need explicit imports at 2-3 call sites?" — real example: `novuhq/novu@HEAD:apps/api/src/app/auth/auth.module.ts:14` is the *only* `@Global()` module in the entire novu API app (grep found exactly 1 across `apps/api/src`), consistent with treating it as a deliberate, rare exception rather than a default | import the module explicitly where its providers are consumed; reserve `@Global()` for true cross-cutting infra (logging, tracing, config) registered once at the composition root |
| 12 | Writes a service unit test that mocks the repository/dependency completely, calls the method, and asserts only `expect(result).toBeDefined()` or `expect(mockRepo.save).toHaveBeenCalled()` with no assertion on arguments or return shape | The test suite is green, coverage tools count the lines as "covered," and CI passes | `grep -c "expect(" path/to/*.spec.ts` relative to `wc -l` — a spec file with many `it(` blocks but few `expect(` calls per block is a smell; grep for `toHaveBeenCalled()` with **no** trailing `.toHaveBeenCalledWith(...)` on the same assertion chain | mock the boundary (repository/HTTP client) but assert both the return value the service produces AND the exact arguments passed downstream — see `immich-app/immich@HEAD:server/src/services/album.service.spec.ts` (`getStatistics` test mocks `mocks.album.getAll` and asserts the exact `{owned, shared, notShared}` result **and** the three distinct call signatures `getAll` was invoked with) as the pattern that avoids this; this ties to the industry-wide gap documented in `research/36-findings-antibloat-in-practice.md:431-459` — assertion-free/over-mocked tests are 1 of 5 AI-bloat failure modes with **zero mechanical CI coverage in any of 46 production repos surveyed**, `nestjs/nest` itself included (its own `CONTRIBUTING.md:217` only says tests are required in prose, and `package.json`'s `test:cov` script is suffixed `\|\| true`, making coverage collection explicitly non-blocking) — there is no tool to catch this; it must be a review question every time |

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | `Scope.REQUEST` provider injected into a `Scope.DEFAULT` (singleton) provider, silently making the whole chain request-scoped and re-instantiated per request (perf leak, or worse, state bleeding if assumed singleton) | Nest resolves this without error; it only shows up as a latency regression or memory growth under load | load test with request-scoped provider count logged (`onModuleInit` counter); or `grep -rn "Scope.REQUEST" src` and manually trace each injector's own scope — real usage at scale: `novuhq/novu@HEAD` has request-scoped usecases in `app/organization/usecases/*`, `app/invites/usecases/*`, `app/events/events.controller.ts:58`, each declared deliberately per-usecase, not accidentally inherited |
| 2 | No `app.enableShutdownHooks()` call, so `SIGTERM` during a rolling deploy kills in-flight requests and open DB/queue connections instead of draining them | Works fine in local dev (`Ctrl+C` just exits); only breaks under an orchestrator sending `SIGTERM` with a grace period | deploy under Kubernetes/ECS with a short termination grace period and watch for connection-reset errors during rollout; confirmed present in `novuhq/novu@HEAD:apps/api/src/bootstrap.ts:186` (`app.enableShutdownHooks();`) |
| 3 | No health check endpoint distinguishing liveness (process up) from readiness (DB/queue reachable), so the orchestrator routes traffic to a pod that's up but can't reach Postgres | Adding *a* `/health` returning `200 OK` unconditionally is the fast path and passes a smoke test | `curl` health endpoint with DB down (stop the DB container) — must return non-200; `@nestjs/terminus` wired to a real check is present in `novuhq/novu@HEAD:apps/api/src/app/health/health.controller.ts` |
| 4 | Outbound HTTP calls (`HttpModule`/`fetch` to a third-party API) have no timeout, so one slow upstream call hangs a request handler indefinitely and exhausts the event loop/connection pool under load | `axios`/`fetch` default timeout is effectively infinite; the call "works" in dev against a fast local/staging dependency | integration test with a deliberately slow mock upstream (delay > expected SLA) — request must fail fast, not hang; review question: "does every `HttpModule.register()`/axios instance set `timeout`?" |
| 5 | Retried writes (client retries a POST after a timeout, without having seen the first response) create duplicate rows because there's no idempotency key check | The happy-path single request works; duplication only appears under network flakiness or client retry logic the backend author didn't write | send the same POST twice with the same idempotency key and assert only one row/side-effect; real implementation: `novuhq/novu@HEAD:apps/api/src/app/shared/framework/idempotency.interceptor.ts`, wired globally at `app.module.ts:53` |
| 6 | List endpoints (`GET /albums`, `GET /users`) have no enforced max `take`/`limit`, so a client (or a scraping bot) can request `?take=1000000` and the DB does a full table scan | Pagination DTOs commonly validate `take` is a number but not that it's bounded | `@Max(100)` (or similar) on the pagination DTO's `take`/`limit` field; test: request with an absurd `take` and assert a 400, or assert response is capped, not that the DB fell over |
| 7 | Transaction wraps the writes but a side effect *outside* the transaction (email send, queue publish, webhook) fires before the commit is confirmed, so a rolled-back transaction still triggers the side effect | Side effects and DB writes are visually adjacent in the same service method, so it reads as "atomic" even though only the DB calls are | review question: "if the transaction rolls back after this line runs, does anything externally observable (email, webhook, queue message) already have happened?" — move side effects to an `afterCommit` hook or an outbox pattern |
| 8 | Timestamps stored/compared without a consistent timezone (`new Date()` mixed with DB `now()`, or comparing a UTC column against a client's local-time string uncritically) | Works in every dev/CI environment because they're all UTC; breaks only for users in other timezones or during DST transitions | test with `TZ=America/Sao_Paulo` (or another non-UTC, DST-observing zone) set on the test process; assert stored/returned timestamps are UTC-normalized |
| 9 | Two concurrent requests read-modify-write the same row (e.g. decrement stock) with no optimistic lock (`@VersionColumn`) or `SELECT ... FOR UPDATE`, causing lost updates under load | Passes every manual/sequential test; only fails under concurrent load, which most PR-level testing never simulates | fire N concurrent requests against the same row and assert the final value equals `initial - N`, not something less negative (lost updates) |
| 10 | DTO validates on the way in but the service layer trusts the DTO's *type* for authorization too (e.g. a `patientId` in the body is used directly without checking it belongs to the authenticated user) — mass-assignment's authorization cousin | `class-validator` decorators make the DTO look "fully checked," but type validity is not the same as ownership/authorization validity | review question: "for every ID accepted in a DTO, is there an explicit ownership/tenant check before it's used in a query, separate from the shape validation?" |

## Approach selection
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| ORM | TypeORM vs Prisma vs Drizzle vs a query builder (Kysely) | TypeORM's Active-Record-ish entity classes and `eager` relations make it easy to accidentally couple validation/business logic onto entities (see failure mode #2, #8) and its migration story is comparatively weak; Prisma's generated client + migration tool is the most "batteries included" for CRUD-heavy APIs; Kysely (used by `immich-app/immich`, 115k★, D-score 11 in `research/10-repo-corpus.md`) gives up ORM convenience for zero hidden joins/eager-loading and fully typed raw-SQL-shaped queries — the right call once query complexity/perf tuning matters more than CRUD velocity | **Prisma** for new CRUD-shaped services (typed client, first-class migrations, smallest surface for an LLM to misuse); reach for Kysely/raw query builder only once you've hit TypeORM's `eager`/lazy-relation footguns in practice — do not default to TypeORM for a new project |
| API style | REST vs GraphQL vs tRPC | REST is what `@nestjs/swagger` + `ValidationPipe` + guards are built around and is what every reviewed production Nest app (`novu`, `immich`) actually ships; GraphQL (`@nestjs/graphql`) adds a schema-first/code-first decision and a whole N+1/dataloader problem class on top of the ORM one; tRPC has no first-class Nest integration and fights the framework's DI/decorator model | **REST** with `@nestjs/swagger` for OpenAPI generation, unless the frontend team is already committed to GraphQL for a specific aggregation need |
| Module granularity | one module per feature (vertical slice) vs one module per architectural layer (`ControllersModule`, `ServicesModule`) | layer-based modules force every feature to import a monolithic "everything" module, defeating Nest's DI boundary entirely and making `forwardRef` common by construction; feature modules keep the `forwardRef` count near zero, as seen in `immich-app/immich@HEAD:server/src` (0 `forwardRef` call sites) vs. `novuhq/novu@HEAD:apps/api/src` (28, in a codebase organized by feature but with a flatter/usecase-heavy import graph) | **feature-based** (one module per bounded domain: `album.module.ts`, `user.module.ts`), each exporting only what other modules actually need |
| Service internals | fat service classes (one `AlbumService` with 20 methods) vs one-class-per-operation ("usecase"/command pattern) | fat services are faster to scaffold and easier to navigate for a small surface; usecase-per-operation (each operation is its own injectable class with one `execute()` method) keeps each unit trivially unit-testable and makes unused operations detectable by unused-provider tooling, at the cost of many more files — `novuhq/novu@HEAD:apps/api/src/app/*/usecases/*` uses this pattern at scale (hundreds of usecase classes) | **fat service per feature module** for teams under ~10 engineers (fewer files to navigate, DI graph stays legible); switch to usecase-per-operation only once a single service file routinely exceeds ~300-400 lines or gets touched by unrelated features in the same PR |
| DTO validation | `class-validator` + `class-transformer` vs `zod` (via `nestjs-zod`) | `class-validator` is what `nest g resource` scaffolds and has the deepest Nest/Swagger integration (decorators double as OpenAPI metadata); `zod` gives a single schema usable on both server and a shared client/SDK package, and forces explicit, compile-checked shapes instead of decorator metadata reflection — `immich-app/immich` runs `ZodValidationPipe`/`ZodSerializerInterceptor` globally (`server/src/app.module.ts`) for exactly this reason | **class-validator** for a Nest-only backend with no shared TS client package (best framework integration, least new tooling); switch to **zod** the moment a monorepo shares types with a frontend or SDK package |
| Config | `@nestjs/config` `ConfigModule` (untyped `.get('KEY')`) vs a typed env schema validated at boot | untyped `configService.get('PORT')` returns `any`/`string \| undefined` and fails silently (`undefined` used as a number) instead of failing at boot; a typed, validated schema fails fast with a clear error before the app starts serving traffic | **typed env schema validated at bootstrap** — `zod`'s `EnvSchema.parse()` (immich pattern, `server/src/dtos/env.dto.ts` consumed by `server/src/repositories/config.repository.ts`) or `class-validator`-based `ConfigModule.forRoot({ validate })`; never leave `ConfigService.get()` calls untyped in service code |
| Testing | unit tests with mocked repositories vs integration tests against a real DB (Testcontainers) | mocked-repository unit tests are fast and are what every large reviewed repo runs on every PR, but per failure mode #12 they degrade to assertion-free scaffolding without discipline; Testcontainers-based integration tests catch real SQL/migration/constraint bugs mocks cannot, at a real CI-time cost | **both, in separate tiers**: fast mocked-repository unit tests on every PR (mock the repository interface, assert return value + call args — not just "was called"), plus a smaller Testcontainers integration suite covering the handful of endpoints with real multi-table writes/transactions, run on every PR but allowed to be slower |
| Monorepo tooling | Nx vs Turborepo vs plain npm/pnpm workspaces | Nx gives affected-only builds/tests and enforceable module-boundary tags (`@nx/enforce-module-boundaries`) out of the box, which is the single mechanically-working architecture gate found across the corpus (`research/36-findings-antibloat-in-practice.md`, failure mode #12 "import cycle/layer crossing" is the *best-covered* architectural mode); Turborepo is lighter but has no built-in boundary enforcement; plain workspaces have neither | **plain pnpm workspaces** for a single Nest app + maybe one shared `packages/types`; move to **Nx** once you have 3+ independently deployable Nest services/apps in one repo and need enforced boundaries and affected-only CI |
| Auth | Passport strategies (`@nestjs/passport`) vs hand-rolled guards | Passport is the documented, first-class Nest integration for JWT/OAuth/local strategies and is what both `novu` (`passport.initialize()` in `bootstrap.ts`) and the framework's own docs assume; hand-rolled guards duplicate strategy logic (token parsing, expiry checks) per project with no shared test coverage | **Passport strategies** for standard JWT/session/OAuth auth; write a custom `CanActivate` guard only for authorization (role/permission checks) layered on top of an already-authenticated request, never to reimplement authentication |

## Verify
```bash
# --- fast, every PR, diff-scoped where the tool supports it ---

# typecheck — full project, ~10-60s depending on repo size; catches type errors nest build's
# transpile-only default swallows
npx tsc --noEmit -p tsconfig.json

# lint — repo's own config; flag if @typescript-eslint/no-floating-promises,
# no-misused-promises, require-await are not set to "error" (see failure mode #10)
npx eslint 'src/**/*.ts' --max-warnings 0
# diff-scoped variant:
npx eslint $(git diff --name-only --diff-filter=ACM origin/main... -- '*.ts') --max-warnings 0

# nest's own build (catches DI wiring errors tsc alone won't — a provider requested but
# not exported/imported fails here, not at tsc time)
npx nest build

# unit tests + coverage — treat the coverage number as informational only; nestjs/nest's own
# package.json suffixes test:cov with `|| true`, i.e. even the framework's own repo does not
# gate merges on it. Gate on the tests PASSING, not on a coverage threshold nobody enforces.
npx jest --coverage --passWithNoTests
# diff-scoped: only run specs touching changed files
npx jest --coverage --findRelatedTests $(git diff --name-only --diff-filter=ACM origin/main... -- '*.ts')

# grep-based checks with no off-the-shelf tool (run these explicitly; nothing else catches them)
grep -n "new ValidationPipe(" src/main.ts | grep -q "whitelist" || echo "FAIL: no whitelist:true on global ValidationPipe"
grep -rn "@Body() .*: any\b" src/**/*.controller.ts && echo "FAIL: any-typed request body"
grep -rln "APP_FILTER\|useGlobalFilters" src/*.module.ts src/main.ts | grep -q . || echo "FAIL: no global exception filter registered"
```

```js
// .dependency-cruiser.cjs — module-boundary enforcement, the one architectural gate that
// mechanically works (research/36-findings-antibloat-in-practice.md, failure mode #12 is the
// best-covered anti-bloat mode in production; pattern adapted from
// TryGhost/Ghost@7c30676:.dependency-cruiser.cjs, the cleanest ruleset found in that survey).
// Assumes feature modules under src/<feature>/ that should not reach into each other's
// internals, only their public module export.
module.exports = {
  forbidden: [
    {
      name: 'no-cross-feature-deep-import',
      comment: 'features may depend on another feature\'s module/index, never its internals',
      severity: 'error',
      from: { path: '^src/([^/]+)/.+' },
      to: {
        path: '^src/([^/]+)/(?!\\1).+\\.(service|repository|entity)\\.ts$',
        pathNot: '\\.module\\.ts$',
      },
    },
    {
      name: 'no-circular',
      comment: 'circular module deps force forwardRef() and hide layering mistakes',
      severity: 'error',
      from: {},
      to: { circular: true },
    },
    {
      name: 'no-controller-imports-controller',
      comment: 'controllers call services, never each other',
      severity: 'error',
      from: { path: '\\.controller\\.ts$' },
      to: { path: '\\.controller\\.ts$', pathNot: '^(?:same file)$' },
    },
  ],
  options: { tsPreCompilationDeps: true, tsConfig: { fileName: 'tsconfig.json' } },
};
```

```json
// eslint-plugin-boundaries alternative (if the repo already runs flat-config eslint and wants
// one tool instead of two): tag src/<feature>/ dirs as element type "feature", forbid
// feature -> feature imports except through the feature's own index/module file.
{
  "settings": {
    "boundaries/elements": [
      { "type": "feature", "pattern": "src/*/", "capture": ["feature"] }
    ]
  },
  "rules": {
    "boundaries/element-types": ["error", {
      "default": "disallow",
      "rules": [{ "from": "feature", "allow": ["feature"], "disallowExceptForward": true }]
    }]
  }
}
```

Expected runtime: `tsc --noEmit` + `eslint` + `nest build` under 2 minutes on a mid-size (~200 file)
Nest app; `jest --coverage` full-repo is the slow one (budget 3-5 min) — always prefer the
`--findRelatedTests` diff-scoped form on a PR.

## Sources
- `nestjs/nest@master:CONTRIBUTING.md:217` — "All features or bug fixes must be tested by one or
  more specs (unit tests)," prose-only test requirement, no enforcing CI check found.
- `nestjs/nest@master:package.json` — `"test:cov": "vitest run --coverage --config vitest.config.coverage.mts || true"`, coverage collection explicitly non-blocking; `"lint": "oxlint packages integration"`.
- `immich-app/immich@HEAD:server/src/app.module.ts` — `APP_PIPE`→`ZodValidationPipe`, `APP_FILTER`→`GlobalExceptionFilter`, `APP_INTERCEPTOR`→`ZodSerializerInterceptor`/`LoggingInterceptor`/`ErrorInterceptor`, all wired centrally.
- `immich-app/immich@HEAD:server/src/middleware/global-exception.filter.ts` — single `@Catch()` filter, strips duplicate `error`/`statusCode` fields, translates `ZodValidationException`.
- `immich-app/immich@HEAD:server/package.json` — `"lint": "eslint ... --max-warnings 0"`, `"check": "tsc --noEmit"`, `"check:all": "pnpm run check:code && pnpm run test:cov"`, `vitest` as the runner.
- `immich-app/immich@HEAD:server/eslint.config.mjs` — `@typescript-eslint/no-floating-promises`, `no-misused-promises`, `require-await` all set to `'error'`.
- `immich-app/immich@HEAD:server/src/services/album.service.spec.ts` — mocked-repository unit test asserting both return value and call arguments (191 `expect(` across 1429 lines).
- `immich-app/immich@HEAD:server/src/repositories/*.repository.ts` — Kysely query builder with explicit `innerJoin`/`leftJoin`/`selectAll`, no ORM-implicit relation loading.
- `immich-app/immich@HEAD:server/src` — 0 `forwardRef(` call sites (grep across full `src/`).
- `novuhq/novu@HEAD:apps/api/src/bootstrap.ts:109-113` — global `ValidationPipe({ transform: true, forbidUnknownValues: false })`, no `whitelist`.
- `novuhq/novu@HEAD:apps/api/src/app/inbox/inbox.controller.ts:681`, `apps/api/src/app/human/human-interactions.controller.ts:64`, `apps/api/src/app/step-resolvers/step-resolvers.controller.ts:126` — per-route `whitelist: true` overrides with explanatory comments.
- `novuhq/novu@HEAD:apps/api/src/exception-filter.ts` — `AllExceptionsFilter`, structured `ErrorDto`, fire-and-forget analytics write with explicit `.catch()`.
- `novuhq/novu@HEAD:apps/api/src` — 28 `forwardRef(` call sites (grep).
- `novuhq/novu@HEAD:apps/api/src/app/auth/auth.module.ts:14` — the only `@Global()` module in the app.
- `novuhq/novu@HEAD:apps/api/src/bootstrap.ts:186` — `app.enableShutdownHooks();`.
- `novuhq/novu@HEAD:apps/api/src/app/health/health.controller.ts` — `@nestjs/terminus`-based health check module.
- `novuhq/novu@HEAD:apps/api/src/app/shared/framework/idempotency.interceptor.ts`, wired at `apps/api/src/app.module.ts:53`.
- `novuhq/novu@HEAD:apps/api/src/app/*/usecases/*` — one-class-per-operation ("usecase") pattern used at scale, hundreds of files.
- `novuhq/novu@HEAD:apps/api/src` — `Scope.REQUEST` usage in `app/organization/usecases/*`, `app/invites/usecases/*`, `app/events/events.controller.ts:58`, `app/integrations/usecases/*`.
- `ever-co/ever-gauzy@develop:packages/core/src/lib/organization/organization.entity.ts:590-598` — `@ManyToOne(() => ImageAsset, { eager: true })`, with the codebase's own comment: "Eager relations are always loaded automatically when relation's owner entity is loaded using find* methods."
- `ever-co/ever-gauzy@develop:packages/core/package.json` — no `typeorm-transactional` dependency present.
- `research/36-findings-antibloat-in-practice.md:431-459` — cross-repo (46 repos) finding that assertion-free/over-mocked tests have zero mechanical CI coverage in any surveyed production repo; cited verbatim for failure mode #12 above.
- `research/10-repo-corpus.md:95,130,65,141` — signal scores for `nestjs/nest` (10), `typeorm/typeorm` (13), `prisma/orm` (17), `immich-app/immich` (11), establishing corpus admission.
- `TryGhost/Ghost@7c30676:.dependency-cruiser.cjs` — cited via `research/36-findings-antibloat-in-practice.md:191` as the cleanest real dependency-cruiser ruleset found; adapted (not copied) for the Nest feature-module boundary example above.
- SOURCE: original — the `.dependency-cruiser.cjs` and `eslint-plugin-boundaries` snippets in `## Verify` are hand-written for this reviewer, adapting the Ghost pattern to a generic Nest feature-module layout; no production Nest repo in the corpus was found running either tool directly (absence noted per Part G rule 6).
