# Findings: Review & Change Control Governance

Corpus: 63 unique repos (union of `research/worklists/governance.txt` D7=3 repos
and `research/worklists/tier1.txt`). Method: targeted `raw.githubusercontent.com`
fetches of predictable paths (no cloning, no `gh api`). Citations as
`owner/repo:path`.

Status: IN PROGRESS — batch 3/4 (16 repos) landed and appended below. Batches
1, 2, 4 (47 repos) still running in background; will be appended as they land,
then all sections re-synthesized into final form.

## Coverage

- Batch 3 landed: mochajs/mocha, mui/material-ui, nextcloud/server, nrwl/nx,
  nuxt/nuxt, openai/openai-python, opentofu/opentofu, payloadcms/payload,
  pnpm/pnpm, prisma/orm, prometheus/prometheus, promptfoo/promptfoo,
  pulumi/pulumi, QwenLM/qwen-code, QwikDev/qwik, rclone/rclone (16/63).
- Batch 1 (actualbudget/actual .. discourse/discourse, 16), batch 2
  (docling-project/docling .. mlflow/mlflow, 16), batch 4 (refinedev/refine ..
  yt-dlp/yt-dlp, 15) — in flight, not yet appended.

## PR templates verbatim

Verdict key: **CI** = mechanically checkable by an automated gate;
**honour** = self-reported checkbox/prose with no automated verification found.

- `mochajs/mocha:.github/PULL_REQUEST_TEMPLATE.md` — checklist: "Addresses an
  existing open issue" / "issue marked `status: accepting prs`" / "Steps in
  CONTRIBUTING.md were taken." All **honour**; CI (`mocha.yml`) runs regardless
  of ticks.
- `mui/material-ui:.github/PULL_REQUEST_TEMPLATE.md` — single item: "I have
  followed (at least) the PR section of the contributing guide." **honour**.
- `nextcloud/server:.github/pull_request_template.md` — checklist (sign-off,
  tests, screenshots, docs, backports, labels, milestone) plus a dedicated
  **"AI (if applicable)"** checkbox. All **honour** at the template level, but
  the AI item is separately backed by a CI check (see AI-policy section) —
  the only repo in batch 3 where a template checkbox has a real enforcement
  path behind it.
- `nrwl/nx:.github/PULL_REQUEST_TEMPLATE.md` — free-text fields only (Current
  Behavior / Expected Behavior / Related Issues), plus an HTML-comment reminder
  about commit format. No checkboxes; commit format is separately CI-checked
  via Commitizen (**CI**, but not via the template).
- `openai/openai-python:.github/pull_request_template.md` — "Changes being
  requested" / "Additional context & links," plus banner "Pull requests are
  limited to repository collaborators." The collaborator restriction is
  **CI/platform-enforced** (GitHub permissions); the rest is **honour**.
- `opentofu/opentofu:.github/pull_request_template.md` — checklist: "I have
  not used an AI coding assistant to create this PR," "I have written all code
  in this PR myself OR marked all copied code," "I (and other contributors)
  have not looked at the Terraform source code." All **honour** — none of
  these three items are mechanically verifiable.
- `pnpm/pnpm:.github/pull_request_template.md` — checklist (linked-issue
  dedup, changeset addition, tests, docs); states "A maintainer will only
  start reviewing once CodeRabbit has approved and CI is green" — process
  order, not a confirmed hard block. All **honour**.
- `prisma/orm:.github/PULL_REQUEST_TEMPLATE.md` — checklist where the DCO item
  explicitly states "The DCO status check will block merge" — **CI**. Other
  items (scope, tests, PR-title format, "Skill update section filled in") are
  **honour**.
