# Go Verification Systems: How 40 Mature Repos Prove Their Code Works

Scope per `research/00-signal-rubric.md` Part D1/D2/D6 and `research/01-skill-contract.md`. Written for
someone competent in another language who is new to Go. Every claim carries `owner/repo@sha:path`.
Absence is recorded, not papered over (Part G rule 6).

## Coverage

40/40 repos on `research/worklists/go.txt` were read: 25 deep-read (full 8-field extraction), 15
breadth-read (6-field extraction: prove-it command, golangci-lint presence, race-in-CI, test/fuzz
counts, codegen drift, `go mod tidy` gate). Method: `git clone --depth 1 --filter=blob:none`, local
grep/cat, clone deleted after extraction, no GitHub REST API calls (quota exhausted for this run).

| Tier | Repo | SHA | Depth |
|---|---|---|---|
| T1 | vitessio/vitess | 83eb933 | deep |
| T1 | gravitational/teleport | 1283425 | deep |
| T2 | prometheus/prometheus | dff7878 | deep |
| T2 | go-gitea/gitea | fba8d7e | deep |
| T2 | mudler/LocalAI | 590512d | deep |
| T2 | k3s-io/k3s | bb14efb | deep |
| T2 | jaegertracing/jaeger | 7ebccce | deep |
| T2 | pulumi/pulumi | 67ff40b | deep |
| T2 | argoproj/argo-cd | b9ff02f | deep |
| T2 | netdata/netdata | 4f911b1 | deep |
| T2 | traefik/traefik | f08328c | deep |
| T2 | gofiber/fiber | 7c56c53 | deep |
| T2 | grafana/k6 | 02a9d6e | deep |
| T2 | grafana/loki | b22cd0d | deep |
| T2 | trufflesecurity/trufflehog | a3fcdde | deep |
| T2 | redis/go-redis | cb175c6 | deep |
| T2 | microsoft/TypeScript (= typescript-go, merged) | 4f5ddae | deep |
| T2 | moby/moby | 5d8f006 | deep |
| T2 | etcd-io/etcd | 7583cc6 | deep |
| T2 | tailscale/tailscale | 2d43793 | deep |
| T2 | dapr/dapr | e170747 | deep |
| T2 | cilium/cilium | 84222dc | deep |
| T2 | temporalio/temporal | 3dafaf9 | deep |
| T2 | wavetermdev/waveterm | c58bf7f | deep |
| T2 | containerd/containerd | 04f9be9 | deep |
| T2 | infiniflow/ragflow | d64b84c | breadth |
| T2 | caddyserver/caddy | 256df3c | breadth |
| T2 | rclone/rclone | 9dc8b71 | breadth |
| T2 | milvus-io/milvus | d2c77fd | breadth |
| T2 | aquasecurity/trivy | 5ba5be0 | breadth |
| T2 | containers/podman (worklist slug `podman-container-tools/podman` unreachable) | 345b2c7 | breadth |
| T2 | opentofu/opentofu | a7af95c | breadth |
| T2 | helm/helm | d31cd69 | breadth |
| T2 | goharbor/harbor | d3e2ad0 | breadth |
| T3 | MHSanaei/3x-ui | 8c023d1 | breadth |
| T3 | dokku/dokku | 540a146 | breadth |
| T3 | kubernetes/minikube | 39ac29d | breadth |
| T3 | authelia/authelia | 3837cff | breadth |
| T3 | lima-vm/lima | c4113bf | breadth |
| T3 | QuantumNous/new-api | 789c970 | breadth |

**One correction worth flagging:** `microsoft/TypeScript` scored as a Go repo because the TypeScript
compiler's Go port (`typescript-go`) has been merged into the main repo — `tsc/` is a 5,128-file Go
tree with its own `go.work`, `.golangci.yml`, and CI, living alongside the legacy JS/TS packaging
layer. Cited as `microsoft/TypeScript@4f5ddae:tsc/...`.

---

## The prove-it command, per repo (complete table)

| Repo | The command | Chain shape |
|---|---|---|
| vitessio/vitess | no single target; CI job `Static Code Checks Etc` chains 10 scripts | K8s-style verify-script chain |
| gravitational/teleport | `make lint-go` + `derive-up-to-date`/`go-generate-up-to-date` + `go mod tidy -diff` | `must-start-clean` + regenerate + diff |
| prometheus/prometheus | `make test` (→ `common-all`: style, license, lint, yamllint, unused, build, test) | Makefile.common shared chain |
| go-gitea/gitea | `make checks` (→ `checks-frontend checks-backend`) + `make lint` | diff-based check-* targets |
| mudler/LocalAI | `make lint` + `make test-coverage-check` (coverage **ratchet**, not floor) | loose, coverage-delta gated |
| k3s-io/k3s | `./scripts/validate` (Docker build stage `validate`) | tidy + dirty-tree + verify + lint |
| jaegertracing/jaeger | `make test-and-lint` (default goal: `test fmt lint`) | `lint` fans to 9 sub-targets |
| pulumi/pulumi | `make lint` (custom-built golangci-lint binary) + `make test_fast` | AGENTS.md maps file-type → command |
| argoproj/argo-cd | `make build && make codegen && make lint && make test` (AGENTS.md §4) | explicit 5-step required sequence |
| netdata/netdata | **no full-project command** — AGENTS.md: "There is no full-project command matrix" | per-subsystem only, deliberately |
| traefik/traefik | `make validate` (→ `lint` + `validate-files`) | AGENTS.md: "run this before pushing" |
| gofiber/fiber | `make audit && make generate && make betteralign && make format && make lint && make test` | AGENTS.md ordered list |
| grafana/k6 | `make check` (→ `lint tests`) | lint config fetched from external pinned repo |
| grafana/loki | `make lint` + `make test` + 7 separate `check-*` diff-gated targets | most `git diff --exit-code` gates of any repo (7) |
| trufflesecurity/trufflehog | `make check` (fmt+vet only) + `make lint` + `make test` | thin — no chained verify |
| redis/go-redis | `make test` → `docker.start && test.ci && docker.stop` | includes a **custom go vet analyzer** (`customvet`) |
| microsoft/TypeScript (typescript-go) | `npx hereby validate` (generate→build→test→lint→format, `AggregateError`) | JS task-runner orchestrating Go |
| moby/moby | `make validate` (→ `hack/validate/default` sourcing 4 scripts) | classic moby `hack/validate/*` chain |
| etcd-io/etcd | `make verify` — 13 named sub-targets, `make fix` mirrors it | cleanest K8s-lineage `verify`/`fix` pair |
| tailscale/tailscale | `make check` (→ `staticcheck vet depaware buildwindows ...`) via `./tool/go` wrapper | pinned-toolchain wrapper for every invocation |
| dapr/dapr | `make check` (→ `format test lint`) + dirty-tree check | `check-diff`/`check-proto-diff` diff gates |
| cilium/cilium | `make precheck` + CI fan-out (`go-mod`, `golangci`, `generate-api`, `generate-k8s-api`) | script-chain, not one Makefile target |
| temporalio/temporal | `make lint-code-fast` (dev) / `make lint-code` (CI) + custom `errortype` vet tool | AGENTS.md mandates it after every change |
| wavetermdev/waveterm | **none** — no `task test`/`task lint` exists; CI never runs `go test`/`go vet`/golangci-lint | the negative case — see below |
| containerd/containerd | `make check` (→ `check-protos` + `golangci-lint run`); AGENTS.md: "Never bypass a check to make CI pass" | `ci` target = `check binaries check-protos coverage` |
| infiniflow/ragflow | none documented; CI (self-hosted, label-gated) is the de facto gate | no Makefile |
| caddyserver/caddy | `go test -short -race ./...` + separate lint workflow | no Makefile |
| rclone/rclone | `make check` (→ `golangci-lint run && bin/markdown-lint`) | |
| milvus-io/milvus | `verifiers: build-cpp getdeps cppcheck rustcheck fmt static-check` | K8s-style chain |
| aquasecurity/trivy | CI: `go mod tidy` diff → golangci-lint → `mage docs:generate` diff → `mage test:unit` | uses `mage`, not Make |
| containers/podman | `make validate` (→ `validate-source validate-binaries`, ~10 sub-targets) | K8s-style chain |
| opentofu/opentofu | `make test` + `make golangci-lint`; CI `consistency-checks` adds tidy+codegen diff | |
| helm/helm | `make test` (Makefile has `-race`, but CI-invoked `test-coverage` target drops it — see race table) | flag defined but not exercised by CI |
| goharbor/harbor | custom shell (`tests/ci/ut_run.sh`) + `make lint` (`src/.golangci.yaml`) | no unified target |
| MHSanaei/3x-ui | `make verify` — explicit comment: "Mirrors `.github/workflows/ci.yml`" | K8s-style chain, small project |
| dokku/dokku | `make lint` (shellcheck-first; `lint-golang` is separate, not default) | bash-first codebase |
| kubernetes/minikube | `make test` / `make gotest` / `make lint` — **not** a `hack/verify-*.sh` chain despite k8s lineage | breaks the pattern despite ancestry |
| authelia/authelia | Buildkite `.buildkite/steps/lint.sh` (`golangci-lint run`) | no GitHub Actions for the main gate |
| lima-vm/lima | `lint:` chains 12 sub-targets (`check-generated`, `golangci-lint`, `gomodjail`, `protolint`, ...) | K8s-style chain, unusually granular |
| QuantumNous/new-api | CI: `go vet` → `go build` → `make test` — **no lint step in CI at all** | |

