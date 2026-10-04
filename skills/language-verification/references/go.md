# Go verification — detail

Reference for `language-verification` (loaded on demand). The numbered rules live in `../SKILL.md`; rule numbers below refer to that file.

What 40 production Go repos actually run. Written for someone competent in another
language who is adopting Go: the toolchain gives you several things for free that
JavaScript and Python must assemble from parts.

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

## Verify

```bash
# minimum viable -- the modal corpus stack (small team)
gofmt -l .                       # prints offending files; empty output = clean
go vet ./...
go test -race ./...
golangci-lint run
go mod tidy -diff

# generated-code drift gate (rules 20-21): the mature form
go generate ./...
git add -N . && git diff --exit-code

# strongest justified (org scale / high blast radius)
govulncheck ./...
go test -race -count=1 ./...     # -count=1 defeats the test cache
go build ./...

# project state vs the corpus baseline
100x stack_audit .
100x audit_ci_gates .

# bind the checks to the code being shipped
100x verified --name test -- go test -race ./...
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
  depguard-banned in 6 of the 25 deep-read repos with a depguard block
  (`prometheus`, `traefik`, `gitea`, `dapr`, `argo-cd`, `helm`) — and used freely in
  others (`loki`, `tailscale`, `teleport`, `trufflehog`). The lesson is not "ban
  pkg/errors"; it is that repos which decided encoded the decision.
- **Zero verification presented as Go simplicity** — `wavetermdev/waveterm` is in the
  corpus and runs no Go verification in CI at all.

**Honest limitations:**
- Complexity limits are not idiomatic here (2/40). Do not import a complexity gate
  from a JS or Python habit without a reason specific to your codebase.
- `netdata/netdata` documents having no single verify command *by design*, for a
  polyglot repo. A monolithic `make verify` is not universally correct.

## Next

Bind the commands to the code being shipped with `verification-gate`. If the diff
touches Kubernetes manifests or Terraform, `stack-reviewer` covers that code shape;
this skill only covers the Go toolchain.

Deleted since the last pass: a "split CI into independent jobs" rule — real advice,
but generic to any CI system, not Go-specific, and unsourced to any repo in
`research/32`. It diluted a skill whose value is measured Go practice, not general
CI hygiene.

## Scale

`solo`: rules 19, 22 — both are one line and the toolchain already ships them.
`small-team (2-10)`: add 20, 21, 23, 25 — the codegen gate earns its keep the first time
a generator output is committed stale.
`org` / `high-blast-radius`: add 24, 26, 27, plus a `make verify` chaining independent
sub-checks (the Kubernetes-lineage pattern, 14/40).

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