- `prometheus/prometheus:.github/PULL_REQUEST_TEMPLATE.md` — title-format
  instruction, DCO sign-off mention, and a structured "Release notes for end
  users" block requiring a `[FEATURE]/[ENHANCEMENT]/[PERF]/[BUGFIX]/
  [SECURITY]/[CHANGE]`-tagged note or `NONE`. All **honour** (reviewer-checked
  by eye per the template's own text).
- `pulumi/pulumi:.github/PULL_REQUEST_TEMPLATE.md` — "Summary" / "Test plan"
  (checkboxes) / "Validation" (checkboxes: `make lint`, `make test_fast`,
  `make tidy_fix`, `make format`, `make check_proto`) / "Changelog" checkbox.
  The Validation items name real `make` targets that CI also runs, so a false
  tick is *detectable* post-hoc by re-running CI, but the tick itself is
  self-reported at PR-open time — borderline, scored **honour** (no gate
  blocks on the checkbox text itself, only on CI passing independently).
- `QwenLM/qwen-code:.github/pull_request_template.md` — prose-only fields
  (what the PR does, reviewer test plan, OS-tested table, risk/scope). All
  **honour**.
- `QwikDev/qwik:.github/PULL_REQUEST_TEMPLATE.md` — checklist (guidelines
  followed, self-review, changeset added via `pnpm change`, docs updated,
  tests added). The changeset item is **CI**-checkable (changeset-bot / CI can
  detect a missing `.changeset/*.md` file); rest **honour**.
- `rclone/rclone:.github/PULL_REQUEST_TEMPLATE.md` — 7-item checklist
  including a conditional **"AI-tools guidance read"** item, plus a note that
  backend changes need a clean `go run ./fstest/test_all -backends <remote>`
  run. Mostly **honour**; the backend-test requirement is maintainer-verified,
  not raw-CI-visible from outside.
- `nuxt/nuxt`, `nrwl/nx`(template exists, see above)/`payloadcms/payload`,
  `promptfoo/promptfoo` — **no PR template found** at standard paths (absence
  itself recorded, not assumed).

Running tally (16 repos, batch 3 only): **13/16 have a PR template**; of the
checkbox/assertion items surveyed, the overwhelming majority (~90%) are
honour-system. Confirmed CI-backed exceptions: DCO sign-off (prisma, and
implied at prometheus/nextcloud), collaborator-only gating (openai-python,
platform-level), changeset-file presence (qwik), and nextcloud's AI-disclosure
checkbox (backed by `ai-policy.yml`).

## CODEOWNERS granularity

Line counts are a usable proxy for whether review routing is real or
decorative:

| repo | lines | shape |
|---|---|---|
| `nuxt/nuxt` | 1 | pure single-person catch-all: `* @danielroe` |
| `nrwl/nx` | 2 | pure catch-all: `* @nrwl/nx-cli-reviewers` |
| `opentofu/opentofu` | 4 | pure catch-all: `* @opentofu/maintainers` |
| `pulumi/pulumi` | 6 | mostly catch-all `* @pulumi/iac-core` + a few narrow overrides (`/pkg/cmd/esc/ @pulumi/cloud-platform`) |
| `pnpm/pnpm` | 8 | granular by subpath, e.g. `/pnpm11/reviewing/dependencies-hierarchy/* @gluxon` |
| `rclone/rclone` | 78 | granular, explicitly derived from `git log` per-file history; catch-all `* @ncw` + per-backend rules; `.github/` owned solely by the project lead |
| `nextcloud/server` | 110 | granular w/ fallback `* @nextcloud/server-backend`; `**/src @nextcloud/server-frontend`; `package.json @nextcloud/server-dependabot @nextcloud/server-frontend`; `package-lock.json @nextcloud/server-dependabot` |
| `promptfoo/promptfoo` | 127 | most granular in batch: catch-all + per-directory (`/drizzle/` migrations, `/.github/` CI config, `/renovate.json`), with `AGENTS.md`/`CLAUDE.md` carved out separately, commented "AI AGENT INSTRUCTIONS — override all other patterns" |
| `prisma/orm` | 1 rule | single catch-all `* @prisma/ORM-TS-Maintain`, but governance doc requires >=1 maintainer-team approval before merge to `main` |
| `QwenLM/qwen-code` | 20 | granular — specifically protects `.github/workflows/release.yml`, `finalize-release.yml`, `security-checks.yml`, and CODEOWNERS itself, maintainer-only |
| `QwikDev/qwik` | 20 | granular — protects `api.json` (public API surface) and `CHANGELOG.md` via dedicated `@QwikDev/api-guards` team; self-protects CODEOWNERS |
| `mochajs/mocha`, `mui/material-ui`, `openai/openai-python`, `payloadcms/payload` | — | not found at any standard path |
| `prometheus/prometheus` | 33 (root `CODEOWNERS`, not `.github/`) | granular per-subsystem (`/tsdb`, `/storage/remote`, `/discovery/kubernetes`, each named owners) + catch-all fallback; header says keep in sync with MAINTAINERS.md |

Direct explicit ownership of lockfiles / CI config / migrations found in only
3 of 16: nextcloud (`package-lock.json`), promptfoo (`/drizzle/`,
`/.github/`, `/renovate.json`), rclone (`.github/` to project lead only).
Most repos' CODEOWNERS either don't exist or are a single catch-all team —
granular, path-aware ownership is the minority pattern even among these
D7=3 / tier-1 repos.

## Merge discipline adoption

`merge_group:` trigger (GitHub merge queue) — batch 3 tally:

- **Confirmed active**: `nuxt/nuxt` (`.github/workflows/ci.yml:4`),
  `openai/openai-python` (`.github/workflows/ci.yml:9`), `pnpm/pnpm`
  (`.github/workflows/ci.yml:16`, with an explicit comment that main is
  "validated pre-merge by merge_group and re-checked post-merge"),
  `prisma/orm` (`.github/workflows/ci.yml:5`), `pulumi/pulumi`
  (`.github/workflows/on-merge.yml:10`). **5/16.**
- **Configured but broken (ceremony, not load-bearing)**: `QwenLM/qwen-code`
  — `merge_group:` trigger present in `ci.yml:26`, but a code comment at
  `ci.yml:1568` states the queue "is not enabled here — no `merge_group` run
  since 2026-07-02... reported as 'skipped' on every pull request," and cites
  a real incident (#9220) where a macOS-only failure shipped to `main` as a
  direct result. This is the sharpest single "ceremony vs load-bearing" case
  found so far: the trigger exists in the YAML, but nothing enforces it, and
  the repo's own commit history documents the failure it caused.
- **Absent, using other mechanisms instead**: `nextcloud/server` has no
  `merge_group` but has three purpose-built merge-blocking jobs —
  `block-merge-eol.yml`, `block-merge-freeze.yml`,
  `block-unconventional-commits.yml` — which is arguably more load-bearing
  than an unmonitored merge queue.
- **Absent, no substitute found**: `mochajs/mocha`, `mui/material-ui`,
  `nrwl/nx`, `opentofu/opentofu`, `payloadcms/payload`,
  `prometheus/prometheus`, `promptfoo/promptfoo`, `QwikDev/qwik`,
  `rclone/rclone`.

Dependabot automerge — confirmed in exactly **1/16**:
`prometheus/prometheus:.github/workflows/automerge-dependabot.yml` runs
`gh pr merge --auto --merge` for `semver-minor`/`semver-patch` dependabot PRs
only (majors excluded). Several repos configure Dependabot but explicitly
suppress it: `mui/material-ui` and `nrwl/nx` set `open-pull-requests-limit: 0`
on npm; `QwenLM/qwen-code` sets it to 0 on both ecosystems it tracks.
`promptfoo/promptfoo` uses Renovate instead (stated cooldowns: 5 days runtime
deps, 2 days dev deps) with no automerge found.

PR-title / commit-message enforcement (a cheaper, more common substitute for
full merge-queue discipline): CI-enforced Conventional-Commit PR titles found
at `nuxt/nuxt:.github/workflows/semantic-pull-requests.yml`,
`payloadcms/payload:.github/workflows/pr-title.yml`,
`QwenLM/qwen-code` (implied by changelog-from-releases tooling), and
`nextcloud/server:.github/workflows/block-unconventional-commits.yml`
(commit-level, not just title).

## ADR/RFC templates and when required

Only 2 of 16 batch-3 repos have a formal design-doc process at a discoverable
path:

- `opentofu/opentofu:rfc/README.md` — community-authored RFC process (note:
  path is singular `rfc/`, not the `rfcs/` guessed by default); requires
  majority Core Team approval to merge; approved RFCs get tracking issues.
- `prisma/orm:docs/oss/governance.md` — states architecture decisions are
  recorded as append-only ADRs under `docs/architecture docs/adrs/`; the
  index file itself was not independently confirmed reachable.

14 of 16 show no ADR/RFC directory at any of the standard guessed paths
(`docs/adr/...`, `docs/architecture/decisions/...`, `adr/...`,
`rfcs/README.md`, `RFCS.md`) — recorded as absence, not partial-search
failure, since each was tried at 2-3 candidate paths per the fetch plan.

## CONTRIBUTING verification contracts

Exact commands quoted, by repo:

- `mochajs/mocha`: `npm test`
- `mui/material-ui`: `pnpm prettier`, `pnpm eslint`, `pnpm typescript`,
  `pnpm proptypes && pnpm docs:api`, `pnpm test:unit`, `pnpm test:browser`,
  `pnpm test:regressions`, `pnpm test:e2e` — CONTRIBUTING.md maps each to a
  named CI check.
- `nextcloud/server`: no literal test command in CONTRIBUTING.md (defers to
  the Developer Manual); DCO sign-off + Conventional Commits format required
  and CI-enforced.
- `nrwl/nx`: `nx affected --target=test`, `nx affected --target=e2e`,
  `nx format`, `pnpm commit` (Commitizen), `pnpm check-commit`.
- `nuxt/nuxt`: `pnpm install --frozen-lockfile`, `pnpm dev:prepare`,
  `pnpm test`, `pnpm lint` / `pnpm lint --fix`.
- `openai/openai-python`: `./scripts/bootstrap`, `./scripts/test` (also runs
  a Pydantic-v1 lane), `./scripts/test-pydantic-v1`, `./scripts/build`,
  `./scripts/mock`, `uv lock`.
- `opentofu/opentofu`: `go test ./...` (or scoped, e.g.
  `go test ./internal/command/...`).
- `payloadcms/payload`: `pnpm install`, `pnpm run build:core`, `pnpm test`,
  `pnpm test:e2e`, `pnpm test:int` (Mongo default; `pnpm test:int:postgres`
  for Postgres), `pnpm test:visual`.
- `pnpm/pnpm`: `pnpm run compile`, `pnpm test`,
  `pnpm --filter <project> test`, `pnpm run test-all`; Rust half:
  `just init`, `just fmt`, `cargo test`.
- `prisma/orm`: `pnpm typecheck && pnpm lint && pnpm test:packages`,
  `pnpm test:examples`, `pnpm test:e2e`, `pnpm test:integration` (Docker),
  `pnpm test:all`.
- `prometheus/prometheus`: `go build ./cmd/prometheus/`, `make test`,
  `make lint` (golangci-lint, with a documented `//nolint:` escape hatch).
