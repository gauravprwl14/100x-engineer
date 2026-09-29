# Findings: Agentic-Dev Corpus (own engineering + agent configuration)

Scope: the 25 repos in `research/worklists/agentic.txt` — products that build AI/agent
tooling, judged first on their **own** engineering (rubric D1, Part B3: never let the
topic flatter the verdict), then harvested for the AI-agent configuration they ship for
their own contributors. This cluster carries the 12-month age exception (rubric v3 R5);
everything else in Part A/B/C still applies.

All 25 were shallow/blobless-cloned (`git clone --filter=blob:none`, full commit graph,
lazy blobs) into a scratch dir; three large repos (mlflow, opik, pydantic-ai) needed a
`--bare --filter=blob:none` clone to get commit history within time budget. SHAs below
are the exact clone heads read. REST API was not used anywhere in this file.

| repo | HEAD sha (short) |
|---|---|
| CherryHQ/cherry-studio | `fd1a69d` |
| QwenLM/qwen-code | `bd45b95` |
| ComposioHQ/composio | `8f3088b` |
| promptfoo/promptfoo | `d3653fd` |
| mlflow/mlflow | `336845b` (shallow, depth 1 — full history via separate bare clone) |
| langflow-ai/langflow | `df9711c` |
| CopilotKit/CopilotKit | `a789183` |
| simstudioai/sim | `8725250` |
| yamadashy/repomix | `0b3f82b` |
| Kilo-Org/kilocode | `53a1dba` |
| vectordotdev/vector | `e44fb91` |
| github/spec-kit | `fcc7d35` |
| pingcap/tidb | `46df29c` |
| ruvnet/ruflo | `b14c79e` |
| crewAIInc/crewAI | `4ed2abc` |
| AstrBotDevs/AstrBot | `e99432c` |
| HKUDS/LightRAG | `453dce8` |
| continuedev/continue | `5522c6f` |
| iOfficeAI/AionUi | `6744099` |
| deepset-ai/haystack | `c2e809e` |
| comet-ml/opik | `98a0a2f` (shallow, depth 1 — full history via separate bare clone) |
| OpenHands/OpenHands | `c3c252a` |
| OpenInterpreter/open-interpreter | `dafe3c8` |
| getzep/graphiti | `6b4b56f` |
| pydantic/pydantic-ai | `e6df922` (shallow, depth 1 — full history via separate bare clone) |

