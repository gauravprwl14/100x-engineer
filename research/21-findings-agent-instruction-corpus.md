# Findings: The Agent-Instruction-File Corpus

Method: probed 61 target repos (raw.githubusercontent.com HEAD) for `AGENTS.md`, `CLAUDE.md`,
`.cursorrules`, `.github/copilot-instructions.md`, `.windsurfrules`, `GEMINI.md`, `.clinerules`,
`.junie/guidelines.md`. One repo name was corrected (`duckduckgo/duckduckgo-android` does not
exist; the real repo is `duckduckgo/Android`). Star counts and file-level last-commit dates pulled
via `gh api graphql`. 89 raw files saved to scratchpad `agentfiles/`. `.cursor/rules/*` directory
enumeration was blocked by GitHub API rate limiting shared across concurrent research sessions and
was not completed — this is a gap, not a null result, and is called out below.

## Corpus

48 of 61 repos (79%) had at least one target file. Stars and dates as of 2026-09-28.

| repo | stars | file(s) found | lines | file last modified |
|---|---|---|---|---|
| n8n-io/n8n | 206,181 | AGENTS.md, CLAUDE.md→@AGENTS.md | 408 | 2026-09-25 |
| microsoft/vscode | 193,208 | .github/copilot-instructions.md, AGENTS.md→pointer | 156 | 2026-09-25 |
| huggingface/transformers | 166,755 | .ai/AGENTS.md, .github/copilot-instructions.md, AGENTS.md/CLAUDE.md→symlink | 40 / 39 | 2026-09-07 |
| langchain-ai/langchain | 147,191 | AGENTS.md | 390 | 2026-09-23 |
| vercel/next.js | 142,827 | AGENTS.md | 527 | 2026-09-24 |
| excalidraw/excalidraw | 133,140 | CLAUDE.md, AGENTS.md (4-line stub), .github/copilot-instructions.md | 34 / 4 / 45 | 2025-05-25 |
| kubernetes/kubernetes | 128,068 | AGENTS.md | 38 | 2026-08-12 |
| facebook/react-native | 126,753 | AGENTS.md | 73 | 2026-09-16 |
| microsoft/TypeScript | 111,253 | .github/copilot-instructions.md | 141 | 2026-09-08 |
| supabase/supabase | 110,852 | AGENTS.md, .github/copilot-instructions.md | 75 / 87 | 2026-09-26 |
| denoland/deno | 108,544 | CLAUDE.md, .github/copilot-instructions.md | 433 / 352 | 2026-07-30 |
| oven-sh/bun | 96,069 | CLAUDE.md, AGENTS.md→pointer(CLAUDE.md) | 240 | 2026-09-21 |
| zed-industries/zed | 90,995 | .rules (target of AGENTS/CLAUDE/GEMINI symlinks) | 190 | 2026-09-27 |
| vllm-project/vllm | 92,858 | AGENTS.md | 158 | 2026-08-20 |
| home-assistant/core | 91,193 | AGENTS.md, .github/copilot-instructions.md, CLAUDE.md→pointer | 56 / 195 | 2026-08-04 |
| astral-sh/uv | 90,243 | AGENTS.md | 33 | 2026-09-22 |
| django/django | 91,226 | .github/copilot-instructions.md (see Anomalies) | 10 | 2026-03-12 |
| laravel/laravel | 85,030 | AGENTS.md, CLAUDE.md (identical duplicate) | 47 / 47 | 2026-08-25 |
| elastic/elasticsearch | 78,021 | AGENTS.md, CLAUDE.md→@AGENTS.md | 184 | 2026-09-10 |
| grafana/grafana | 76,963 | AGENTS.md, CLAUDE.md→@AGENTS.md | 172 | 2026-08-21 |
| apache/superset | 74,946 | AGENTS.md, CLAUDE.md/GEMINI.md/copilot-instructions.md→symlink/pointer | 321 | 2026-09-14 |
| strapi/strapi | 73,249 | AGENTS.md, CLAUDE.md→@AGENTS.md | 262 | 2026-08-20 |
| ghostty-org/ghostty | 61,630 | AGENTS.md | 39 | 2026-04-08 |
| appwrite/appwrite | 57,497 | AGENTS.md, CLAUDE.md→@AGENTS.md | 308 | 2026-09-23 |
| rails/rails | 58,782 | AGENTS.md | 201 | 2026-06-03 |
| mattermost/mattermost | 39,210 | AGENTS.md | 17 | 2026-09-09 |
| PostHog/posthog | 39,978 | AGENTS.md, .cursorrules (legacy, distinct content) | 317 / 24 | 2026-09-25 |
| directus/directus | 37,989 | AGENTS.md, .github/copilot-instructions.md | 239 / 265 | 2026-09-18 |
| medusajs/medusa | 36,504 | CLAUDE.md | 447 | 2026-09-28 |
| ray-project/ray | 43,939 | AGENTS.md | 99 | 2026-07-14 |
| discourse/discourse | 47,918 | AI-AGENTS.md (target of AGENTS/CLAUDE/GEMINI symlinks) | 98 | 2026-09-03 |
| apache/airflow | 46,999 | AGENTS.md, CLAUDE.md→pointer | 250 | 2026-09-25 |
| astral-sh/ruff | 49,820 | AGENTS.md, CLAUDE.md→@AGENTS.md | 212 | 2026-09-21 |
| vercel/ai | 27,011 | AGENTS.md | 320 | 2026-08-24 |
| sst/sst (now anomalyco/sst) | 26,327 | CLAUDE.md, AGENTS.md→pointer(CLAUDE.md) | 30 | 2026-04-19 |
| tursodatabase/turso | 24,417 | AGENTS.md, CLAUDE.md→pointer | 166 | 2026-09-27 |
| gitlabhq/gitlabhq | 24,552 | AGENTS.md, CLAUDE.md (identical duplicate) | 71 / 71 | 2026-09-23 |
| temporalio/temporal | 23,334 | AGENTS.md, .github/copilot-instructions.md | 105 / 138 | 2026-08-26 |
| elastic/kibana | 21,302 | AGENTS.md | 103 | 2026-09-17 |
| bluesky-social/social-app | 18,311 | AGENTS.md, CLAUDE.md→@AGENTS.md | 588 | 2026-09-06 |
| tldraw/tldraw | 50,618 | AGENTS.md, CLAUDE.md→@AGENTS.md | 228 | 2026-09-26 |
| element-hq/element-web | 13,520 | AGENTS.md | 202 | 2026-09-15 |
| mozilla-mobile/firefox-ios | 13,050 | AGENTS.md, CLAUDE.md→@AGENTS.md | 45 | 2026-05-19 |
| calcom/cal.com (now calcom/cal.diy) | 48,710 | AGENTS.md, CLAUDE.md→pointer | 244 | 2026-04-15 |
| cloudflare/workers-sdk | 4,588 | AGENTS.md, CLAUDE.md (5-line pointer w/ prose) | 157 / 5 | 2026-09-23 |
| wordpress-mobile/WordPress-iOS | 3,906 | AGENTS.md, CLAUDE.md→@AGENTS.md | 74 | 2026-07-16 |
| duckduckgo/Android | 4,835 | CLAUDE.md | 138 | 2026-08-19 |
| sst/opencode (now anomalyco/opencode) | 210,533 | AGENTS.md | 161 | 2026-06-25 |

