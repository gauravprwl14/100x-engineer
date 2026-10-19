# Express + Node.js reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

For NestJS (which runs on Express) use `nestjs.md` instead; this file covers plain Express,
and Node services built on Express-style middleware.

## Applies when
- `package.json` has `express` as a direct dependency and no `@nestjs/core`.
- A module calls `express()` or `express.Router()`; `app.use(` / `router.get(` appear in the diff.

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | No floating promise and no promise passed where a callback is expected (`arr.forEach(async ...)`, an `async` handler on an `EventEmitter`) | `npx eslint --rule '{"@typescript-eslint/no-floating-promises":"error","@typescript-eslint/no-misused-promises":"error"}' <changed>` (type-aware config required) | work that finishes after the response, or an unhandled rejection; since Node 15 the default `--unhandled-rejections=throw` crashes the process (`nodejs/node@main:doc/api/cli.md`) |
| 2 | On Express 4, every `async` handler catches and calls `next(err)` (or is wrapped); on Express 5 a rejected handler promise reaches `next` automatically | `grep -n '"express"' package.json` for the major; on 4.x: review every `async (req, res` handler for a `try`/`catch` that calls `next(err)` | Express 4 never sees the rejection: the request hangs until the client times out (`expressjs/expressjs.com@main:src/content/docs/en/4x/guide/error-handling.mdx`; `.../en/5x/guide/error-handling.mdx`) |
| 3 | One error-handling middleware with four arguments `(err, req, res, next)` is registered after all routes, maps known errors to status codes, and never sends `err.stack` or `err.message` of an unknown error to the client | `grep -rnE "\(err, req, res, next\)" src` non-empty; review its position (last `app.use`) and response body | stack traces and internal messages in 500 responses; a three-argument "error handler" that Express treats as normal middleware |
| 4 | Every route validates `req.body`, `req.query` and `req.params` against a schema before use | review: does each handler parse input with zod/joi/express-validator (`schema.safeParse(req.body)`) before reading a field? | type confusion (`?id[]=1` arrives as an array), 500s on missing fields, injection |
| 5 | `helmet()` is registered before routes; CORS has an explicit origin list on credentialed routes | `grep -rn "helmet()" src` non-empty; `grep -rnE "cors\(\)\|origin:\s*(true\|'\*')" src` empty | missing security headers; any site reading authenticated responses (`expressjs/expressjs.com@main:src/content/pages/en/advanced/best-practice-security.mdx`, "Use Helmet") |
| 6 | No recursive merge or dynamic property write with client-controlled keys (`obj[key] = v`, `_.merge`, `Object.assign` over a parsed body into a shared object) unless keys are allowlisted or the target is `Object.create(null)` / a `Map` | `grep -rnE "\[(req\.(body\|query\|params)\|key\|k)\]\s*=" src`; review every deep-merge of request data | prototype pollution: `{"__proto__": {"isAdmin": true}}` changes every object (`OWASP/CheatSheetSeries@master:cheatsheets/Prototype_Pollution_Prevention_Cheat_Sheet.md`) |
| 7 | Body parsers keep a size limit (`express.json()` defaults to `100kb`); raising it is a stated decision | `grep -rnE "limit:\s*['\"][0-9]+(mb\|gb)" src` reviewed | memory exhaustion and long `JSON.parse` blocking (`expressjs/body-parser@master:README.md`) |

## Common AI failure modes in this stack
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | Writes `async (req, res) => { const u = await db.find(); res.json(u) }` on Express 4 with no `try`/`catch` | identical code is correct on Express 5 and in most tutorials | blocking rule 2 | wrap, or upgrade to Express 5 |
| 2 | Calls `res.json(...)` and keeps going (no `return`), then sends again in a later branch | each branch looks complete on its own | `ERR_HTTP_HEADERS_SENT` in logs; review: every `res.send/json/status().end` that is not the last statement is preceded by `return` | `return res.status(400).json(...)` |
| 3 | Error middleware with three arguments, or registered before the routes | it "catches errors" in the one test | blocking rule 3 | four-argument handler, registered last |
| 4 | Reads `req.body.amount` as a number without parsing | JSON bodies usually carry numbers | review; schema validation (rule 4) | coerce and validate in the schema |
| 5 | Logs the whole `req.body` or `req.headers` | helps debugging | `grep -rnE "log.*req\.(body\|headers)" src` | log an allowlist of fields; redact `authorization`, `cookie`, passwords |
| 6 | Fires a side effect without awaiting it to "make the response faster" | latency improves | `@typescript-eslint/no-floating-promises` | await it, or hand it to a queue; if fire-and-forget is intended, `void p.catch(log)` |
| 7 | Uses `fs.readFileSync`, `crypto.pbkdf2Sync` or `bcrypt.hashSync` in a request path | simpler than callbacks | `grep -rnE "Sync\(" src` outside startup code; `node --trace-sync-io` | async variants; Express's guide says sync calls are justified only at startup (`expressjs/expressjs.com@main:src/content/pages/en/advanced/best-practice-performance.mdx`, "Don't use synchronous functions") |

