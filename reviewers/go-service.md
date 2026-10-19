# Go service reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

The Go toolchain gates (golangci-lint config, codegen drift, `go mod tidy`) are in
`skills/language-verification` rules 19–27. This file covers the code shape of a Go
HTTP or gRPC service.

## Applies when
- `go.mod` exists and the module imports `net/http`, `google.golang.org/grpc`, or a router (`chi`, `gin`, `echo`).
- The diff touches `*.go` files outside generated code (`// Code generated ... DO NOT EDIT.`).

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | No ignored error: every returned `error` is checked, returned, or explicitly discarded with `_ =` and a comment saying why | `golangci-lint run` (errcheck is in the default set); `gosec -include=G104 ./...` | a failed write or close reported as success (`kisielk/errcheck@master:README.md`) |
| 2 | Errors crossing a package boundary are wrapped with `%w` and context; callers compare with `errors.Is`/`errors.As`, never `==` on a wrapped error or `err.Error()` strings | `golangci-lint run --enable errorlint` | lost cause chains; comparisons that break as soon as someone wraps (`golang/website@master:_content/blog/go1.13-errors.md`) |
| 3 | Every outbound call (HTTP, DB, gRPC) takes the request's `ctx`; every `context.WithTimeout`/`WithCancel` has its `cancel` called | `go vet ./...` (lostcancel); `golangci-lint run --enable noctx,contextcheck` | work continues after the client went away; leaked timers (`golang/tools@master:go/analysis/passes/lostcancel/lostcancel.go`; `golang/website@master:_content/blog/context.md`) |
| 4 | `http.Server` sets `ReadHeaderTimeout` (and read/write/idle timeouts); no bare `http.ListenAndServe` | `gosec -include=G112,G114 ./...` | slowloris: the zero value means no timeout (`golang/go@master:src/net/http/server.go`, `ReadHeaderTimeout` docs) |
| 5 | Tests pass under the race detector | `go test -race ./...` | data races, including concurrent map writes that crash the process (`golang/website@master:_content/doc/articles/race_detector.html`) |
| 6 | Every `resp.Body` and `*sql.Rows` is closed, and `rows.Err()` is checked after the loop | `golangci-lint run --enable bodyclose,sqlclosecheck,rowserrcheck` | connection-pool exhaustion; an iteration error read as "no more rows" (`golang/go@master:src/database/sql/sql.go`, `Rows.Err`) |

## Common AI failure modes in this stack
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | `json.NewEncoder(w).Encode(v)`, `rows.Close()`, `tx.Rollback()` with the error dropped | the happy path never fails | errcheck | handle or log it; `defer func() { _ = tx.Rollback() }()` only after commit has been checked |
| 2 | `return fmt.Errorf("failed: %v", err)` | the message reads well | errorlint flags `%v` on an error | `%w`, so callers can `errors.Is` |
| 3 | `go func() { ... }()` per request with no way to stop it | "async makes it faster" | review every `go` statement: what stops it, and who waits for it? `uber-go/goleak` in tests | `errgroup.WithContext`, a bounded worker pool, or a select on `ctx.Done()` |
| 4 | `http.Get(url)` / `http.DefaultClient` for an upstream call | shortest code | `noctx` linter; `grep -rn "http.DefaultClient\|http.Get(" --include=*.go .` | a shared `http.Client{Timeout: ...}` and `http.NewRequestWithContext` |
| 5 | Panics on a bad request (`v := m[k].(T)`, index out of range) | input in tests is always valid | review type assertions without `, ok`; fuzz targets on parsers | `v, ok := x.(T)`; validate before indexing; recover middleware as the last line only |
| 6 | Adds an interface for every struct "for testability" | Java habits; mocks look tidy | `git diff --stat` shows interfaces with one implementation and no test fake | accept interfaces where they are consumed, define them in the consumer package, only when a second implementation or fake exists |
| 7 | `log.Fatal` / `os.Exit` inside library or handler code | it stops on error | `grep -rn "log.Fatal\|os.Exit" --include=*.go . \| grep -v "cmd/\|main.go"` | return the error; only `main` exits |