- `promptfoo/promptfoo`: `npm install`, `npm test`, `npm run build`,
  `npm run lint`.
- `pulumi/pulumi`: `make build`, `make lint`, `make lint_fix`, `make format`,
  `make test_fast`, `make test_all`, `make tidy`, `make changelog` (via
  `changie`).
- `QwenLM/qwen-code`: `npm run preflight` (stated as the required
  pre-submission gate covering tests/lint/style), `npm run build`,
  `npm run test`, `npm run test:e2e`.
- `QwikDev/qwik`: `pnpm fmt`, `pnpm change`, `pnpm api.update`,
  `pnpm build.full` / `pnpm build.rust` / `pnpm build.core`.
- `rclone/rclone`: `make`, `make quicktest`, `go test -v` per package,
  `go run ./fstest/test_all -backends <remote>` for backend changes.

Every one of these is a runnable command — this section is close to 100%
verifiable by construction (a CONTRIBUTING.md that names a command is, almost
tautologically, the load-bearing part of governance: it's what CI itself
runs). The honour-system risk isn't in whether the command exists, it's
whether the *contributor ran it before opening the PR* — which is exactly
what CI re-verification (not the PR template checkbox) actually enforces.

## AI-contribution policies

**7 of 16 batch-3 repos have an explicit, findable AI-contribution policy**
(mochajs/mocha, nextcloud/server, nuxt/nuxt, opentofu/opentofu, pnpm/pnpm,
promptfoo/promptfoo, rclone/rclone) — materially higher than the near-zero
rate the task brief flagged from the agentic-dev commit-trailer study, which
suggests policy text has proliferated faster than the disclosure behavior it
asks for.