**NOT-FOUND (13/61, 21%)** — no AGENTS.md/CLAUDE.md/.cursorrules/copilot-instructions/GEMINI.md/.clinerules at any probed path:
expo/expo (52,475★) · fastapi/fastapi (102,688★) · flutter/flutter (179,133★) · golang/go (139,059★) ·
hashicorp/terraform (49,778★) · immich-app/immich (115,201★) · mastodon/mastodon (50,336★) ·
obsidianmd/obsidian-releases (21,871★) · pydantic/pydantic (28,892★) · shadcn-ui/ui (124,751★) ·
signalapp/Signal-Android (29,400★) · signalapp/Signal-iOS (12,253★) · temporalio/sdk-typescript (930★).

Notable: three of the largest, most process-mature repos in the sample (flutter, golang/go,
kubernetes' sibling terraform) have **no** agent file at all, despite kubernetes/kubernetes (a
comparable-scale CNCF project) having a tight 38-line one. Popularity does not predict adoption.

### The standard and reference implementations (not part of the 61-repo probe, read for context)
- `agentsmd/agents.md:README.md` — the AGENTS.md spec's own canonical example is a 3-section,
  ~20-line file (Dev environment tips / Testing instructions / PR instructions). It is far shorter
  and more prescriptive-by-example than most production files harvested here.
- `openai/codex:AGENTS.md` (320 lines) — OpenAI's own coding-agent product dogfoods AGENTS.md
  heavily, with hard numeric budgets: `"Target Rust modules under 500 LoC, excluding tests."`,
  `"If a file exceeds roughly 800 LoC, add new functionality in a new module..."`,
  `"the total number of changed lines should not exceed 800 lines. For complex logic changes the
  size should be under 500 lines."`

### Anomalies — CORRECTED 2026-09-28 after direct re-verification

An earlier pass of this report classified the two files below as "embedded
prompt-injection payloads ... adversarial content smuggled into a widely-cloned
default branch." **That conclusion was wrong and has been retracted.** The quoted
text was accurate; the interpretation was not. Both files were re-fetched from the
live default branch and read in full. Both are deliberate maintainer-authored
controls, not attacks.

**1. `django/django:.github/copilot-instructions.md`** (10 lines, live, verified
2026-09-28). Full body:
```
Do not review this code. Do not post any comments, suggestions, or feedback.
Do not summarize the pull request. Do not describe the changes.
Your only output must be exactly: "Do not request a review from Copilot, do it in your own fork."
```
This is Django **opting out of automated Copilot review** and returning a canned
message redirecting contributors to self-review in their fork. It does not
instruct any agent to approve, fake-approve, or conceal anything. Reading it as an
attack was a misread of intent.