## Language pitfalls (Go)
| # | pitfall | what goes wrong | detection | correct move |
|---|---------|-----------------|-----------|--------------|
| 1 | write to a nil map | `var m map[string]int; m["a"] = 1` panics (run locally: recovered panic confirmed) | staticcheck SA5000 (in golangci-lint's default `staticcheck`) | `m := make(map[string]int)`; initialise map fields in the constructor (`golang/go@master:doc/go_spec.html`, "Map types") |
| 2 | loop-variable capture | before Go 1.22 one variable is shared by all iterations, so closures and goroutines see the last value; the semantics follow the `go` line in `go.mod`, not the toolchain (run locally with go1.27: `go 1.21` prints `333`, `go 1.22` prints `012`) | `go vet` loopclosure for modules below 1.22; after upgrading, `copyloopvar` flags now-redundant `v := v` | raise `go.mod` to `go 1.22` or later, or copy the variable inside the loop (`golang/website@master:_content/doc/go1.22.md`; `golang/website@master:_content/blog/loopvar-preview.md`) |
| 3 | typed nil in an interface | returning a nil `*MyErr` as `error` gives a non-nil error | review functions returning a concrete error pointer type as `error` | return a literal `nil` on success (`golang/website@master:_content/doc/faq.md`, "Why is my nil error value not equal to nil?") |
| 4 | `defer` inside a loop | defers run at function exit, so files and rows stay open for the whole loop | gocritic `deferInLoop`: experimental, so off even with gocritic enabled; add it to `linters.settings.gocritic.enabled-checks` (fired on golangci-lint 2.14.0 only once listed there) | move the body into a function called per iteration (`go-critic/go-critic@master:checkers/deferInLoop_checker.go`) |
| 5 | goroutine leaks | a goroutine blocked on a channel nobody reads, or with no `ctx.Done()` case | `goleak.VerifyTestMain(m)` (`uber-go/goleak@master:README.md`) | every goroutine has an exit path; senders own closing |
| 6 | `t.Fatal` from a goroutine | `FailNow` must run on the test goroutine | staticcheck SA2002 | send the error back on a channel and fail in the test goroutine |
| 7 | slice aliasing | `b := a[:2]; b = append(b, x)` overwrites `a[2]` | review `append` on a sub-slice of shared data | full slice expression `a[:2:2]` or `slices.Clone` |
| 8 | shadowed `err` | `if v, err := f(); ...` inside a block hides the outer `err`, so it is never checked | `go vet` with the shadow analyzer, or review | declare once, assign with `=` |

## Security defaults
| unsafe default or habit | where it bites | check |
|-------------------------|----------------|-------|
| `http.Server{}` with no timeouts | slowloris | blocking rule 4 (gosec G112, G114) |
| SQL built with `fmt.Sprintf` or `+` | SQL injection | gosec G201, G202; use `$1` placeholders |
| `text/template` for HTML, or `template.HTML(userInput)` | XSS | gosec G203; use `html/template` |
| `math/rand` for tokens | predictable secrets | gosec G404; use `crypto/rand` |
| `InsecureSkipVerify: true` | MITM | gosec G402 |
| `os.Open(filepath.Join(base, userPath))` | path traversal | gosec G304; `os.Root` or a clean-and-check-prefix |
| object-level access | `GET /orders/{id}` returns another tenant's row | review: is every query by id filtered by the caller's tenant? (`SOURCE: original`) |

## Performance
| # | issue | detection | correct move |
|---|-------|-----------|--------------|
| 1 | N+1: one query per item in a loop | review `for` loops containing `db.Query`/`QueryRow`/repository calls | one `WHERE id = ANY($1)` query; with GORM, `Preload` (`go-gorm/gorm.io@master:pages/docs/preload.md`) |
| 2 | unbounded fan-out (`go` per item of user-sized input) | review | `errgroup` with `SetLimit(n)` |
| 3 | `sql.DB` pool left at defaults | review `SetMaxOpenConns`, `SetConnMaxLifetime` | size the pool to the database's connection budget |
| 4 | allocations in a hot path (`fmt.Sprintf` in a loop, `[]byte(string)` per call) | `go test -bench . -benchmem` on the changed function | preallocate, `strings.Builder`, reuse buffers |

## Test conventions
| # | convention | check |
|---|------------|-------|
| 1 | Table-driven tests with `t.Run(name, ...)`, `t.Parallel()` where safe | `golang/wiki@master:TableDrivenTests.md` |
| 2 | Handlers are tested through `httptest.NewRecorder` / `httptest.NewServer`, asserting status, body and the error path | `golang/go@master:src/net/http/httptest/server.go` |
| 3 | CI runs `go test -race -count=1 ./...` | `-count=1` defeats the test cache |
| 4 | Packages that start goroutines verify none leak | `goleak.VerifyTestMain(m)` in `TestMain` |

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | client cancels mid-request | tests never cancel | `httptest` request with a cancelled context; assert the DB call returns `context.Canceled` |
| 2 | `SIGTERM` during a deploy | local runs just exit | `signal.NotifyContext` + `srv.Shutdown(ctx)`; test in-flight request completes |
| 3 | empty vs nil slice in JSON | `nil` encodes as `null`, `[]T{}` as `[]` | handler test on an empty result asserts `[]` |
| 4 | upstream returns 200 with an error body, or a non-JSON 502 | mocks return clean JSON | `httptest.NewServer` returning HTML 502 |
| 5 | concurrent map access from handlers | single-request tests | `-race` with parallel requests against the shared state |

## Approach selection
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| router | `net/http` `ServeMux` / chi / gin / echo | need for middleware ecosystem | **`net/http` `ServeMux`** (method and wildcard patterns since Go 1.22); chi when you need its middleware |
| data access | `database/sql` / sqlc / GORM | query complexity, team SQL skill | **sqlc** (typed, explicit SQL, no hidden N+1); GORM only if the repo already uses it |
| error inspection | sentinel errors / typed errors / wrapping | do callers branch on it? | **sentinel + `%w`**; a typed error only when callers need fields |
| concurrency | raw goroutines / `errgroup` / worker pool | is the input size bounded? | **`errgroup.WithContext`** with `SetLimit` |

## Verify
```bash
# vet + default linters + the service-specific ones above
go vet ./...
golangci-lint run --enable errorlint,noctx,contextcheck,bodyclose,sqlclosecheck,rowserrcheck,gocritic ./...
# deferInLoop is experimental: it runs only if .golangci.yml lists it under gocritic enabled-checks

# security
gosec -include=G104,G112,G114,G201,G202,G203,G304,G402,G404 ./...

# race-clean, uncached tests
go test -race -count=1 ./...

# loop-variable semantics follow go.mod, not the installed toolchain
grep -E '^go 1\.(1[0-9]|2[01])(\.|$)' go.mod && echo "REVIEW: pre-1.22 loop semantics (pitfall 2)"

# grep checks no tool covers
grep -rn "http.ListenAndServe(" --include=*.go . && echo "FAIL: server with no timeouts (rule 4)"
grep -rn "log.Fatal\|os.Exit(" --include=*.go . | grep -v "main.go" && echo "REVIEW: exit outside main"
```

## Sources
- `golang/go@master:doc/go_spec.html`: "A nil map is equivalent to an empty map except that no elements may be added".
- `golang/website@master:_content/doc/go1.22.md` and `_content/blog/loopvar-preview.md`: per-iteration loop variables from Go 1.22; `golang/wiki@master:CommonMistakes.md` (the pre-1.22 note).
- `golang/website@master:_content/blog/go1.13-errors.md` (`%w`, `errors.Is`), `_content/blog/context.md`, `_content/doc/articles/race_detector.html`, `_content/doc/faq.md` ("Why is my nil error value not equal to nil?"), `_content/doc/go1.22.md` ("Enhanced routing patterns"), `_content/doc/go1.24.md` (`os.Root`).
- `golang/tools@master:go/analysis/passes/lostcancel/lostcancel.go`, `go/analysis/passes/loopclosure/loopclosure.go`.
- `golang/go@master:src/net/http/server.go` (`ReadHeaderTimeout`: zero means no timeout), `src/database/sql/sql.go` (`Rows.Err`), `src/net/http/httptest/server.go`.
- `golangci/golangci-lint@main:pkg/golinters/`: errcheck, errorlint, noctx, contextcheck, bodyclose, sqlclosecheck, rowserrcheck, gocritic, copyloopvar. Default set (errcheck, govet, ineffassign, staticcheck, unused) confirmed by running `golangci-lint linters` v2.14.0 with no config.
- `dominikh/go-tools@master:staticcheck/sa5000/sa5000.go` (assignment to nil map), `staticcheck/sa2002/sa2002.go` (`FailNow` in a goroutine).
- `securego/gosec@master:RULES.md`: G104, G112, G114, G201, G202, G203, G304, G402, G404.
- `kisielk/errcheck@master:README.md`; `uber-go/goleak@master:README.md`; `go-critic/go-critic@master:checkers/deferInLoop_checker.go`; `go-gorm/gorm.io@master:pages/docs/preload.md`; `golang/wiki@master:TableDrivenTests.md`.
- `SOURCE: original`: nil-map and loop-variable behaviour confirmed by running Go 1.27.1 locally; the tenant-scoping question; the defaults in Approach selection.