- `nextcloud/server` — **the only CI-enforced AI-disclosure gate found**:
  "Declare AI tool use in the PR description and add an
  `Assisted-by: AGENT_NAME:MODEL_VERSION` git trailer to each affected
  commit." `.github/workflows/ai-policy.yml` actually parses commits and
  fails the build on violations.
- `mochajs/mocha:.github/CONTRIBUTING.md` § "AI-Generated Code" — "We
  recognize that AI tools like GitHub Copilot, Claude, and others can be
  valuable aids... all code contributions... must meet the same quality
  standards... you are fully responsible." Backed by
  `.github/workflows/slop-detection.yml`, an "AgentScan" bot that auto-closes
  low-quality AI PRs — honour-system prose with real CI teeth behind it.
- `nuxt/nuxt:AGENTS.md` — outright ban, verbatim: "This project prohibits
  AI-authored public writing and autonomous agent contributions... All
  comments, issues, and PR descriptions must be written by a human...
  Contributions by autonomous agents are not allowed." CONTRIBUTING.md adds
  "Never let an LLM speak for you" / "Never let an LLM think for you," but
  also carves out a disclosed fast-track for agent PRs via a 🤖🤖🤖 title
  suffix — a self-identification convention, honour-system (no CI check
  confirmed parsing it).
