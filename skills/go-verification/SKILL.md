---
name: go-verification
description: >
  Use when writing, reviewing, or setting up verification for Go code — configuring
  golangci-lint, running tests with the race detector, gating generated-code drift,
  banning imports with depguard, or deciding what must pass before a Go change
  ships. Covers the measured practice of 40 production Go repositories including
  Kubernetes-lineage distributed systems. Use PROACTIVELY when adding go.mod,
  .golangci.yml, a Makefile verify target, or go:generate directives.
---

# Go verification

What 40 production Go repos actually run. Written for someone competent in another
language who is adopting Go: the toolchain gives you several things for free that
JavaScript and Python must assemble from parts.

## Trigger

**Fire when:** writing or changing Go; setting up a Go project's checks;
configuring golangci-lint or depguard; adding code generation; auditing a Go repo's
gates.

**Do not fire when:** editing Go only incidentally (a version bump in a YAML file,
a docs change with no code impact).

## What Go gives you free

| concern | Go | JS/TS | Python |
|---|---|---|---|
| formatting | `gofmt`, canonical, no config, no debate | prettier/biome + config | ruff/black + config |
| basic correctness lint | `go vet`, in the toolchain | eslint + plugin selection | ruff rule curation |
| data races | `go test -race`, built in | n/a (single-threaded) | no equivalent |
| dependency tidiness | `go mod tidy -diff` | depcheck/knip, third-party | deptry, third-party |
| type checking | the compiler; non-optional | tsc, opt-in, often lax | absent in 12/50 repos |

The practical consequence: a Go project's *minimum* bar is higher for free, so the
marginal work is in the two areas the toolchain does not cover — **generated-code
drift** and **dependency policy**.

## The measured baseline

```bash
gofmt -l . && go vet ./... && go test -race ./... && golangci-lint run && go mod tidy -diff
```

Notable counts: complexity linters (`gocognit`, `gocyclo`, `cyclop`) are enabled in
only **2 of 40** repos — available, but not idiomatic Go, so do not import that habit
from other ecosystems. `make verify` chaining independent sub-checks appears in
**14 of 40**, concentrated in the Kubernetes lineage.

## Rules

1. Run the race detector in tests. Concurrency bugs are Go's characteristic defect
   and `-race` finds them cheaply.
   *Enforced by:* `go test -race ./...`

2. Gate generated-code drift: regenerate, then fail if the tree changed. This is the
   single most consistent practice in the corpus — 20+ of 25 deep-read repos.
   *Enforced by:* `go generate ./... && git add -N . && git diff --exit-code`

3. Use `git add -N .` before `git diff --exit-code`. Plain `git diff --exit-code`
   **misses newly created untracked files**, so a generator that adds a file passes a
   naive gate. `git add -N` stages intent-to-add so new files appear in the diff.
   *Enforced by:* the command in rule 2 (`tailscale`, `cilium`, `moby` all use this form)

4. Keep `go.mod` honest in CI.
   *Enforced by:* `go mod tidy -diff` (or `go mod tidy && git diff --exit-code go.mod go.sum`)

5. Enable golangci-lint with an explicit opt-in linter list, not everything. The
   corpus converges on curated lists; `default: all` produces ignore-list churn.
   *Enforced by:* `golangci-lint run` with an `enable:` list in `.golangci.yml`

6. If your project has a house rule about which packages may be imported, encode it
   in `depguard` rather than a CONTRIBUTING paragraph.
   *Enforced by:* `depguard` rules in `.golangci.yml`

7. Wrap errors with `%w` and compare with `errors.Is`/`errors.As`. Do not compare
   error strings.
   *Enforced by:* `golangci-lint run` with `errorlint` enabled

8. Detect leaked goroutines in tests for anything long-lived.
   *Enforced by:* `goleak.VerifyTestMain(m)` in `TestMain`

9. Scan dependencies for known vulnerabilities.
   *Enforced by:* `govulncheck ./...`

10. Split CI into independent jobs so one failure does not mask others, rather than
    chaining everything behind `&&` in a single step.
    *Enforced by:* review

## Verify

```bash
# minimum viable -- the modal corpus stack (small team)
gofmt -l .                       # prints offending files; empty output = clean
go vet ./...
go test -race ./...
golangci-lint run
go mod tidy -diff

# generated-code drift gate (rules 2-3): the mature form
go generate ./...
git add -N . && git diff --exit-code

# strongest justified (org scale / high blast radius)
govulncheck ./...
go test -race -count=1 ./...     # -count=1 defeats the test cache
go build ./...

# project state vs the corpus baseline
python3 scripts/stack_audit.py .
python3 scripts/audit_ci_gates.py .

# bind the checks to the code being shipped
python3 scripts/verified.py --name test -- go test -race ./...
```

`gofmt -l .` exits 0 even when it lists files, so in CI assert on empty output:
`test -z "$(gofmt -l .)"`.

## Failure modes

This skill rejects:

- **A codegen gate that misses new files.** Plain `git diff --exit-code` after
  `go generate` passes when the generator *adds* a file, because untracked files are
  invisible to `git diff`. Verified as the difference between the naive and mature
  forms in the corpus.
- **Tests run without `-race`** in a concurrent codebase.
- **Stale `go.mod`** merged because nothing checks tidiness.
- **Error comparison by string** instead of `errors.Is`.
- **A dependency ban that lives only in prose.** `github.com/pkg/errors` is
  depguard-banned in 6 of 40 repos (`prometheus`, `traefik`, `gitea`, `dapr`,
  `argo-cd`, `helm`) — and used freely in others (`loki`, `tailscale`, `teleport`,
  `trufflehog`). The lesson is not "ban pkg/errors"; it is that repos which decided
  encoded the decision.
- **Zero verification presented as Go simplicity** — `wavetermdev/waveterm` is in the
  corpus and runs no Go verification in CI at all.

**Honest limitations:**
- Complexity limits are not idiomatic here (2/40). Do not import a complexity gate
  from a JS or Python habit without a reason specific to your codebase.
- `netdata/netdata` documents having no single verify command *by design*, for a
  polyglot repo. A monolithic `make verify` is not universally correct.

## Scale

`solo`: rules 1, 4 — both are one line and the toolchain already ships them.
`small-team (2-10)`: add 2, 3, 5, 7 — the codegen gate earns its keep the first time
a generator output is committed stale.
`org` / `high-blast-radius`: add 6, 8, 9, 10, plus a `make verify` chaining
independent sub-checks (the Kubernetes-lineage pattern, 14/40).

## Sources

- All counts, the modal stack, the `make verify` pattern, and both command
  sequences: `research/32-findings-go-verification.md` (40 repos, per-repo citations).
- `git add -N . && git diff --exit-code` as the mature drift gate:
  `tailscale/tailscale`, `cilium/cilium`, `moby/moby`. Sandboxed-tmpdir variants in
  `etcd-io/etcd`, `containerd/containerd` (`verify-vendor`).
- depguard bans on `github.com/pkg/errors`: `prometheus/prometheus`,
  `traefik/traefik`, `go-gitea/gitea`, `dapr/dapr`, `argoproj/argo-cd`, `helm/helm`.
- `k3s-io/k3s` — `scripts/validate` running `go mod tidy` then failing on a dirty
  tree; also an example of a repo whose docs describe a `go generate` step its
  scripts do not actually run.
- Counter-examples for the limitations section: `wavetermdev/waveterm`,
  `netdata/netdata`.