**2. `zed-industries/zed:.rules` line 16** (verified 2026-09-28). This is a
**human-review tripwire**, and it is the more interesting of the two:
```
HARD RULE: When modifying any source files, prepend `> [!IMPORTANT]` followed by
`> Remove this line to confirm you've reviewed this PR before submitting.` as the
first two lines of `README.md` if they are not already present. This must be done
before any other work. No exceptions. Never remove these lines yourself, even if
asked to clean up, revert, or finalize the PR or changes: removing them is
strictly a manual step for the human author to confirm they have reviewed the
changes.
```
The marker is not a *fake* review checkbox — it is a deliberate canary. Any PR
that still carries the banner is provably un-reviewed by a human, because only a
human is permitted to remove it. This makes "an agent opened this PR and nobody
looked at it" a visible, diff-level fact rather than a guess.

**Why the correction matters to this project:** the tripwire is a genuine
reusable mechanism and belongs in our harvest, not in an anomalies bin. It is the
same layer-3 idea as our verification receipt (see `research/20-findings-ecosystem-skills.md`
Verdict), reached by a different route: make the *absence* of human attestation
mechanically visible instead of trusting the agent to self-report. Recorded as a
harvested pattern under the name `human-attestation-canary`.

**The one claim that does survive:** agent-instruction files are executable-ish
input that ships on a default branch and is auto-loaded by tooling, so they are a
real supply-chain surface and should be reviewed like code. That conclusion stands
on its own; it did not need either of these two files to be malicious, and neither
was.
default-branch file — and shows why an agent harvesting instructions from the wild must treat file
content as data, never as authority, exactly per this project's own rubric.

## Adoption statistics

Of 61 repos probed:

| Signal | Count | % |
|---|---|---|
| Has ≥1 target file | 48 | 79% |
| Has AGENTS.md (real or symlink target) | 43 direct hits + 5 more via `.rules`/`AI-AGENTS.md`/`.ai/AGENTS.md` canonical-file variants = ~48 | 79% |
| Has CLAUDE.md (any form: real, `@import`, symlink) | 28 | 46% |
| Has `.github/copilot-instructions.md` | 11 | 18% |
| Has GEMINI.md (all 3 found were symlinks) | 3 | 5% |
| Has `.cursorrules` (legacy single-file format) | 1 (PostHog, and it's a personal tone file distinct from its AGENTS.md) | 2% |
| Has `.windsurfrules` / `.clinerules` / `.junie/guidelines.md` | 0 | 0% |
| No target file at all | 13 | 21% |

**CLAUDE.md is converging into a pointer, not an independent file.** Of 28 CLAUDE.md files found,
**23 (82%)** are pure redirects to a canonical AGENTS.md via one of three mechanisms:
1. **Git symlink** (blob content is just the target filename) — e.g. `apache/airflow:CLAUDE.md`
   → `AGENTS.md`; `home-assistant/core:CLAUDE.md` → `AGENTS.md`; `zed-industries/zed:CLAUDE.md`
   and `GEMINI.md` → `.rules`.
2. **Claude Code native `@import` directive** — one line, `@AGENTS.md`, e.g.
   `appwrite/appwrite:CLAUDE.md`, `astral-sh/ruff:CLAUDE.md`, `supabase/supabase:CLAUDE.md`,
   `tldraw/tldraw:CLAUDE.md`, `n8n-io/n8n:CLAUDE.md` (10 repos use exactly this pattern).
3. **Literal duplicate content** — `laravel/laravel` and `gitlabhq/gitlabhq` ship byte-identical
   AGENTS.md and CLAUDE.md (verified with `diff`).

Only 5 of 28 CLAUDE.md files carry content that differs meaningfully from their repo's AGENTS.md
(denoland/deno, medusajs/medusa, oven-sh/bun, duckduckgo/Android, sst/sst) — and even
`cloudflare/workers-sdk:CLAUDE.md`, one of the "independent" ones, is 5 lines whose only
substance is `See @AGENTS.md`. **AGENTS.md is functioning as the single source of truth; CLAUDE.md
is legacy compatibility plumbing.** This is the single strongest structural finding in the corpus.

## Verification demands (the highest-value section)

Grouped by stack. Every line is copied verbatim from the cited file.

### JS/TS (pnpm/yarn/npm monorepos)
- `pnpm --filter=next types` — "~10s type-error check, faster than build" — vercel/next.js:AGENTS.md
- `pnpm lint # Full lint (types, prettier, eslint, ast-grep)` — vercel/next.js:AGENTS.md
- `pnpm new-test --args true my-feature e2e` — "Generating tests using `pnpm new-test` is mandatory." — vercel/next.js:AGENTS.md
- `pnpm type-check:full # Run from workspace root` — vercel/ai:AGENTS.md
- `pnpm check # Run linting (oxlint) and formatting (oxfmt) checks` — vercel/ai:AGENTS.md
- `Always use these pnpm scripts, never call the underlying tools directly` guarding `pnpm test`, `pnpm lint`, `pnpm typecheck` — bluesky-social/social-app:AGENTS.md
- `yarn type-check:ci --force # Type check (always run before pushing)` — calcom/cal.com:AGENTS.md
- `TZ=UTC yarn test # Run unit tests` — calcom/cal.com:AGENTS.md
- `pnpm typecheck` / `pnpm api-check` (validates public API reports) — tldraw/tldraw:AGENTS.md
- `pnpm typecheck # typecheck all packages` — supabase/supabase:AGENTS.md
- `yarn test:unit && yarn test:front && yarn test:ts && yarn lint && yarn prettier:check` (minimum pre-PR bar) — strapi/strapi:AGENTS.md
- `npx hereby validate # Build, test, lint, and format the project`, with an explicit PR-blocking checklist: `"YOU MUST RUN THESE COMMANDS AT THE END OF YOUR SESSION! IF THESE COMMANDS FAIL, CI WILL FAIL, AND YOUR PR WILL BE REJECTED OUT OF HAND."` — microsoft/TypeScript:.github/copilot-instructions.md
- `npm run typecheck-client for the main sources under src/`, `scripts/test.sh ... Add a targeted selector such as --grep whenever possible` — microsoft/vscode:.github/copilot-instructions.md
- `pnpm agent:lint` and `pnpm agent:typecheck` (full-repo gates); `pnpm agent:setup` chains install→build→test — n8n-io/n8n:AGENTS.md
- `Always offer to run yarn test:app in the project root after modifications are complete and attempt fixing the issues reported` — excalidraw/excalidraw:.github/copilot-instructions.md
- `Full lint (types, format, js, styles, workflows, knip) | pnpm lint`; `pnpm coverage:diff` with target `"Aim for ≥80% coverage on the diff; CI checks this."` — element-hq/element-web:AGENTS.md