### The `make verify` / `hack/verify-*.sh` pattern, explained

This is the single strongest, most copyable pattern in the corpus. Origin: Kubernetes' `hack/verify-*.sh`
convention. Shape: **one entrypoint chains N independent sub-checks**, each of which is a script that
exits non-zero on failure; CI runs the entrypoint (or the sub-checks individually, for parallel
scheduling and clearer failure attribution). The sub-checks fall into three families:

1. **Static checks** — format, license headers, import order, lint.
2. **Regenerate-and-diff** — run the code generator, then fail if the tree changed (full pattern below,
   "Generated-code drift detection").
3. **Dependency-tidy-and-diff** — run `go mod tidy`, fail if `go.mod`/`go.sum` changed.

The cleanest instance is `etcd-io/etcd@7583cc6:Makefile`:
```makefile
verify: verify-bom verify-lint verify-dep verify-shellcheck verify-mod-tidy \
  verify-shellws verify-proto-annotations verify-genproto verify-yamllint \
  verify-markdown-marker verify-go-versions verify-gomodguard \
  verify-go-workspace verify-grpc-experimental
```
paired with a `make fix` that runs the same list in write-mode. **Why this beats a single
`golangci-lint run`:** each sub-check has a distinct failure message, can be run in isolation
(`make verify-mod-tidy` alone when iterating), and can be assigned to a separate CI job for
parallelism and clearer failure triage — visible in `argoproj/argo-cd@b9ff02f:.github/workflows/ci-build.yaml`,
which runs `check-go`, `lint-go`, `test-go`, `test-go-race`, `codegen` as five separate required jobs
rather than one.

