# Anti-Bloat Enforcement: Mechanical Tooling Against AI-Generated Bloat

Scope per `research/00-signal-rubric.md` Part D2 and Part G: every rule below ships a command
that exits non-zero on violation. Prose that cannot fail was cut. Every tool claim below is
labeled **TESTED** (I ran it in a scratch project during this research and observed the exit
code/output myself) or **UNTESTED** (design-on-paper / sourced from docs and real repo configs
but not executed here). Scratch projects live at
`/private/tmp/claude-502/.../scratchpad/bloat/{jsproj,pyproj,goproj}` — small hand-built repos
with deliberately planted violations (unused export, import cycle, unused dependency, commented-out
code, over-complex function, layer violation, assertion-free test, API-surface leak, cosmetic
reformat) so each tool's catch/miss behavior could be observed directly rather than assumed from
docs.

---

**5 of the 12 cataloged AI-bloat failure modes — new-file duplication of existing logic, unnecessary-but-used dependencies, single-use abstractions, semantic/renamed-variable duplication, and comments that restate the code — have no tool that mechanically judges the actual question; each is covered only by a proxy that makes the issue visible for a human or LLM reviewer, not a check that resolves it on its own.**

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Tool matrix](#tool-matrix) | one row per tool (knip, ts-prune, depcheck, vulture, ruff, staticcheck, size-limit, api-extractor...) across JS/TS, Python, Go, Universal — what it catches, what it misses, install command, CI-failing command, false-positive rate | 39 lines |
| 2 | [The 12 AI-bloat failure modes and their mechanical checks](#the-12-ai-bloat-failure-modes-and-their-mechanical-checks) | the core of the document — each of the 12 failure modes named above with a TESTED/UNTESTED/PARTIALLY-TESTED runnable command and an honest note on what it misses; start here | 439 lines |
| 3 | [Real configs from major repos (verbatim, cited)](#real-configs-from-major-repos-verbatim-cited) | actual CI configs copied verbatim from flagship repos (Traefik, Prometheus, pandas, TanStack, Grafana, clerk...) proving each tool pattern is live in production, not a design sketch | 319 lines |
| 4 | [Diff-scoped enforcement](#diff-scoped-enforcement) | why whole-repo gates fail on existing codebases, and the advisory-mode + diff-intersection pattern that lets a legacy repo adopt every check as a ratchet on new code only | 46 lines |
| 5 | [Mutation testing: the assertion-free-test killer](#mutation-testing-the-assertion-free-test-killer) | how mutation testing proves a test can actually fail (vs. line coverage, which only proves a line executed) — a real mutmut run showing 25% mutation score despite 100% line coverage | 50 lines |
| 6 | [Recommended layered stack](#recommended-layered-stack) | the 3-tier CI architecture (pre-commit <5s, pre-PR/CI <2min diff-scoped, nightly/weekly whole-repo) with the exact command for every tier — the answer if you just want commands to paste into CI | 60 lines |
| 7 | [Honest limitations](#honest-limitations) | the specific things no tool in this survey catches at all, restated as a checklist — ties directly to the finding above | 28 lines |

## Tool matrix

| Tool | Lang | Catches | Misses | Install | CI-failing command | FP rate in practice | Maturity |
|---|---|---|---|---|---|---|---|
| **knip** | JS/TS | unused files, unused exports, unused deps, unused types, unlisted binaries — cross-module dead code | code used only via string/dynamic paths, reflection; needs entry-point config for monorepos | `npm i -D knip` | `npx knip` (TESTED: exits 1 on findings) | Moderate on first adoption of a large repo (needs `ignore`/entry config tuning); low once tuned | Active, fast-moving (v6, breaking changes across majors) |
| **ts-prune** | TS | unused exports only | unused files, unused deps, local unused vars; **archived/unmaintained upstream** | `npm i -D ts-prune` | `npx ts-prune --error` (TESTED: default `ts-prune` exits **0** even with findings — you MUST pass `--error` or grep output) | Higher than knip — no ignore-file config, only inline `// ts-prune-ignore-next` | Unmaintained (archived on GitHub); knip is its de facto successor |
| **depcheck** | JS/TS | unused `dependencies`/`devDependencies`, missing deps | dynamic `require()`, plugin-style deps (eslint configs, babel presets) loaded by string name — classic false positive source | `npm i -D depcheck` | `npx depcheck` (TESTED: exits 255 on findings) | High on framework-plugin-heavy repos unless `ignores` configured | Stable, low-velocity maintenance |
| **unimported** | JS/TS | unused files not reachable from entry points, unresolved imports | monorepo workspace boundaries need explicit config | `npm i -D unimported` | `npx unimported` | Moderate — needs `.unimportedrc.json` entry/ignore tuning | Stable, low-velocity |
| **madge** | JS/TS | circular imports (module graph cycles) | doesn't catch layer/architecture violations, only cycles | `npm i -D madge` | `npx madge --circular --extensions ts src` (TESTED: exits 1, correctly reported `cycleA.ts > cycleB.ts`) | Low — cycles are unambiguous | Stable |
| **dependency-cruiser** | JS/TS | cycles, layer/boundary violations, orphan modules, forbidden cross-package imports | needs the ruleset written by hand; not enforcing anything out of the box | `npm i -D dependency-cruiser` | `npx dependency-cruiser --config .dependency-cruiser.cjs --output-type err src` (TESTED: exits 1 on the same cycle madge found) | Low once rules written; false positives if `tsConfig`/path aliases aren't wired in (silently mis-resolves imports) | Active, most configurable of the graph tools |
| **eslint-plugin-import** (`no-cycle`, `no-restricted-paths`) | JS/TS | cycles, forbidden cross-directory imports, at lint time (fails fast, IDE-visible) | `no-cycle` is slow on large graphs (resolves every import); duplicate work with madge/dependency-cruiser if both run | `npm i -D eslint-plugin-import` | `eslint . --rule 'import/no-cycle: error'` or via `.eslintrc` | Low-moderate; `no-cycle` has known perf/false-negative edges with re-exports | Stable |
| **eslint-plugin-boundaries** | JS/TS | enforces declared architecture layers (e.g. `features` can't import `app`) | requires modeling the layer taxonomy up front; silent no-op if types aren't tagged | `npm i -D eslint-plugin-boundaries` | `eslint .` with `boundaries/element-types` rule set to `error` | Moderate until element types are fully tagged | Active, smaller community than import plugin |
| **@size-limit/preset-*** | JS/TS | bundle size budget breach (minified+brotli) | doesn't catch source bloat that tree-shakes away; per-entry-point only | `npm i -D size-limit @size-limit/preset-small-lib` | `npx size-limit` (TESTED: exits 1 when a 500 B budget was set on a file that pulls in 23 KB via `lodash`) | Low — it's a hard byte number | Stable, widely adopted (Preact, Redux) |
| **bundlewatch** | JS/TS | bundle size regression vs. base branch, PR comment integration | needs a build step already producing static bundles | `npm i -D bundlewatch` | `bundlewatch --config bundlewatch.config.json` | Low | Stable, lower activity than size-limit |
| **@microsoft/api-extractor** | TS | public API surface changes vs. a checked-in `.api.md` golden file — this is the strongest tool for failure mode #8 | only works cleanly in Rush/rollup-oriented build setups; steep setup cost for non-monorepo projects | `npm i -D @microsoft/api-extractor` | `api-extractor run --local` fails if the rolled-up `.d.ts` differs from the committed API report unless `--local` regenerates it; in CI use `api-extractor run` without `--local` (TESTED equivalent, see below: `tsc --declaration` + `diff` against a committed baseline reproduces the same failure class and exit-1 behavior) | Low — it's a text diff against a golden file | Stable, Microsoft-maintained |
| **are-the-types-wrong** | TS | broken/mismatched type exports across CJS/ESM, `package.json` `exports` map errors | doesn't check runtime correctness, only the type-resolution graph | `npm i -D @arethetypeswrong/cli` | `attw --pack .` (non-zero on problems) | Low | Active |
| **publint** | JS/TS | invalid/misleading `package.json` fields before publish (missing `main`/`types`, wrong `exports`) | packaging-shape only, not code quality | `npm i -D publint` | `npx publint` (non-zero exit on errors) | Low | Active |
| **jscpd** | Universal | literal / renamed-symbol copy-paste blocks above a token/line threshold | **misses semantic duplication** — logic re-implemented with renamed variables in a different order is NOT flagged by default tokenizer (TESTED: two functions doing identical arithmetic with `item`→`value`, `items`→`values` renamed produced **0 clones**; an exact copy with only the function name renamed WAS caught, exit 1, 15% duplication) | `npm i -D jscpd` | `npx jscpd src --min-lines 5 --min-tokens 50 --threshold 0` (TESTED: exits 1 when duplication % > threshold) | Moderate — needs per-language `min-tokens` tuning or trivial boilerplate (getters/setters, generated code) triggers noise | Stable |
| **PMD-CPD** | Universal (Java-first, supports many langs) | same class as jscpd, more languages via one binary | same semantic-duplication blind spot | `brew install pmd` or download release | `pmd cpd --minimum-tokens 75 --dir src --format text --failOnViolation true` | Similar to jscpd | Stable, long-lived (Java ecosystem staple) |
| **semgrep** | Universal | custom AST-pattern rules — can encode org-specific anti-patterns (e.g. "new HTTP client class defined outside `lib/http`") | only catches what you write a rule for; no built-in "this is bloat" ruleset | `pip install semgrep` or `brew install semgrep` | `semgrep --config p/ci --error` (non-zero on findings) | Depends entirely on rule quality — custom rules can have high FP until tuned | Active, well-funded |
| **lizard** | Universal | cyclomatic complexity, function length, parameter count, across many languages in one pass | no dead-code/dependency detection | `pip install lizard` | `lizard -C 10 -L 80 -a 5 --warnings_only src` exits non-zero style via `-C`/CI wrapper (lizard itself always exits 0; wrap with `lizard ... \| grep -q . && exit 1` or use `--CCN` threshold with the `xenon`-style wrapper) | Low on the complexity signal itself, high threshold-tuning needed per codebase age | Stable |
| **scc / tokei** | Universal | LOC/file-count accounting, language breakdown, complexity estimate — the metric a file/LOC *budget* is built on | doesn't itself enforce anything; needs a wrapper script comparing before/after counts | `brew install scc` / `cargo install tokei` | `scc --format json` piped into a budget-comparison script (see failure-mode #9 section) | N/A (measurement, not judgment) | Stable |
| **git-sizer** | Universal | repo bloat at the git-object level: huge blobs, huge trees, too many refs — catches binary/asset bloat AI agents commit (screenshots, node_modules accidentally committed) | doesn't look at source-code bloat, only repo/object shape | `brew install git-sizer` | `git-sizer --threshold 10MiB` (non-zero exit if any metric exceeds threshold) | Low | Stable, maintained by GitHub engineer |
| **vulture** | Python | unused functions/classes/variables/imports via static + whitelist heuristics | high false positives on code only reachable via framework magic (Django models, pytest fixtures, `__all__`-exported public API used by callers outside the analyzed tree) — TESTED: flagged `used()`, a function actually called by other code, as "unused" simply because nothing in the single analyzed file called it and it wasn't in `__all__` | `pip install vulture` | `vulture pkg/ --min-confidence 80` (TESTED: exits 3 on findings; confidence tuning cuts FPs) | High without `--min-confidence` tuning and a `whitelist.py`; moderate once tuned | Stable, low-velocity |
| **ruff** (F401, C901, PLR0913, ERA, TID) | Python | F401 unused import (TESTED, exit 1), ERA001 commented-out code (TESTED, exit 1), C901 excess cyclomatic complexity (TESTED with `max-complexity=3`, caught an 8-deep nested function, exit 1), PLR0913 too-many-args (TESTED, 7 args > 5 default, exit 1), TID251 banned-API imports | doesn't catch cross-file dead code (a function defined and exported but never imported elsewhere — that's vulture/deptry's job) | `pip install ruff` (or `uv tool install ruff`) | `ruff check .` (TESTED: exits 1 on any finding) | Low — Ruff's rules are conservative by design; F401 has near-zero FP, C901/PLR0913 FP rate is a threshold-tuning problem not a detection problem | Extremely active, becoming the Python lint/format default |
| **pyflakes** | Python | subset of ruff's F-series (unused imports/names, undefined names) | superseded in practice by ruff (which reimplements pyflakes' checks and is 10-100x faster) | `pip install pyflakes` | `pyflakes .` (non-zero on findings) | Low | Stable, largely feeds into ruff/flake8 now |
| **deptry** | Python | unused declared deps (DEP002, TESTED: exits 1, flagged `click` added to `pyproject.toml` but never imported), missing deps used-but-undeclared (DEP001), transitive deps used directly (DEP003), misplaced dev deps (DEP004) | can't see deps loaded via plugin/entry-point string names (same blind spot as depcheck) | `pip install deptry` | `deptry .` (TESTED: exits 1 on DEP002) | Low-moderate; needs `per-rule-ignores` for CLI-entry-point/type-stub-only packages | Active, purpose-built for exactly this failure mode |
| **pip-audit** | Python | known CVEs in installed/declared dependencies — catches the *security* half of dependency creep | doesn't judge whether the dependency was necessary in the first place | `pip install pip-audit` | `pip-audit` (non-zero exit on vulnerability found) | Low (CVE match is objective); occasional noise from unfixed advisories on inactive transitive deps | Active, PyPA-maintained |
| **import-linter** | Python | layered-architecture contracts — "package X must not import package Y" (TESTED: `lint-imports` CLI, exit 1, correctly caught `pkg.mod` importing a forbidden `pkg.infra`) | needs the contract hand-written; says nothing if no contract is defined | `pip install import-linter` | `lint-imports` (TESTED — note: **not** `python -m importlinter.cli`, the installed console script is `lint-imports`) | Low — binary yes/no on a stated boundary | Stable, used by real layered-architecture Python codebases |
| **radon** | Python | cyclomatic complexity (`cc`), maintainability index (`mi`), raw metrics | `radon` itself always exits 0 — it's a reporter, not a gate; need `xenon` (same author) or a grep wrapper to fail CI | `pip install radon xenon` | `xenon --max-absolute B --max-modules A --max-average A src` (xenon exits non-zero on threshold breach; TESTED `radon cc -n B` alone: confirmed it only *prints*, exit 0, even flagged functions) | Moderate — complexity thresholds need per-codebase calibration | Stable |
| **mypy --strict** | Python | untyped code, implicit `Any`, unchecked None-handling — not bloat detection per se, but forces explicit interfaces which surfaces over-abstraction (too many `Any`-typed passthrough layers become visible as type noise) | doesn't detect bloat directly, it's a correctness ratchet that makes bloat *harder to hide* | built into `mypy` | `mypy --strict .` (non-zero on any type error) | High initially on untyped legacy code; near-zero once a codebase is strict-clean | Stable |
| **golangci-lint** (unused, dupl, gocyclo, gocognit, depguard) | Go | `unused` = dead code/vars/consts (via staticcheck's U1000 under the hood), `dupl` = copy-paste, `gocyclo`/`gocognit` = complexity, `depguard` = banned-import enforcement | doesn't see reflection-loaded code; `dupl` shares jscpd's semantic-duplication blind spot | `brew install golangci-lint` | `golangci-lint run` (TESTED: `brew install golangci-lint` [v2.14.0], ran default config against the scratch Go project's dead `unused()` function — `main.go:9:6: func unused is unused (unused)`, exit 1) | Low-moderate, `dupl`'s threshold needs tuning like jscpd | Very active, the Go community default |
| **staticcheck (U1000)** | Go | unused functions/types/vars across the whole build graph (TESTED: `go install honnef.co/go/tools/cmd/staticcheck@latest`, ran against a file with a genuinely dead `unused()` function, exit 1, correctly reported `U1000`) | doesn't see code only reachable via reflection/plugin loading | `go install honnef.co/go/tools/cmd/staticcheck@latest` | `staticcheck ./...` (TESTED: exit 1) | Low — Go's whole-program compilation makes dead-code analysis unusually reliable vs. dynamic languages | Stable, widely embedded inside golangci-lint |
| **go mod tidy -diff** | Go | stale/unused entries in `go.mod`/`go.sum` (TESTED: added an unused `require github.com/pkg/errors` to `go.mod`, ran `go mod tidy -diff`, exit 1, printed the exact diff that would remove it; a tidy `go.mod` gave exit 0) | doesn't check whether a *used* dependency was actually necessary vs. reimplementable in ~20 lines — that's a human call | built into `go` toolchain (Go 1.23+) | `go mod tidy -diff` (TESTED, exits 1 on drift, prints unified diff, changes nothing — safe for CI) | Near-zero — it's checking a derived file against its own generator | Stable, first-party |
| **go-arch-lint** | Go | declared architecture-layer violations (like dependency-cruiser for Go) | needs a hand-written `.go-arch-lint.yml` component map | `go install github.com/fe3dback/go-arch-lint@latest` | `go-arch-lint check` (non-zero exit on violation) | Moderate until component boundaries fully modeled | Smaller community, actively maintained |
| **OpenSSF Scorecard** | Universal (repo-level) | supply-chain hygiene proxies: branch protection, dependency pinning, SAST presence, fuzzing, token permissions — not code bloat, but dependency-creep-adjacent (flags unpinned/unreviewed dependency updates) | says nothing about code-level bloat | `go install github.com/ossf/scorecard/v5@latest` or GitHub Action | `scorecard --repo=<repo> --checks=Pinned-Dependencies` with a score threshold check in a wrapper script | N/A (advisory score, not a hard gate by default) | Active, CNCF/OpenSSF-backed |

---

## The 12 AI-bloat failure modes and their mechanical checks

### 1. Agent creates a new file when it should have edited an existing one

**Detection method:** no tool detects author *intent*; the mechanical proxy is content-similarity
of the newly added file against the existing tree, using the same clone-detection engine as
duplicate-logic detection (jscpd), scoped to just the diff's added files vs. the whole repo.

**Exact command (TESTED mechanism, UNTESTED as a packaged script):**
```bash
# list files added in this PR
NEW_FILES=$(git diff --name-only --diff-filter=A origin/main...HEAD)
# run jscpd across the new files + the existing tree; if a new file is >50% duplicate
# of something that already existed, fail.
npx jscpd $NEW_FILES src --min-lines 5 --min-tokens 30 --threshold 0 || exit 1
```
The clone-detection primitive here is the same jscpd invocation TESTED above (confirmed it
catches literal/renamed-symbol duplication at exit 1, 15% duplication on a contrived pair).
Wiring it to "new files only" is UNTESTED as an assembled script but uses only tested primitives.

**Tuning notes:** raise `--min-tokens` on codebases with lots of legitimately short files. Shares
failure mode #5's structural miss (renamed-variable duplication is invisible to token clone
detection), so pair with a cheap co-occurrence flag: a PR that both adds a file and touches an
existing file in the same directory is the actual smell worth a human look.

**Label: PARTIALLY TESTED** (clone-detection primitive tested; the "new-file-only" wrapper is
assembled from tested pieces but not run end-to-end as a script).

---

### 2. Agent adds a dependency for something the stdlib/existing deps already do

**Detection method:** dependency-hygiene tools (depcheck/deptry/`go mod tidy -diff`) only catch
*unused* deps, not *unnecessary but used* ones. The mechanical proxy that actually exists: a
**allowlist/denylist gate on `package.json`/`pyproject.toml`/`go.mod` diffs** that fails CI when a
new dependency is added without matching an approved list, forcing a human decision at PR time
instead of post-hoc detection.

**Exact command (TESTED building blocks, script UNTESTED end-to-end):**
```bash
# JS/TS: fail if package.json's dependency set grew without an update to an allowlist file
git diff origin/main...HEAD -- package.json | grep -E '^\+\s+"[a-zA-Z0-9@/_-]+":' \
  | grep -vFf .allowed-new-deps.txt && { echo "new dependency not in .allowed-new-deps.txt"; exit 1; }
exit 0
```
```bash
# Python: deptry catches the "unused" half mechanically (TESTED above, DEP002, exit 1).
# For the "unnecessary" half, pair with a stdlib-shadow denylist via ruff's TID251:
# pyproject.toml: [tool.ruff.lint.flake8-tidy-imports.banned-api]
# "six" = {msg = "Python 3 stdlib covers this; remove the dependency."}
ruff check --select TID251 .
```
**What it MISSES:** nothing mechanical can know a new dependency duplicates 20 lines of stdlib
logic — that needs a human or LLM-judge step (see Honest Limitations). The gate only converts
"silent addition" into "explicit, reviewed addition." This is a live pattern, not a sketch:
Traefik's and Prometheus's `.golangci.yml` both `depguard`-deny `github.com/pkg/errors` with
`desc: "Use 'errors'/'fmt' instead"` (verbatim in Real Configs below) — the Go equivalent, already
shipping in two major repos.

**Label: PARTIALLY TESTED** (deptry DEP002 and ruff TID251 mechanics TESTED individually; the
allowlist-diff wrapper is UNTESTED as an assembled script; the Go depguard pattern is a cited real
config, not run in this session).

---

### 3. Agent writes an abstraction/interface used exactly once

**Detection method:** static analysis of interface/abstract-class declarations cross-referenced
against their implementer/consumer count. No off-the-shelf tool ships this as a named rule; it is
assembled from knip/ts-prune's exported-symbol graph (which already computes reference counts)
plus a threshold filter.

**Exact command (TESTED primitive, threshold filter UNTESTED):**
```bash
# knip reports exported types/interfaces with a reference count; grep the "used X times" style
# output isn't built in, so use dependency-cruiser's metrics mode instead:
npx dependency-cruiser --output-type metrics src | jq '.modules[] | select(.instability == 1 and (.dependents | length) <= 1)'
```
For Python, a simple AST script counting `class Foo(Protocol)`/`class Foo(ABC)` definitions
against `Foo(` instantiation/subclass sites in the repo (grep-based, cheap):
```bash
python3 - <<'EOF'
import ast, glob, collections
defs, uses = {}, collections.Counter()
for f in glob.glob("**/*.py", recursive=True):
    tree = ast.parse(open(f).read(), filename=f)
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and any(
            (getattr(b, "id", "") in ("ABC", "Protocol")) for b in n.bases
        ):
            defs[n.name] = f
        if isinstance(n, ast.Name):
            uses[n.id] += 1
single_use = [name for name in defs if uses[name] <= 1]
if single_use:
    print("Interfaces defined but referenced <=1 time:", single_use)
    exit(1)
EOF
```
**What it MISSES:** an interface with exactly two implementations where one is a test double is
legitimately single-purpose and this will false-positive on it; needs a `# noqa`-style escape
hatch. Also misses interfaces used once *today* but designed for a near-certain second
implementation (a real future extension point) — mechanical tools cannot distinguish premature
abstraction from deliberate seams; this is judgment territory, flagged not blocked.

**Label: UNTESTED** (dependency-cruiser metrics mode not run in scratch environment this session;
the Python AST script is a design sketch following the same pattern as the TESTED assertion-free
detector below, but was not executed).

---

### 4. Agent leaves dead code, unused imports, commented-out blocks

**Detection method:** this is the best-covered failure mode — direct, mature tooling exists per
language.

**Exact commands (ALL TESTED):**
```bash
# JS/TS
npx knip                 # unused files/exports/deps — TESTED, exit 1 on 5 findings
npx ts-prune --error     # unused exports only, needs --error flag — TESTED, exit 1

# Python
ruff check --select F401,ERA .   # unused imports + commented-out code — TESTED, exit 1 on both
vulture pkg/ --min-confidence 80 # unused functions/classes — TESTED, exit 3

# Go
staticcheck ./...        # U1000 unused code — TESTED, exit 1
```
**What it MISSES:** knip/ts-prune only see cross-*module* dead code (exported but never
imported); they do not flag an unused *local* variable inside a function body — that's
`eslint no-unused-vars`/`ruff F841`'s job, not a dead-code tool's. Vulture's confidence score is
necessary because it cannot see framework-magic call sites (Django views, pytest fixtures,
plugin entry points) — TESTED false positive: it flagged `used()`, a genuinely-called function,
as unused at 60% confidence purely because nothing in the single-file scratch project called it
outside that file's own analysis scope; `--min-confidence 80`+ or an explicit `whitelist.py`
suppresses these.

**Label: TESTED** (all four commands run against planted violations in this session, all
correctly caught, all exit non-zero).

---

### 5. Agent duplicates near-identical logic instead of reusing

**Detection method:** token-based clone detection (jscpd/PMD-CPD).

**Exact command:**
```bash
npx jscpd src --min-lines 5 --min-tokens 50 --threshold 0   # TESTED: exit 1, 15% duplication, on identical-body/renamed-function-name pair
```
**What it MISSES — this is the single most important negative result in this research:**
jscpd's default tokenizer did **not** flag two functions implementing identical logic
(iterate, filter positive, sum) with only the loop-variable names changed (`item`/`total` vs.
`value`/`total`). Zero clones reported, 0% duplication, exit 0. This is exactly the shape of
duplication an AI agent produces most often — it doesn't copy-paste, it re-derives the same
logic with fresh variable names because it didn't search for an existing implementation first.
Token-based CPD tools are tuned for literal copy-paste (refactor extraction targets), not
semantic equivalence.

**Mitigation that is actually mechanical:** none of the surveyed tools solve semantic-duplicate
detection reliably. The closest real lever is `semgrep` with a hand-written structural pattern
per known-duplicated shape (`pattern: for $X in $Y: if $X > 0: $TOTAL += $X` matches regardless
of variable names) — but this requires a human to notice the duplication once and then encode it,
which is retroactive, not preventive.

**Label: TESTED** (both the positive case — literal/renamed-function clone caught, exit 1 — and
the negative case — semantic clone with renamed variables missed, exit 0 — were run and observed
directly).

---

### 6. Agent writes redundant comments restating the code

**Detection method:** no mainstream tool has a "comment says nothing the code doesn't already
say" check — this requires semantic comparison of the comment text against the following
statement, which is an LLM-judgment task, not a static-analysis one. The closest mechanical
proxies:
- `eslint` rule `capitalized-comments` / a custom `no-restricted-syntax` regex rule flags
  comments matching common restatement patterns (`// increment X`, `// return the result`,
  `// set X to Y`) immediately followed by code doing exactly that pattern.
- Ratio-based proxy: comment-density outlier detection — flag files where comment-to-code line
  ratio exceeds N standard deviations from the repo median (catches over-commented files as a
  batch, not per-line).

**Exact command (UNTESTED, sketch only):**
```bash
# crude ratio heuristic via scc
scc --format json | jq '.[] | select(.Lines > 0) | {Name, ratio: (.Comment / .Code)}' \
  | jq 'select(.ratio > 0.6)'   # flag files >60% comment-to-code
```
**What it MISSES:** everything semantic. This is the clearest example in the whole survey of "no
tool exists" — Part G says cut prose rules that never reject anything; this one is kept only
because it ships a runnable (if weak) ratio check, and is explicitly flagged as the weakest
mechanism in this document.

**Label: UNTESTED, and honestly weak** — recommend LLM-as-reviewer for this failure mode (see
Honest Limitations), not a lint rule.

---

### 7. Agent adds a README/doc nobody asked for

**Detection method:** a diff-scoped file-pattern gate — fail CI if a PR adds a new
`*.md`/`*.rst`/`README*` file outside an explicit allowlist of doc directories, unless the PR is
itself labeled/described as a docs change.

**Exact command (TESTED mechanism — file-pattern matching against `git diff` — assembled here,
not previously run as a unit but built from plain `git`/`grep`, so it is trivially reliable):**
```bash
git diff --name-only --diff-filter=A origin/main...HEAD \
  | grep -E '\.(md|rst)$|^README' \
  | grep -vE '^(docs/|CHANGELOG\.md$)' \
  && { echo "New doc file added outside docs/. Requires explicit docs: label or move to docs/."; exit 1; }
exit 0
```
Verified the grep/diff-filter mechanics directly:
```bash
$ git diff --name-only --diff-filter=A HEAD~1
src/newfile.md
```
This pattern was exercised against the scratch git repo's `--diff-filter=A` output during the
reformat-inflation testing (see failure mode #11) and confirmed to correctly isolate added files.

**What it MISSES:** a legitimately-needed README placed inside `docs/` sails through with zero
signal on whether it was *asked for* — the gate only catches location, not necessity. Pair with a
repo-wide budget: `find . -name '*.md' | wc -l` compared against a committed baseline count,
failing if it grows without a corresponding entry in a `docs-manifest.txt` that a human curates.

**Label: PARTIALLY TESTED** (the underlying `git diff --diff-filter=A --name-only` mechanic was
exercised and confirmed in this session's git testing; the full grep-gate script as written was
not executed end-to-end).

---

### 8. Agent silently widens a public API surface

**Detection method:** emit the public type surface (`.d.ts` for TS, could be paired with
`api-extractor`'s `.api.md` golden file for a more complete version including JSDoc), diff it
against a committed baseline, fail on any addition/change.

**Exact command (TESTED, full working example):**
```bash
npx tsc --declaration --emitDeclarationOnly --outDir /tmp/api-baseline src/index.ts src/helper.ts
diff /tmp/api-baseline/helper.d.ts api-snapshots/helper.d.ts
```
Ran this exact mechanism against the scratch project: committed a baseline `.d.ts`, then added
`export function newlyExportedInternalDetail()` to `src/helper.ts`, re-emitted, and diffed:
```
6a7
> export declare function newlyExportedInternalDetail(): string;
```
`diff` exited 1. This is the same golden-file mechanism `@microsoft/api-extractor`'s `.api.md`
uses (run `api-extractor run` without `--local` in CI — it fails the build if the rolled-up API
doesn't match the committed report), tested here via plain `tsc` + `diff` because it required no
extra setup.

**For Python:** the equivalent is `griffe check` (compares two versions of a package's public
API and reports breaking/additive changes) or a simpler `python -c "import pkg; print(sorted(pkg.__all__ or dir(pkg)))"` diffed against a committed snapshot — UNTESTED here.

**What it MISSES:** internal-but-exported-for-tests symbols will false-positive every time
(needs a `/** @internal */` JSDoc convention that api-extractor understands natively but the
plain `tsc`+`diff` version does not — a real gap in the cheap version vs. the real tool).

**Label: TESTED** (full round-trip: baseline emit, mutation, re-emit, diff, non-zero exit,
observed directly).

---

### 9. Agent grows the bundle / binary / install size

**Detection method:** byte-budget assertion tools (size-limit for JS bundles, a `du`/`scc`-based
wrapper for install size, binary-size diff for Go).

**Exact command (TESTED):**
```json
// package.json
"size-limit": [{ "path": "src/index.ts", "limit": "500 B" }]
```
```bash
npx size-limit
```
Ran this against the scratch project with a deliberately tiny 500 B budget on a file that pulls
in `lodash`: output reported "Package size limit has exceeded by 22.58 kB... Size: 23.08 kB",
and — important gotcha, same class of bug as depcheck/ts-prune above — **piping the command
through `| tail` silently ate the exit code**; run it unpiped or capture `$?` immediately:
confirmed direct invocation exits 1.

**Go binary size:**
```bash
go build -o /tmp/bin ./... && ls -l /tmp/bin | awk '{print $5}'
# compare against a committed budget file; fail if grown beyond threshold
```
UNTESTED as a full script (build ran fine in the scratch Go project; the budget-diff wrapper
around it was not assembled).

**Install size (node_modules bloat from a new transitive dependency):**
```bash
du -sh node_modules | awk '{print $1}'   # compare pre/post npm install in CI, fail on delta > N MB
```
UNTESTED here.

**What it MISSES:** byte budgets need per-project calibration and go stale as the app
legitimately grows — a hard 500 B limit (as used in this test) is only sane for a
zero-dependency micro-library; real repos (Preact, Redux) set budgets in the tens of KB, ratchet
them down over time, and treat a bump as a deliberate PR, not a bug.

**Label: TESTED** (size-limit, full round trip with real byte numbers and confirmed exit code).

---

### 10. Agent writes tests that assert nothing (or mock everything so the test can't fail)

Covered in depth in its own section below (**Mutation testing**). Summary here:

**Static detection (TESTED):** a ~30-line Python AST script flagging any `test_*` function with
no `assert` statement and no `assert*`-prefixed call:
```bash
python3 assertionless_check.py
# tests/test_mod.py:3: test_used_runs_without_asserting has no assert/expect call
# 1 assertion-free test(s) found
# exit 1
```
Ran exactly this against a deliberately assertion-free test (`used()` called but never checked)
— caught it, exit 1. JS/TS equivalent is a real, shipped ESLint rule:
`eslint-plugin-jest`'s `jest/expect-expect` — TESTED directly: installed `eslint-plugin-jest`,
wrote a flat `eslint.config.mjs` scoping the rule to `tests/**/*.test.js`, and ran it against
`test("does something but asserts nothing", () => { const x = 1 + 1; })`. Output: `error Test has
no assertions jest/expect-expect`, exit 1.

**Dynamic/real proof (mutation testing, TESTED at small scale):** `mutmut` on the same scratch
package. `mutmut run` generated 8 mutants across `pkg/mod.py`; result: **2 killed, 6 survived
(no covering test)** — a 25% mutation score, despite `coverage.xml` earlier reporting 100% *line*
coverage on the same code. That gap is the entire point of mutation testing: line coverage proved
the code executed; it did not prove any test would fail if the logic were wrong.

**Label: TESTED** (both the static AST check and the mutmut run were executed and produced the
numbers quoted above).

---

### 11. Agent reformats untouched lines, inflating the diff

**Detection method:** format-normalize both the pre-image and post-image of a changed file
through the project's canonical formatter, then diff the *normalized* outputs instead of the raw
git diff. If the normalized diff is materially smaller than the raw diff, the gap is pure
reformatting noise.

**Exact command (TESTED, full working example):**
```bash
git show origin/main:src/index.ts > /tmp/old.ts
cp src/index.ts /tmp/new.ts
npx prettier --parser typescript /tmp/old.ts > /tmp/old.fmt.ts
npx prettier --parser typescript /tmp/new.ts > /tmp/new.fmt.ts
diff /tmp/old.fmt.ts /tmp/new.fmt.ts
```
Ran this against a scratch commit that both (a) swapped every double quote for a single quote
(pure cosmetic) and (b) made one genuine logic change (added a third parameter). Result: after
passing both versions through Prettier, the quote-style churn fully canceled out (Prettier
normalizes both to the same quote style) and the normalized diff isolated exactly the 2 real
logic lines — **except** inside a comment (`// return 'dead';`), where Prettier does not touch
string content, so that line's cosmetic change survived normalization. That's a genuine,
observed limitation: formatters don't normalize comment *contents*, only code structure, so this
technique has a blind spot on comment-only cosmetic churn.

**A cruder but simpler CI-only proxy** (Python, catches the whitespace-only subset):
```bash
git diff -w --numstat   # ignores whitespace-only changes; compare its line count to plain `git diff --numstat`
```
This only catches whitespace/indentation reformatting, not quote-style/formatter-preference
churn — confirmed it does NOT catch the quote-swap case in this session's test (both raw and
`-w` numstat reported the same 6/6 changed lines), which is why the formatter-normalize technique
above is the more complete check.

**What it MISSES:** any reformatting inside comments/strings, and any formatter that isn't
idempotent/deterministic on the exact same input twice.

**Label: TESTED** (both techniques run against a planted mixed cosmetic+real-change commit; the
formatter-normalize approach correctly isolated the real change; the `git diff -w` proxy was
confirmed to miss the non-whitespace cosmetic churn, an honest negative result).

---

### 12. Agent introduces an import cycle or crosses a layer boundary

**Detection method:** graph-based cycle detection (madge, dependency-cruiser) plus explicit
layer-boundary rules (dependency-cruiser custom rules, eslint-plugin-boundaries, Python
import-linter contracts, Go depguard/go-arch-lint).

**Exact commands (ALL TESTED):**
```bash
npx madge --circular --extensions ts src
# ✖ Found 1 circular dependency! 1) cycleA.ts > cycleB.ts   — exit 1

npx dependency-cruiser --config .dependency-cruiser.cjs --output-type err src
# error no-circular: src/cycleA.ts → src/cycleB.ts → src/cycleA.ts   — exit 1

lint-imports
# mod cannot import from a fake infra layer BROKEN — exit 1
```
The `.dependency-cruiser.cjs` rule used (verbatim, as tested):
```js
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "Import cycles make module boundaries meaningless.",
      from: {},
      to: { circular: true },
    },
  ],
  options: { tsPreCompilationDeps: true, tsConfig: { fileName: "tsconfig.json" } },
};
```
The `.importlinter`-style contract used (verbatim, as tested, in `setup.cfg`):
```ini
[importlinter]
root_package = pkg

[importlinter:contract:1]
name = mod cannot import from a fake infra layer
type = forbidden
source_modules = pkg.mod
forbidden_modules = pkg.infra
```
**What it MISSES:** all three tools need the boundary/cycle rule to exist before it can be
enforced — a fresh repo with no rules gets zero protection on day one. Also, `dependency-cruiser`
silently mis-resolves imports if `tsConfig`/path aliases aren't wired in — confirmed during
testing that it required an actual `typescript` install (not just present in `package.json`,
must be in `node_modules`) to resolve `.ts` extensions correctly; without it, it emitted a
`missing-typescript-transpiler` warning and undercounted modules (ran with 0 modules cruised
before the fix).

**Label: TESTED** (madge, dependency-cruiser, and import-linter all run against planted
violations — an import cycle and a layer violation — all caught, all exit non-zero).

---

## Real configs from major repos (verbatim, cited)

Fetched from `raw.githubusercontent.com` (main/master branch as of 2026-09-28) via a dedicated
research pass, not reconstructed from memory. Where a real verbatim example could not be found
in a flagship repo after genuine search, that is stated explicitly rather than invented, per
Part G rule 5.

**Knip — `TanStack/router@main:knip.json`**:
`{ "$schema": "https://unpkg.com/knip@5/schema.json", "ignoreWorkspaces": ["examples/**"] }`.
Flagship repos keep the config minimal and put the strictness in the invocation, not the file —
see the TanStack/query CI example below.

**ts-prune — `trpc/trpc@ec0b0a4:package.json`**
(https://raw.githubusercontent.com/trpc/trpc/ec0b0a47ab6c6ffabcb2ba6b80fa08c1410145a9/package.json):
```json
"lint-prune": "! ts-prune | grep -v \"used in module\" | grep -v rpc | grep -v observable | grep -v http | grep -v __fixtures__ | grep -v __generated__ | grep -v heyapi | grep -v 'openapi/test/routers' | grep -v 'openapi/test/scripts'",
```
Confirms this research's own finding: ts-prune exits 0 regardless of output, so tRPC inverts a
filtered grep's exit code (`!`) to actually fail the script — the same gotcha TESTED above.

**madge — `mermaid-js/mermaid@develop:packages/mermaid/package.json`**
(https://raw.githubusercontent.com/mermaid-js/mermaid/develop/packages/mermaid/package.json):
```json
"checkCircle": "npx madge --circular ./src",
```
Same pattern independently verified at `web-scrobbler/web-scrobbler` (`"lint:circular": "madge --circular src"`) and `HubSpot/hubspot-cli` (`"circular-deps": "yarn madge --circular ."`).

**dependency-cruiser — `microsoft/FluidFramework@main:packages/runtime/container-runtime/.dependency-cruiser.cjs`**:
```js
forbidden: [{
  name: "summarizer-delay-loaded-not-statically-imported",
  severity: "error",
  comment: "The summarizer must stay dynamically importable so a bundler can split it into its " +
    "own chunk that non-summarizer clients never download. [...] A new static value import " +
    "would pull it back into the initial chunk and silently defeat the delay-load.",
  from: { pathNot: ["^src/summary/summaryDelayLoadedModule/", "^src/summary/index\\.ts$"] },
  to: { path: "^src/summary/summaryDelayLoadedModule(/|$)", dependencyTypesNot: ["dynamic-import"] },
}],
```
A bundle-size boundary rule, not an architecture-layer one — stops a static import from silently
defeating code-splitting. A different anti-bloat use of the tool than the cycle rule TESTED above.

**eslint-plugin-import `no-cycle` — `jquery/jquery@main:eslint.config.js`**
(https://raw.githubusercontent.com/jquery/jquery/main/eslint.config.js):
```js
rules: {
  ...jqueryConfig.rules,
  "import/extensions": [ "error", "always" ],
  "import/no-cycle": "error",
}
```
Counter-example worth citing for the FP-rate claim above: `Shopify/flash-list` sets
`"import/no-cycle": "off"` in `.eslintrc.js` — real evidence the rule is costly enough on large
graphs that a major repo disables it in favor of madge/dependency-cruiser.

**eslint-plugin-import `no-restricted-paths` — `nytimes/kyt@master:packages/eslint-config-kyt/base.js`**:
`'import/no-restricted-paths': ['error', { zones: [{ target: './src', from: './src/server' }] }]`
— prevents client code importing server code, the classic bleed-into-client-bundle guard.

**eslint-plugin-boundaries — `rainbow-me/browser-extension@62ea10c:.eslintrc.js`**, trimmed:
```js
settings: { 'boundaries/elements': [
  { type: 'entry-popup', pattern: 'src/entries/popup/**' },
  { type: 'core-keychain', pattern: 'src/core/keychain/**' },
]},
rules: { 'boundaries/element-types': ['error',
  { default: 'disallow', rules: [
      { from: ['entry-popup'], allow: ['entry-background'] },
      { from: ['core-keychain'], allow: ['core-state'] },
  ]},
]}
```
`default: 'disallow'` is load-bearing — deny-by-default, every legal edge allow-listed explicitly.

**@size-limit/preset-small-lib — `ai/nanoid@main:package.json`**
(https://raw.githubusercontent.com/ai/nanoid/main/package.json):
```json
"size-limit": [
  { "name": "nanoid", "import": "{ nanoid }", "limit": "127 B" },
  { "name": "customAlphabet", "import": "{ customAlphabet }", "limit": "219 B" },
  { "name": "urlAlphabet", "import": "{ urlAlphabet }", "limit": "58 B" }
]
```
Budgets are per-named-import, in single-to-triple-digit *bytes*, enforced by
`"test:size": "pnpm clean && size-limit"`. Note: Preact and Redux Toolkit — commonly cited as
size-limit examples — no longer carry an inline `size-limit` array; Preact has moved to
`preactjs/compressed-size-action` in CI instead. Don't cite them for this without re-checking.

**bundlewatch — `clerk/javascript@main:packages/clerk-js/bundlewatch.config.json`**
(https://raw.githubusercontent.com/clerk/javascript/main/packages/clerk-js/bundlewatch.config.json):
```json
{
  "files": [
    { "path": "./dist/clerk.js", "maxSize": "554KB" },
    { "path": "./dist/clerk.browser.js", "maxSize": "81KB" },
    { "path": "./dist/clerk.legacy.browser.js", "maxSize": "124.5KB" },
    { "path": "./dist/vendors*.js", "maxSize": "7KB" }
  ]
}
```
Quarter-KB precision (`124.5KB`) — thresholds ratcheted just above current measured size.

**Bundle-size CI gate — `clerk/javascript@main:.github/workflows/ci.yml`**, job `bundle-size`,
with its own inline comment explaining *why* it's wired this way:
```yaml
  bundle-size:
    needs: [check-permissions, build-packages]
    name: Bundle size
    steps:
      # No continue-on-error: an over-budget chunk fails this job, which is the gate.
      # Enforcement rides on this job's exit code, not the `bundlewatch` commit status
      # (which collides across packages and can be masked by a sibling's pass).
      - name: Check size using bundlewatch
        run: pnpm turbo bundlewatch $TURBO_ARGS
```
Lesson in the comment: a shared GitHub commit status can be silently overwritten by a sibling
package's passing check in a monorepo — the gate must be the CI job's own exit code.

**api-extractor — `microsoft/fluentui@master:scripts/api-extractor/api-extractor.common.json`**:
```json
{
  "apiReport": { "enabled": true },
  "docModel": { "apiJsonFilePath": "<projectFolder>/dist/<unscopedPackageName>.api.json", "enabled": true },
  "dtsRollup": { "enabled": true },
  "mainEntryPointFilePath": "<projectFolder>/lib/index.d.ts"
}
```
`apiReport.enabled: true` is the gate: it forces a committed `.api.md` snapshot, so any public
API surface change (failure mode #8) must appear in the PR diff and be reviewed — the real-tool
version of the `tsc --declaration` + `diff` technique TESTED earlier in this document.

**publint + are-the-types-wrong — `TanStack/query@main:packages/query-core/package.json`**:
`"test:build": "publint --strict && attw --pack"`.

**The CI YAML that actually fails a build on dead code — `TanStack/query@main:.github/workflows/pr.yml`**,
run step `run: pnpm run test:pr`, resolving through root `package.json`:
```json
"test:pr": "nx affected --targets=test:sherif,test:knip,test:docs,test:eslint,test:lib,test:types,test:build,build",
"test:knip": "knip && knip --strict --include unlisted --no-gitignore",
```
No `continue-on-error` anywhere, so a non-zero `knip` exit fails `nx affected` → fails the job.
The double invocation is deliberate: plain `knip` for unused files/exports, then
`--strict --include unlisted --no-gitignore` to also catch undeclared dependencies — this is the
diff-scoped-via-`nx-affected` pattern this document recommends below, seen live gating real PRs.

**Dependency-addition policy — `ProjectMirador/mirador@master:CONTRIBUTING.md`**, section
"Adding dependencies" (https://github.com/ProjectMirador/mirador/blob/master/CONTRIBUTING.md),
verbatim:
> Careful consideration should be given when adding software dependencies to Mirador. During the
> code review process, new dependencies may be evaluated on the following considerations:
> - added size of the dependency
> - whether or not that dependency is maintained and tested
> - how the dependency may interact with Mirador embedded in other environments
>
> As a general rule, dependencies added should not be committed directly, but should instead use
> a package manager to require the dependency.

Prose, not a command — the exact real-world shape the allowlist gate under failure mode #2 is
meant to mechanize: Mirador enforces this only via human review today, the honest baseline every
mechanical gate here is trying to reduce reliance on.

*JS/TS gaps (Part G rule 5):* no `.depcheckrc` found on the research target list (depcheck lost
adoption to knip at flagship tier — the cited example is a smaller repo); no
`eslint-plugin-boundaries` flagship adopter found either.

### Python

**Ruff rule families — `litestar-org/litestar@main:pyproject.toml`**
(L390-436, https://raw.githubusercontent.com/litestar-org/litestar/main/pyproject.toml):
```toml
lint.select = [
  "A", "B", "BLE", "C4", "C90", "D", "DJ", "DTZ", "E", "ERA", "EXE", "F",
  "TC", "TID", "UP",   # …and more
]
[tool.ruff.lint.mccabe]
max-complexity = 12
```
TID banned-api, real and specific — `pandas-dev/pandas@main:pyproject.toml` (L406-424):
```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"pytest.warns".msg = "Use tm.assert_produces_warning instead of pytest.warns"
"os.remove".msg = "Do not use os.remove"
"datetime.datetime.now".msg = "Use a fixed datetime, not the current time (GH#44341)"
```
**Honest finding on PLR0913:** both pandas and Home Assistant `select` the `PL` family and then
explicitly `ignore` PLR0913 (pandas `pyproject.toml` L287; Home Assistant `pyproject.toml` L738,
`"PLR0913", # Too many arguments to function call"`) — no flagship repo enforces it. The
too-many-args check exists in the tool; real maintainers judged it too noisy to gate on.

**vulture — real enforcement wrapper, `pandas-dev/pandas@main:scripts/run_vulture.py`**, invoked
from `.pre-commit-config.yaml`:
```python
for item in Vulture().get_unused_code(min_confidence=100):
    if item.typ == "unreachable_code":
        print(item.get_report()); ret = 1
sys.exit(ret)
```
Pandas gates at `min_confidence=100`, only on `unreachable_code` — narrower than this document's
own `--min-confidence 80` test: direct evidence of a flagship repo trading recall for zero noise.

**deptry — real adopter, `mandiant/capa@master:pyproject.toml`** (L172-235):
```toml
[tool.deptry]
extend_exclude = ["sigs", "tests", "web"]
known_first_party = ["binaryninja", "flirt", "ghidra", "idapro"]

[tool.deptry.per_rule_ignores]
DEP002 = ["build", "bump-my-version", "deptry", "mypy"]
```

**import-linter in real production use — `PostHog/posthog@master:pyproject.toml`** (L550+):
```toml
[tool.importlinter]
root_packages = ["products", "owners_yaml"]
include_external_packages = true

[[tool.importlinter.contracts]]
name = "presentation must use facade"
type = "forbidden"
source_modules = ["products.*.backend.presentation"]
forbidden_modules = ["products.*.backend"]
allow_indirect_imports = true
```
PostHog's CI (`ci-backend.yml` L1489) runs this as `lint-imports` directly — a required job step,
the same command TESTED against the planted violation earlier in this document.

**radon/xenon gate — `aws-powertools/powertools-lambda-python@develop:Makefile`** (L71-75):
```make
complexity-baseline:
	poetry run radon mi aws_lambda_powertools
	poetry run xenon --max-absolute C --max-modules A --max-average A aws_lambda_powertools
```

**mypy strict — `encode/httpx@master:pyproject.toml`**: `[tool.mypy] ignore_missing_imports =
true` / `strict = true`, with `[[tool.mypy.overrides]] module = "tests.*"` relaxing only
`disallow_untyped_defs` for test code.

**pip-audit in CI — `crytic/slither@master:.github/workflows/pip-audit.yml`**:
```yaml
      - name: Run pip-audit
        uses: pypa/gh-action-pip-audit@1220774d901786e6f652ae159f7b6bc8fea6d266 # v1.1.0
        with: { inputs: requirements.txt }
```
No `allow-failure` — a vulnerable dependency fails the build.

### Go

**`.golangci.yml`, deny-by-default with rationale — `traefik/traefik@master:.golangci.yml`**:
```yaml
linters:
  default: all
  disable:
    - cyclop      # duplicate of gocyclo
    - dupl        # Too strict
    - gocognit    # Too strict
    - gocyclo     # FIXME must be fixed
    - maintidx    # kind of duplicate of gocyclo
    - nestif      # Too many false-positive.
  settings:
    gocyclo:
      min-complexity: 14
```
This is the single best documented false-positive-suppression example in this whole survey: a
major repo enabling *every* linter by default and then justifying each individual disable inline
— exactly the "problem it solves" discipline Part G demands, applied by the repo's own
maintainers.

**depguard denying a dependency stdlib already covers — `traefik/traefik@master:.golangci.yml`**:
```yaml
depguard:
  rules:
    main:
      deny:
        - pkg: github.com/pkg/errors
          desc: Should be replaced by standard lib errors package
```
Independently confirmed at `prometheus/prometheus@main:.golangci.yml` (same `pkg/errors` denial,
plus `io/ioutil` → `"Use corresponding 'os' or 'io' functions instead."`) — two unrelated major
repos converging on the identical rule is real, running, CI-enforced evidence of exactly the
mechanism this document sketches under failure mode #2, not a design sketch.

**depguard as Go's layer-boundary tool — `grafana/grafana@main:.golangci.yml`** (L35-75):
```yaml
depguard:
  rules:
    apimachinery:
      files: ['**/pkg/apimachinery/*', '**/pkg/apimachinery/**/*']
      allow: [github.com/grafana/grafana/pkg/apimachinery]
      deny: [{ pkg: github.com/grafana/grafana/pkg, desc: apimachinery is not allowed to import grafana core }]
```
Per-directory `depguard` is Grafana's Go equivalent of Python's import-linter contracts — no
`go-arch-lint` adoption was found in any major Go repo probed (Kubernetes, Moby, Terraform, Hugo,
Cobra, Prometheus, Grafana, Caddy, Traefik, CockroachDB); the tool's only real config is its own
author's repo. **staticcheck.conf naming U1000 explicitly** —
`tailscale/tailscale@main:staticcheck.conf`: `checks = ["SA*", "-SA1019", "ST1000", "ST1001",
"U1000"] # catch unused code`.

**Dependency hygiene, the real-world pattern (not `go mod tidy -diff`) —
`prometheus/prometheus@main:Makefile.common`** (L228-232):
```makefile
common-unused:
	$(GO) mod tidy
	@git diff --exit-code -- go.sum go.mod
```
`go mod tidy -diff` itself was not found in any surveyed repo — `tidy` then `git diff --exit-code`
is the dominant real pattern and predates the `-diff` flag.

**golangci-lint gating releases — `prometheus/prometheus@main:.github/workflows/ci.yml`** (L344-388):
the `golangci` job (`uses: golangci/golangci-lint-action@…`, `args: --verbose`) is a listed
dependency of `publish_main`/`publish_release` — a lint failure blocks the release job directly,
not just the PR check.

**Python/Go gaps, stated honestly:** ERA (commented-out code) found only in Litestar among
Python repos checked (pandas/pydantic/polars/airflow/Home Assistant don't enable it); radon/xenon
adoption is genuine but narrow (AWS Powertools, not the wider ecosystem); `go-arch-lint` has
effectively zero major-repo adoption; `go mod tidy -diff` was not found anywhere in practice.

---

## Diff-scoped enforcement

**Why whole-repo gates fail on existing codebases:** running `knip`/`vulture`/`ruff check` with
zero tolerance on a codebase that has accumulated years of pre-existing dead code and complexity
violations fails on day one, for code nobody touched, with no path to green. Contributors either
mass-suppress (defeating the tool) or the gate gets disabled. The fix is scoping every check to
the **diff**, not the tree.

**Exact commands:**
```bash
# knip: advisory mode (no exit-code), pipe findings through a diff filter to fail only on
# files changed in this PR
npx knip --no-exit-code --reporter json > knip.json
CHANGED=$(git diff --name-only origin/main...HEAD)
jq -r '.files[]' knip.json | grep -Ff <(echo "$CHANGED") && exit 1 || exit 0
```
```bash
# eslint: only lint changed files, and don't fail on files with zero matches (monorepo-safe)
git diff --name-only --diff-filter=ACMR origin/main...HEAD -- '*.ts' '*.tsx' \
  | xargs -r npx eslint --no-error-on-unmatched-pattern
```
```bash
# diff-cover: gate coverage only on lines changed in this PR, not the whole file/repo — TESTED
coverage run -m pytest -q
coverage xml
diff-cover coverage.xml --compare-branch=$(git merge-base HEAD origin/main) --fail-under=80
```
Ran `diff-cover` exactly this way against the scratch Python repo (two real commits, a
`coverage.xml` from `coverage run` + `coverage xml`, `--compare-branch=<first-commit-sha>`):
correctly scoped the report to only the one line added between commits and printed a per-file
diff-coverage percentage. Confirmed working end-to-end.

**Codecov's "patch" status** (`codecov.yml` → `coverage: status: patch:`) is the hosted
equivalent of diff-cover as a required GitHub status check — UNTESTED here (needs a Codecov
account), but the standard deployment of the same idea: gate the *patch*, not the *project*.

**The general pattern**, applicable to every tool in the matrix above: run the tool in
full/advisory mode (`--no-exit-code`, `--reporter json`, non-failing), intersect its findings'
file list with `git diff --name-only <merge-base>...HEAD`, and only fail CI if the intersection
is non-empty. This lets a large legacy codebase adopt every check in this document immediately,
on new code only, with pre-existing violations grandfathered until touched — the moment someone
edits a file with legacy violations, those become blocking too (a "ratchet," not a one-time
grandfather).

---

## Mutation testing: the assertion-free-test killer

**How it works:** the mutation tool parses source, generates many small semantic mutants (flip a
comparison operator, negate a boolean, change a return value, delete a statement), reruns the
test suite against each mutant, and classifies each as **killed** (a test failed — good) or
**survived** (no test failed — the mutant is undetectable, meaning some code path has no test
that can distinguish correct from wrong behavior). **Mutation score = killed / total mutants.**
This is the only signal in this entire survey that directly proves a test *can* fail — line
coverage only proves a line *executed*.

**Real cost demonstrated in this session:** even a ~20-line Python file with 2 tests took several
real seconds of wall-clock for `mutmut run` to generate + evaluate 8 mutants (one pytest
subprocess per mutant, default single-worker mode). On a real codebase with thousands of
functions, full-suite mutation testing is minutes-to-hours — not viable as a per-PR blocking
gate, matching the well-known industry consensus (Stryker's and PIT's own docs) that mutation
testing must be **scoped to changed files only** to be CI-affordable.

**Scoping to changed files only (the affordable pattern):**
```bash
# mutmut: mutate only files touched in this PR
CHANGED_PY=$(git diff --name-only origin/main...HEAD -- '*.py')
# mutmut's pyproject.toml [tool.mutmut] source_paths accepts a path list;
# regenerate it per-PR from $CHANGED_PY, or use mutmut's own diff-based mode if available in
# the installed version (varies by release — TESTED version 3.x's config schema; the CLI
# surface for path-restriction differs across mutmut major versions, confirmed via the
# "paths_to_mutate is deprecated, rename to source_paths" warning hit in this session)
mutmut run
mutmut results   # TESTED: printed per-mutant "no tests" / killed status
```
```bash
# stryker (JS/TS) — UNTESTED in this session, but its documented mechanism is the direct
# equivalent: stryker.conf supports a `mutate` glob restricted to files in the diff
npx stryker run --mutate "$(git diff --name-only origin/main...HEAD -- '*.ts' | tr '\n' ',')"
```
```bash
# go-mutesting / cosmic-ray (Go/Python alternatives) — UNTESTED here; same diff-scoping pattern
# applies: pass the changed-file list as the mutation target set instead of the whole module.
```
**Threshold recommendation (design, not tested at scale):** gate PRs on mutation score for
*changed lines only* at a modest bar (e.g. 60-70%, not 100% — mutation testing has known
"equivalent mutant" false positives where a mutant is semantically identical to the original and
can never be killed), and run full-repo mutation testing nightly/weekly, not per-PR, tracking the
trend rather than gating on the absolute repo-wide number.

**Label: TESTED at small scale (mutmut, 8 mutants, 2 killed / 6 survived, 25% mutation score
computed by hand from `mutmut results` output); the diff-scoping wrapper and Stryker/go-mutesting
equivalents are UNTESTED design sketches following mutmut's confirmed mechanism.**

---

## Recommended layered stack

### Tier 1 — pre-commit (<5s, local, blocks the commit)
```bash
# JS/TS
npx eslint --fix $(git diff --cached --name-only --diff-filter=ACM -- '*.ts' '*.tsx')
npx prettier --write $(git diff --cached --name-only --diff-filter=ACM -- '*.ts' '*.tsx')

# Python
ruff check --fix .        # TESTED primitive: F401/ERA/C901/PLR0913, exit 1 on unfixable findings
ruff format --check .

# Universal
git diff --cached --name-only --diff-filter=A | grep -E '\.(md|rst)$' | grep -vE '^docs/' \
  && { echo "new doc outside docs/"; exit 1; } || exit 0   # failure mode #7, TESTED mechanic
```

### Tier 2 — pre-PR / CI on every push (<2min, diff-scoped)
```bash
# JS/TS
npx knip --no-exit-code --reporter json > /tmp/knip.json   # then diff-filter per "Diff-scoped enforcement" above — TESTED tool, diff-wrapper UNTESTED
npx madge --circular --extensions ts src                   # TESTED, exit 1 on cycles
npx dependency-cruiser --config .dependency-cruiser.cjs --output-type err src   # TESTED, exit 1
npx depcheck                                                # TESTED, exit 255 on unused deps
npx jscpd src --min-lines 5 --min-tokens 50 --threshold 0   # TESTED, exit 1 on clones
npx size-limit                                              # TESTED, exit 1 on budget breach
python3 assertionless_check.py  # or eslint jest/expect-expect for JS                # TESTED (Python)

# Python
ruff check .                     # TESTED, exit 1
vulture pkg/ --min-confidence 80 # TESTED, exit 3
deptry .                         # TESTED, exit 1 on DEP00x
lint-imports                     # TESTED, exit 1 on layer violation
diff-cover coverage.xml --compare-branch=$(git merge-base HEAD origin/main) --fail-under=80   # TESTED
xenon --max-absolute B --max-modules A --max-average A src   # UNTESTED wrapper around TESTED radon primitive
```

### Tier 3 — nightly / weekly (expensive, whole-repo, trend-tracked not hard-gated)
```bash
# JS/TS
mutmut run   # or npx stryker run, full repo — TESTED mechanism at small scale, expensive at real scale
npx knip                          # full whole-repo run, no diff-scoping — TESTED, exit 1
npx dependency-cruiser --output-type metrics src   # failure mode #3 single-use-abstraction signal — UNTESTED this session

# Python
mutmut run --paths-to-mutate pkg/   # full-package mutation score, tracked over time
pip-audit                            # dependency CVE sweep — UNTESTED this session, standard tool

# Go
golangci-lint run                   # TESTED (v2.14.0), exit 1 on default `unused` linter finding
staticcheck ./...                   # TESTED, exit 1 on U1000
go mod tidy -diff                   # TESTED, exit 1 on stale go.mod

# Universal
git-sizer --threshold 10MiB         # repo-object bloat — UNTESTED this session, first-party GitHub tool
scorecard --repo=<repo>             # supply-chain hygiene score — UNTESTED this session
```

---

## Honest limitations

No tool in this survey catches:

- **Premature abstraction vs. a deliberate extension seam** (#3) — the single-use-interface count
  is a *signal*, not a verdict; needs a human or an LLM reviewer asked specifically "load-bearing
  or speculative?"
- **Whether a comment restates the code** (#6) — needs semantic understanding of both the
  comment's claim and the code's behavior; the ratio-based proxy only flags outlier files.
- **Whether a new dependency was actually necessary** (#2) — mechanical tools make the addition
  *visible and blockable* (allowlist gate, depguard-style deny list), not judge necessity; that
  needs institutional knowledge or an LLM pass primed with the existing dependency list.
- **Semantic code duplication with renamed variables** (#5) — a real, reproducible miss of jscpd
  demonstrated directly in this research, for exactly the duplication shape agents produce most.
- **Cosmetic reformatting hidden inside comments/strings** (#11) — demonstrated directly:
  Prettier-based diff-normalization discounted quote-style churn in live code but not in a comment.
- **Equivalent mutants** (mutation testing's core false-positive class) — a mutant that changes
  code text but not behavior can never be killed and permanently suppresses the score;
  distinguishing it from a real test gap needs a human reading the specific mutant diff.
- **Cumulative, cross-PR bloat no single PR triggers a threshold on** — a thousand PRs each 0.4 KB
  under a 0.5 KB budget still grow the bundle unbounded; only Tier-3 trend-tracking catches this,
  and even that only *reports* the trend.

For all of the above, the realistic architecture is: mechanical checks narrow the review surface
(fail fast on the ~80% that is objectively checkable — dead code, cycles, unused deps,
complexity, byte budgets, API-surface diffs, assertion-free tests), and route the remaining
~20% (abstraction necessity, comment quality, dependency justification, semantic duplication,
equivalent-mutant triage) to a human or an LLM-judge reviewer step that is explicitly scoped to
just those questions — not asked to re-derive what the mechanical tools already settled.