### Python
- `uv run --project <PROJECT> pytest path/to/test.py::TestClass::test_method -xvs` (single test) — apache/airflow:AGENTS.md
- `Never run pytest, python, or airflow commands directly on the host — always use breeze.` — apache/airflow:AGENTS.md
- `uv run ruff format <file_path>` and `uv run ruff check --fix <file_path>` "immediately after writing or editing" — apache/airflow:AGENTS.md
- `Target exactly 100% coverage of what the PR changes — no more, no less.` — apache/airflow:AGENTS.md
- `hogli test <file_or_directory>` — auto-detects Python/Jest/Playwright/Rust/Go — PostHog/posthog:AGENTS.md
- `run mypy the way CI does — uv run mypy --cache-fine-grained ., repo-wide, never a file subset.` — PostHog/posthog:AGENTS.md
- `.venv/bin/python -m pytest tests/path/to/test_file.py -v`; `Never use system python3 or bare pip/pip install. All Python commands must go through uv and .venv/bin/python.` — vllm-project/vllm:AGENTS.md
- `make fixup` — apply style/consistency fixes; `Code style is enforced in the CI.` — huggingface/transformers:.github/copilot-instructions.md
- `make style` (ruff format+lint), `make typing` (ty + model-structure rules), `make check-repo` — huggingface/transformers:.ai/AGENTS.md
- `uv run --no-sync pytest`; `uv run --no-sync prek run --all-files` "After finishing a code session" — home-assistant/core:AGENTS.md
- `pytest tests/unit_tests/specific_test.py # Single file`; `curl -f http://localhost:8088/health || echo "❌ Setup required..."` — apache/superset:AGENTS.md
- `make test` (unit tests, no network); `make lint` / `make format`; `uv run --group lint mypy .` — langchain-ai/langchain:AGENTS.md

### Rust
- `cargo nextest run` with `INSTA_FORCE_PASS=1 INSTA_UPDATE=always MDTEST_UPDATE_SNAPSHOTS=1` prefix; `cargo clippy --workspace --all-targets --all-features -- -D warnings`; `Get your tests to pass. If you didn't run the tests, your code does not work.` — astral-sh/ruff:AGENTS.md
- `NEVER perform builds with the release profile, unless asked`; `cargo xwin clippy` for cross-compile checks — astral-sh/uv:AGENTS.md
- `cargo build # build. never build with --release`; `cargo clippy --workspace --all-features --all-targets -- --deny=warnings`; `make -C sqlite/conformance run-rust ARGS='--snapshot-filter __never__'` — tursodatabase/turso:AGENTS.md
- `just test -p codex-tui` then `cargo insta pending-snapshots -p codex-tui` then `cargo insta show ...` before `cargo insta accept -p codex-tui` — openai/codex:AGENTS.md
- `Do not run cargo test directly. Use just test so test execution follows the repo defaults.` — openai/codex:AGENTS.md
- `cargo build --bin deno`; `Do NOT run these directly with ./target/debug/deno test — they depend on the cargo test harness for correct setup.` — denoland/deno:CLAUDE.md

### Go
- `make test WHAT=./pkg/kubelet GOFLAGS=-v # Unit tests (one package)`; `make verify # All verification checks`; `make update # ALL generators and formatters` — kubernetes/kubernetes:AGENTS.md
- `make lint-code-fast` (fast Go lint on changed packages); `make unit-test`; always `-tags test_dep` — temporalio/temporal:AGENTS.md
- `go test -run TestName ./pkg/services/myservice/`; `make test-go-unit`; `make lint-go` — grafana/grafana:AGENTS.md
- `node scripts/check.js --scope=local|staged|branch` (Jest+types+lint in one gate) — elastic/kibana:AGENTS.md

### Other stacks
- `./gradlew jvm_checks` (spotless+lint+unit tests in one gate); `./gradlew spotlessApply`; `./gradlew :my-feature-impl:testDebugUnitTest --tests "..."` — duckduckgo/Android:CLAUDE.md
- `docker compose exec appwrite test tests/e2e/Services/[Service] --filter=[Method]`; `composer analyze` (PHPStan level 4); `composer refactor:check` (Rector dry-run, CI "Refactor" check) — appwrite/appwrite:AGENTS.md
- `bin/qunit path/to/test-file.js`; `bin/lint --fix path/to/file` once "before handing off completed changes, committing, or pushing" — discourse/discourse:AI-AGENTS.md
- `Run the full suite with xcodebuild -workspace WordPress.xcworkspace -scheme WordPress -testPlan WordPressUnitTests test. Do not use swift test.` — wordpress-mobile/WordPress-iOS:AGENTS.md
- `zig build test`; `zig build test -Dtest-filter=<test name>`; `zig fmt .` — ghostty-org/ghostty:AGENTS.md
- `./script/clippy` instead of `cargo clippy` (repo-specific wrapper) — zed-industries/zed:.rules
- `bundle exec rubocop`; `bundle exec rake test:sqlite3 # Default` — rails/rails:AGENTS.md

