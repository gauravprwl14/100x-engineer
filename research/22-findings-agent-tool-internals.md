# 22 — Agent tool internals: how the coding agents verify their own output

Source method: shallow-cloned every target at its current default branch and read the actual
source (not docs/marketing). Star counts could not be pulled live — `gh api` rate-limited for
the entire research window — so the Scorecard marks them **approx.** from general knowledge as
of this session; every other claim is a file:line citation against the cloned tree. Two targets
(`sourcegraph/cody`, `sourcegraph/amp`) return HTTP 404 — reported as absence, not guessed.

---

**SWE-agent is the only tool in this set whose verification fails closed — a bad edit is lint-checked and rolled back before it ever lands on disk; every other agent here (cline, opencode, aider, OpenHands) fails open, writing the bad edit first and merely flagging it on the next turn.**

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Scorecard](#scorecard) | one row per tool (cline, Roo-Code, OpenHands, aider, SWE-agent, codex, gemini-cli, plandex...) with test count, CI setup, verification-loop type, edit mode and sandbox — the reference table for the whole file | 28 lines |
| 2 | [Verification loops, compared](#verification-loops-compared) | which tools verify before vs. after writing to disk, why SWE-agent's pre-flight lint-and-rollback is the strongest design found, and which tools have no loop at all | 63 lines |
| 3 | [Edit mechanics, compared](#edit-mechanics-compared) | exact-match vs. fuzzy-match strategy per tool, and why exact-match-first resists bloat better than cline's always-fuzzy tiers | 29 lines |
| 4 | [Context selection / repo-map algorithms](#context-selection--repo-map-algorithms) | how aider's PageRank-based repo-map actually works (parse, build symbol graph, rank, fit token budget) — the only tool in the set with a real graph-ranking algorithm | 46 lines |
| 5 | [Harvested system prompts (verbatim)](#harvested-system-prompts-verbatim) | actual system-prompt text on verification, minimality/anti-bloat, file creation, scope discipline and code style, copied from 5+ tools — the largest section, direct quotable source material | 154 lines |
| 6 | [SWE-bench verification model](#swe-bench-verification-model) | how FAIL_TO_PASS/PASS_TO_PASS before/after test diffing proves a patch is correct without trusting the agent's own claim | 30 lines |
| 7 | [Transferable mechanisms](#transferable-mechanisms) | 10 ranked, reusable mechanisms, each tied to the specific failure class it prevents — the actionable takeaway list; start here for the synthesis | 51 lines |
| 8 | [Notes on category and absence findings](#notes-on-category-and-absence-findings) | which tools were rejected or excluded and why — dead repos, HTTP 404s, wrong shape for this study's Q1-Q4 | 14 lines |

## Scorecard

| tool | stars (approx.) | D1 (0-3) | tests | CI | verification loop? | edit mode | sandbox | verdict |
|---|---|---|---|---|---|---|---|---|
| cline/cline | ~48k | 3 | 796 test files, ~984 unit tests in one package alone | 12 workflows: unit/integration/e2e/lint split per app | **Yes, automatic** — IDE diagnostics diffed after every write | apply_patch (context-diff) + legacy SEARCH/REPLACE, tiered fuzzy match | VS Code approval dialog per tool call + command-guard allow/deny list | Tier 1 — best-engineered VS Code agent in the set |
| RooCodeInc/Roo-Code | ~17k | 3 | present, not counted (contention) | knip + lint + typecheck + test all gated in `code-qa.yml` | Not confirmed (time-boxed) | MultiSearchReplace, Levenshtein similarity, exact by default | mode-based `FileRestrictionError` (scope gate, not a sandbox) | Tier 1 on D2 (knip in CI is rare) |
| All-Hands-AI/OpenHands (Canvas UI) | ~63k (combined w/ SDK identity) | 3 | frontend has Stryker **mutation testing** config | lint→test→build→pack, live+mock Playwright E2E | N/A (this repo is UI only) | N/A | N/A | Tier 1 D1/D3 |
| OpenHands/software-agent-sdk | (same product) | 3 | 605 test_*.py, golden prompt snapshots | pyright, ruff, integration-runner (real model matrix), blocking security-scan | **Yes** — ToolError → error observation fed back | `str_replace`, exact match only | Docker (`workspace/docker`, `agent_sandbox`) | Tier 1 — the real agent lives here, not in the OpenHands repo people clone |
| Aider-AI/aider (=paul-gauthier/aider) | ~35k | 2 | 36 test files | ubuntu+windows test workflows, pre-commit | **Yes, bounded** — `max_reflections=3` | SEARCH/REPLACE, exact-match only; also whole-file, udiff | none (local process) | Tier 1 — canonical repo-map |
| princeton-nlp/SWE-agent | ~15k | 2 | 21 test files | pytest.yaml | **Yes, in-tool** — pre/post flake8 diff, rollback on new errors | line-range replace w/ built-in linter gate | Docker (task envs) | Tier 1 on D1 — strongest single verification gate found |
| princeton-nlp/SWE-bench (harness) | ~7k | 2 | present | codecov.yml, pytest | **Is** the verification model (F2P/P2P) | N/A (grader, not editor) | per-instance Docker image | Tier 1 — reusable as our correctness-proof pattern |
| gpt-engineer-org/gpt-engineer | ~54k | 1 | 18 test files | ci.yaml, pre-commit.yaml | **Format-retry only**, no correctness loop | unified-diff hunks, format-retry up to `MAX_EDIT_REFINEMENT_STEPS` | none | Tier 3 — no real verification |
| continuedev/continue | ~28k | 2 | 58 sampled in core/ | dogfoods own CLI to auto-fix its failing CI tests | Partial — lazy-apply reconciliation, no default test-run gate | lazy-apply (tree-sitter) → unified-diff fallback | none built-in | Tier 2 |
| block/goose | ~18k | 3 | 85 Rust test files sampled | cargo-deny, cargo-machete, code-review.yml, 20+ workflows | Not confirmed built-in; extensions/permission system exists | exact `string_replace`, "did you mean" suggestions | extension permission system | Tier 1 on D2/D5 |
| sst/opencode | ~18k | 3 | 254 test files | 60 workflows | **Yes, automatic** — LSP diagnostics wired directly into the edit tool | exact-match `replace()`, `replaceAll` opt-in | none built-in found | Tier 1 |
| microsoft/autogen | ~46k | 2 | 99 test files (v0.4+) | 12 workflows | **Opt-in only** — Docker/Jupyter code executors are composable, not default | N/A (framework, not a file editor) | Docker code executors (opt-in) | Tier 2 — framework, not an agent |
| crewAIInc/crewAI | ~34k | 2 | 372 test files | CodeQL, vulnerability-scan, type-checker, linter, **pr-size labeler** | No default write→verify loop found | N/A (orchestration framework) | none found | Tier 2 |
| stitionai/devika | ~19k | 0 | **0** | **none** | No | N/A | none | **Reject (B3)** — repo redirects to a successor product, 1 commit/year |
| danny-avila/LibreChat | ~28k | 2 | 266 test files | 29 workflows | Out of category — chat UI + sandboxed code-interpreter *service*, not a repo-editing agent | N/A | remote sandboxed interpreter (external service) | Tier 2, out-of-category for Q1-Q4 |
| google-gemini/gemini-cli | ~65k | 3 | 415 test files | 47 workflows | Model-driven only (no built-in gate); has an LLM-based edit self-corrector | exact + whitespace-flexible match, `allow_multiple` | none found in core | Tier 1 |
| openai/codex | ~35k | 3 | 1,915 Rust test files | 32 workflows, clippy+test+build | Model-driven only; `apply_patch` itself is strict, not a test gate | V4A context patch, strict context match | dedicated `sandboxing` crate: Seatbelt / bubblewrap / Windows MXC | Tier 1 — strongest sandbox of the set |
| QwenLM/qwen-code | ~10k | 3 | 2,358 test files | 60 workflows | Same as gemini-cli (fork) | Same as gemini-cli (fork) | none found | Tier 1 — fork that outgrew upstream's own test count |
| plandex-ai/plandex | ~14k | 1 | **6** `_test.go` files | **1 workflow** (docker-publish only) | **Yes, LLM-based** — validate-and-fix loop, escalates to a stronger model on failure | whole-file / structured-edit build step, LLM-validated | none found | Tier 2 on the idea, Tier 3 on own engineering |
| entropy-research/Devon | ~7k | 0 | 20 files (stale) | stale | No (dead project) | N/A | N/A | **Reject (B3)** — last commit 2024-07-29 |
| sourcegraph/cody / sourcegraph/amp | — | — | — | — | — | — | — | **Absent** — both return HTTP 404; no public source to evaluate |

---

## Verification loops, compared

**princeton-nlp/SWE-agent — strongest design.** The edit tool itself is the gate. Every call to
`edit <range>` runs `flake8` on the file before and after applying the change; if the edit
introduces *new* lint/syntax errors that weren't there before, the tool calls `wf.undo_edit()`,
reverting the write on disk, and returns the diff plus an explicit instruction not to retry the
same command blindly.
`SWE-agent/tools/windowed_edit_linting/bin/edit:95-122`. This is categorically different from
every other tool in the set: the bad code **never lands**, versus everyone else's
write-then-diagnose pattern.

**cline/cline & sst/opencode — automatic, built into the edit path.** cline diffs VS Code's
diagnostics collection before/after every write (`getNewDiagnostics`,
`cline/apps/vscode/src/integrations/diagnostics/index.ts:7`) and appends a `newProblemsMessage`
to the tool result (`cline/apps/vscode/src/core/prompts/responses.ts:264-300`) — the model sees
new compiler/linter errors on the very next turn, with zero opt-in required. opencode goes
further and calls the Language Server directly inside the edit tool itself:
`lsp.touchFile(filePath, "document")` then `lsp.diagnostics()`
(`sst-opencode/packages/opencode/src/tool/edit.ts:197-205`) — not a side "mention" feature, the
core tool call.

**Aider-AI/aider — bounded reflection loop.** `auto_lint` (default on) and `auto_test` (opt-in via
`--test`) run after every edit; failures are assigned to `self.reflected_message` and become the
next turn's user message, capped at `max_reflections = 3`
(`aider/aider/coders/base_coder.py:100-101,939-943,1599-1622`). This is the closest analog to a
classic CI retry budget inside a chat loop.

**princeton-nlp/SWE-bench — not an agent, but the reference *proof* of correctness.** See its own
section below.

**plandex-ai/plandex — LLM-graded, with model escalation.** `buildValidateLoop`
(`plandex/app/server/model/plan/build_validate_and_fix.go:44-106`) re-validates its own generated
diff against the target file, resets a retry counter per phase, and explicitly "switch[es] to [a]
stronger model after the first attempt failed" (line 98) — verification by asking a smarter model
to check the first model's work, rather than by running anything deterministic.

**OpenHands/software-agent-sdk — standard tool-error feedback, no fixed retry cap.** A failed
`str_replace` raises `ToolError`, which is caught and turned into
`FileEditorObservation(is_error=True)` (`openhands-tools/openhands/tools/file_editor/impl.py:68-71`)
— the loop is bounded only by the agent's own iteration/step budget, not a dedicated reflection
counter.

**No built-in loop at all — a real, reportable finding:**
- **gpt-engineer-org/gpt-engineer**: `_improve_loop` retries only on *diff-format-parsing*
  failure (`MAX_EDIT_REFINEMENT_STEPS`,
  `gpt-engineer/gpt_engineer/core/default/steps.py:315-334`); `execute_entrypoint` runs the
  generated program for a **human** to watch — its output is never fed back to the LLM
  (`steps.py:205-236`). No correctness verification exists.
- **microsoft/autogen**: Docker/Jupyter/Azure code executors exist
  (`autogen/python/packages/autogen-ext/src/autogen_ext/code_executors/`) but are opt-in
  components a user wires into a `CodeExecutorAgent` — there is no default write→verify→retry
  gate on every code-writing action.
- **crewAIInc/crewAI**: no default verification path found; it is an orchestration framework, and
  correctness is entirely the responsibility of whatever agent/tool the user configures.

**Which design is strongest, and why:** SWE-agent's pre-flight lint-and-rollback is the strongest
mechanism because it fails *closed* — a bad edit is refused, not merely flagged. Everything else
in the set (cline, opencode, aider, OpenHands) fails *open*: the bad edit lands on disk and the
model is merely told about it on the next turn, which is weaker whenever the loop terminates
early (budget exhaustion, user interruption) with broken code already written.

---

## Edit mechanics, compared

| tool | mode | match strategy | on failure |
|---|---|---|---|
| aider | SEARCH/REPLACE (also whole-file, udiff) | exact, character-for-character, first-occurrence-only | prompt literally demands exact match; no fuzzy fallback |
| SWE-agent | line-range replace | positional (`start:end`) | pre/post lint diff — rejects & rolls back on new errors |
| OpenHands SDK | `str_replace` | exact only; strip-and-retry once | `ToolError` if 0 or >1 matches — model must add context |
| cline (apply_patch) | context patch (OpenAI V4A grammar) | **tiered fuzzy**: exact → trimEnd → trim → similarity ≥ 0.66 | `DiffError` listing every skipped hunk + its best-match context |
| Roo-Code | SEARCH/REPLACE | Levenshtein similarity, **exact by default** (`fuzzyThreshold=1.0`, user-tunable) | error shows similarity %, required threshold, line-context of best guesses |
| goose | `string_replace` | exact only | "Did you mean: …" fuzzy suggestion + file preview; on N>1 matches, shows line context of the first two |
| opencode | `replace()` | exact-first; `replaceAll` opt-in | "Found multiple matches… provide more surrounding context" |
| gemini-cli / qwen-code | old_string/new_string | exact + a secondary whitespace-"flexible" pass | occurrence-count error; **also** an LLM-call self-corrector (`editCorrector.ts`) for a known escaping-bug class |
| codex | V4A context patch | strict context-line seek (`seek_sequence.rs`) | `ApplyPatchError::ComputeReplacements("Failed to find context…")` — no fuzzy fallback |
| plandex | whole-file / structured edits | LLM re-validates the diff against the file | `buildValidateLoop` retries, escalating model strength |
| gpt-engineer | unified-diff hunks | hunk must apply | format-only retry loop (not content-correctness) |

**Which approach best resists bloat, and why.** Every tool here is diff/patch-based, not
whole-file-rewrite — that is the real anti-bloat lever, and it is universal in this set (aider
still *offers* whole-file mode but defaults to SEARCH/REPLACE). Within diff-based editing, the
**strict, exact-match-first family (aider, OpenHands, codex, goose, opencode, Roo-Code's default)**
resists bloat better than cline's always-fuzzy tiers: a fuzzy match can silently apply a patch
against the *wrong* nearby code when a file has repeated structure, which is exactly the kind of
error that then requires more code to "fix," compounding growth. Exact-match-with-a-clear-error
forces the model to re-read and re-target — slower per attempt, but it never edits the wrong
place. SWE-agent's pre-flight lint-and-rollback is strictly stronger again: it prevents even a
*correctly targeted but lint-broken* edit from landing.

---

## Context selection / repo-map algorithms

**aider — the canonical implementation, explained precisely.** `aider/aider/repomap.py`:

1. **Parse.** `get_tags` (`repomap.py:233`) tree-sitter-parses every candidate file using
   per-language `.scm` tag queries (`get_scm_fname`, `repomap.py:805`), extracting `def` and `ref`
   tags — i.e. every identifier a file *defines* and every identifier it *references*.
2. **Build the symbol graph.** `get_ranked_tags` (`repomap.py:365`) collects these into
   `defines`/`references` dicts, then constructs an `nx.MultiDiGraph` where each node is a file and
   each edge `referencer → definer` is weighted by how "interesting" the identifier looks:
   snake/kebab/camel-case identifiers ≥8 chars get a 10× multiplier, identifiers referenced by
   the model's own message get another 10×, leading-underscore or promiscuously-defined (>5
   definers) identifiers get 0.1×, references from files already in the chat get 50×, and raw
   reference counts are square-root-dampened so high-frequency low-value mentions don't dominate
   (`repomap.py:472-511`).
3. **Rank.** `nx.pagerank(G, weight="weight", personalization=personalization, dangling=personalization)`
   (`repomap.py:525`) — a personalized PageRank where files already open in the chat, or files
   whose name matches something the user just typed, get a non-uniform personalization score
   (`repomap.py:382-445`), so the rank favors code near what's actually being discussed, not
   just globally central files.
4. **Fit a token budget.** `get_ranked_tags_map_uncached` (`repomap.py:629`) does a binary-search-like
   loop — starting from `num_tags // 25` — rendering successively larger/smaller slices of the
   ranked tag list into a tree-sitter-derived source outline (`render_tree`, `repomap.py:710`)
   until the rendered text's token count lands within tolerance of `max_map_tokens`
   (`repomap.py:660-710`).

The result: the model is shown a compressed, PageRank-ordered outline of the *whole* repo, biased
toward files it's already touching, that fits a fixed token budget — without ever dumping full
file contents it doesn't need.

**Others, more briefly.**
- **gemini-cli / qwen-code**: no repo-map; context is whatever the model explicitly reads via
  file/glob/grep tools, plus a `GEMINI.md`/project-memory file.
- **cline**: no PageRank-style map; relies on the model's own `search_files`/`list_files` tool
  calls plus an optional `@workspace_diagnostics` mention.
- **OpenHands SDK**: no repo-map; context is built from explicit tool calls (`grep`, `glob`,
  `file_editor view`) plus a condenser that summarizes old conversation turns
  (`openhands-sdk/openhands/sdk/context/condenser/`) — a different problem (long-conversation
  compression) than repo-selection.
- **SWE-agent**: no repo-map; the `windowed_edit_*` tools expose a scrolling file window instead.

Aider is the only tool in this set with a real graph-ranking context-selection algorithm; every
other agent relies on the model's own tool-calling to navigate the repo.

---

## Harvested system prompts (verbatim)

### Verification

`OpenHands/software-agent-sdk@main:openhands-sdk/openhands/sdk/context/prompts/sections/static.py`
```
<PROBLEM_SOLVING_WORKFLOW>
1. EXPLORATION: Thoroughly explore relevant files and understand the context before proposing solutions
2. ANALYSIS: Consider multiple approaches and select the most promising one
3. TESTING:
   * For bug fixes: Create tests to verify issues before implementing fixes
   * For new features: Consider test-driven development when appropriate
   * Do NOT write tests for documentation changes, README updates, configuration files, or other non-functionality changes
   * Do not use mocks in tests unless strictly necessary and justify their use when they are used. You must always test real code paths in tests, NOT mocks.
   * If the repository lacks testing infrastructure and implementing tests would require extensive setup, consult with the user before investing time in building testing infrastructure
   * If the environment is not set up to run tests, consult with the user first before investing time to install all dependencies
4. IMPLEMENTATION:
   * Make focused, minimal changes to address the problem
   * Always modify existing files directly rather than creating new versions with different suffixes
   * If you create temporary files for testing, delete them after confirming your solution works
5. VERIFICATION: If the environment is set up to run tests, test your implementation thoroughly, including edge cases. If the environment is not set up to run tests, consult with the user first before investing time to run tests.
</PROBLEM_SOLVING_WORKFLOW>
```

`SWE-agent/SWE-agent@main:tools/windowed_edit_linting/bin/edit`
```
_LINT_ERROR_TEMPLATE = """Your proposed edit has introduced new syntax error(s). Please read this error message carefully and then retry editing the file.

ERRORS:
{errors}

This is how your edit would have looked if applied
------------------------------------------------
{window_applied}
------------------------------------------------

This is the original code before your edit
------------------------------------------------
{window_original}
------------------------------------------------

Your changes have NOT been applied. Please fix your edit command and try again.
DO NOT re-run the same failed edit command. Running it again will lead to the same error."""
```

### Minimality / anti-bloat

`Aider-AI/aider@main:aider/aider/coders/base_prompts.py`
```
overeager_prompt = """Pay careful attention to the scope of the user's request.
Do what they ask, but no more.
Do not improve, comment, fix or modify unrelated parts of the code in any way!
"""

lazy_prompt = """You are diligent and tireless!
You NEVER leave comments describing code without implementing it!
You always COMPLETELY IMPLEMENT the needed code!
"""
```

`OpenHands/software-agent-sdk@main:openhands-sdk/openhands/sdk/context/prompts/sections/static.py`
```
<CODE_QUALITY>
* Write clean, efficient code with minimal comments. Avoid redundancy in comments: Do not repeat information that can be easily inferred from the code itself.
* Only add a comment when the code expresses something genuinely unintuitive (a non-obvious invariant, a workaround, a subtle ordering/locking requirement, or a deliberate trade-off). Do NOT restate the code, narrate the diff/change history, or describe non-local behavior — that context belongs in the PR description or commit message, not in the source.
* When implementing solutions, focus on making the minimal changes needed to solve the problem.
* Before implementing any changes, first thoroughly understand the codebase through exploration.
* If you are adding a lot of code to a function or file, consider splitting the function or file into smaller pieces when appropriate.
* Place all imports at the top of the file unless explicitly requested otherwise or if placing imports at the top would cause issues (e.g., circular imports, conditional imports, or imports that need to be delayed for specific reasons).
</CODE_QUALITY>
```

Model-specific addenda, same file:
```
"anthropic_claude": """\
* Try to follow the instructions exactly as given - don't make extra or fewer actions if not asked.
* Avoid unnecessary defensive programming; do not add redundant fallbacks or default values — fail fast instead of masking misconfigurations.
* When backward compatibility expectations are unclear, confirm with the user before making changes that could break existing behavior.""",
"google_gemini": """\
* Avoid being too proactive. Fulfill the user's request thoroughly: if they ask questions/investigations, answer them; if they ask for implementations, provide them. But do not take extra steps beyond what is requested.""",
```

`continuedev/continue@main:.github/workflows/auto-fix-failed-tests.yml` (prompt sent to their own agent)
```
Focus on:
- Understanding what the tests are trying to validate
- Identifying why they're failing (code changes, environment issues, test logic errors)
- Making minimal, targeted fixes that address the root cause
- Ensuring the fixes don't break other functionality
```

`sst/opencode@main:AGENTS.md`
```
- Do not extract single-use helpers preemptively. Inline the logic at the call site unless the helper is reused, hides a genuinely complex boundary, or has a clear independent name that improves the caller.
...
- Do not over-abstract simple expressions into many single-use helpers; extract only when it names a real concept like `requireConfig` or `readMetadata`.
```

### File creation

`OpenHands/software-agent-sdk@main:openhands-sdk/openhands/sdk/context/prompts/sections/static.py`
```
<FILE_SYSTEM_GUIDELINES>
* When a user provides a file path, do NOT assume it's relative to the current working directory. First explore the file system to locate the file before working on it.
* If asked to edit a file, edit the file directly, rather than creating a new file with a different filename.
* For global search-and-replace operations, consider using `sed` instead of opening file editors multiple times.
* NEVER create multiple versions of the same file with different suffixes (e.g., file_test.py, file_fix.py, file_simple.py). Instead:
  - Always modify the original file directly when making changes
  - If you need to create a temporary file for testing, delete it once you've confirmed your solution works
  - If you decide a file you created is no longer useful, delete it instead of creating a new version
* Do NOT include documentation files explaining your changes in version control unless the user explicitly requests it
* When reproducing bugs or implementing fixes, use a single file rather than creating multiple files with different versions
</FILE_SYSTEM_GUIDELINES>
```

### Scope discipline

`OpenHands/OpenHands@main:.agents/skills/custom-codereview-guide.md`
```
Out of scope here, because another repository owns it:

- reusable agent-server, runtime, SDK, and client contracts
  (`OpenHands/software-agent-sdk`);
- generic automation scheduling, state, dispatch, and profile machinery
  (`OpenHands/automation`); and
- reusable extensions, skills, plugins, and automation bundles
  (`OpenHands/extensions`).

Cross-repository work is acceptable when the PR contains only the Canvas-owned
integration and depends on public interfaces from the owning repository. When a
change belongs in one of the repositories above, say so and ask a maintainer to
confirm before reviewing the rest.
```

`RooCodeInc/Roo-Code@main:src/core/prompts/sections/rules.ts`
```
Some modes have restrictions on which files they can edit. If you attempt to edit a restricted file, the operation will be rejected with a FileRestrictionError that will specify which file patterns are allowed for the current mode.
```

### Code style

`sst/opencode@main:AGENTS.md`
```
- Avoid `try`/`catch` where possible
- Avoid using the `any` type
- Rely on type inference when possible; avoid explicit type annotations or interfaces unless necessary for exports or clarity
...
- Never alias imports. Do not use `import { foo as bar } from "..."` or renamed imports like `resolve as pathResolve`.
- Never use star imports. Do not use `import * as Foo from "..."` or `import type * as Foo from "..."`.
- Avoid `else` statements. Prefer early returns.
```

---

## SWE-bench verification model

`princeton-nlp/SWE-bench@main:swebench/harness/grading.py` is the reference implementation for
"how do you *prove*, not just claim, that a patch fixes a bug."

1. Every benchmark instance ships two pre-recorded test-name lists, computed once by the dataset
   maintainers by running the *gold* human patch: **FAIL_TO_PASS** (tests that fail on the
   unpatched repo and must pass after a correct fix) and **PASS_TO_PASS** (tests that already pass
   on the unpatched repo and must *keep* passing — the regression guard).
2. A candidate's patch is applied inside a per-instance Docker image
   (`build_instance_images`, `swebench/harness/run_evaluation.py:650`) via a fallback chain —
   `git apply --verbose`, then `--3way`, then `--reject` (`run_evaluation.py:55-57`) — and the
   outcome is recorded as `APPLY_PATCH_PASS`/`APPLY_PATCH_FAIL`.
3. The full test suite (or the relevant subset) runs inside the container; each test's outcome is
   parsed into a status map. `test_passed`/`test_failed`
   (`grading.py:85-108`) classify each `FAIL_TO_PASS`/`PASS_TO_PASS` case against that map — note
   `test_failed` explicitly treats a *skipped* FAIL_TO_PASS test as a failure, closing the
   loophole where a patch could make an inconvenient test simply not run.
4. `compute_fail_to_pass`/`compute_pass_to_pass` (`grading.py:292-306`) turn each list into a
   pass ratio; `get_resolution_status` (`grading.py:309-326`) assigns:
   - **FULL** — 100% of FAIL_TO_PASS now pass *and* 100% of PASS_TO_PASS still pass,
   - **PARTIAL** — some but not all FAIL_TO_PASS pass, PASS_TO_PASS fully maintained,
   - **NO** — anything else, including any PASS_TO_PASS regression.

The reusable idea for us: correctness is proven by a **before/after test-status diff against a
fixed, pre-recorded baseline**, not by re-running an LLM judge or trusting the agent's own "tests
pass" claim. F2P proves the fix is real; P2P proves nothing else broke. Both are required.

---

## Transferable mechanisms

Ranked by leverage — each entry names the failure class it prevents, not just what the tool does.

1. **Pre-flight verify-then-write, not write-then-verify (SWE-agent).** Run the check (lint,
   syntax, whatever is cheap) *before* committing an edit to disk, and roll back on regression.
   Prevents: broken code ever landing, even transiently, which is what silently compounds into
   "fix the fix" bloat when an agent's budget runs out mid-task.
2. **F2P/P2P-style before/after test diffing against a fixed baseline (SWE-bench).** Never trust
   "tests pass" from the same run that wrote the tests; snapshot which tests failed *before* the
   change and require the specific ones the change claims to fix to flip, while everything else
   stays green. Prevents: an agent reporting success because it weakened or deleted an
   inconvenient test.
3. **Bounded reflection/retry with the failure text as the next prompt (aider, cline, SWE-agent).**
   A fixed retry cap (aider: 3) stops infinite self-correction loops while still giving the model
   one deterministic signal — the actual compiler/linter/test output — instead of a vague "try
   again." Prevents: unbounded token spend on a task that isn't converging, and prevents silent
   failure (the loop terminates with an explicit "gave up" state instead of guessing forever).
4. **Exact-match-first edit tools with a loud, specific error (aider, OpenHands, codex, goose,
   opencode).** Refuse to guess when `old_string` doesn't match uniquely; report the similarity
   score / occurrence count / line context instead of silently picking the "closest" location.
   Prevents: patches landing on the wrong occurrence of a common code pattern — the single most
   dangerous class of bug in an autonomous edit loop, because it looks like success.
5. **Golden snapshot tests for the system prompt itself (OpenHands SDK).**
   `tests/sdk/context/prompts/snapshots/*.txt` locks the rendered prompt per
   provider/feature-flag combination. Prevents: a refactor of prompt-assembly code silently
   changing what the model actually sees, with no test failure to catch it.
6. **Automatic diagnostics/LSP feedback wired into the edit tool itself, not a side feature
   (opencode, cline).** The verification signal is attached to the *tool result* the model
   already reads, not a separate mention the model has to remember to request. Prevents: the
   model shipping a type/syntax error because nothing forced it to look.
7. **Literal minimality clauses in the system prompt, not just "be a good engineer" (aider's
   `overeager_prompt`, OpenHands' `CODE_QUALITY`, opencode's `AGENTS.md`).** Concrete, checkable
   sentences ("do not modify unrelated parts," "do not extract single-use helpers preemptively")
   rather than vibes. Prevents: scope creep and speculative abstraction — both are literally named
   as the failure mode in the source text, which is exactly the rubric's "no advice without a
   command" bar for a skill rule.
8. **File-creation restraint as an explicit rule, with the exact anti-pattern named
   (OpenHands' `FILE_SYSTEM_GUIDELINES`).** "NEVER create multiple versions of the same file with
   different suffixes (file_test.py, file_fix.py, file_simple.py)." Prevents: the most common
   concrete symptom of AI-driven repo bloat — abandoned near-duplicate files from failed attempts.
9. **CI-enforced dead-code detection (Roo-Code's `knip` in `code-qa.yml`, goose's
   `cargo-machete`).** A machine check, not a review comment, blocking merge on unused
   exports/dependencies. Prevents: bloat that a human reviewer stops noticing after the tenth PR.
10. **Model-strength escalation on repeated verification failure (plandex's `buildValidateLoop`).**
    Retry the *same* fix with a cheaper model twice, then escalate to a stronger model rather than
    retrying identically forever. Prevents: burning budget on a fix a weak model structurally
    cannot produce, while still trying the cheap path first.

---

## Notes on category and absence findings

- **stitionai/devika** and **entropy-research/Devon** are dead: zero recent commits, and in
  devika's case the README itself redirects readers to a successor project. Rubric B3 exists
  precisely for repos like these — high star count, no ongoing engineering, nothing to harvest.
- **sourcegraph/cody** and **sourcegraph/amp** have no public source at all (both 404) as of
  2026-09-28 — consistent with Sourcegraph's public sunsetting of Cody and Amp's closed-source
  distribution. Nothing to evaluate; reported as absence per rubric Part G rule 6, not invented.
- **danny-avila/LibreChat**, **microsoft/autogen**, and **crewAIInc/crewAI** are well-engineered
  by their own D1/D2 numbers but are the wrong *shape* for this study's Q1-Q4: LibreChat is a chat
  UI with a sandboxed remote code-interpreter, and autogen/crewAI are orchestration frameworks
  where verification is a capability a user composes, not a guarantee the framework provides by
  default. Their engineering quality is real; their applicability to "does this tool prove its own
  edits are correct" is not.