## Language pitfalls (JavaScript / TypeScript)
| # | pitfall | what goes wrong | detection | correct move |
|---|---------|-----------------|-----------|--------------|
| 1 | missing `await` | the function returns before the work ends; errors become unhandled rejections | `@typescript-eslint/no-floating-promises`, `require-await` | `await`, or return the promise |
| 2 | `forEach(async ...)` | `forEach` ignores the returned promises, so nothing waits and nothing catches | `@typescript-eslint/no-misused-promises` | `for (const x of xs) await f(x)` for order, `await Promise.all(xs.map(f))` for concurrency (`typescript-eslint/typescript-eslint@main:packages/eslint-plugin/docs/rules/no-misused-promises.mdx`) |
| 3 | prototype pollution | `__proto__`, `constructor`, `prototype` keys in parsed JSON reach `Object.prototype` through merges | blocking rule 6; run with `node --disable-proto=delete` | `Map`, `Object.create(null)`, key allowlists (`nodejs/node@main:doc/api/cli.md`, `--disable-proto`) |
| 4 | `==` coercion | `"0" == 0`, `null == undefined`, `[] == false` are true | eslint `eqeqeq` | `===` |
| 5 | number precision | IEEE doubles: `0.1 + 0.2 !== 0.3`; ids above `2**53` lose digits through `JSON.parse` | review money and big-id fields | integer minor units or a decimal library for money; ids as strings |
| 6 | `this` lost in callbacks | `app.get("/", controller.handle)` calls `handle` with `this` undefined | review class-method handlers passed by reference | arrow functions or `.bind(controller)` |

## Security defaults
| what Express does not do by default | where it bites | the line that adds it |
|-------------------------------------|----------------|-----------------------|
| security headers | clickjacking, MIME sniffing | `app.use(helmet())` (`helmetjs/helmet@main:README.md`) |
| hide the framework | `X-Powered-By: Express` aids fingerprinting | `app.disable("x-powered-by")` or helmet (best-practice-security, "Reduce fingerprinting") |
| rate limiting | credential stuffing on `/login` | `express-rate-limit` on auth routes (`express-rate-limit/express-rate-limit@main:readme.md`) |
| input validation | every handler | blocking rule 4 |
| CSRF protection for cookie sessions | forged POSTs | `SameSite` cookies plus a CSRF token middleware; review when sessions use cookies |
| object-level authorization | `GET /orders/:id` returns any user's order | review: is every lookup by id filtered by the authenticated user or tenant? (`SOURCE: original`) |

## Performance
| # | issue | detection | correct move |
|---|-------|-----------|--------------|
| 1 | sync APIs and CPU work on the event loop | `node --trace-sync-io`; event-loop lag metric | async APIs, worker threads, or a queue (`nodejs/learn@main:pages/asynchronous-work/dont-block-the-event-loop.md`) |
| 2 | ReDoS: a user string matched against a backtracking regex | review new regexes with nested quantifiers (`(a+)+`) applied to request data | linear patterns, length caps (same doc, "Blocking the Event Loop: REDOS") |
| 3 | `JSON.parse` / `JSON.stringify` on large payloads | body size limit (rule 7) | stream or cap (same doc, "JSON DOS") |
| 4 | `await` inside a loop over independent items, or one query per item (N+1) | eslint `no-await-in-loop` | batch the query (`WHERE id IN (...)`, ORM `include`), or a DataLoader per request (`graphql/dataloader@main:README.md`) |
| 5 | outbound `fetch` with no timeout | review | `AbortSignal.timeout(ms)` |