## Prohibitions and anti-bloat rules

### No new files / prefer editing
- `Prefer editing existing files over creating new files. Do not add new documentation files unless requested.` — tldraw/tldraw:AGENTS.md
- `Avoid writing new files into the /view directory and subdirectories.` / `Avoid writing new top-level subdirectories within /src.` — bluesky-social/social-app:AGENTS.md
- `Default: add your test to the existing test file for the code you're changing. Do not create a new file.` — oven-sh/bun:CLAUDE.md
- `Default: add coverage to the narrowest existing test harness that can express the bug. Prefer extending an existing test file or directory over creating a new one.` — tursodatabase/turso:AGENTS.md
- `A new docs/** file requires a person to request that specific document in the current conversation. Existing related docs, PR checklists, and general docs requirements do not authorize one.` — PostHog/posthog:AGENTS.md
- `Do not create a class unless it is a well-defined domain concept... Do not create Helper, Utils, or similarly named classes or methods.` — appwrite/appwrite:AGENTS.md
- `Never create files with mod.rs paths - prefer src/some_module.rs instead of src/some_module/mod.rs.` — zed-industries/zed:.rules

### No new dependencies
- `Never add a dependency without checking for existing alternatives in the repo.` — elastic/elasticsearch:AGENTS.md
- `NEVER assume a library/framework is available or appropriate.` / `Do not introduce new third party libraries unless specifically requested.` — temporalio/temporal:AGENTS.md
- `NEVER update all dependencies in the lockfile and ALWAYS use cargo update --precise to make lockfile changes.` — astral-sh/uv:AGENTS.md
- `Small amounts of straightforward functionality are implemented directly rather than through a new dependency.` — temporalio/temporal:.github/copilot-instructions.md
- `Add new dependencies without running pnpm update-references` listed under `## Do Not` — vercel/ai:AGENTS.md
- `don't add new dependencies unless strictly required — when you do, justify them` — langchain-ai/langchain:AGENTS.md

### No touching generated code
- `Never hand-edit generated files. Instead, edit the source they are generated from and regenerate.` — elastic/elasticsearch:AGENTS.md
- `Never hand-edit zz_generated.* or generated.pb.go. Run make update.` — kubernetes/kubernetes:AGENTS.md
- `Never hand-edit api.schemas.ts, api.ts or api.zod.ts — change the serializer and regenerate.` — PostHog/posthog:AGENTS.md
- `Never modify *.generated.ts files directly - they're created by app-store-cli.` — calcom/cal.com:AGENTS.md
- `the modeling file should never be edited directly! Instead, changes should be made in the modular file` — huggingface/transformers:.github/copilot-instructions.md
- `Never hand-edit generated files: packages/api-types/types/**, **/routeTree.gen.ts, **/__generated__/**` — supabase/supabase:AGENTS.md
- `NEVER write migration files by hand` — medusajs/medusa:CLAUDE.md
- `Do not edit src/generated or src/generated-effect directly.` — sst/opencode:AGENTS.md

### No comments (or comment discipline)
- `Default to no comment: prefer self-documenting code... Never add: narration of trivial code, conversational/temporal residue, process/plan references.` with a code example of each violation class — duckduckgo/Android:CLAUDE.md
- `Do not add comments. Instead, focus on making your code expressive.` — tursodatabase/turso:AGENTS.md
- `NEVER talk to the user or describe your changes through comments.` — temporalio/temporal:AGENTS.md
- `Minimize use of comments. Eliminate comments which are redundant, preferring legible and self-documenting code.` — vllm-project/vllm:AGENTS.md
- `Comment discipline — cap comments at 1-3 lines and only add one when the why is non-obvious... delete comments that just restate the code, by default, not only when asked to trim.` — gitlabhq/gitlabhq:AGENTS.md
- `Do not add comments that just restate the code on the following line(s)` / `Do not add section or divider comments... since those can easily become stale and be misleading.` — home-assistant/core:.github/copilot-instructions.md
- `Never include links (Slack, GitHub, Jira, etc.) in code comments.` — grafana/grafana:AGENTS.md
- `In core, never name plugin features or specific libraries in comments/docs — describe by mechanism` — discourse/discourse:AI-AGENTS.md
- `After every code comment you write, ask yourself, "Is this information the next Claude would spend multiple tool calls trying to understand?". If the answer isn't clearly yes, the code comment is noise - delete it.` — oven-sh/bun:CLAUDE.md
- `If you need a paragraph-long comment to justify why the workaround is OK, the code is wrong — fix the code.` — oven-sh/bun:CLAUDE.md
- `Do not write organizational or comments that summarize the code.` — zed-industries/zed:.rules