**Counter-evidence, recorded honestly:** two K8s-lineage repos in this corpus do **not** follow the
pattern — `kubernetes/minikube` (despite being literally kubernetes-org) uses a flat `make test`/`make lint`,
and `netdata/netdata` explicitly rejects having *any* single verify command
(`netdata/netdata@4f911b1:AGENTS.md`: *"There is no full-project command matrix. Use the narrowest
existing command that validates the changed subsystem, and do not claim full-project validation from
it."*). The pattern is common, not universal — 12 of 40 repos in this corpus have an explicit chained
verify/check target (vitess, teleport, prometheus, k3s, jaeger, pulumi, argo-cd, dapr, cilium,
containerd, milvus, podman, 3x-ui, lima — actually 14), the rest use a flatter `lint` + `test` pair
or nothing at all (waveterm, ragflow, new-api).

---

## golangci-lint configs verbatim (cited)

| Repo | Config present | Linters enabled (approx) | Complexity gate (`gocognit`/`gocyclo`/`cyclop`) |
|---|---|---|---|
| vitess | yes | 16, opt-in (`default: none`) | **ABSENT** |
| teleport | yes | 16, opt-in | **ABSENT** |
| prometheus | yes | 20, opt-in | **ABSENT** |
| gitea | yes | 26, opt-in | **ABSENT** |
| LocalAI | yes | `default: standard` + `forbidigo` | **ABSENT** |
| k3s | yes | **2 only** (`govet`, `revive`) | present in revive but `disabled: true` |
| jaeger | yes | 24, opt-in, `errcheck` explicitly disabled | present in revive but `disabled: true` |
| pulumi | yes | ~30 (implicit std set + enable list), 2 in-house custom linters | **ABSENT** |
| argo-cd | yes | 19, opt-in | **ABSENT** |
| netdata | **ABSENT** (no file anywhere in repo) | golangci-lint default set only, via reviewdog | n/a — unconfigurable without a file |
| traefik | yes | `default: all` minus a commented disable-list | present (`gocyclo: 14`) but linter **disabled**, `# FIXME must be fixed` |
| fiber | yes | 60, opt-in | **ABSENT** (revive explicitly disables cyclomatic/cognitive rules) |
| k6 | yes, **fetched from external repo** `grafana/k6-ci` at pinned SHA + local patch | ~55 | **present and enforced**: `cyclop: max-complexity: 25`, `funlen: 80/60` — the only repo in the corpus that enforces one |
| loki | yes | 10, opt-in | **ABSENT** |
| trufflehog | yes, 8 lines total | golangci-lint defaults + `depguard` + 3 CLI flags | **ABSENT** |
| go-redis | yes | no explicit enable list (defaults) | **ABSENT** |
| moby | yes | ~35, opt-in, `errcheck` disabled | **ABSENT** |
| etcd | yes (`tools/.golangci.yaml`, applied repo-wide) | 14, opt-in | **ABSENT** |
| tailscale | yes | **5 only** (`bidichk`,`govet`,`importas`,`misspell`,`revive`) — thinnest of any mature repo, compensated by custom tools (see Concurrency) | **ABSENT** |
| typescript-go | yes | ~35, opt-in, including a **custom plugin linter** (`customlint`, hand-written analysis passes) | **ABSENT** (commented "TODO enable") |
| dapr | yes | `default: all` minus ~45 disabled, incl. `errcheck`, `gocognit`, `gocyclo` | present in config, dormant (linters disabled) |
| cilium | yes | 16, opt-in | **ABSENT** |
| temporal | yes | 10, opt-in + custom vet tool | present and enforced via **revive** (`cognitive-complexity: 25`, `cyclomatic: 25`) — not a dedicated linter but functionally equivalent |
| waveterm | yes, 8 lines total (`disable: [unused]`) | defaults only | **ABSENT** |
| containerd | yes | 11, opt-in, `errcheck` disabled | **ABSENT** |
| caddy | yes | ~82 | **ABSENT** (not confirmed) |
| rclone | yes | ~71 | not confirmed present |
| milvus | yes (4 separate config files: root/pkg/client/tests) | ~148 in root config | not confirmed |
| trivy | yes | ~115 | not confirmed |
| podman | yes | ~64 | not confirmed |
| opentofu | yes, minimal (~8 lines, default set only) | defaults | **ABSENT** |
| helm | yes | ~67 | not confirmed |
| harbor | yes (`src/.golangci.yaml`) | ~46 | not confirmed |
| 3x-ui | yes, curated small list (`default: standard` + 8 named) | ~9 | **ABSENT** |
| dokku | yes (`.golangci-lint.yml`) | 16 incl. `gocyclo` (threshold not confirmed) | present, threshold unconfirmed |
| minikube | yes (3 files: default/max/min) | 13 (default config) incl. `gocyclo` | present |
| authelia | yes | 19 incl. `gocyclo` | present |
| lima | yes | 15 | **ABSENT** |
| new-api | **ABSENT** (no file found) | golangci-lint not run in CI at all | n/a |
| ragflow | **ABSENT** | n/a | n/a |

**Headline finding: complexity linters are almost universally absent or disabled.** Of 40 repos, only
`grafana/k6` enforces `cyclop`/`funlen` as a blocking gate, and `temporalio/temporal` gets equivalent
coverage via revive's `cognitive-complexity`/`cyclomatic` rules at threshold 25. Two repos
(`traefik`, `k3s`) have the threshold **configured but the linter disabled**, with an explicit
comment acknowledging the debt (`traefik/traefik@f08328c:.golangci.yml`: `gocyclo # FIXME must be fixed`).
A JS/Python engineer expecting Go's tooling to gate cyclomatic complexity the way `eslint-plugin-complexity`
or `radon`/`xenon` can will not find that enforced in this corpus by default — it is a rare, deliberate
opt-in, not an idiom.

### Verbatim configs worth copying directly

**Strictest errcheck** (`gofiber/fiber@7c56c53:.golangci.yml`):
```yaml
errcheck:
  disable-default-exclusions: true
  check-type-assertions: true
  check-blank: true
  exclude-functions:
    - (*bytes.Buffer).Write
    - (*github.com/valyala/bytebufferpool.ByteBuffer).Write
```
paired with AGENTS.md consequence text: *"Never discard a type-assertion result with `_`. `v, _ := x.(T)` fails `errcheck`."*

**Architectural layering via depguard, not just legacy-package bans** (`vitessio/vitess@83eb933:.golangci.yml`):
five package-scoped rules ban `vitess.io/vitess/go/vt/servenv`, `github.com/spf13/pflag`,
`go/vt/dbconfigs`, `go/vt/topotools` from low-level packages, each rationale: *"should be usable as a
library without server infrastructure dependencies."* `go-gitea/gitea@fba8d7e:.golangci.yml` does the
same for migrations: ban `models`/`modules/structs` imports with `HINT: MIGRATION-STRUCT-FROZEN`.

**Lint config as its own versioned artifact** — `grafana/k6@02a9d6e:Makefile` does not keep
`.golangci.yml` in-repo at all; it downloads it from a sibling repo at a pinned commit
(`https://raw.githubusercontent.com/grafana/k6-ci/$(K6_CI_REF)/.golangci.yml`) and applies a local
patch. This decouples the lint contract's version from the code's version — a supply-chain-relevant
pattern worth knowing exists, not necessarily worth copying at small scale.

---

## Banned-import (`depguard`) rules and their rationale

The earlier research track's claim — that Traefik and Prometheus both ban `github.com/pkg/errors` in
favor of stdlib `errors` — is **confirmed**, and the corpus surfaces several more instances, but the
practice is **not universal**; several mature repos actively use `pkg/errors` with no ban at all.

**Confirmed `github.com/pkg/errors` bans, quoted:**

```yaml
# prometheus/prometheus@dff7878:.golangci.yml
- pkg: "github.com/pkg/errors"
  desc: "Use 'errors' or 'fmt' instead of github.com/pkg/errors"

# traefik/traefik@f08328c:.golangci.yml
- pkg: github.com/pkg/errors
  desc: Should be replaced by standard lib errors package

# go-gitea/gitea@fba8d7e:.golangci.yml
- pkg: github.com/pkg/errors
  desc: use builtin errors package instead

# dapr/dapr@e170747:.golangci.yml
- pkg: github.com/pkg/errors
  desc: must use standard library (errors package and/or fmt.Errorf)
```
Plus `argoproj/argo-cd@b9ff02f:.golangci.yaml` (via `gomodguard_v2`, no reason string given) and
`helm/helm@d31cd69:.golangci.yml` (paired with a ban on `hashicorp/go-multierror`, both "use errors instead").
**Six confirmed bans** in this corpus: prometheus, traefik, gitea, dapr, argo-cd, helm.

**Confirmed non-bans — the package is actively used, unenforced:**
- `grafana/loki@b22cd0d:` — **222 files** import `github.com/pkg/errors`; no depguard rule bans it.
- `trufflesecurity/trufflehog@a3fcdde:` — active direct dependency, imported in `pkg/giturl`, `pkg/common`, `pkg/sources/gcs`.
- `mudler/LocalAI@590512d:` — has **no depguard block at all**, and `pkg/errors` is imported in `pkg/oci/tarball.go`.
- `gravitational/teleport@1283425:` and `tailscale/tailscale@2d43793:` — present in `go.mod`, not banned, not the dominant idiom (both standardize on other mechanisms instead — see Error-handling section).
- `grafana/k6@02a9d6e:` — **no depguard mechanism exists in the config at all**, so nothing is banned.

**Verdict for the skill:** the `pkg/errors → errors` ban is real and appears in roughly 6 of the 25
deep-read repos with a depguard block — common enough to recommend, not common enough to assert as
"the Go way." It correlates with mature CNCF/Kubernetes-lineage projects, not with Go maturity per se.

**Other recurring ban families, with rationale quoted:**

| Banned import | Reason (quoted) | Repos |
|---|---|---|
| `io/ioutil` | "deprecated, use os/io instead" | teleport, gitea, jaeger, fiber, trivy |
| `math/rand` (bare) | "use math/rand/v2" | vitess, cilium, lima |
| `github.com/golang/protobuf` | "use google.golang.org/protobuf" | teleport, pulumi |
| `go.uber.org/atomic` | "use sync/atomic instead" | teleport |
| `sync/atomic` | "use go.uber.org/atomic instead" (**inverse** of teleport's rule) | prometheus, loki |
| stdlib `regexp` | "use github.com/grafana/regexp" / "use wasilibs/go-re2" (perf) | prometheus, trufflehog |
| `github.com/hashicorp/go-multierror` | "use errors.Join instead" | moby, jaeger, helm |
| `go.uber.org/goleak` (direct import) | "use our wrapper instead" (own package curates ignore-lists) | cilium, jaeger |
| `github.com/sirupsen/logrus` et al. | "use log/slog instead" | teleport |
| `time`/`sync.Mutex` (stdlib, wholesale) | "use our wrapper for testability/deadlock-detection" | cilium (`pkg/time`, `pkg/lock`), teleport |
| `github.com/pborman/uuid` | "use github.com/google/uuid" | temporal |
| `encoding/json` | "use our own json package" (perf/compat) | gitea, typescript-go |

The `sync/atomic` vs `go.uber.org/atomic` contradiction between teleport and prometheus/loki is worth
citing directly to a JS/Python audience: **even at this maturity tier, Go projects disagree on which
direction to ban.** There is no single correct answer; each project picked one and enforced it
mechanically. The lesson to copy is the *mechanism* (pick a direction, encode it in `depguard`, write
the reason), not any specific direction.

---

## Test layers and fuzz adoption (counts)

| Repo | `*_test.go` | Fuzz files/funcs | `.golden` files | `testdata/` dirs | Benchmarks | Integration via build tag? |
|---|---|---|---|---|---|---|
| vitess | 1,240 | 2 files | 0 | 21 | 68 | no (path-separated) |
| teleport | 2,135 | 34 files | **340** | 47 | 77 | no (path-separated) |
| prometheus | 282 | 2 files, 8 funcs, OSS-Fuzz member | 0 | 16 | 179 | no (`.test` files + tags) |
| gitea | 1,049 | 1 file, 2 funcs | 0 | 5 | 17 | no (path-separated) |
| LocalAI | 921 | **0** | 0 | 0 | 2 | no (Ginkgo `DescribeTable`) |
| k3s | 93 | 1 func | 0 | 6 | **0** | no (test-name prefix) |
| jaeger | 610 | **0** | 0 | 10 | 16 | no (test flags, not build tags) |
| pulumi | 875 | 1 native + 36 files property-based (`rapid`) | 0 (uses `PULUMI_ACCEPT=1` golden convention) | 44 | 17 | 125 files `!all` tag |
| argo-cd | 406 | **0** | 0 | 363 | 34 | no (path-separated); 5 files tagged `!race` |
| netdata | 1,324 (src/go) | 8 files | 0 | 147 | 301 | no |
| traefik | 276 | **0** | 0 | 3 | 6 | no (path-separated) |
| fiber | 138 | 6 files, 10 funcs | 0 | 1 | **457** | no; 3,927 `t.Parallel()` calls |
| k6 | 326 | **0** | 0 | 3 | 52 | no; `race`/`!race` variant tags |
| loki | 1,118 | 9 files | 0 | 13 | 301 | yes, `integration` tag (13 files) |
| trufflehog | 2,000 | 2 files | 0 | 2 | **986** | yes, `detectors` tag on 914 files |
| go-redis | 236 | 1 func | 0 | 1 | 18 | no (Ginkgo) |
| typescript-go | 4,556 | 3 | **48,124** (baseline reference corpus, inherited) | 3 | 23 | no |
| moby | 832 | 7 files | **657** | 18 | 29 | no (path-separated) |
| etcd | 419 | 1 func | 0 | 4 | 19 | no; dedicated `tests/robustness/` |
| tailscale | 719 | 22 files | 0 | 11 | 64 | no |
| dapr | 428 | **0** | 0 | 3 | 4 files | yes, `integration` tag (1 file) |
| cilium | 992 | 13 files, OSS-Fuzz-adjacent (`tests-cifuzz.yaml`) | 8 | 46 | not counted | no |
| temporal | 978 | 2 files | 0 | 6 | 17 files | no |
| waveterm | 36 | **0** | 0 | 0 | **0** | no |
| containerd | 352 | 20 files, dedicated `contrib/fuzz/`, OSS-Fuzz wired | 0 | 3 | not counted | no |
| ragflow | 1,161 | **0** | — | — | — | — |
| caddy | 136 | **0** | — | — | — | — |
| rclone | 383 | **0** | — | — | — | — |
| milvus | 1,717 | 1 | — | — | — | — |
| trivy | 587 | 1 | — | — | — | — |
| podman | 354 | 1 | — | — | — | — |
| opentofu | 654 | **0** | — | — | — | — |
| helm | 241 | 3 | — | — | — | — |
| harbor | 568 | **0** | — | — | — | — |
| 3x-ui | 525 | 3 | — | — | — | — |
| dokku | 57 | **0** | — | — | — | — |
| minikube | 216 | **0** | — | — | — | — |
| authelia | 361 | 2 | — | — | — | — |
| lima | 90 | 6 | — | — | — | — |
| new-api | 279 | **0** | — | — | — | — |

**Fuzz adoption is a minority practice even in this tier.** 23 of 40 repos (58%) have zero native
`func Fuzz*` targets, including several with very large test suites (jaeger 610 files/0 fuzz, argo-cd
406/0, k6 326/0, opentofu 654/0). Where fuzzing appears, it clusters around parsers, decoders, and
untrusted-input boundaries — prometheus's metric-text parser, cilium's monitor-format parser,
teleport's IID/credential parsers, netdata's SMBIOS/topology parsers — which is the correct targeting
strategy, not scattershot adoption. OSS-Fuzz membership (continuous fuzzing infra, not just
`go test -fuzz`) is explicit in prometheus, containerd, cilium.

**Golden files are bimodal, not gradual.** Most repos have zero (`.golden` grep returns 0 in 34/40),
but three have deep golden-file discipline: teleport (340 files), moby (657 files), and
typescript-go's inherited 48,124-file conformance baseline corpus (a special case — ported wholesale
from the original TypeScript compiler test suite, not built from scratch in Go).

**Property-based testing exists but is rare and always opt-in.** `testing/quick` (stdlib) appears in
exactly one file across the whole corpus (vitess's decimal test). `pgregory.net/rapid` is used
properly in pulumi (36 files, wired to a dedicated `test_lifecycle_fuzz` Makefile target running
10,000 checks by default).

---

## Race detector and CI matrix practice

| Repo | `-race` in CI | Scope | Go version matrix |
|---|---|---|---|
| vitess | yes | every PR (2 dedicated legs + separate e2e-race workflow) | no — single version from go.mod, checked by script |
| teleport | yes | every PR (baked into `make test-go-unit` etc., not visible in workflow YAML) | no — single buildbox image |
| prometheus | yes | every PR, 3 separate ways | no — but **computes oldest-supported Go at runtime** from `go.dev/dl/?mode=json` |
| gitea | yes | every backend PR | no — single, `go-version-file` |
| LocalAI | **partial** — only on 2 path-filtered conformance scripts, one referenced by no workflow at all | narrow, inconsistent | no — per-workflow drift (1.25/1.26/1.27 used inconsistently) |
| k3s | **no** — zero hits anywhere | — | no |
| jaeger | yes | every PR (all archs except s390x, unsupported there) | no — single; separate non-gating Go-tip workflow |
| pulumi | yes, **default-on** (`GO_TEST_RACE ?= true`) | every PR, off only on Windows and the rapid-fuzz targets | **yes** — 1.26.x + 1.27.x |
| argo-cd | yes | every PR, dedicated `test-go-race` job | no — single pinned version |
| netdata | yes | every PR touching Go, 3 separate raced jobs incl. sudo-privileged | no — single version, but 6-platform cross-compile matrix |
| traefik | **no** — zero hits anywhere | — | no |
| fiber | yes | every PR + push, plus a dedicated 3-way `-count=5` repeated-shuffle job | yes — 1.26.x + 1.27.x × 3 OS |
| k6 | yes | every push/PR, dropped only on Windows | current + prev + gotip (resolved from external repo) × 3 OS |
| loki | yes (in Makefile, invisible in workflow YAML) | every PR via external reusable workflow | no — single pinned |
| trufflehog | **no in CI** — only a local `make test-race` target | — | no — single pinned |
| go-redis | yes | every PR | yes — 1.25.x/oldstable/stable × 5 Redis versions |
| typescript-go | yes | every push/PR (skipped only on merge_group/forks) | no — single pinned, but OS/arch matrix |
| moby | **opt-in only**, not default in the standard unit path | — | no — single pinned |
| etcd | yes, **default in the pass-based runner** (`RACE="--race"` on amd64/arm64) | no visible in-repo CI workflow for the main pipeline at all (external Prow-style CI) | no — single, `.go-version` file |
| tailscale | yes | every PR (dedicated sharded race-integration job + matrix cell) | no — single, but `./tool/go` wrapper pins per-repo |
| dapr | defined (`test-race` target, curated package allowlist) but **not invoked by any workflow** — dead target | — | no — single |
| cilium | opt-in via `RACE=1` env, applied at CI-image build time, not a plain `go test -race` unit gate | — | no — single pinned |
| temporal | yes, **default-on** (`TEST_RACE_FLAG ?= on`) | every PR; separate Slack-notify job for flaky-race false negatives | no — single |
| waveterm | **no** — no `go test` step exists in CI at all | — | no |
| containerd | yes | every PR/merge_group, applied to integration target | **yes** — 1.26.8 + 1.27.1 (explicit compatibility comment re: k8s 1.36) |
| ragflow | yes (label + cron gated, not every PR) | — | — |
| caddy | yes | every push/PR | — |
| rclone | yes | every push/PR (subset of matrix) | — |
| milvus | no evidence | — | — |
| trivy | no evidence | — | — |
| podman | no evidence | — | — |
| opentofu | yes, but only on 6 named packages, not `./...` | every commit | — |
| helm | defined in Makefile, **not exercised by the CI-invoked target** (same dead-target pattern as dapr) | — | — |
| harbor | no evidence | — | — |
| 3x-ui | yes | every PR touching Go files | — |
| dokku | yes | CI (`go-tests`) | — |
| minikube | no evidence | — | — |
| authelia | no evidence (Buildkite scripts) | — | — |
| lima | no evidence | — | — |
| new-api | no evidence | — | — |

**Race-on-every-PR is common but not universal, and "defined but dead" is a real failure mode worth
naming.** At least three repos (dapr, helm, and moby's non-default path) have a `-race` target that
*exists in the Makefile* but is either never invoked by CI or invoked only on a narrow allowlist —
this is a place where a repo *looks* race-disciplined by grepping the Makefile but isn't in practice.
The lesson: verify the CI workflow actually calls the race target, not just that the target exists.

**Go version matrices are the exception, not the rule.** Only 4 of 40 repos genuinely matrix Go
versions (pulumi, fiber, go-redis, containerd); the dominant idiom is a single pinned version read
from `go.mod` via `go-version-file:`, sometimes with a script asserting consistency across files
(vitess's `check_go_versions.sh`, k3s deriving `GOTOOLCHAIN` from a version script). Prometheus's
self-updating oldest-supported-version job (querying `go.dev/dl/?mode=json` at CI time) is the most
sophisticated pattern found and is worth calling out as a specific, copyable idea.

---

## Error-handling conventions (quoted)

No repo in this corpus has extensive prose error-handling documentation; the convention is almost
always enforced by linter, not written down. The exceptions are worth quoting in full.

**Wrap-with-context, log-or-return (not both)** — `trufflesecurity/trufflehog@a3fcdde:CONTRIBUTING.md`:
> "Either log an error or return it. Doing one or the other will help defer logging for when there is
> more context for it and prevent duplicate 'bubbling up' logs."

**Typed sentinel via a project-wide error package** — `vitessio/vitess@83eb933:AGENTS.md`:
> "Use `vterrors` for user-facing errors. Use the applicable `vtrpcpb.Code`. Use `vterrors.Wrapf` to
> add context to an error."
Teleport runs the same shape at larger scale, but built on a different package — its own `trace`
library (`gravitational/teleport@1283425:go.mod`), imported in **3,666 files** with **31,678**
`trace.Wrap(` call sites, the single heaviest use of one error-wrapping mechanism found anywhere in
this corpus.

**Hook-contract discipline (structural, not just prose)** — `redis/go-redis@cb175c6:AGENTS.md`:
> "Wrap errors with custom error types that implement `Unwrap`, or use `fmt.Errorf("...: %w", err)`.
> Always call `cmd.SetErr(...)` after wrapping so typed-error checks still pass."
plus a hard rule on the hook chain itself: hooks "must call `next`, must not call `Close`, must not
panic, must not mutate client/connection state."

**Core-invariant vs recoverable severity** — `temporalio/temporal@3dafaf9:AGENTS.md`:
> "Check and handle all errors... Use `logger.Fatal` for core invariant violations... Use
> `logger.DPanic` for issues that are important but should not crash production... errors MUST be
> handled, not ignored."

**Documented forbidden-package table doubling as the depguard rationale** —
`grafana/loki@b22cd0d:CODING_STANDARDS.md`:
> "Wrap errors with context using `fmt.Errorf("doing X: %w", err)` so callers can inspect them with
> `errors.Is` / `errors.As`. Do not swallow errors silently; if an error is intentionally ignored,
> document why."

**Typed-domain-error-with-checker-function pattern**, the strongest structural convention found,
`go-gitea/gitea@fba8d7e:models/user/error.go:13-29`:
```go
type ErrUserAlreadyExist struct{ Name string }
func IsErrUserAlreadyExist(err error) bool { ... }
func (err ErrUserAlreadyExist) Unwrap() error { return util.ErrAlreadyExist }
```
Repeated identically across `models/asymkey/error.go`, `models/db/error.go`,
`models/deploykey/error.go` — every domain error is a struct with a checker function and an
`Unwrap()` back to a shared sentinel, giving both `errors.Is` compatibility and rich per-error
context.

**Counts across the deep-read repos** (non-test `.go` files, `errors.Is(` / `errors.As(` / `%w` wraps):

| Repo | `errors.Is` | `errors.As` | `%w` wraps | Notable |
|---|---|---|---|---|
| vitess | 71 | 10 | 95 | |
| teleport | 914 | 294 | 496 | 31,678 `trace.Wrap()` calls dominate instead |
| prometheus | 208 | 22 | 881 | 99 `errors.Join` |
| gitea | 479 | 36 | 1,420 | typed-error-with-Unwrap is the dominant idiom |
| cilium | 1,047 | 1,027 | 1,382 | unusually high `errors.As` — reflects heavy typed-error inspection |
| argo-cd | 81 | 23 | 4,483 total `Errorf`, ~40% with `%w` | |
| netdata | 859 | 77 | 1,664 | 577 `errors.Join` — aggregate-error style is idiomatic here |
| loki | 386 | 26 | 1,615 | 222 files still import banned-elsewhere `pkg/errors` |

---

## Concurrency and reliability patterns

This is where the production-reliability lineage of this corpus earns its keep. Four independent,
copyable mechanisms recur.

### 1. `goleak` — wrapped, not used raw

Direct `go.uber.org/goleak` imports appear in only a minority of repos (prometheus 6 files, loki 6,
go-redis N/A-absent, temporal 1, k6 2 — via `goleak.VerifyTestMain`). The two most disciplined repos
**ban the direct import and force a wrapper**:

`cilium/cilium@84222dc:.golangci.yaml` (via `gomodguard_v2`):
```yaml
- module: go.uber.org/goleak
  recommendations: [github.com/cilium/cilium/pkg/testutils]
  reason: Use testutils.Goleak* instead for the shared default options.
```

`jaegertracing/jaeger@7ebccce:internal/testutils/leakcheck.go` does the same and goes further —
`scripts/lint/check-goleak-files.sh` is a **dedicated CI lint step** that fails if any package
containing tests lacks a `TestMain` calling `testutils.VerifyGoLeaks`. This is the strongest
mechanical enforcement of goroutine-leak checking found anywhere in the corpus: not "we use goleak
somewhere" but "every test package is checked, or CI fails."

`prometheus/prometheus@dff7878:util/testutil/testing.go:31-45` shows the shared-wrapper shape
directly:
```go
// TolerantVerifyLeak verifies go leaks but excludes the go routines that are
// launched as side effects of some of our dependencies.
func TolerantVerifyLeak(m *testing.M) {
	goleak.VerifyTestMain(m,
		goleak.IgnoreTopFunction("go.opencensus.io/stats/view.(*worker).start"),
		goleak.IgnoreTopFunction("k8s.io/klog/v2.(*loggingT).flushDaemon"),
		goleak.IgnoreTopFunction("k8s.io/client-go/util/workqueue.(*Type).updateUnfinishedWorkLoop"),
	)
}
```
**The pattern to copy:** don't call `goleak.VerifyNone` bare in every test; write one project-local
wrapper with your dependencies' known background goroutines pre-ignored, and either mandate it via
`TestMain` convention or lint-enforce its presence.

**Repos with no goleak practice at all** (worth recording as absence): gitea, LocalAI, k3s, traefik,
fiber, moby, tailscale (uses a homegrown alternative instead, see below), dapr, waveterm, containerd,
pulumi, argo-cd. This is the majority — goleak is a minority practice even here.

### 2. Homegrown leak/lock tooling beats third-party libraries at the frontier

`tailscale/tailscale@2d43793:tstest/resource.go` — `ResourceCheck(tb)` snapshots
`runtime.NumGoroutine()`/stacks before a test, polls up to 300 times post-test for the count to
return to baseline, and **panics if called from a parallel test**.

`tailscale/tailscale@2d43793:.github/workflows/checklocks.yml` runs gVisor's
`checklocks` static analyzer as a `go vet -vettool`, enforcing mutex-discipline via
`// +checklocks:` annotation comments — a genuinely novel pattern (annotation-based lock-ordering
verification) not found in any other repo in this corpus.

`etcd-io/etcd@7583cc6:client/pkg/testutil/leak.go` is explicitly a **stopgap**, with the comment
`// TODO: Replace with https://github.com/uber-go/goleak.` still in the code — evidence that even
mature repos carry unmigrated tech debt in this area.

### 3. Retry/backoff/circuit-breaker: mostly hand-rolled, third-party libs are secondary

| Repo | Backoff | Circuit breaker |
|---|---|---|
| gitea | hand-rolled (`modules/queue/backoff.go`) | none |
| teleport | hand-rolled (`api/utils/retryutils/`, built on `clockwork` for testability) | **hand-rolled** (`api/breaker/breaker.go`), not gobreaker |
| prometheus | `cenkalti/backoff/v5` (direct dep) | `sony/gobreaker/v2` present only as **indirect** dep — zero direct imports, effectively unused |
| traefik | `cenkalti/backoff/v4` (direct) | first-party middleware wrapping `vulcand/oxy/cbreaker`; `gobreaker` only indirect |
| loki | `dskit/backoff` (45 files) | **both**: `sony/gobreaker/v2` (direct, used in memcached client) AND a first-party one in `pkg/distributor/circuit_breaker.go` |
| dapr | `cenkalti/backoff/v4` (26 uses; v1-v3 depguard-banned) | `sony/gobreaker` wrapped in `pkg/resiliency/breaker/` — part of a first-class `pkg/resiliency` policy package |
| trufflehog | `hashicorp/go-retryablehttp` (direct) | none |
| k6 | `cenkalti/backoff` only indirect — effectively unused | none |
| pulumi | hand-rolled (`sdk/go/common/util/retry/until.go`, `DefaultBackoff = 1.5`) | none |
| argo-cd | `cenkalti/backoff/v5` + k8s `client-go/util/retry` + `wait.ExponentialBackoff` (3 different mechanisms in one repo) | none |
| tailscale | hand-rolled (`util/backoff/backoff.go`) | none (hand-rolled retry instead) |
| fiber | hand-rolled (`addon/retry/exponential_backoff.go`, `crypto/rand`-based jitter) | none |
| k3s | k8s `apimachinery/pkg/util/wait` (`wait.Backoff`) | none |
| netdata | **prohibited by default** — see below | none |

**The most interesting finding is netdata's anti-pattern rule**, worth quoting in full because it
inverts the usual advice — it argues *against* adding retry/backoff machinery speculatively:
`netdata/netdata@4f911b1:src/go/AGENTS.md`, §"Evidence Before Complexity":
> "Code MUST NOT introduce population, byte, concurrency, queue, retry, or backpressure limits, nor
> add accounting, scheduling, pooling, caching, custom data structures, or lifecycle machinery, unless
> the design follows from a concrete correctness, liveness, protocol, compatibility, or security
> contract, a documented scale requirement, or a measured production workload. ... A round number, a
> hypothetical abuse case, or a benchmark in isolation is not evidence of a product requirement."

This is a real, load-bearing anti-goal from a production Go codebase and belongs in any skill that
tells an agent to "add retry logic" or "add a circuit breaker" — the counter-question is *what failure
class, observed how, does this prevent*, matching Part G rule 1 of the rubric almost exactly.

### 4. Context propagation — mechanically enforced, rarely written down

Documented prose rules are rare; when they exist they are specific and worth quoting:

`traefik/traefik@f08328c:AGENTS.md`:
> "Context propagation. `context.Context` is always the first argument, named `ctx`. Avoid
> `context.Background()` in request paths; propagate from the caller. Define custom context keys as
> unexported struct types (`type myKey struct{}`) to prevent collisions."

`go-gitea/gitea@fba8d7e:docs/guidelines-backend.md:62-63`:
> "Functions that participate in a transaction take a `context.Context` as their first parameter so
> the transaction can be propagated."

`temporalio/temporal@3dafaf9:.github/.golangci.yml` (`forbidigo` rules, enforced not just documented):
bans `context.Background()` in tests ("use t.Context() instead"), bans `time.Sleep` ("use
await.Require / s.Await"), bans bare `time.Now` inside `chasm/lib` ("use ctx.Now(component) instead").

Where no prose exists, enforcement is via the `contextcheck`/`fatcontext` linters (cilium, jaeger,
fiber, argo-cd via revive's `context-as-argument` rule) or simply unenforced (majority of repos).
**A JS/Python developer should not assume "ctx-first" is written down anywhere** — it is Go community
convention, occasionally lint-enforced, rarely documented in-repo.

---

## Generated-code drift detection

This is the highest-value, most consistently present pattern in the entire corpus — present in some
form in at least 20 of the 25 deep-read repos. **The primitive is always the same: regenerate, then
fail if the working tree changed.** Three refinements distinguish a good implementation from a naive
one.

### The naive form
```bash
make generate
git diff --exit-code
```
Works, but has two holes: (1) a stale-but-present generated file can mask drift if the generator
itself is non-deterministic or skips unchanged-looking output, and (2) it misses **new, untracked**
generated files (a genuinely new type that should have produced a new generated file, but didn't).

### Refinement 1 — delete before regenerating
`prometheus/prometheus@dff7878:Makefile:163-166`:
```makefile
check-generated-parser: clean-parser promql/parser/generated_parser.y.go
	@git diff --exit-code -- promql/parser/generated_parser.y.go || \
	  (echo "Generated parser is out of date. Please run 'make parser' and commit the changes." && false)
```
`clean-parser` deletes the target file first, so an absent-but-should-exist file cannot hide behind a
stale copy.

### Refinement 2 — prerequisite: tree must already be clean before you start
`gravitational/teleport@1283425:Makefile:1762-1852`:
```makefile
must-start-clean/host:
	@if ! git diff --quiet; then \
		echo 'This must be run from a repo with no unstaged commits.'; \
		git diff; exit 1; \
	fi

derive-up-to-date: must-start-clean/host derive
	@if ! git diff --quiet; then \
		./build.assets/please-run.sh "derived functions" "make derive"; exit 1; \
	fi
```
This closes a subtler hole: if the check itself runs against an already-dirty tree (e.g. a prior step
left artifacts), a real drift can be masked by unrelated noise. Same shape reused for
`protos-up-to-date`, `go-generate-up-to-date`, `crds-up-to-date`, `terraform-resources-up-to-date`,
`bpf-up-to-date`, `cli-docs-up-to-date` — seven independent gates built on one two-line primitive.

### Refinement 3 — catch new untracked files, not just modified ones
`cilium/cilium@84222dc:.github/workflows/lint-go.yaml` (job `generate-api`):
```bash
git add --intent-to-add .
diff="$(git diff)"; diff_staged="$(git diff --staged)"
if [ -n "$diff" ] || [ -n "$diff_staged" ]; then
	echo "Ungenerated api source code: ..."; exit 1
fi
```
`git add --intent-to-add .` stages new files without their content, so a plain `git diff` afterward
picks them up as additions — a bare `git diff --exit-code` would silently ignore a new untracked file.
`tailscale/tailscale@2d43793` uses the identical trick (`git add -N .` before its diff-exit-code
check) and `moby/moby@5d8f006:hack/dockerfiles/generate-files.Dockerfile` combines both refinements
in one script (`git status --porcelain` instead of `git diff`, which naturally includes untracked
files, then filters out known-noisy paths with `:!vendor`).

### Refinement 4 — sandbox the whole check in a disposable worktree
`etcd-io/etcd@7583cc6:scripts/verify_genproto.sh` — the most defensive form found:
```bash
tmpWorkDir=$(mktemp -d -t 'twd.XXXXXX')
cp -r . "$tmpWorkDir"; pushd "$tmpWorkDir"
git add -A; git commit -m init || true
./scripts/genproto.sh
diff=$(git diff --numstat | awk '{print $3}')
popd
if [ -z "$diff" ]; then exit 0; fi
exit 1
```
`containerd/containerd@04f9be9:Makefile:497` (`verify-vendor`) does the same for the whole vendor
tree: copy to `mktemp -d`, run `go mod tidy && go mod vendor && go mod verify` there, then
`diff -r -u -q` the two trees. This is the strongest possible form because it cannot be polluted by
anything already in the working directory.

### Coverage table

| Repo | Drift gate present | PR-blocking? | Mechanism |
|---|---|---|---|
| vitess | yes, 5 independent checks | yes | `git status --porcelain` diff before/after |
| teleport | yes, 7 gates sharing `must-start-clean` prerequisite | yes | `git diff --quiet` |
| prometheus | yes, 4 gates | yes | `clean-then-regenerate` + `git diff --exit-code` |
| gitea | yes, 3 gates (`swagger-check` etc.) | yes | regenerate + diff, one uses `git add` first for untracked SVGs |
| LocalAI | **no gate** — drift avoided structurally (`.pb.go` gitignored, always regenerated) | n/a | different strategy: never commit generated output |
| k3s | **no codegen at all** (drift check is dependency-only) | — | — |
| jaeger | yes, protobuf + mocks + monitoring dashboard | yes | `git status --porcelain \| grep '??'` + `git diff --exit-code` (catches untracked too) |
| pulumi | yes, 2 gates (`check_proto`, `sdk/go gen`) | yes | `git diff --quiet` / `git status --porcelain` |
| argo-cd | yes, whole `codegen-local` chain, deliberately exempts `go.sum`/`go.mod`/`swagger.json` | yes | `git diff --exit-code -- . ':!go.sum' ':!go.mod' ...` |
| netdata | yes, **but only on `push: master`, not on `pull_request`** — drift caught post-merge | **no**, post-merge only | `git diff --exit-code`; separate `go fix` check currently commented out |
| traefik | yes, 2 gates | yes | plain `git diff --exit-code` |
| fiber | **no CI gate** — offers a `/generate` PR-comment bot instead (fixer, not gate) | no | manual trigger |
| k6 | yes, 2 gates (incl. untracked-file check) | yes | `git status --porcelain` + explicit `git ls-files --others` check |
| loki | yes, **7 separate gates** (most of any repo) — generated code, mixins, docs, format, release-workflow YAML | yes | `git diff --exit-code` |
| trufflehog | **only the man page** — protobuf/mockgen output has **no drift gate** | partial | `git diff --exit-code docs/man/trufflehog.1` |
| go-redis | **no gate** | no | `go mod tidy` runs without a following diff check |
| typescript-go | yes, 2 gates (`generate`, plus staged-diff after tests for the 48k-file baseline corpus) | yes | `git add . && git diff --staged --exit-code --stat` |
| moby | yes, dedicated Dockerfile stage | yes | `git status --porcelain` with path exclusions |
| etcd | yes, sandboxed tmp-worktree (strongest form) | yes (via `make verify`) | `diff` on `git diff --numstat` in a disposable copy |
| tailscale | yes, 2 gates (dedicated `go_generate` job + general dirty-check after tests) | yes | `git add -N .` then `git diff --name-only --exit-code` |
| dapr | yes, `check-proto-diff` names 9 explicit generated files | yes | per-file `git diff --exit-code` |
| cilium | yes, 2 gates (API + k8s codegen), untracked-safe | yes | `git add --intent-to-add .` then `git diff` |
| temporal | yes (`fmt`, `parallelize-tests` jobs) | yes | `git status --porcelain` |
| waveterm | **no gate at all** — and no CI runs `go test`/lint either (see race table) | no | — |
| containerd | yes, `check-protos` via `buf format --diff --exit-code` | yes, dependency of `check`/`ci` | buf's own diff mode |
| milvus | yes | yes | `git diff --exit-code -- pkg/util/merr/segcore_codes_gen.go` |
| opentofu | yes | yes | `make generate protobuf` + `git status --porcelain` |
| minikube | yes (docs only) | yes | `make generate-docs` + `git status --porcelain` |
| lima | yes | yes | `check-generated: git diff --exit-code \|\| (echo "run make generate" && false)` |
| 3x-ui | yes | yes | `git diff --exit-code -- frontend/src/generated ...` |
| trivy | yes (docs) | yes | `mage docs:generate` + `git status --porcelain` |
| others (ragflow, caddy, rclone, harbor, podman, helm, dokku, authelia, new-api) | not confirmed / not found | — | — |

**For the skill: the canonical 3-line pattern to hand an agent is**
```bash
make generate   # or: go generate ./... ; buf generate ; etc.
git add -N .    # stage new files by name only, so untracked additions are visible to diff
git diff --exit-code
```
This single addition (`git add -N .` before the diff) is the one line that separates a naive
implementation from what tailscale, cilium, and moby actually run, and it is the most common gap when
someone hand-writes this check from memory.

---

## Dependency hygiene

| Repo | `go mod tidy` + diff gate in CI | `vendor/` checked in | `pkg/errors` banned |
|---|---|---|---|
| vitess | yes (`go mod tidy` + `git status -s`, all sub-modules) | no | no (bans `math/rand` instead) |
| teleport | yes, cleanest form: `go mod tidy -diff` (no working-tree mutation) | no | no |
| prometheus | yes (`common-unused`: tidy + `git diff --exit-code go.sum go.mod`) | no | **yes** |
| gitea | yes (`tidy-check`) | no (target exists, unused by default) | **yes** |
| LocalAI | **no** — only a pre-release GoReleaser hook, no diff check | no | no (unbanned, actively imported) |
| k3s | yes (`scripts/validate`: tidy + dirty-tree check) | no | no (no depguard at all) |
| jaeger | **no** — no CI job runs tidy+diff on the main module | no | no |
| pulumi | yes, most rigorous: `go mod tidy -diff` per-module + **bans `toolchain` directives** ("we don't want CI overridden by a toolchain directive") | no | no (bans `golang/protobuf` instead) |
| argo-cd | yes, broad (`go mod tidy` + `git diff --exit-code -- .`, whole tree not just go.mod/go.sum) | no (transient, `rm -rf vendor/` after codegen) | **yes**, via `gomodguard_v2` |
| netdata | **no** — CI runs `go mod download` only, never `go mod tidy` | no | no (unbanned but 0 first-party imports anyway) |
| traefik | yes (`script/validate-vendor.sh`) | no | **yes** |
| fiber | **no** — `make tidy` exists, never invoked by CI | no | no (bans `flag`/`log`/`io/ioutil` instead) |
| k6 | yes, but via external `grafana/k6-ci` reusable workflow | **yes** (49M) | no (no depguard mechanism at all) |
| loki | yes (`check-mod`: tidy + vendor + `git diff --exit-code`) | **yes** (282M) | no — 222 files import it |
| trufflehog | **no** | no | no — active dependency |
| go-redis | tooling exists (`go_mod_tidy` target), **not wired to a CI gate** | no | no |
| typescript-go | yes, both modules + `go work sync` | no | no (bans `encoding/json` instead) |
| moby | yes (`hack/validate/vendor`, tidy + vendor + license check) | **yes** | no (bans testify/fsutil/multierror instead) |
| etcd | yes, diff-only (`go mod tidy -diff`, workspace variant too) | no | no (no third-party depguard) |
| tailscale | yes (`make_tidy` job), plus **`depaware`** — a stronger, separate gate diffing each binary's full transitive-import graph against a checked-in allowlist | no | no (unbanned) |
| dapr | yes (`modtidy check-diff`) + retracted-dependency check | no | **yes** |
| cilium | yes (`go mod tidy && go mod vendor` + `git status --porcelain`) | **yes** (251M) | not confirmed |
| temporal | **no** — tidy exists as Makefile target only | no | no (bans `pborman/uuid` instead) |
| waveterm | **no** — no Go verification runs in CI at all | no | not applicable (no depguard config) |
| containerd | yes, strongest form: sandboxed tmpdir copy, tidy+vendor+verify, full-tree `diff -r -u -q` | **yes** | no (bans `opencontainers/runc` instead) |
| milvus | not confirmed | not confirmed | **yes**, bans `errors`, `pkg/errors`, `pingcap/errors`, `x/xerrors` in favor of `cockroachdb/errors` |
| trivy | yes | not confirmed | no (bans `x/exp/slices`, `x/exp/maps`, `io/ioutil`) |
| helm | yes (`go mod tidy -diff`) | not confirmed | **yes** |
| lima | not confirmed | not confirmed | no (bans `x/net/context`, `math/rand`) |
| others (ragflow, caddy, rclone, podman, harbor, 3x-ui, dokku, minikube, authelia, new-api) | not confirmed present | not confirmed | not confirmed |

**Vendoring is a minority practice concentrated in a few large, old projects** (k6, loki, moby,
cilium, containerd) — most repos in this corpus rely on the module proxy and Go's content-addressed
`go.sum` instead. Where vendoring exists, the tidy+vendor+diff gate is always three commands chained,
never `go mod tidy` alone.

**Tailscale's `depaware` is the standout finding in this section** — a mechanism stronger than any
`go mod tidy` diff check, because it doesn't just verify `go.mod` is internally consistent, it asserts
that the **actual transitive dependency graph of each shipped binary** matches a checked-in,
human-reviewed allowlist (`cmd/tailscaled/depaware.txt` etc.), annotated per-package for risk (💣 for
cgo, `W`/`L` for platform-specific). Any new transitive dependency — even one pulled in by an existing,
approved direct dependency's own upgrade — fails CI until a human updates the allowlist. This is the
closest thing in the corpus to a "no silent supply-chain growth" gate and is worth recommending
independently of the `pkg/errors` question.

---

## Synthesis: minimum viable vs strongest justified Go stack

Tagged per Part G rule 4 (scale-appropriate). All commands are real, copied from the corpus above —
not invented.

### Minimum viable (solo / small team, 2-10 people)

```bash
# one-time setup
go install honnef.co/go/tools/cmd/staticcheck@latest      # or use golangci-lint's bundled staticcheck
go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@latest

# the prove-it sequence, run before every commit
gofmt -l .                        # exits non-zero output if anything is unformatted; pair with `gofmt -w .`
go vet ./...                      # free, built into the toolchain — catches real bugs (printf mismatches, lock copies, etc.)
go test -race ./...               # -race costs ~2x build time, ~5-10x runtime; worth it below ~50k LOC
golangci-lint run                 # start with a small opt-in linter list, not `default: all`
go mod tidy -diff                 # Go 1.23+: verifies without mutating; CI-safe
```
A minimal `.golangci.yml` worth starting from (assembled from the smallest real configs in this
corpus — trufflehog's 8-line file and 3x-ui's curated list):
```yaml
version: "2"
linters:
  enable:
    - depguard      # even with zero rules yet, gives you the mechanism to add bans later
    - errorlint      # forces %w / errors.Is over == comparisons
    - bodyclose      # catches unclosed HTTP response bodies — a real, common Go bug class
    - copyloopvar
```
This is enough to catch: unformatted code, `go vet`'s static-analysis bug class (which is broader
than most JS/Python linters' default set — see next section), data races, and the two or three most
common HTTP-client leak bugs. Nothing here requires a chained `make verify`; a flat sequence is
proportionate at this scale.

### Strongest justified (org, 10+ engineers, high blast radius)

This is what containerd/vitess/teleport/argo-cd actually run — copy the *shape*, not necessarily
every check:

```bash
# 1. Static + format (fast, every save)
gofmt -l . && go vet ./...

# 2. Lint, opt-in linter list with depguard rules for your actual banned-import list
golangci-lint run --timeout 10m

# 3. Codegen drift — regenerate, stage new files, diff
go generate ./...
git add -N .
git diff --exit-code

# 4. Dependency tidy, non-mutating
go mod tidy -diff

# 5. Unit + race, every PR
go test -race -count=1 ./...

# 6. Vulnerability scan (cheap, catches known CVEs in deps — not covered by anything above)
govulncheck ./...
```
Wire steps 1-4 as independent CI jobs (not one script) so a failure in codegen drift doesn't hide a
lint failure, and so contributors can run `make verify-lint` alone while iterating — the
etcd/vitess/lima pattern. Add, only once the team has a concrete reason (Part G rule 1):
- **goleak**, wrapped in a project-local helper with known-noisy dependencies pre-ignored
  (prometheus/cilium/jaeger pattern) — pays off once you have long-running services with real
  goroutine-leak incidents, not before.
- **depaware-style transitive-dependency allowlisting** — pays off once your binary ships to
  production and a supply-chain incident (typosquat, compromised transitive dep) is a real risk you're
  defending against, not a hypothetical.
- **A `make verify` chain over a flat script** — pays off once you have enough sub-checks (5+) that
  attributing a CI failure to "which check" from a single wall of output becomes the bottleneck.

### What NOT to copy at small scale

- Complexity linters (`gocognit`/`gocyclo`/`cyclop`) — **38 of 40 repos in this corpus don't enforce
  them**, including some of the largest and most disciplined (vitess, teleport, prometheus). This is
  not an idiom worth importing by default.
- Go version matrices — only 4/40 repos do this; a single pinned version via `go-version-file: go.mod`
  is the norm and is sufficient below "maintaining a published library with external consumers on
  older Go."
- Sandboxed tmpdir-worktree diff checks (etcd, containerd's `verify-vendor`) — genuinely the most
  defensive pattern found, and genuinely overkill below org scale; a plain `git diff --exit-code` in
  the working tree is fine until you have evidence of the specific failure mode (a dirty pre-existing
  tree masking drift) it defends against.

---

## What Go gives free vs what JS/Python must bolt on

This is the most useful framing for someone switching stacks, because it changes what "equivalent
rigor" costs to set up.

| Capability | Go | JS/TS | Python |
|---|---|---|---|
| Formatter | `gofmt`/`go fmt` — built into the toolchain, zero-config, one true style, no bikeshedding possible | `prettier` — separate install, separate config file, competing style options | `black`/`ruff format` — separate install, config choices |
| Static analysis catching real bugs (not just style) | `go vet` — built in, ships with every install, catches printf-arg mismatches, `sync.Mutex` copies by value, unreachable code, struct-tag typos | ESLint — separate install, rules are opt-in and community-maintained, no built-in equivalent to `go vet`'s deeper checks | none built in; `mypy`/`pyflakes`/`ruff` are all separate installs, none catch Go-vet-class issues (Python's dynamic typing makes several of them structurally impossible to catch statically anyway) |
| Data-race detector | `-race` flag on `go test`/`go build` — built into the toolchain, instruments real memory access at runtime | no equivalent — JS is single-threaded per-realm by design, so the failure class mostly doesn't exist; Node worker-thread races are not caught by any standard tool | GIL mostly prevents the classic race class for pure-Python code; `asyncio` has its own class of bugs (no built-in detector); C-extension races are invisible to any Python tool |
| Dependency-tidy verification | `go mod tidy -diff` — built into the toolchain (Go 1.23+), verifies without mutating, one command | no direct equivalent; closest is `npm ci` (fails on lockfile drift) or `depcheck`/`knip` for unused deps — separate installs, different tools for different halves of the problem | no direct equivalent; `pip-audit`, `deptry` — separate installs, and Python's lack of a canonical single lockfile format (requirements.txt vs poetry.lock vs uv.lock) fragments this further |
| Table-driven test idiom | a language/stdlib convention (`[]struct{...}` + `t.Run` subtests), zero extra dependency, works with the standard `testing` package | requires `.each`/`test.each` (Jest/Vitest) — a testing-framework feature, not a language idiom; behavior varies by framework | requires `@pytest.mark.parametrize` — a pytest feature, not a language idiom; unittest's stdlib runner has no native equivalent |
| Static binary / zero-runtime-dependency deploy | default build output — a single self-contained binary, cross-compilable to another OS/arch with one env var (`GOOS=... GOARCH=... go build`), no interpreter or node_modules to ship | requires bundlers (webpack/esbuild/vite) to get close, and still needs a Node runtime on the target unless further packaged (pkg, nexe) | requires PyInstaller/Nuitka/similar, historically fragile, and the interpreter+stdlib+deps footprint is much larger than Go's static binary |
| Built-in benchmark harness | `func Benchmark*` + `go test -bench` + `benchstat` for statistical comparison — all first-party, no separate install | no stdlib equivalent; needs `benchmark.js`, Vitest's `bench`, or similar third-party tooling | `pytest-benchmark` or `timeit` (stdlib but manual, no harness/reporting) — separate install for anything beyond ad-hoc timing |
| Fuzzing | `go test -fuzz` — built into the toolchain since Go 1.18, generates and mutates inputs, integrates with `go test` directly | no built-in equivalent; `jsfuzz`/`jazzer.js` exist but are separate installs with much smaller ecosystems | `atheris` (libFuzzer-based) — separate install, less integrated with the standard test runner than Go's version |

**The net effect for a JS/Python team evaluating Go:** a meaningful fraction of what this corpus
found as "verification system" for Go repos is actually *free from the toolchain* — `gofmt`, `go vet`,
`-race`, `go mod tidy`, table-driven tests, and (since 1.18) fuzzing are zero-additional-dependency.
What Go projects *add* on top (golangci-lint, depguard, goleak, protobuf codegen tooling, `mage`/task
runners) is comparable in kind to what a JS/Python project already bolts on (ESLint, ruff, ts-prune,
pytest plugins) — the delta is specifically in the free tier underneath, not in the discipline of the
mature projects themselves. This corpus's complexity-linter absence (38/40 repos) and thin prose
conventions (error handling, context rules almost never documented, only lint-enforced) suggest Go's
*culture* leans on toolchain defaults and community convention over written style guides more than
this research's JS/Python tracks likely found — worth checking against `research/20-23-*.md` if a
direct comparison is wanted.