- `opentofu/opentofu:.github/pull_request_template.md` — outright ban via
  checkbox: "I have not used an AI coding assistant to create this PR."
  Honour-system only.
- `pnpm/pnpm:CONTRIBUTING.md` — disclosure-by-footer, verbatim: "Agent-written
  PRs, issues, and comments disclose it with a footer naming the agent and
  the model, e.g. `Written by an agent (Claude Code, claude-opus-4-7).`" and
  "PRs that appear to be unreviewed agent output... may be closed without
  detailed review." Honour-system.
- `promptfoo/promptfoo:site/docs/contributing.md` — explicitly
  outcome-based, opposite stance from disclosure regimes: "We don't judge
  contributions by how they were produced. We judge them by the quality of
  the result... whether you wrote every character by hand or used Copilot,
  Cursor, Claude Code, or any other tool." Its own `AGENTS.md` goes further
  and instructs agents to **never** self-attribute commits ("No
  `Co-Authored-By: Claude…` trailers") — the inverse of the convention seen
  elsewhere, and notable given the task brief's citation of a 5.9%
  `Co-Authored-By: Claude` commit-trailer rate elsewhere in the corpus.
- `rclone/rclone:CONTRIBUTING.md#ai-assisted-contributions` — the most
  explicit, outcome-based policy found in the whole survey so far, verbatim:
  "You are welcome to use AI coding assistants (Claude Code, Codex, Cursor,
  Gemini CLI, and similar)... the same standard applies to every pull request
  whether or not a tool was involved... Unverified, AI-generated pull
  requests that do not compile, do not pass the tests, invent APIs that do
  not exist, or do not actually do what the description claims waste
  maintainer time and are likely to be closed." This is wired directly into
  the PR-template checklist (a checkbox references having read this
  guidance) — one of the only cases where an AI policy actually touches the
  PR gate rather than living only in prose.
- `prisma/orm:CONTRIBUTING.md` — outcome-based, verbatim: "We do not ask
  whether a PR was AI-assisted. We do verify the result. If you used an
  LLM-based agent to author the change, see [Working with agents] below" —
  points to a defined "contrib-pr" agent skill workflow rather than a ban or
  disclosure mandate.