### No reformatting / scope discipline
- `Follow existing formatting in the file; do not reformat unrelated code.` — elastic/kibana:AGENTS.md
- `This repo does not use prettier or eslint — running prettier here reformats files against the project style and reports failures that do not exist.` — element-hq/element-web:AGENTS.md
- `Keep changes focused — avoid over-engineering` — grafana/grafana:AGENTS.md
- `Keep changes scoped to the request and the affected package. Do not refactor unrelated code.` — tldraw/tldraw:AGENTS.md
- `Keep each change focused — no unrelated refactors, formatting, or dependency updates.` — facebook/react-native:AGENTS.md
- `Never edit unrelated files; keep diffs tightly scoped to the task at hand.` — elastic/elasticsearch:AGENTS.md
- `no refactors, cleanups, or unrelated improvements, and no edits outside the repo you were pointed at` — gitlabhq/gitlabhq:AGENTS.md
- `Keep changes minimal and focused; avoid drive-by changes.` — denoland/deno:.github/copilot-instructions.md

### PR-size / abstraction budgets
- `Never create large PRs (>500 lines or >10 files) - split them instead.` — calcom/cal.com:AGENTS.md
- `Unless the change is mechanical the total number of changed lines should not exceed 800 lines. For complex logic changes the size should be under 500 lines.` — openai/codex:AGENTS.md
- `Target Rust modules under 500 LoC, excluding tests. If a file exceeds roughly 800 LoC, add new functionality in a new module instead of extending the existing file...` — openai/codex:AGENTS.md
- `Do not open one-off PRs for tiny edits (single typo, isolated style change, one mutable default, etc.).` — vllm-project/vllm:AGENTS.md, ray-project/ray:AGENTS.md (same policy, both repos)
- `Pure code-agent PRs are not allowed. A human submitter must understand and defend the change end-to-end.` — ray-project/ray:AGENTS.md, vllm-project/vllm:AGENTS.md
- `Do not optimize for reuse at all costs. A little duplication is better than an abstraction that is harder to follow.` — appwrite/appwrite:AGENTS.md
- `Do not jump through extra layers. Extract a method only when it improves clarity... not because a block is used once.` — appwrite/appwrite:AGENTS.md
- `resist adding code to codex-core! ... before adding to codex-core, consider whether there is an existing crate... or it is time to introduce a new crate` — openai/codex:AGENTS.md
- `Do not create small helper methods that are referenced only once.` — openai/codex:AGENTS.md

### No AI attribution / no process leakage
- `Do not add "Co-Authored-By" or any AI attribution trailers to commit messages, by any means—including --trailer, -m, or any other git flag.` — elastic/elasticsearch:AGENTS.md
- `Never list an agent as a commit co-author.` — apache/airflow:AGENTS.md
- `Do not add Co-authored-by: in commit messages` — kubernetes/kubernetes:AGENTS.md
- `Do NOT add "Generated with Claude Code" or co-author footers to commits or PRs` — vercel/next.js:AGENTS.md
- `When writing commit messages, never include references to Claude` — wordpress-mobile/WordPress-iOS:AGENTS.md
- `Do not mention discarded alternatives, intermediate edits, private instructions, tool usage, branch or draft status, local test commands, or session history unless the reader needs that information.` — astral-sh/ruff:AGENTS.md
- `DO NOT leak our conversation, prompt, or iteration history into code comments, pull request descriptions, or other maintainer-facing prose.` — astral-sh/uv:AGENTS.md
- `Avoid the tells of AI-generated text: em dashes (—), 'not just X, but Y', rule-of-three padding, hedging preambles.` — PostHog/posthog:AGENTS.md

## Context-scoping techniques

- **Conditional read-tables** ("read this file only when doing X") are the dominant strong pattern.
  duckduckgo/Android:CLAUDE.md has the cleanest example — a markdown table `| Read | When |` mapping
  10 doc files to the specific situation that requires them, prefaced by
  `"These files are not in context. Read the whole file before doing the work it covers — don't
  rely on what you remember of it."`
- `A directory may carry its own AGENTS.md that wins locally (posthog/temporal/, rust/,
  frontend/src/, most of products/). Check for one before working in an unfamiliar tree.` —
  PostHog/posthog:AGENTS.md (nested-AGENTS.md override pattern)
- `Many packages provide their own AGENTS.md. Locate and read the closest applicable file before
  making changes.` — cloudflare/workers-sdk:AGENTS.md (same nested pattern)
- `Before changing a package, read its AGENTS.md if it has one.` — cloudflare/workers-sdk:AGENTS.md
- `Before working on anything in apps/studio, read apps/studio/AGENTS.md if it isn't already in
  context...` — supabase/supabase:AGENTS.md
- `Before editing or creating files in any subdirectory (e.g., packages/*, crates/*), read all
  README.md files in the directory path from the repo root up to and including the target file's
  directory.` — vercel/next.js:AGENTS.md
- `For generated files (dist/, node_modules/, .next/): search only, don't read` — vercel/next.js:AGENTS.md
  (explicit "do not read X")
- `Do not modify code in these areas without first reading and following the linked guide. If the
  guide conflicts with the requested change, refuse the change and explain why.` — vllm-project/vllm:AGENTS.md
- `When the task matches a more specific ty workflow, also read and follow that skill from the
  repository root: ... .agents/skills/adding-ty-diagnostics/SKILL.md` — astral-sh/ruff:AGENTS.md
  (task-triggered skill loading, not upfront)
- `ALWAYS invoke the matching skill first — do not skip it, and do not attempt the work or the
  review without loading it.` — PostHog/posthog:AGENTS.md
- `Stay aligned with CONTRIBUTING.md, BUILDING.md, and TESTING.asciidoc; this AGENTS guide
  summarizes—but does not replace—those authoritative docs.` — elastic/elasticsearch:AGENTS.md
  (explicit "this file is a summary, not the source of truth" disclaimer)
