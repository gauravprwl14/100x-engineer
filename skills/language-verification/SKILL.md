---
name: language-verification
description: >
  tsconfig, eslint, biome, vitest, ruff, mypy, pytest, golangci-lint, go vet, race detector:
  which TypeScript/Python/Go checks really gate CI — type errors, coverage, codegen drift. Not
  for framework code (→ stack-reviewer).
---

# Language verification

What 72 JS/TS, 50 Python and 40 Go production repos actually run, counted rather than
recommended. One skill, three toolchains: pick the section for the language in the diff.
Formerly `typescript-verification`, `python-verification` and `go-verification`.

| language | rules | detail (baseline, full command sets, failure cases, sources) |
|---|---|---|
| JavaScript / TypeScript | 1–10 | `references/typescript.md` |
| Python | 11–18 | `references/python.md` |
| Go | 19–27 | `references/go.md` |

## Trigger

**Fire when:** writing or changing JS/TS, Python or Go; setting up or auditing a project's
checks; configuring tsconfig, eslint/biome, vitest/jest, turbo/nx, ruff/mypy/pyright/pytest,
uv/poetry, golangci-lint/depguard; adding code generation; deciding merge gates.

**Do not fire when:** editing a JSON/YAML config with no code impact; a one-off script outside a
project or a notebook with no shipped artifact; Go touched only incidentally (a version bump in
YAML). Framework code shape (a NestJS pipe, a React list key) is `stack-reviewer`.

## Rules

### JavaScript / TypeScript

1. Set `"strict": true` in tsconfig — the highest-value single flag and the corpus baseline.
   *Enforced by:* `npx tsc --noEmit`
2. Run typecheck as its own fast gate, separate from build (~10s, catches most breakage early).
   *Enforced by:* `npx tsc --noEmit` as a distinct CI job and package script
3. Gate coverage on the **patch**, not the repo; a whole-repo threshold gets disabled.
   *Enforced by:* codecov `patch:` status with `informational: false`, or `diff-cover` against the merge base
4. Add `knip` for unused files, exports and dependencies — the strongest JS anti-bloat tool.
   *Enforced by:* `npx knip`
5. With more than one package, enforce architectural boundaries mechanically, not in prose.
   *Enforced by:* `turbo boundaries`, `dependency-cruiser --output-type err`, or `eslint-plugin-boundaries`
6. Budget bundle size for anything shipped to a browser; 97% of the corpus has none, so pick it.
   *Enforced by:* `npx size-limit`
7. In a monorepo, run only affected work; full-graph CI on every PR trains people to ignore CI.
   *Enforced by:* `turbo run test --filter=...[origin/main]`
8. Never suppress the type-checker to pass CI; `@ts-ignore` and `any` hide the bug it found.
   *Enforced by:* `@typescript-eslint/no-explicit-any` and `@typescript-eslint/ban-ts-comment` in eslint
9. Verify your gates actually gate before trusting green CI.
   *Enforced by:* `100x audit_ci_gates`
10. Consider `noUncheckedIndexedAccess` (catches a real bug class; expect friction on old code).
    *Enforced by:* the flag in tsconfig plus `npx tsc --noEmit`

### Python

11. Run `ruff format --check` and `ruff check` first; one binary replaces black, isort, flake8.
    *Enforced by:* `uv run ruff format --check . && uv run ruff check .`
12. Pick one type checker and let it gate, or have none; an advisory checker catches nothing.
    *Enforced by:* `100x audit_ci_gates` (flags `continue-on-error`, `set +e`, `|| true`, `--exit-zero`, `.disabled` workflows)
13. Curate ruff rules with `extend-select`; never `select = ["ALL"]` plus an unmaintained ignore list.
    *Enforced by:* review
14. Commit a lockfile; `uv.lock` is the fastest-growing choice in the corpus.
    *Enforced by:* `uv lock --check` (or `poetry check --lock`)
15. Make pytest strict about its own configuration: unknown markers and unexpected passes fail.
    *Enforced by:* `addopts = "--strict-markers --strict-config"` and `xfail_strict = true`
16. Scope type checking honestly and log the scope: `100x decide new "mypy --strict scope" --affects "<package>/**"`.
    *Enforced by:* `uv run mypy --strict <package>/` on named packages, in CI
17. For parser, schema or numeric libraries add property-based tests (hypothesis) — the largest unclaimed gap.
    *Enforced by:* `uv run pytest tests/property/` once written
18. Do not trust a coverage percentage as proof tests can fail; mutation testing is absent in 50/50 repos.
    *Enforced by:* `100x bloat_check --only assertionless`

### Go

19. Run the race detector in tests; concurrency bugs are Go's characteristic defect.
    *Enforced by:* `go test -race ./...`
20. Gate generated-code drift: regenerate, then fail if the tree changed (20+ of 25 deep-read repos).
    *Enforced by:* `go generate ./... && git add -N . && git diff --exit-code`
21. Use `git add -N .` before `git diff --exit-code`; plain `git diff` misses new untracked files.
    *Enforced by:* the command in rule 20 (`tailscale`, `cilium`, `moby` all use this form)