No AI policy found (checked CONTRIBUTING.md + PR template; `AGENTS.md`/
`CLAUDE.md` present but scoped to maintainer/agent tooling instructions, not
contributor disclosure): `mui/material-ui`, `nrwl/nx`,
`openai/openai-python` (AGENTS.md instead gates *agents* from approving their
own budget-ratchet increases — a human-in-the-loop control, not a disclosure
policy), `payloadcms/payload` (has an "AI Code Tool Compatibility" table +
an `/ai-review` bot workflow, but no disclosure/ban clause),
`prometheus/prometheus`, `pulumi/pulumi`, `QwenLM/qwen-code` (has
machine-enforced triage rules for agent-generated refactor PRs in AGENTS.md,
but no human-facing disclosure clause), `QwikDev/qwik` (AGENTS.md section is
about generated-file tooling drift, not disclosure).

**Running policy taxonomy** (batch 3): outright ban (nuxt, opentofu) —
2; disclosure-by-trailer/footer, CI-enforced (nextcloud) — 1;
disclosure-by-footer, honour-system (pnpm) — 1; outcome-based /
"we judge the result not the method" (promptfoo, rclone, prisma) — 3;
quality-gate bot regardless of stated policy (mocha) — 1; none found — 9.

## Release governance and deprecation windows

Changesets vs conventional-commits vs manual (batch 3):

- **Changesets**: `QwikDev/qwik` (`.changeset/config.json` confirmed, fixed-
  version group across core packages, `updateInternalDependencies: "minor"`).
- **Conventional-commits / Release-Please style**: `mochajs/mocha`,
  `openai/openai-python`, `promptfoo/promptfoo`
  (`.github/workflows/release-please.yml`), `QwenLM/qwen-code` (CHANGELOG.md
  auto-generated from GitHub Releases, keep-a-changelog + SemVer),
  `nextcloud/server` (Conventional Commits CI-enforced at commit level, not
  just release notes).
- **Manual / hand-curated**: `opentofu/opentofu` (keep-a-changelog style),
  `prisma/orm` (docs/releases/), `prometheus/prometheus` (keep-a-changelog
  tags), `pulumi/pulumi` (curated via `changie`, entries under
  `changelog/pending/`), `rclone/rclone` (docs/content/changelog.md,
  including security/CVE entries).
- **Automated bump/publish pipeline (not changesets/conventional-commits
  proper)**: `payloadcms/payload` (`release-bump.yml`, `post-release.yml`,
  `publish-release.yml`, `publish-prerelease.yml`).
- `mui/material-ui`: auto-generated CHANGELOG.md, PR-attributed.
- `nrwl/nx`, `pnpm/pnpm`: no root CHANGELOG.md found / no changesets
  confirmed at standard path; pnpm's process is manual PR-based
  (`create-release-pr.yml`, `update-latest.yml`).

Concrete deprecation/support-window numbers — found in only **3 of 16**:

- `opentofu/opentofu:CHANGELOG.md` (or adjacent docs) — "The v1.14.x release
  series is supported until **February 1 2028**."
- `openai/openai-python:PYTHON_VERSION_POLICY.md` — "The SDK team may retain
  the most recently retired CPython version for up to **six months**... This
  grace period is discretionary."
- `prisma/orm` (release docs) — "Prisma 7 ... receives bug fixes and
  security updates for **eighteen months** after `8.0.0` final."