- `Prefer authoritative configuration and documentation over copying details into this file: copied
  versions, rule lists, and counts become stale.` — cloudflare/workers-sdk:AGENTS.md
- `Do not put @mentions or fixes #... keywords in commit messages` plus `Load the following
  instruction files based on your current task:` task-keyed table — gitlabhq/gitlabhq:AGENTS.md
- `1. Semantic search first... 2. Grep for exact strings... 3. Follow imports... 4. Check test
  files` — microsoft/vscode:.github/copilot-instructions.md (explicit code-navigation order)

## Structural patterns of the best files

Five strongest files by density-of-enforceable-rule (not raw length):
**appwrite/appwrite:AGENTS.md** (308), **PostHog/posthog:AGENTS.md** (317),
**vercel/next.js:AGENTS.md** (527), **duckduckgo/Android:CLAUDE.md** (138),
**tursodatabase/turso:AGENTS.md** (166).

What they do that weak files don't:

1. **Tag every rule with its enforcement mechanism.** PostHog is explicit about this as policy:
   `"Each rule is tagged with what catches a violation. [lint: <id>] means a linter, semgrep rule,
   or invariant test blocks it... [review] means nothing catches it automatically — a reader is the
   only control."` — PostHog/posthog:AGENTS.md. Example tagged rule: `"A stdlib @dataclass must
   declare frozen= explicitly. [lint: prefer-frozen-dataclasses, test_dataclass_defaults.py]"`.
   This is the single clearest instance of the rubric's D1/anti-bloat distinction (lint-enforced
   vs. honor-system) being made *by the source file itself*, not inferred by us.
2. **Give the good/bad code pair, not just the prose rule.** appwrite/appwrite:AGENTS.md and
   duckduckgo/Android:CLAUDE.md both follow every "don't do X" with a fenced code block showing the
   violating pattern (`count++ // increment the counter -> narration of trivial code`). Files that
   only state the rule in prose (e.g. rails/rails:AGENTS.md) are harder to self-check against.
3. **State a meta-rule for editing the rules file itself.** zed-industries/zed:.rules: `"After any
   agentic session, ... What NOT to put in .rules — Avoid architectural descriptions of a crate...
   No drive-by additions."` ray-project/ray:AGENTS.md has a whole numbered section "3. Editing these
   instructions." This prevents the file itself from becoming the bloat it warns against.
4. **Say explicitly this file is a pointer, not the source of truth**, when that's true — the best
   short files (cloudflare/workers-sdk:AGENTS.md, elastic/elasticsearch:AGENTS.md) state it, rather
   than silently duplicating CONTRIBUTING.md and drifting out of sync.
5. **Distinguish "always read" from "read on demand."** vercel/next.js:AGENTS.md: `"Use skills for
   conditional, deep workflows. Keep baseline iteration/build/test policy in this file."` — splits
   the 527-line file into an always-loaded core plus named skills (`$pr-status-triage`,
   `$create-pr`) fetched only when relevant, avoiding a single monolithic context dump.

Weak files, by contrast, are flat, undifferentiated bullet lists with no enforcement tags and no
distinction between mandatory and situational guidance (e.g. astral-sh/uv:AGENTS.md, mattermost:AGENTS.md,
laravel/laravel:AGENTS.md — the latter is a bootstrap stub for a third-party tool, not
hand-authored project guidance at all).

## Length vs quality

| Bucket | Lines | Example | Quality signal |
|---|---|---|---|
| Stub/pointer | 0–10 | microsoft/vscode:AGENTS.md (5), django:copilot-instructions.md (10, review opt-out) | Length says nothing — both are legitimate; one redirects, one opts out of review |
| Minimal | 17–47 | mattermost (17), astral-sh/uv (33), ghostty (39), kubernetes (38), laravel (47) | Terse but not weak: kubernetes' 38 lines carry 4 concrete `make` verification commands and 5 explicit "never" rules — high rule-density despite low line count |
| Mid | 100–250 | duckduckgo/Android (138), turso (166), PostHog/posthog:AGENTS.md (317) | This is where the most-cited, most copy-pasteable files cluster |
| Long | 300–530 | appwrite (308), vercel/ai (320), langchain (390), n8n (408), vercel/next.js (527) | Longest files are monorepos with genuinely heterogeneous subsystems (frontend/backend/CLI/docs); length tracks repo surface area, not verbosity for its own sake |
| Outlier | 588 | bluesky-social/social-app:AGENTS.md | Longest in corpus; still organized into 13 clearly-scoped H2 sections, not padding |

**No linear correlation between length and quality.** kubernetes/kubernetes (38 lines) and
appwrite/appwrite (308 lines) are both Tier-1-strength by rule density; astral-sh/uv (33 lines,
flat unstructured bullet list) and calcom/cal.com (244 lines, well-organized with a `## Do` / `## Don't`
split) sit at opposite quality levels despite similar-to-different lengths. What correlates with
quality is **structure** (named sections, enforcement tags, read-when tables) and **specificity**
(a named command, a named lint rule, a numeric budget) — not word count. The weakest files in the
corpus are short *and* unstructured (flat bullet dumps); the strongest short files (kubernetes,
ghostty) are short *because* they defer detail to `make verify` / `CONTRIBUTING.md` rather than
restating it.

## Synthesis: the 15 rules that recur most across serious repos

Ranked by number of distinct repos observed using the pattern (of 48 repos with a file).