22. Keep `go.mod` honest in CI.
    *Enforced by:* `go mod tidy -diff` (or `go mod tidy && git diff --exit-code go.mod go.sum`)
23. Enable golangci-lint with an explicit opt-in linter list, not `default: all`.
    *Enforced by:* `golangci-lint run` with an `enable:` list in `.golangci.yml`
24. Encode import bans in `depguard`, and log each ban: `100x decide new "Ban <import path>" --affects ".golangci.yml"`.
    *Enforced by:* `depguard` rules in `.golangci.yml`
25. Wrap errors with `%w`; compare with `errors.Is`/`errors.As`, never by string.
    *Enforced by:* `golangci-lint run` with `errorlint` enabled
26. Detect leaked goroutines in tests for anything long-lived.
    *Enforced by:* `goleak.VerifyTestMain(m)` in `TestMain`
27. Scan dependencies for known vulnerabilities.
    *Enforced by:* `govulncheck ./...`

## Verify

```bash
# every language: project state vs the measured corpus, and do the gates gate (~1s)
100x stack_audit .
100x audit_ci_gates .

# JS/TS minimum viable (the modal corpus stack)
pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm test
npx eslint . --max-warnings=0          # eslint exits 0 on warnings without this

# Python minimum viable
uv sync && uv run ruff format --check . && uv run ruff check . && uv run pytest

# Go minimum viable, plus the drift gate
test -z "$(gofmt -l .)"                # gofmt -l exits 0 even when it lists files
go vet ./... && go test -race ./... && golangci-lint run && go mod tidy -diff
go generate ./... && git add -N . && git diff --exit-code

# bind whichever checks you rely on to the code being shipped
100x verified --name test -- pnpm test        # or: uv run pytest / go test -race ./...
```

The strongest-justified command sets (knip, dependency-cruiser, size-limit, madge, diff-cover,
`mypy --strict`, `govulncheck`, `-count=1`) are in each `references/<language>.md`. Runtime:
minimum stacks take seconds on a small repo; `mypy --strict` on a large package is the slow step.

## Failure modes

This skill rejects:

- **A repo with no root `test` script** (5/72 JS repos, including `supabase/supabase`).
- **A whole-repo coverage threshold** on a large existing codebase — set to 0 within a week.
- **`informational: true`** on a codecov status, or `eslint .` without `--max-warnings=0`.
- **`@ts-ignore` added to make CI green.**
- **Layer rules that live only in a README** — `reactive-resume` is the one JS repo that gates them.
- **`[tool.mypy] strict = true` that CI never invokes** (`invoke-ai/InvokeAI`), or a lint run under
  `set +e` (`scikit-learn/scikit-learn`), or a blocking `ty` job with 15 rule categories off
  (`huggingface/transformers`), or `pytest.yml.disabled` (`ranaroussi/yfinance`).
- **A codegen gate that misses new files** — plain `git diff --exit-code` after `go generate`.
- **Go tests without `-race`** in a concurrent codebase; a stale `go.mod`; errors compared by string.
- **A dependency ban that lives only in prose** — repos that decided encoded it in depguard.
- **A coverage number offered as proof the tests are good.**

**Honest limitations:** mutation and property-based testing are absent from all 72 JS and 50
Python repos, so "can these tests actually fail?" has no ecosystem answer beyond
`100x bloat_check --only assertionless`. Complexity linters are not idiomatic Go (2/40).

## Next

Bind the chosen commands with `verification-gate`. A rule you depart from (a coverage threshold,
an `any` exception, a mypy scope) is logged with `100x decide new`. Framework diffs also get
`stack-reviewer`; this skill covers the toolchain, not the code shape.

## Scale

| tier | JS/TS | Python | Go |
|---|---|---|---|
| `solo` | 1, 2, 8 | 11, 14, 15 | 19, 22 |
| `small-team (2-10)` | + 3, 4, 9 | + 12, 16 | + 20, 21, 23, 25 |
| `org` / `high-blast-radius` | + 5, 6, 7, merge queue | + 13, 17, 18, coverage floor | + 24, 26, 27, `make verify` |

Copying a 30-hook pre-commit setup or per-shard CI timing into a three-person team is cargo-culting.

## Sources

- JS/TS counts, modal stack and command sequences: `research/30-findings-js-verification.md`;
  `TriliumNext/Trilium` (rule 3), `TanStack/table` (rule 6), `reactive-resume` (rule 5),
  `vercel/next.js:AGENTS.md` (rule 2), `elastic/kibana:AGENTS.md` (rule 8).
- Python counts and the configured-but-not-enforced cases: `research/31-findings-python-verification.md`;
  `PrefectHQ/prefect`, `ray-project/ray` (rule 16).
- Go counts, `make verify`, drift gates: `research/32-findings-go-verification.md`;
  `tailscale/tailscale`, `cilium/cilium`, `moby/moby` (rules 20–21); depguard bans in
  `prometheus/prometheus`, `traefik/traefik`, `go-gitea/gitea`, `dapr/dapr`, `argoproj/argo-cd`, `helm/helm`.
- Advisory-gate detection patterns in `scripts/audit_ci_gates.py`: `SOURCE: original`.