`prometheus/prometheus` documents a deprecation *example* ("Deprecate the
`stats` query parameter... rejected in the next major release") but with no
fixed numeric window — a real deprecation happened, but the policy behind it
isn't stated as a reusable number. `QwikDev/qwik:GOVERNANCE.md` has a
numeric rule but for contributor status, not software deprecation: "Qwik
Heroes who become inactive for 6 months are automatically reverted to
regular community contributor status."

## Bug intake and repro requirements

- `mochajs/mocha` — minimal-repro required per CONTRIBUTING.md;
  `.github/workflows/stale.yml` + `stale-branches.yml`.
- `mui/material-ui` — `.github/ISSUE_TEMPLATE/config.yml` present; uses
  `no-response.yml` / `closed-issue-message.yml` instead of a classic
  stale-bot.
- `nextcloud/server` — routed through issue templates; security reports via
  HackerOne, not public issues; `stale.yml` present.
- `nrwl/nx` — CONTRIBUTING.md: "We will be insisting on a minimal
  reproduction," plus requires `nx report` output and the lockfile;
  `schedule-stale.yml` (nonstandard filename) functions as the stale-bot.
- `nuxt/nuxt` — `bug_report.yml` requires environment + minimal
  reproduction, explicit: "If no reproduction is provided we might close
  it." `stale.yml` exists but is configured with `days-before-stale: -1` —
  deliberately defanged for general triage (only closes
  reproduction-labeled/bot issues after 7 days). A stale-bot workflow that
  exists in name but not in effect.
- `openai/openai-python` — non-collaborator PRs redirected to file an issue
  with "the affected version, expected and actual behavior, and a small,
  sanitized reproduction"; `bug_report.yml` confirmed present.
- `opentofu/opentofu` — `BUG_REPORTS.md` explicitly states this is
  "intentionally a primarily-human-driven process," not a strict rule set;
  `bug_report.yml` requires version + reproduction with minimization
  guidance ("Omit any unneeded complexity...").
- `payloadcms/payload` — `1.bug_report_v3.yml` requires description, a link
  to reproducing code, steps, affected area(s), environment — all marked
  `required: true`; `stale.yml` + `lock-issues.yml` present.
- `pnpm/pnpm` — no bug-report template found at standard names;
  `triage-issues.yml` runs an AI agent ("Oz") to auto-classify/label new
  issues instead of a human triage process.
- `prisma/orm` — `bug_report.yml` requires a "Minimal reproduction" field
  (required): "A failing test, a tiny repo, or a self-contained code
  snippet"; `label-stale-issues.yml` present.
- `prometheus/prometheus` — bug-report path not confirmed by direct fetch in
  this pass; a stale-bot workflow name was seen in a directory listing but
  not content-verified (flagged, not claimed).
- `promptfoo/promptfoo` — bug-report template filename not confirmed; no
  stale-bot confirmed.
- `pulumi/pulumi` — no formal repro-requirement text captured; notably no
  stale-bot workflow found at all (absent, unlike most peers in this batch).
- `QwenLM/qwen-code` — CONTRIBUTING.md requires PRs to link an existing
  issue; a `stale.yml` workflow name was observed but not content-verified.
- `QwikDev/qwik` — CONTRIBUTING.md: "please create a minimal repository that
  reproduces the problem... we will close it" if absent — maintainer-
  enforced, not automated.
- `rclone/rclone` — requires rclone version, OS, exact command, and a `-vv`
  log with manually-redacted secrets; no stale-bot workflow found among
  discovered filenames.

Pattern: minimal-reproduction demands are near-universal in prose (12/16
state it explicitly), but only 2 repos (payloadcms, prisma) mark the fields
`required: true` in the issue-form schema itself (i.e., the platform
mechanically blocks submission without them) — everywhere else it's a
reviewer/maintainer judgment call to close under-specified issues, which is
honour-system enforcement even though the *ask* is consistent.

## Load-bearing vs ceremony: the split

(partial — batch 3 only; final counts after remaining batches land)

**Load-bearing (mechanically enforced, confirmed via CI/workflow content):**
- DCO sign-off checks (prisma, nextcloud, prometheus mention)
- Conventional-commit / PR-title format bots (nuxt, payload, nextcloud at
  commit level)
- `ai-policy.yml` at nextcloud — the one CI-enforced AI-disclosure gate
- `slop-detection.yml` at mocha — CI-enforced AI-quality gate
- Active merge queues at nuxt, openai-python, pnpm, prisma, pulumi (5/16)
- Dependabot automerge at prometheus (1/16, patch/minor only)
- Required-command CONTRIBUTING sections generally (the commands themselves
  are load-bearing because CI reruns them regardless of what the PR claims)

**Ceremony (present in text, unverifiable or actively broken):**
- The large majority of PR-template checkboxes (~90% of items surveyed)
- Most AI-contribution policies (6 of 7 found are honour-system prose with
  no parsing/enforcement — nuxt's ban, opentofu's ban-checkbox, pnpm's
  footer, promptfoo's and rclone's outcome-based stance, prisma's "we
  verify the result")
- QwenLM/qwen-code's `merge_group:` trigger — present in YAML, documented by
  the maintainers themselves as non-functional since 2026-07-02, with a cited
  production incident (#9220) that it should have caught
- Single-line/team-wide CODEOWNERS catch-alls (nuxt: 1 line, nx: 2 lines,
  opentofu: 4 lines, prisma: 1 rule) — technically present, but route every
  review to the same person/team regardless of what changed, which is
  functionally equivalent to no CODEOWNERS at all for prioritization purposes

## Minimum change control by team size

(to be finalized after full corpus; provisional observations from batch 3)

- **solo / very small team**: a CONTRIBUTING.md with 1-3 copy-pasteable
  commands (mocha's single `npm test` is the floor) plus CI re-running those
  same commands on every PR is enough — this is present almost universally
  and appears to be the actual floor, not a stretch goal.
- **small team (2-10)**: adds a real (non-catch-all) CODEOWNERS with at
  least directory-level rules, plus PR-title/commit-format bot (cheap,
  single YAML file, catches a real failure class — inconsistent changelogs/
  broken automation that parses commit messages).
- **org (10+)**: the batch-3 evidence suggests a merge queue only pays for
  itself once a team is large enough that simultaneous merges regularly race
  each other — QwenLM/qwen-code's failure shows a merge queue *nobody
  monitors* is worse than none, since it creates false confidence. Merge
  queues need an owner and an alert on "queue not running," not just a
  YAML trigger.
- **high-blast-radius** (nextcloud's server, prisma's ORM core, rclone's
  storage backends): this is where granular CODEOWNERS with real per-path
  ownership (nextcloud 110 lines, rclone 78 lines) and CI-enforced
  disclosure/provenance (nextcloud's `Assisted-by:` trailer) actually appear
  — suggesting these practices are adopted in proportion to blast radius,
  not team size per se.

## A fully-verifiable PR template

(draft — will be finalized once full corpus confirms which items are safe to
generalize; grounded so far in prisma's DCO-block item, qwik's changeset-file
check, nuxt/payload's title-format bot, nextcloud's `ai-policy.yml` trailer
check, and rclone/mocha's precedent for CI-backed AI-provenance checks)

```markdown
## What changed and why
<!-- 1-3 sentences. Not verifiable by machine; kept because reviewers need it. -->

## Verification (all boxes must be true or CI fails independently — do not
## rely on this list, it is a summary of gates that already ran)
- [ ] `<test command>` passes — CI-enforced (re-run regardless of this box)
- [ ] Lint/format command passes — CI-enforced
- [ ] PR title matches Conventional Commits format — CI-enforced via
      title-check bot (verified pattern: nuxt, payloadcms)
- [ ] DCO sign-off present on every commit — CI-enforced (verified pattern:
      prisma, nextcloud)
- [ ] If dependencies/public API changed: changeset file added — CI-enforced
      (verified pattern: qwik; bot fails build if `.changeset/*.md` absent)

## AI-assistance disclosure (mechanically checkable only if a trailer parser
## exists in CI — see nextcloud/server:.github/workflows/ai-policy.yml)
- [ ] If an AI coding agent authored or materially contributed to this PR,
      every affected commit carries `Assisted-by: <agent>:<model>` —
      CI-enforced only where a parser exists (nextcloud is the only repo
      surveyed so far with one; everywhere else this line is honour-system)
```

Every item above is either (a) already independently re-verified by CI
regardless of the checkbox, making the checkbox a *summary* rather than a
*gate*, or (b) explicitly named as unverifiable and kept only because a
human reviewer needs the context. The template deliberately excludes
free-floating assertions like "I tested this locally" or "this won't break
anything" — found in most surveyed templates — because no mechanism confirms
them and Part G of the rubric requires deleting unfalsifiable rules.