| # | Rule | Repos (≈) | Citation 1 | Citation 2 |
|---|---|---|---|---|
| 1 | Never hand-edit generated/derived files — change the source and regenerate | 10+ | kubernetes/kubernetes:AGENTS.md `"Never hand-edit zz_generated.* or generated.pb.go. Run make update."` | elastic/elasticsearch:AGENTS.md `"Never hand-edit generated files. Instead, edit the source they are generated from and regenerate."` |
| 2 | No AI/agent attribution in commits or PRs | 8+ | apache/airflow:AGENTS.md `"Never list an agent as a commit co-author."` | vercel/next.js:AGENTS.md `"Do NOT add 'Generated with Claude Code' or co-author footers to commits or PRs"` |
| 3 | Comments explain *why*, never *what*; delete narration | 15+ | duckduckgo/Android:CLAUDE.md `"Comments explain the why... not the what"` | gitlabhq/gitlabhq:AGENTS.md `"cap comments at 1-3 lines and only add one when the why is non-obvious"` |
| 4 | A single named command is the proof-of-done ("run this before you claim it works") | 30+ | apache/superset:AGENTS.md `"Always run pre-commit against the files changed by the current branch before pushing."` | microsoft/TypeScript:.github/copilot-instructions.md `"YOU MUST RUN THESE COMMANDS AT THE END OF YOUR SESSION!"` |
| 5 | Keep diffs scoped; no drive-by refactors/reformatting | 12+ | elastic/elasticsearch:AGENTS.md `"Never edit unrelated files; keep diffs tightly scoped to the task at hand."` | facebook/react-native:AGENTS.md `"Keep each change focused — no unrelated refactors, formatting, or dependency updates."` |
| 6 | Prefer editing/extending an existing file over creating a new one | 8+ | tldraw/tldraw:AGENTS.md `"Prefer editing existing files over creating new files."` | tursodatabase/turso:AGENTS.md `"Prefer extending an existing test file or directory over creating a new one."` |
| 7 | Don't add a dependency without checking for an existing alternative first | 8+ | elastic/elasticsearch:AGENTS.md `"Never add a dependency without checking for existing alternatives in the repo."` | astral-sh/uv:AGENTS.md `"NEVER update all dependencies in the lockfile"` |
| 8 | Never suppress the type-checker/linter — fix the root cause | 6+ | elastic/kibana:AGENTS.md `"Never suppress type errors with @ts-ignore... fix the root cause."` | astral-sh/ruff:AGENTS.md `"prefer to use #[expect()] over [allow()]"` |
| 9 | Small/no-value PRs and pure-agent PRs are rejected outright | 3 (verbatim shared policy) | ray-project/ray:AGENTS.md `"Pure code-agent PRs are not allowed. A human submitter must understand and defend the change end-to-end."` | vllm-project/vllm:AGENTS.md (identical policy language) |
| 10 | Directory-local AGENTS.md overrides the root one; check before working in an unfamiliar tree | 5+ | PostHog/posthog:AGENTS.md `"A directory may carry its own AGENTS.md that wins locally... Check for one before working in an unfamiliar tree."` | cloudflare/workers-sdk:AGENTS.md `"Many packages provide their own AGENTS.md. Locate and read the closest applicable file..."` |
| 11 | Numeric size/complexity budgets (PR line count, module LoC) | 5+ | calcom/cal.com:AGENTS.md `"Never create large PRs (>500 lines or >10 files)"` | openai/codex:AGENTS.md `"Target Rust modules under 500 LoC... total changed lines should not exceed 800"` |
| 12 | This file is a summary/pointer, not the source of truth — defer to CONTRIBUTING/docs | 6+ | elastic/elasticsearch:AGENTS.md `"this AGENTS guide summarizes—but does not replace—those authoritative docs"` | cloudflare/workers-sdk:AGENTS.md `"Prefer authoritative configuration and documentation over copying details into this file"` |
| 13 | CLAUDE.md is a pointer, not a second document — `@AGENTS.md` or symlink | 23 of 28 CLAUDE.md files | appwrite/appwrite:CLAUDE.md — full content `"@AGENTS.md"` | grafana/grafana:CLAUDE.md — full content `"@AGENTS.md"` |
| 14 | Never leak session/process/tool-usage narration into commit messages, PR bodies or code | 6+ | astral-sh/ruff:AGENTS.md `"Do not mention discarded alternatives, intermediate edits, private instructions, tool usage... unless the reader needs it"` | astral-sh/uv:AGENTS.md `"DO NOT leak our conversation, prompt, or iteration history into code comments, pull request descriptions..."` |
| 15 | Run the narrowest/fastest check first, broaden only if needed | 6+ | appwrite/appwrite:AGENTS.md `"Run the narrowest command that validates the change... before broadening."` | vercel/next.js:AGENTS.md `"~10s type-error check, faster than build"` as the recommended first gate |

Runner-up patterns that didn't make the top 15 but recurred 3+ times: DCO/human-accountability
requirement for AI-assisted PRs (ray-project/ray, vllm-project/vllm), explicit "never force-push /
never rebase a pushed PR branch" (denoland/deno, home-assistant/core, element-hq/element-web), and
tagging every convention with `[lint: id]` vs `[review]` (PostHog/posthog is the only file that does
this as a systematic scheme, but n8n-io/n8n and vercel/ai both cite specific enforcing lint-rule
names inline).