## Test conventions
| # | convention | check |
|---|------------|-------|
| 1 | Route tests run the real app in-process with supertest (`request(app).get(...)`), asserting status, body and side effect | `ladjs/supertest@master:README.md` |
| 2 | Each route has an error-path test: invalid input expects 400, unknown id expects 404, a thrown dependency expects the error middleware's shape | review |
| 3 | Unit tests never hit the network; mock at the HTTP client or repository boundary and assert the call arguments | review |
| 4 | Tests that `await` nothing are a smell: an un-awaited `request(app)` passes even when the assertion fails | `@typescript-eslint/no-floating-promises` on test files too |

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | query param sent twice (`?id=1&id=2`) arrives as an array | clients send it once | test expects 400 from the schema |
| 2 | body with `__proto__` / `constructor` keys | nobody writes that by hand | test posts `{"__proto__":{"x":1}}` and asserts `({}).x === undefined` afterwards |
| 3 | `SIGTERM` during a deploy | local `Ctrl+C` just exits | on `SIGTERM`, `server.close()` then close pools; test sends SIGTERM mid-request |
| 4 | slow client upload | fast local network | Node 18+ `server.requestTimeout` defaults to 300s; set it to the route's real budget (`nodejs/node@main:doc/api/http.md`) |
| 5 | async error thrown after the response was sent | rare branch | test asserting no `ERR_HTTP_HEADERS_SENT` in logs |

## Approach selection
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| Express major | 4 / 5 | can you upgrade? | **Express 5** for new code (async errors forwarded); on 4, wrap every async handler |
| validation library | zod / joi / express-validator | TypeScript and shared types | **zod** (`schema.safeParse`) for TypeScript (`colinhacks/zod@main:README.md`) |
| framework | Express / Fastify / NestJS | team size and need for DI and modules | **follow the repo**; NestJS once the service has many modules and teams (`nestjs.md`) |
| test runner | jest / vitest / `node:test` | existing tooling | **follow the repo**; `node:test` needs no dependency (`nodejs/node@main:doc/api/test.md`) |

## Verify
```bash
CHANGED=$(git diff --name-only --diff-filter=ACM origin/main... -- '*.ts' '*.js')

# type-aware lint: no-floating-promises, no-misused-promises, eqeqeq, no-await-in-loop
npx eslint $CHANGED --max-warnings 0
npx tsc --noEmit

# tests, including error paths
npm test

# runtime check for sync IO in request paths (dev only)
node --trace-sync-io dist/server.js

# grep checks no tool covers
grep -rnE "\(err, req, res, next\)" src >/dev/null || echo "FAIL: no 4-argument error middleware (rule 3)"
grep -rn "helmet()" src >/dev/null || echo "FAIL: helmet not registered (rule 5)"
grep -rnE "cors\(\)|origin:\s*(true|'\*')" src && echo "FAIL: CORS without an origin list (rule 5)"
grep -rnE "Sync\(" src --include='*.ts' --include='*.js' && echo "REVIEW: sync API, startup only"
```

## Sources
- `expressjs/expressjs.com@main:src/content/docs/en/4x/guide/error-handling.mdx` and `src/content/docs/en/5x/guide/error-handling.mdx`: async errors need `next(err)` on 4; rejected promises call `next` on 5; four-argument error handlers.
- `expressjs/expressjs.com@main:src/content/pages/en/advanced/best-practice-security.mdx` ("Use Helmet", "Reduce fingerprinting") and `best-practice-performance.mdx` ("Don't use synchronous functions", `--trace-sync-io`).
- `expressjs/body-parser@master:README.md`: `limit` default `'100kb'`.
- `nodejs/node@main:doc/api/cli.md`: `--unhandled-rejections` default `throw`; `--disable-proto`. `doc/api/http.md`: `server.requestTimeout` default 300000 since v18. `doc/api/process.md`: `'unhandledRejection'`. `doc/api/test.md`.
- `nodejs/learn@main:pages/asynchronous-work/dont-block-the-event-loop.md`: ReDoS and JSON DoS.
- `typescript-eslint/typescript-eslint@main:packages/eslint-plugin/docs/rules/no-floating-promises.mdx`, `no-misused-promises.mdx`; `eslint/eslint@main:docs/src/rules/no-await-in-loop.md`.
- `OWASP/CheatSheetSeries@master:cheatsheets/Prototype_Pollution_Prevention_Cheat_Sheet.md`: `Map`/`Set`, `Object.create(null)`.
- `helmetjs/helmet@main:README.md`; `express-rate-limit/express-rate-limit@main:readme.md`; `ladjs/supertest@master:README.md`; `graphql/dataloader@main:README.md`; `colinhacks/zod@main:README.md`.
- `SOURCE: original`: the tenant-scoping review question, `return res...` rule, `this` binding and number-precision rows, and the defaults in Approach selection.