Note on repo identity: `openinterpreter/openinterpreter` in the worklist resolves to
`OpenInterpreter/open-interpreter`, which as of this clone is a **rebrand of a fork of
OpenAI's `codex-rs`** (`FORK_BRANDING.md` in the tree) — the original Python "natural
language interface for your computer" project has been replaced by a Rust Codex-CLI
fork under the same name/star count. This is disclosed, not concealed, but it means the
Rust-language, Rust-CI-workflow evidence below describes the *current* tree, not the
project the stars were earned under.

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Own-engineering scorecard](#own-engineering-scorecard) | per-repo table of stars, age, test-file counts, CI-workflow counts, coverage gates and a D1 verdict for all 25 repos — the base evidence every other section draws on | 39 lines |
| 2 | [The popularity/discipline gap](#the-popularitydiscipline-gap) | which repos are worse (spec-kit, ruflo, graphiti, AionUi) or better (repomix, composio, haystack, vector) than their star count implies, plus a flagged Rust test-file-undercounting methodology trap | 56 lines |
| 3 | [Agent configs harvested (verbatim, cited)](#agent-configs-harvested-verbatim-cited) | verbatim AGENTS.md excerpts on verification commands, anti-bloat/minimal-diff rules, scope discipline and style conventions, grouped by theme — the largest raw-evidence section in the file | 138 lines |
| 4 | [Hooks: mechanical enforcement audit](#hooks-mechanical-enforcement-audit) | which of the 25 repos wire an actual blocking `PreToolUse`/`PostToolUse` hook (3 of 25), exactly what each one blocks, and the confirmed absence of any hook that runs the test suite itself | 97 lines |
| 5 | [Skills and commands defined by these repos](#skills-and-commands-defined-by-these-repos) | skill/command counts per repo, including the one repo (mlflow) that unit-tests its own skill tooling and the one (composio) that CI-tests its skill routing | 42 lines |
| 6 | [AI-authored code and its gates](#ai-authored-code-and-its-gates) | the `Co-Authored-By: Claude` commit share per repo (5.9% aggregate across 466k commits), and the finding that no repo runs a different CI path for AI-authored commits | 69 lines |
| 7 | [Transferable mechanisms, ranked](#transferable-mechanisms-ranked) | **highest-value section**: 9 ranked, copyable mechanisms, each tied to the specific failure class it prevents and the team-size scale where it starts paying off | 82 lines |

---

## Own-engineering scorecard

Method: test-file counts via `find` on TS/JS/Py naming conventions
(`*.test.*`/`*.spec.*`/`test_*.py`/`*_test.py`), with a supplementary inline-`#[test]`
grep for the two Rust repos where the naming convention doesn't apply. CI workflow
counts are `ls .github/workflows/`. "CI blocks merge" is **not observable without the
REST API** (branch protection is not in a git clone) — the column instead states what
IS observable: whether PR-triggered jobs exist that would fail the run.

| repo | stars | age | test files | CI workflows | typecheck | coverage gate | CI blocks merge (observable) | D1 | verdict |
|---|--:|--:|--:|--:|---|---|---|--:|---|
| CherryHQ/cherry-studio | 52,208 | 28mo | 2,499 | 23 | tsconfig ×3 | none found | PR-triggered ci.yml + e2e-regression-test.yml + snapshot.yml | 3 | Exemplary. AGENTS.md documents *why* (rejects behavior-pinning tests explicitly), CI has a real e2e/nightly/snapshot spread. |
| QwenLM/qwen-code | 28,192 | 15mo | 3,114 | 57 | tsconfig | none found | ci.yml, e2e.yml, codeql.yml, security-checks.yml, scorecard-monthly.yml (OpenSSF) | 3 | Extremely wide CI surface incl. security scanning; no coverage gate. |
| ComposioHQ/composio | 30,348 | 31mo | 461 | 36 | pyproject + tsconfig.base | none found (one mock JSON matched grep, not a real gate) | ts.test.yml, py.test.yml, ts.typecheck.yml, dead-code.yml, agent-substrate.yml (see below) | 3 | Dead-code CI + a CI-enforced check on its own agent-guidance files (rare; see harvest section). |
| promptfoo/promptfoo | 25,526 | 41mo | 1,236 | 13 | tsconfig strict | `codecov.yml` + referenced in `main.yml` | main.yml, code-scan | 3 | Knip dead-code CI gate documented with an explicit escape-hatch policy; genuine `PreToolUse` deny hook (see hooks section). |
| mlflow/mlflow | 28,160 | 100mo | 1,699 | 90+ | pyproject | none found | master.yml, cross-version-tests.yml, lint.yml | 3 | Huge CI surface (90+ workflows) incl. cross-version compat matrix; two genuine `PreToolUse` deny hooks. |
| langflow-ai/langflow | 155,326 | 44mo | 2,231 | 48 | pyproject | `codecov.yml`, referenced in python_test.yml/jest_test.yml/ci.yml | ci.yml, python_test.yml | 3 | Real coverage gate + broad matrix; weak on D2/D6/D7 per prior screen despite being the highest-star repo in the corpus (see gap section). |
| CopilotKit/CopilotKit | 37,580 | 39mo | 2,742 | 60+ | tsconfig (nested, not root) | none found | static_bundle_size.yml, static_danger.yml (Danger.js PR gate), static_quality.yml | 2 | Size-budget + Danger.js gate is a real D2 signal, but no coverage gate and no root typecheck config found. |
| simstudioai/sim | 29,746 | 21mo | 3,540 | 16 | tsconfig (nested) | none found | ci.yml, codeql.yml, test-build.yml | 2 | Very high test count but thin CI workflow count relative to it (16) and no coverage gate. |
| yamadashy/repomix | 28,517 | 26mo | 164 | 21 | tsconfig | referenced in ci.yml | ci.yml, ci-quality.yml, benchmark.yml (perf-regression layer) | 3 | Small repo, proportionate test count; perf-benchmark-history.yml is a genuine perf-regression test layer, rare in this cluster. |
| Kilo-Org/kilocode | 27,429 | 19mo | 1,760 | 33 | tsconfig | none found | typecheck.yml (dedicated job), visual-regression.yml, codeql-kotlin.yml | 3 | Dual-target CI (VS Code ext + JetBrains plugin, incl. Kotlin CodeQL) + visual regression — a real test layer most repos here lack. |
| vectordotdev/vector | 22,631 | 97mo | 2,916 inline `#[test]` (425 files) | 51 | N/A (Rust) | `coverage.yml` workflow | unit-tests.yml, integration.yml, k8s_e2e.yml, regression.yml, scorecard.yml | 3 | Mature Rust CI: k8s e2e, perf regression, OpenSSF scorecard. Naming-convention test search undercounts Rust by two orders of magnitude — worth flagging as a methodology trap. |
| github/spec-kit | 139,218 | 13mo | 266 | 26 | pyproject | none found | test.yml, lint.yml, codeql.yml | 1 | **Gap.** 836 tracked files, 23MB tree — a small scaffolding CLI carrying 139k stars, the highest star count of any repo in this cluster after langflow. Most of its "workflows" (`bug-assess.lock.yml`, `feature-assess.lock.yml`, `bug-fix.lock.yml`) are AI-agent orchestration definitions, not test/build CI. |
| pingcap/tidb | 40,597 | 133mo | 1,991 | 7 (GH Actions) | go vet (implied, not directly observed) | `.codecov.yml` present | Only 7 GH workflows visible — TiDB is known to run most CI on a separate Jenkins system (consistent with rubric R3's finding that GH-visible CI undercounts non-GHA projects) | 2 | Real engineering (1991 test files, mature Go project) but this probe under-observes it; scored conservatively for what's visible. |
| ruvnet/ruflo | 73,421 | 16mo | 665 | 30 | tsconfig ×2 | none found | ci.yml, v3-ci.yml, verification-pipeline.yml | 1 | **Gap — see below.** Renamed from `claude-flow`; README is heavily self-promotional (4 sibling products, "8.1M+ ecosystem downloads" badge); 108 `.claude/agents/*.md` files, many templated; workflow names (`neural-trader-smoke.yml`, `chatgpt-federation.yml`, `no-agentbbs-smoke.yml`) suggest scope sprawl. |
| crewAIInc/crewAI | 59,132 | 35mo | 397 | 16 | pyproject | none found | tests.yml, type-checker.yml, linter.yml, pr-size.yml (diff-size gate) | 2 | Modest, proportionate CI for repo size; `pr-size.yml` is a genuine anti-bloat mechanism. |
| AstrBotDevs/AstrBot | 41,145 | 46mo | 196 | 11 | pyrightconfig + pyproject | `coverage_test.yml` | unit_tests.yml, smoke_test.yml, code-format.yml | 2 | Coverage workflow present and separate from unit tests; modest but proportionate. |
| HKUDS/LightRAG | 39,898 | 24mo | 607 | 11 | pyproject | none found | tests.yml, linting.yaml, webui-tests.yml | 2 | Reasonable CI for size; only hook is a non-blocking `SessionStart` script (see hooks section). |
| continuedev/continue | 36,052 | 40mo | 331 | 33 | tsconfig | none found | cli-pr-checks.yml, main.yaml, snyk-agent.yaml | 2 | `auto-fix-failed-tests.yml` is an unusual workflow name — worth independent verification of what it actually does (not read in depth here). |
| iOfficeAI/AionUi | 33,182 | 14mo | 532 | 14 | tsconfig ×3 | `.codecov.yml` present but **`informational: true`** — does not fail the build | 1 | Coverage config exists but is explicitly non-blocking — a soft gate, not a hard one. |
| deepset-ai/haystack | 26,623 | 82mo | 224 | 33 | pyproject | `coverage_comment.yml` (posts a comment; not confirmed to block) | e2e.yml, slow.yml, cflite_pr.yml (**ClusterFuzzLite** — fuzzing), scorecard.yml, license_compliance.yml | 3 | Fuzzing + OpenSSF scorecard + license-compliance CI is a rare combination in this cluster; low test-file count for repo maturity is the one soft spot. |
| comet-ml/opik | 22,271 | 41mo | 1,147 | 90+ | none found at root | `qa_coverage_reconcile.yml` | 20+ per-provider integration test workflows (`lib-openai-tests.yml`, `lib-anthropic-tests.yml`, …), `load_tests.yml` | 3 | The most exhaustive third-party-integration test matrix in the cluster. |
| OpenHands/OpenHands | 89,363 | 30mo | 776 | 20 | tsconfig | none found | ci.yml, mock-llm-e2e.yml (agent-behavior test w/ mocked LLM) | 2 | `mock-llm-e2e.yml`/`mock-llm-docker-e2e.yml` are a genuine agent-behavior test layer, distinct from unit tests — notable for an agent product. |
| OpenInterpreter/open-interpreter | 68,462 | 38mo | 9,150 inline `#[test]` (Rust, post-rebrand) | 28 | N/A (Rust) | none found | rust-ci-full-nextest-platform.yml, cargo-deny.yml (dependency policy), blob-size-policy.yml | 2 | Post-rebrand tree inherits Codex's mature Rust test discipline; `blob-size-policy.yml` is a real repo-bloat gate. |
| getzep/graphiti | 31,250 | 26mo | 66 | 15 | pyproject | none found | typecheck.yml, unit_tests.yml, mcp-server-tests.yml | 2 | Smallest full commit history in the cluster (1,232 commits ever) for a 31k-star repo — thin relative to its popularity (see gap section). |
| pydantic/pydantic-ai | 20,233 | 27mo | 538 | 30+ | pyproject | pyproject coverage config | ci.yml, pr-guard.yml | 3 | Majority of its "workflows" are scheduled autonomous AI-agent bots (bug-hunter, regression-detector, docs-drift) via `gh-aw`, not traditional CI — genuinely novel, covered in Transferable Mechanisms. |

---

## The popularity/discipline gap

Rubric B3, applied with numbers, not vibes.

**Worse than their star count suggests:**

- **`github/spec-kit` — 139,218 stars, 836 tracked files, 23MB tree, 266 test files.**
  Second-highest star count in the whole 25-repo cluster, carried by a small
  Python scaffolding CLI. Most of its `.github/workflows/*.lock.yml` files are AI-agent
  task definitions (`bug-assess`, `feature-assess`, `bug-fix`), not build/test CI — the
  workflow *count* (26) overstates the traditional CI investment. D1=1.
- **`ruvnet/ruflo` (renamed from `claude-flow`) — 73,421 stars, no coverage gate,
  108 `.claude/agents/*.md` files** (many templated boilerplate — `github-pr-manager.md`,
  `sparc-coordinator.md`, `memory-coordinator.md` are near-duplicates of each other),
  a README built around 4 cross-linked commercial sibling products and an "8.1M+
  ecosystem downloads" badge, and a `PreToolUse` hook whose console output includes an
  unrelated sponsorship upsell (`cognitum.one/meta-llm`, quoted in the hooks section).
  This repo also has the highest AI-commit share in the cluster (38.2%, see AI-authored
  section) — consistent with a codebase that has scaled by generation rather than by
  reviewed, incremental engineering. D1=1.
- **`getzep/graphiti` — 31,250 stars but only 1,232 commits in its entire history** —
  the thinnest full commit history of any repo in this cluster, by a wide margin
  (compare `promptfoo` at 23,299 or `tidb` at 49,006). Popularity arrived faster than
  the codebase accumulated engineering evidence.
- **`iOfficeAI/AionUi` — coverage config present but `informational: true`.** The repo
  *looks* like it has a coverage gate (`.codecov.yml` exists, is wired into CI) but the
  config explicitly opts out of blocking: `target: auto`, `threshold: 10%`,
  `informational: true` at both patch and project level. This is a coverage-shaped
  object with no coverage-shaped enforcement — worth flagging because it would pass a
  shallow "does `codecov.yml` exist?" check.

**Better than their star count suggests:**

- **`yamadashy/repomix` — 28,517 stars, only 164 test files, but proportionate**: a
  genuinely small, focused CLI tool with a real perf-regression test layer
  (`perf-benchmark-history.yml`, `perf-benchmark.yml`) that most 5-10x larger repos in
  this cluster don't have, plus the cleanest, most CI-enforced agent-guidance setup
  outside promptfoo/composio (see harvest section).
- **`ComposioHQ/composio` — 30,348 stars** ships a CI job (`agent-substrate.yml`) that
  runs a **deterministic routing smoke test over its own AI-agent skill descriptions**
  on every push/PR — turning "does the skill still trigger on the task it's meant for"
  into a mechanically-checked regression, which no other repo in this cluster (or the
  separately-screened skills-ecosystem corpus) was found to do.
- **`deepset-ai/haystack` — 26,623 stars, only 224 test files (low for its 82-month
  age and ML-framework scope)**, but it is the only repo in the cluster running
  **ClusterFuzzLite** (`cflite_pr.yml`) and an OpenSSF Scorecard — security-adjacent
  discipline the raw test-file count doesn't show.
- **`vectordotdev/vector`** — the naming-convention test-file search returns **2**
  (near-zero), because Rust tests live inline as `#[test]` inside source files; the real
  count is **2,916** inline test functions across 425 files, plus a Kubernetes e2e suite
  and OpenSSF scorecard. This is as much a finding about the *measurement method* as
  about the repo: any test-file-count probe that doesn't special-case Rust will
  systematically undercount every Rust repo in a corpus.

---

## Agent configs harvested (verbatim, cited)

### Verification instructions

**`CherryHQ/cherry-studio@fd1a69d:AGENTS.md`** — precise, scoped verification command,
explicitly telling the agent CI is not its job to fully replicate:

> `Check what you changed, not the whole repo`: for code, run `pnpm lint` (it covers
> format + typecheck + `i18n:check`) plus the tests covering your change — per-project
> wrappers (`pnpm test:main <file>`, `test:renderer`, `test:aicore`, `test:shared`,
> `test:pkg:ui`, `test:scripts`) or `pnpm exec vitest run <file>` for a few files; full
> `pnpm test` only when the change is broad or you can't name the affected tests. Never
> use `pnpm test <path>`: the script chains several vitest invocations with `&&`, CLI
> args reach only the last one, and earlier projects run their full suites unfiltered.
> [...] CI runs the full gate; your job is to not obviously break it.

Same file, on what counts as a real test (this is a rejection criterion with teeth,
not a style preference):

> **No behavior-pinning tests**: a test whose only assertion records what the code
> currently does [...] has zero value. It cannot fail for a real reason, it breaks on
> every refactor, and it certifies existing bugs as "expected". Assert the contract
> instead [...] Before writing a test, state the bug it would catch; if you cannot, do
> not write it. **The existing suite is full of these** — delete the ones in a file you
> are already editing rather than keeping them green.

**`promptfoo/promptfoo@d3653fd:AGENTS.md`** — the standard verification command for
behavior changes is a real end-to-end run, not just unit tests:

> For behavior changes, do not stop at unit tests. Run the actual CLI or example with
> the local build. [...] `npm run local -- eval -c path/to/promptfooconfig.yaml
> --no-cache -o output.json` [...] Inspect exported JSON for `success`, `score`,
> `error`, provider outputs, traces, and redteam findings. If you claim a redteam ran,
> report the plugins, strategies, interesting findings, and the evidence reviewed.

Same file on post-merge ownership (rare — most AGENTS.md files stop at "open a PR"):

> **After landing a PR, watch `main` until its CI is green.** Merging is not the end of
> the loop. [...] **Classify before reacting.** [...] A failure is a *flake* when the
> tests themselves pass and the job dies on infrastructure noise [...] A *real* failure
> is deterministic and attributable to the change.

**`ComposioHQ/composio@8f3088b:AGENTS.md`** — verification commands are listed, but the
file also tells the agent the commands are not guaranteed current and to check:

> Verify every command you write against the current `package.json`, `Makefile`,
> `noxfile.py`, or workflow file.

### Anti-bloat / minimal-diff

**`CherryHQ/cherry-studio@fd1a69d:AGENTS.md`** ("Surgical Changes"):

> Touch only what the task requires. Do not "improve" adjacent code, comments, or
> formatting. Do not refactor things that are not broken. Match existing style even if
> you would do it differently. If you notice unrelated dead code, mention it — do not
> delete it. Remove imports / variables / functions that **your** changes orphaned.
> Leave pre-existing dead code alone unless asked. Every changed line must trace
> directly to the user's request.

And ("Simplicity First"):

> Write the minimum code that solves the problem. Nothing speculative. No features
> beyond what was asked. No abstractions for single-use code. No "flexibility" or
> "configurability" that was not requested. [...] If you wrote 200 lines and it could
> be 50, rewrite it.

**`promptfoo/promptfoo@d3653fd:AGENTS.md`** — dead-code CI is named and the escape
hatch is specified precisely enough to be auditable:

> CI runs a full Knip audit (`npm run knip -- --no-progress --reporter github-actions`)
> in the Style Check job. It fails the build on unused files, exports, and dependencies
> [...] **Actually dead?** Delete the code. [...] **Loaded by convention or path
> string**? Add an `entry` in `knip.jsonc` with a comment stating the loading
> mechanism. [...] Every allowlist entry in `knip.jsonc` must have a comment explaining
> why it exists — never remove an entry [...] without checking its stated consumer
> first.

**`ComposioHQ/composio@8f3088b:AGENTS.md`** ("Contribution Policy"):

> Keep the change focused on meaningful improvements to the SDKs, CLI, or docs. Don't
> produce cosmetic, speculative, or drive-by edits. The author is responsible for every
> line. Keep diffs small enough to read, report the checks you actually ran, and tell
> the author to review the full diff before submitting.

**`crewAIInc/crewAI`** ships a `pr-size.yml` CI workflow — a mechanical diff-size gate,
not a prose instruction (the only repo in the cluster observed to enforce this in CI
rather than just asking for it).

### Scope discipline / context scoping

**`promptfoo/promptfoo@d3653fd:AGENTS.md`** — hierarchical AGENTS.md, one per directory,
with a routing table so the agent only loads what's relevant to the subtree it's
editing (24 nested `AGENTS.md` files: `src/redteam/AGENTS.md`, `src/providers/AGENTS.md`,
`test/AGENTS.md`, etc.):

> | Directory | Purpose | Local Docs | [...] **Read the relevant AGENTS.md when working
> in that directory.**

**`ComposioHQ/composio@8f3088b:AGENTS.md`** — the same pattern plus an explicit
"smallest relevant skill" rule and a generated/vendored-paths carve-out:

> Use the smallest relevant skill: `repo-guidance` [...] `bug-fixing` [...]
> `cross-sdk-parity` [...] Do not hand-edit these. They are regenerated or vendored, and
> edits will be overwritten. [...] `ts/vendor/**` [...] `ts/packages/core/generated/**`
> [...] `pnpm-lock.yaml`, `uv.lock`, `**/bun.lock` — change them by running the package
> manager, never by hand.

`mlflow`, `haystack`, `CopilotKit`, `pydantic-ai`, `sim`, `tidb`, and `kilocode` all
ship the same nested-AGENTS.md pattern (per-package or per-module files, 5-30 of them
each) — this is the single most consistent convention across the whole cluster,
present in 15 of 25 repos.

### Style / project conventions

**`simstudioai/sim@8725250:.claude/rules/`** ships 20 separate topic-scoped rule files
(`sim-stores.md`, `sim-api-contracts.md`, `sim-react-performance.md`,
`sim-list-ordering.md`, `sim-url-state.md`, …) rather than one large file — the opposite
of promptfoo/composio's nested-AGENTS.md approach, same goal (keep an agent's loaded
context proportional to the task).

Sim also ships a family of skills literally named for negative space — codifying
*removal* rules, not just addition rules:

> `you-might-not-need-a-comment`, `you-might-not-need-a-callback`,
> `you-might-not-need-an-effect`, `you-might-not-need-state`,
> `you-might-not-need-url-state`

From `simstudioai/sim@8725250:.claude/skills/you-might-not-need-a-comment/SKILL.md`:

> A comment must add information the code cannot express itself. Code says *what* and
> *how*; a comment earns its place only by explaining *why* [...] If deleting the
> comment loses no information a competent reader wouldn't recover from the code in
> seconds, delete it. [...] **Anti-patterns to detect**: 1. Restates the code [...]
> 2. Narrates the obvious from names [...] 3. Section-divider / banner comments [...]
> Against convention. Delete.

---

## Hooks: mechanical enforcement audit

Of 25 repos, **6 ship a `.claude/settings.json`**; of those, **3 define an actual
`hooks` key** (`promptfoo`, `ruvnet/ruflo`, `mlflow`); 2 have the file but an empty/no
`hooks` key (`repomix`, `pydantic-ai`); one (`HKUDS/LightRAG`) has only a non-blocking
`SessionStart` script. **19 of 25 repos have no `.claude/settings.json` at all.**

None of the three active hook configs is the specific pattern prior research (the
skills-ecosystem corpus, `research/20-findings-ecosystem-skills.md`) found nobody
wires: a `PreToolUse`/`Stop` hook that runs the **test suite** and blocks on failure.
But two of them are genuinely mechanical, blocking gates on *other* failure classes —
that distinction matters and is reported precisely below, not rounded up or down.

**`promptfoo/promptfoo@d3653fd:.claude/settings.json`** — closest thing in the cluster
to a real verification-blocking hook:

```json
{
  "PreToolUse": [
    { "matcher": "Bash", "hooks": [
      { "type": "command", "command": "${CLAUDE_PROJECT_DIR}/node_modules/.bin/block-no-verify" }
    ]}
  ],
  "PostToolUse": [
    { "matcher": "Edit|Write", "hooks": [
      { "type": "command", "command": "npm run l && npm run f" }
    ]}
  ]
}
```

`block-no-verify` is a third-party npm package (`package.json` pins `^1.2.0`) that
inspects the `git commit`/`git push` command an agent is about to run and denies it if
it contains `--no-verify` — i.e. it mechanically prevents the agent from bypassing the
repo's own pre-commit hooks. The `PostToolUse` hook runs lint+format after every
`Edit`/`Write`; because promptfoo's AGENTS.md documents `npm run l && npm run f` as
"before committing," and the hook fires that automatically after every file write, a
non-zero exit here surfaces to the agent as a failure it must fix before continuing —
functionally a lint-blocking gate, even though it is not literally a test-suite gate.

**`mlflow/mlflow@336845b:.claude/settings.json`** — two `PreToolUse` deny hooks:

```json
{
  "PreToolUse": [
    { "matcher": "Bash", "hooks": [
      { "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/enforce-uv.sh", "timeout": 5.0 },
      { "type": "command", "command": "uv run --directory=$CLAUDE_PROJECT_DIR --no-project .claude/hooks/validate_pr_body.py", "timeout": 5.0 }
    ]}
  ]
}
```

`enforce-uv.sh` greps the proposed Bash command for a bare `python`/`python3`/`pip`/
`pip3` invocation and returns a `permissionDecision: deny` if found, forcing `uv run`/
`uv pip` instead:

> `deny_reason="Use 'uv run python' instead. [...]"` / `if [[ -n "$deny_reason" ]];
> then echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse",
> "permissionDecision": "deny", ...}}'; fi`

`validate_pr_body.py` intercepts `gh pr create` calls and denies the command if the
`--body` doesn't contain every heading from `.github/pull_request_template.md` — a
mechanical PR-template-completeness gate, enforced *before* the PR is created rather
than reviewed after.

**`ruvnet/ruflo@b14c79e:.claude/settings.json` / `.claude/helpers/hook-handler.cjs`** —
also has `PreToolUse`/`PostToolUse`/`UserPromptSubmit`/`SessionStart` hooks wired, but
the `pre-bash` handler is a **dangerous-command safety blocklist**
(`rm -rf /`, `format c:`, fork bombs), not a code-quality or test gate:

```js
'pre-bash': () => {
  const dangerous = ['rm -rf /', 'format c:', 'del /s /q c:\\', ':(){:|:&};:'];
  for (const d of dangerous) {
    if (cmd.includes(d)) { console.error(`[BLOCKED] ...`); process.exit(1); }
  }
}
```

and `post-edit` only records session telemetry, it does not run lint or tests. The same
handler file also emits an unrelated commercial nudge on session events:

> `console.log('[COGNITUM] Hit your Claude usage limit? Free sponsored capacity is
> available at cognitum.one/meta-llm — run: ruflo proxy sponsor-enable --yes');`

**Bottom line for this section**: the specific pattern "a hook runs the test suite and
blocks the agent on failure" was **not found in any of the 25 repos** — that null
result from the prior corpus holds here too. But the stronger claim "nobody wires *any*
blocking hook" is **false**: `promptfoo` and `mlflow` both wire genuine
`permissionDecision: deny` `PreToolUse` gates against specific, well-defined
anti-patterns (bypassing pre-commit hooks; bypassing the project's package-manager
convention; submitting an incomplete PR template) — mechanical enforcement of a policy
prose alone cannot guarantee, just not the *verification* policy specifically.

---

## Skills and commands defined by these repos

Counts (via `find` for `SKILL.md`, and files under any `agents/`/`commands/` dir),
top skill-bearing repos:

| repo | skills | commands | agents-dir files | notable |
|---|--:|--:|--:|---|
| `ruvnet/ruflo` | 0 (skills-style content lives in `agents/`) | several | 108 | swarm/hive-mind/SPARC role-play agents (`byzantine-coordinator.md`, `queen-coordinator.md`) — see gap section |
| `simstudioai/sim` | ~38 | — | — | most disciplined *negative-space* skill set in the cluster (see above) |
| `mlflow/mlflow` | 9 | — | — | skill package ships its own **unit tests** (`.claude/skills/tests/test_*.py` × 7) — the only repo observed to test its own skill tooling |
| `CherryHQ/cherry-studio` | 11 (root) + 6 (bundled "cherry-assistant" agent) | — | — | ships a whole nested Claude plugin (`.claude-plugin/plugin.json`) as a product feature, not just contributor tooling |
| `ComposioHQ/composio` | canonical tree at `.agents/skills`, `.claude/skills` kept as a symlink | 2 | — | CI-enforced routing test (see gap section) |
| `pydantic/pydantic-ai` | 6 | — | — | `pre-push-review`, `address-feedback`, `i-have-adhd` (session-scoping skill) |
| `yamadashy/repomix` | 5 + 3 plugin bundles | 2 (in a plugin) | 1 (`explorer.md`) | ships Claude Code **plugins** (`.claude-plugin/plugin.json`) distributing skills/commands/MCP config as an installable unit |

**`mlflow/mlflow@336845b:.claude/skills/tests/`** is worth calling out specifically:
seven pytest files (`test_utils.py`, `test_review_payload_schema.py`,
`test_validate_review.py`, `test_upload_media.py`, `test_uploads.py`,
`test_embed_media.py`, `test_annotate_diff.py`) that test the Python package
*implementing the PR-review skill itself* — i.e. the agent tooling is held to the same
CI bar as product code, not shipped as unverified prose+scripts.

**`ComposioHQ/composio@8f3088b:.github/workflows/agent-substrate.yml`** — the strongest
single mechanism found for keeping agent guidance from silently rotting:

> Guards the repo-level AI-agent guidance — the files coding agents read — so it cannot
> silently drift from reality: `pnpm validate:agent-skills` — SKILL.md frontmatter and
> reference links, the `.agents/skills` <-> `.claude/skills` compatibility symlink,
> required nested AGENTS.md files, stale guidance references, and every pnpm/make/nox
> command mentioned in guidance checked against its real definition. `pnpm
> validate:skill-routing` — deterministic routing smoke test: each skill keeps a probe
> asserting it is the unique top match for a representative task, so description edits
> cannot silently break routing. [...] These checks run nowhere else, so this workflow
> is their only enforcement point. It runs on every push and PR with no path filters.

This is a CI-enforced eval harness for the repo's *own* agent-facing documentation and
skill-trigger reliability — the exact mechanism the separately-screened skills-ecosystem
corpus found only in `anthropics/skills` and `wshobson/agents`, now also confirmed
inside a production **corpus** repo (not a skills-distribution repo).

---

## AI-authored code and its gates

Method: `git log --all -i --grep='co-authored-by:.*claude' -E` on full commit history
(bare/blobless clone). This is the **strict** count — an initial pass also matched
`--grep='generated with'`, which produced false positives (`"Regenerated with
pnpm@8.15.9"` in `ruvnet/ruflo` matched and was not AI-related); the loose count is
discarded and only the strict co-author-trailer count is reported below.

| repo | AI-attributed commits | total commits (full history) | % |
|---|--:|--:|--:|
| ruvnet/ruflo | 5,063 | 13,238 | **38.2%** |
| comet-ml/opik | 4,761 | 28,636 | **16.6%** |
| getzep/graphiti | 225 | 1,232 | 18.3% |
| yamadashy/repomix | 1,030 | 5,964 | 17.3% |
| ComposioHQ/composio | 1,667 | 12,011 | 13.9% |
| github/spec-kit | 313 | 2,276 | 13.8% |
| HKUDS/LightRAG | 1,498 | 11,210 | 13.4% |
| CherryHQ/cherry-studio | 2,938 | 23,308 | 12.6% |
| mlflow/mlflow | 2,127 | 17,327 | 12.3% |
| CopilotKit/CopilotKit | 2,099 | 22,655 | 9.3% |
| pydantic/pydantic-ai | 698 | 8,523 | 8.2% |
| promptfoo/promptfoo | 1,824 | 23,299 | 7.8% |
| simstudioai/sim | 576 | 9,741 | 5.9% |
| deepset-ai/haystack | 203 | 7,887 | 2.6% |
| crewAIInc/crewAI | 224 | 9,426 | 2.4% |
| QwenLM/qwen-code | 775 | 35,245 | 2.2% |
| iOfficeAI/AionUi | 126 | 6,988 | 1.8% |
| OpenHands/OpenHands | 347 | 20,503 | 1.7% |
| continuedev/continue | 229 | 22,501 | 1.0% |
| vectordotdev/vector | 175 | 19,995 | 0.9% |
| pingcap/tidb | 354 | 49,006 | 0.7% |
| langflow-ai/langflow | 341 | 56,295 | 0.6% |
| AstrBotDevs/AstrBot | 29 | 6,492 | 0.4% |
| OpenInterpreter/open-interpreter | 54 | 14,142 | 0.4% |
| Kilo-Org/kilocode | 74 | 38,547 | 0.2% |
| **Total** | **27,750** | **466,447** | **5.9%** |

**This is real, not marginal.** Across 25 repos totaling 466k commits, 5.9% carry an
explicit `Co-Authored-By:` trailer naming Claude — and that's a floor, since it only
catches commits where the tool/author chose to disclose. A sample check on
`promptfoo/promptfoo@d3653fd` confirms these are ordinary merged PRs, not a separate
lane:

```
851641e fix(env): honor --env-file and config env for prompt separator and assertion
concurrency (#11059)
Co-authored-by: mldangelo <...> / Co-authored-by: Claude Opus 5.5 (1M context)
<noreply@anthropic.com> / Co-authored-by: Michael D'Angelo <...>
```

**What gate did this code pass through?** In every repo sampled, the same one every
other commit passes through: the PR-triggered CI workflows listed in the scorecard
table above (tests, lint, typecheck, coverage-report-where-present). No repo in this
cluster was found to run a *different*, lighter, or heavier CI path for
AI-co-authored commits — there is no separate AI-PR lane, no extra required review, and
(per `CONTRIBUTING.md` greps) **no repo in the cluster has an explicit written policy on
AI-authored contributions** beyond `promptfoo/promptfoo@d3653fd:AGENTS.md`'s instruction
to the *agent itself*:

> **Never attribute commits or PR bodies to Claude / Claude Code.** No
> `Co-Authored-By: Claude…` trailers, no "Generated with Claude Code" footers. Use your
> configured git identity only.

— which is a policy about *disclosure*, not about *review rigor*, and (per the 1,824
Claude-attributed commits actually merged into that same repo) is evidently not applied
retroactively or enforced against the disclosed cases already in history.

---

## Transferable mechanisms, ranked

Each with the specific failure class it prevents and the scale where it starts paying
for itself.

1. **CI-enforced eval on the agent's own skill-trigger reliability**
   (`ComposioHQ/composio@8f3088b:.github/workflows/agent-substrate.yml`). Prevents:
   a skill description silently drifting until it no longer fires on the task it names,
   or fires on the wrong one — the exact failure mode that makes most SKILL.md files
   unfalsifiable prose. Scale: org (10+) — building the routing-probe harness is not
   worth it below a double-digit skill count.

2. **`PreToolUse` deny hook for tooling-convention bypass**
   (`mlflow/mlflow@336845b:.claude/hooks/enforce-uv.sh`). Prevents: an agent silently
   using `pip`/`python` directly in a `uv`-managed repo, producing an environment that
   diverges from CI's. Small, ~40-line bash script; pays for itself at any team size
   with a pinned toolchain.

3. **`PreToolUse` deny hook for PR-template completeness**
   (`mlflow/mlflow@336845b:.claude/hooks/validate_pr_body.py`). Prevents: an agent (or
   a human) opening a PR that's missing the "how was this tested" section before a
   reviewer ever sees it — moves a review-time nag into a pre-submission mechanical
   gate. Scale: small-team+ with an enforced PR template.

4. **`PreToolUse` deny hook against `--no-verify`**
   (`promptfoo/promptfoo@d3653fd`, via the `block-no-verify` package). Prevents: an
   agent (which has every incentive to get past a failing pre-commit hook quickly)
   silently bypassing the repo's own lint/format checks. This is the single most
   direct answer available in this corpus to "does anyone actually block on
   verification" — not a test-suite gate, but a gate that *keeps the existing
   verification gate from being switched off*.

5. **Hierarchical `AGENTS.md`, one per subtree, with a routing table at the root**
   (present in 15/25 repos; cleanest examples: `promptfoo`, `composio`, `mlflow`,
   `haystack`). Prevents: context-budget waste and rule drift — an agent editing
   `src/redteam/` only loads redteam-specific conventions, not the whole repo's rules,
   and a change to one subtree's conventions doesn't require editing a monolith. Scale:
   any repo with 5+ meaningfully-different subtrees.

6. **Named "you-might-not-need-X" skill family as an explicit deletion ratchet**
   (`simstudioai/sim@8725250:.claude/skills/you-might-not-need-*`). Prevents: additive
   bias — most agent-config effort in this corpus (and the wider ecosystem) teaches
   agents what to *add* (tests, docs, types); this is the only cluster example of a
   skill whose entire job is finding code to *remove*, with a concrete anti-pattern
   list agents can pattern-match against. Scale: any team size; cheapest mechanism on
   this list to add (one file, no CI wiring required — though none here is CI-wired).

7. **Skill package with its own unit tests** (`mlflow/mlflow@336845b:.claude/skills/tests/`).
   Prevents: agent tooling silently breaking (a skill's helper script throwing on an
   edge case) with no signal until an agent hits it mid-task. The only repo in the
   cluster holding its *own* agent tooling to the product's normal test bar. Scale:
   org (10+) — worth it once agent-facing tooling is nontrivial Python/JS, not a single
   markdown file.

8. **Sandboxed, output-capped, auto-expiring scheduled agent bots via `gh-aw`**
   (`pydantic/pydantic-ai@e6df922:.github/workflows/pydantic-ai-bug-hunter.md` +
   `.lock.yml`). A weekly autonomous Claude agent runs inside a firewalled container
   (`gh-aw-firewall`), reads the repo read-only (`permissions: contents: read`), and
   its only allowed effect is `create-issue: max: 1` with a 7-day auto-expiry and
   dedup via `close-older-key`. Prevents the two failure modes of "let an AI agent run
   unattended against your repo": unbounded blast radius (capped permissions, capped
   output count) and issue-tracker spam accumulation (auto-expiry). This is the most
   structurally sophisticated agent-safety mechanism found in the entire corpus, not
   just this cluster — worth a dedicated look by whoever owns agent tooling next, cited
   here as a pointer rather than fully explored (the `gh-aw` schema was not otherwise
   read in this pass). Scale: org running any unattended/scheduled agent job — the
   safe-outputs cap is the load-bearing part, and it's cheap to replicate regardless of
   which agent runtime is used.

9. **`pr-size.yml` as a mechanical (not prose) diff-size gate** (`crewAIInc/crewAI`).
   Prevents: the generic "keep diffs small" instruction every AGENTS.md in this corpus
   states in prose (cherry-studio, composio, promptfoo all do) from being the *only*
   place that rule lives — this is the one repo in the cluster that also checks it in
   CI. Scale: any team size; trivial to add, and the only anti-bloat mechanism on this
   list that requires zero maintenance once configured.

**What did not transfer / absence worth recording:** no repo in this 25 was found
running a `PreToolUse`/`Stop` hook that executes the test suite and blocks the tool call
on failure — the specific pattern the prior skills-ecosystem screen also found absent.
The three real hooks found here (mlflow ×2, promptfoo ×1) all gate *process*
(tool choice, PR completeness, bypass prevention), not *correctness*. That gap — from
"block bypassing verification" to "block on verification actually failing" — remains
open across both corpora screened so far.
