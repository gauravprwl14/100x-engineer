# Signal Rubric v1

The screening contract. Every repo in the corpus is admitted or rejected by these
rules, and every skill produced downstream must cite repos that passed them.

Design principle: **a signal is a file on disk or a number from the API.**
If a criterion cannot be checked by `gh api` or `grep`, it is not a signal — it is
an opinion, and it does not belong here.

---

## Part A — Admission gate (ALL must pass)

| # | Gate | Hard threshold | How checked |
|---|------|----------------|-------------|
| A1 | Popularity | `stargazers_count >= 20000` | API |
| A2 | Alive | `pushed_at` within 90 days of screen date | API |
| A3 | Sustained | `>= 500` commits in trailing 12 months | API (commit activity) |
| A4 | Not solo | `>= 20` distinct committers in trailing 12 months | API (contributors) |
| A5 | Not archived | `archived == false && disabled == false` | API |
| A6 | Not a fork | `fork == false` | API |
| A7 | Licensed | `license != null` (we must be able to read & adapt) | API |
| A8 | Ships software | Repo builds/publishes a runnable artifact or library — see B | tree probe |
| A9 | Has a quality system | `>= 1` CI workflow AND `>= 1` automated test signal | tree probe |

A repo failing **any** A-gate is out. No exceptions, no "but it's famous".

---

## Part B — Noise exclusion (ANY match = reject)

The 20k-star tier is dominated by content, not software. These are rejected
**before** any deep read, by name pattern and by tree shape.

### B1. Name/topic patterns (regex, case-insensitive)
```
awesome-?         ^awesome        -roadmap$        roadmap$
free-programming  interview       coding-challenge  leetcode
cheatsheet        cheat-sheet     ^every-programmer ^project-based
build-your-own    ^system-design  ^tech-interview  ^computer-science
^the-book-of      ^papers         ^resources       ^guide(s)?$
^tutorial         ^course         ^learn-          ^30-seconds
^public-apis      ^dev-?roadmap   ^clean-code      ^design-patterns
^hello-world      ^demo           ^example         ^starter
^boilerplate      ^template       ^dotfiles        ^config(s)?$
```

### B2. Tree-shape rejects
- `> 70%` of tracked files are `.md`/`.rst`/`.txt` and there is no build manifest
  → content repo, not software.
- No dependency/build manifest at all (`package.json`, `pyproject.toml`,
  `setup.py`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle*`, `Gemfile`,
  `composer.json`, `CMakeLists.txt`, `Makefile`) → not a buildable artifact.
- Only file types are images/PDF/data → asset dump.

### B3. Category rejects (judgment, applied by the screening agent with a cited reason)
- **Model weights / dataset mirrors** — no engineering system to learn from.
- **Single-binary curiosities with no test suite** — nothing to harvest.
- **AI-agent frameworks with no production deployment story.** This one matters:
  a 40k-star agent framework whose own repo has 3 tests and no CI teaches us
  nothing about reliability. Judge the repo's *own* engineering, never its topic.

> The B3 rule is the sharpest edge of this rubric. Star count measures attention.
> We are buying evidence of engineering discipline, and those correlate weakly.

---

## Part C — Production-reality evidence (need >= 2 of 5)

"Running in production with real users" is not directly observable from a repo,
so we require converging proxies.

| # | Evidence | Probe |
|---|----------|-------|
| C1 | Published releases with semver cadence | `>= 12` releases, latest within 180d |
| C2 | Distribution channel | on npm / PyPI / Docker Hub / pkg.go.dev / app store, with download volume |
| C3 | Named production adopters | `ADOPTERS.md`, `USERS.md`, or a README users section |
| C4 | Operational surface | `SECURITY.md` + a published vuln/CVE history, or a status page |
| C5 | Migration/upgrade discipline | `CHANGELOG.md` with breaking-change notes, or `migrations/`, or codemods |

---

## Part D — Extraction schema (what we harvest from admitted repos)

This is the payload. Each deep-read produces one JSON record per repo.
Absence is data: record `false`, never guess.

### D1. Verification stack — *how do they know it works?*
- test layers present: `unit | integration | e2e | contract | property | fuzz | snapshot | mutation | perf-regression | visual`
- test runner(s) and config path
- coverage gate: threshold value + enforcing file
- typecheck strictness: `tsconfig.strict`, `mypy --strict`, `pyright`, `go vet`
- required CI checks (branch protection where visible)
- pre-commit / pre-push hook config
- **the single command a contributor runs to prove a change is good** ← highest-value field

### D2. Anti-bloat mechanisms — *how do they stop the codebase growing garbage?*
- dead-code detection: `knip`, `ts-prune`, `depcheck`, `vulture`, `deadcode`, `unimport`
- bundle/size budgets: `size-limit`, `bundlewatch`, `bundlesize`, custom CI assertion
- API-surface review: `api-extractor`, `.api.md` goldens, `cargo-public-api`
- dependency-addition policy: text in CONTRIBUTING, or a CI check on lockfile diff
- file/LOC budgets or complexity limits in lint config
- codegen boundaries: what is generated vs hand-written, and how drift is caught
- monorepo hygiene: task graph, affected-only builds, ownership boundaries

### D3. Agentic-development artifacts — *the direct ask*
- `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/`, `.github/copilot-instructions.md`,
  `.windsurfrules`, `GEMINI.md`, `.clinerules`
- `.claude/skills/`, `.claude/agents/`, `.claude/commands/`, `.claude/hooks/`,
  `.claude/settings.json`
- MCP server config
- **verbatim excerpts of the rules they give AI agents** ← harvest the text, not a summary
- evidence of AI-authored commits and what gate they had to pass

### D4. Correctness ratchets
- typed boundaries at the edge: `zod`, `pydantic`, `io-ts`, `valibot`, protobuf, OpenAPI
- error-handling convention (Result types, sentinel errors, exception policy)
- exhaustiveness enforcement
- DB migration safety: reversibility, expand/contract, zero-downtime rules
- feature flags / progressive rollout / canary
- invariant checks, assertions, runtime contracts

### D5. Security posture
- SAST (CodeQL, Semgrep), dependency scanning (Dependabot, Renovate),
  secret scanning, SBOM, artifact signing (sigstore/cosign)
- fuzzing (OSS-Fuzz membership)
- OpenSSF Scorecard
- `SECURITY.md` disclosure policy + response SLA
- authz test patterns

### D6. Reliability & operations
- structured logging, tracing, metrics conventions
- SLO definitions in-repo
- runbooks / incident docs
- graceful degradation, timeout/retry/backoff/circuit-breaker patterns
- rollback mechanism

### D7. Review & change control
- `CODEOWNERS` granularity
- PR template: what it forces an author to assert
- RFC / ADR / design-doc process
- merge-queue, required approvals, stacked-diff tooling

---

## Part E — Scoring

Per repo, per dimension D1-D7: `0` absent · `1` present · `2` enforced in CI · `3` exemplary + documented rationale.

`signal_score = sum(D1..D7)` → max 21.

- **Tier 1 (>= 15)** — primary source. Deep-read every file, harvest verbatim.
- **Tier 2 (10-14)** — secondary. Harvest specific strong dimensions only.
- **Tier 3 (< 10)** — corpus member for breadth stats; no harvesting.

A repo may be Tier 1 on one dimension and Tier 3 overall — record per-dimension
scores so a weak repo with one world-class practice is not discarded.

---

## Part F — Stack allocation

Weighted to the stated stack: JavaScript/TypeScript and Python primary, Go on deck.

| Cluster | Target | Rationale |
|---------|--------|-----------|
| JS/TS — frameworks, build tools, runtimes | 55 | primary stack |
| JS/TS — production apps (real users) | 35 | primary stack, app-shaped |
| Python — web, data, ML infra | 50 | primary stack |
| Go — infra, distributed systems | 40 | stated next stack |
| Mobile — RN, Flutter, native iOS/Android | 30 | stated target |
| Agentic-dev tooling (judged on own engineering) | 25 | direct ask |
| Reliability/security exemplars (any language) | 25 | the "doesn't break" requirement |
| **Total** | **260** | |

Rust/C/C++/Java repos are admitted **only** as reliability/security exemplars
(D5/D6 harvesting) — e.g. SQLite's test culture, curl's release discipline.
We take the practice, not the language.

---

## Part G — Anti-goals

Guardrails against the failure modes of exactly this kind of research.

1. **No cargo-culting.** A practice is only harvested with the problem it solves.
   "Kubernetes does X" is not a reason; "X catches failure class Y, which appears
   when Z" is.
2. **No advice without a command.** Every skill rule ships a runnable check or it
   is deleted. Prose that cannot fail is decoration.
3. **No skill without a failure mode.** If a rule never rejects anything, cut it.
4. **Scale-appropriate.** Kubernetes' process would sink a 3-person team. Tag every
   practice with the team size / blast radius where it starts paying for itself.
5. **No unsourced claims.** Every assertion carries `owner/repo@ref:path`.
6. **Absence is a finding.** If the top 50 repos have no AI-agent config, that is a
   headline result, not a gap to paper over with invention.

---

# Revisions

## v2 — 2026-09-28, after first full run against 1124 repos

v1 was written before seeing data. Four rules were wrong. Recorded here rather
than silently patched, because the calibration is itself a finding.

### R1. A3 lowered: 500 → 250 commits / 12 months
**Why:** 500/yr (~10 commits/week) excluded mature, stable, genuinely-maintained
production libraries — `axios/axios` (469), `ionic-team/ionic-framework` (462),
`iina/iina` (460), `react-hook-form/react-hook-form` (392). These are exactly the
repos we want to learn from; a stable library in maintenance is not an abandoned
one. 500 was measuring *churn*, not *life*. 250/yr (~5/week) still excludes the
genuinely dormant (`AppFlowy-IO/AppFlowy` at 8, `android/architecture-samples` at 0).

### R2. A4 gains an escape hatch: `authors_last100 >= 10` **OR** `commits_12mo >= 2000`
**Why:** the A4 proxy samples the last 100 commits, which breaks on repos with a
bot-dominated or squash-merge commit stream. `appwrite/appwrite` has 12,103 commits
in 12 months and was rejected for "2 authors" — an artifact of release automation,
not evidence of a solo project. A repo sustaining 2000+ commits/yr is not solo
regardless of who authored the most recent 100.

### R3. A9 split: CI presence is no longer a hard gate
**Why:** the probe can only see `.github/workflows` and a handful of other paths.
`swiftlang/swift` was rejected for "no CI" — it runs a large dedicated CI system
outside GitHub Actions. Gating on *observable* CI punishes projects for not using
GitHub's runner. **Revised:** A9 requires a **test signal** (the thing we actually
care about). CI presence moves from gate to D1 score input. This trades a false-
negative problem for a slightly weaker gate, which is the correct direction —
absence of evidence in our probe is not evidence of absence.

### R4. Cluster assignment must use topics + language, never description prose
**Why:** matching `\bios\b`, `mobile`, `android` against the description routed
`axios/axios`, `Leaflet/Leaflet`, `react-hook-form/react-hook-form`,
`fatedier/frp` (Go), `sxyazi/yazi` (Rust) and `appwrite/appwrite` into the mobile
cluster. A library that merely *mentions* React Native is not a mobile project.
**Revised:** mobile requires `primaryLanguage ∈ {Swift, Kotlin, Dart}` **or** an
explicit mobile *topic*. Same tightening applied to `agentic-dev`.

### Honest consequence
These four changes raise the corpus size. That is a legitimate reason to distrust
them, so the direction of each was chosen against the specific false negative it
fixed, and each names the repos that motivated it. R3 in particular *weakens* a
gate; it is included because the alternative was systematically excluding
non-GitHub-CI projects, which is a worse bias than a looser gate.

## v3 — 2026-09-28, after age/velocity analysis

### R5. New gate A10 — repo age
`age >= 24 months`, except `agentic-dev` where `age >= 12 months`.

**Why:** the brief asks for software "running in production with millions of
users" and "active development" sustained over time. A repo 3 months old cannot
evidence either, whatever its star count. Practices that have not survived a
dependency major-bump, a security incident, or a maintainer turnover have not been
tested by the thing we are trying to measure.

**The agentic-dev exception** exists because that field is genuinely new — a
24-month bar would empty the cluster and silently discard the most relevant
evidence we have. 12 months is the compromise, and it is recorded as a known
weakness of that cluster's findings rather than hidden.

**What this costs:** it also excludes legitimately excellent young projects
(`openai/codex`, `github/spec-kit`, `microsoft/markitdown`, `browser-use/browser-use`).
That is a real loss. It is accepted because the alternative — hand-picking which
young repos are "really" good — replaces a mechanical rule with my taste, which is
exactly what Part G forbids.

### R6. New gate A11 — star-velocity sanity bound
`stars / month_of_age <= 15000`.

**Why:** measured across the 1124 enriched repos, `stars/month` splits cleanly:

| cohort | n | median stars/month |
|--------|---|--------------------|
| mature (>= 24mo) | 920 | 345 |
| young (< 24mo) | 204 | 4,424 |

The young cohort's top end reaches 157,756 stars/month (238k stars in 1.5 months).
The threshold of 15,000 sits far above every legitimate viral project observed
(`openai/codex` 7,247; `microsoft/markitdown` 8,340; `github/spec-kit` 10,516) and
below the implausible cohort.

**Framing, deliberately:** this is *not* a fraud accusation, and must never be
written up as one. It is a statement about **our** measurement: at that velocity we
cannot distinguish organic adoption from anything else with the signals available
to us, so the repo carries no usable production-adoption evidence and is excluded
for lack of signal. A repo excluded by A11 may be excellent.

### R7. Mobile cluster tightened again
R4's topic-based rule still admitted `zulip` (Python), `appwrite` (PHP),
`matomo` (PHP), `tauri` (Rust), `yazi` (Rust TUI) and `raylib` (C) — projects that
*ship* a mobile client or are cross-platform, but whose repository is not mobile
engineering. **Revised:** mobile requires
`primaryLanguage ∈ {Swift, Kotlin, Dart, Objective-C, Java}`
**or** an explicit framework topic ∈ {react-native, flutter, expo, ionic, nativescript}.
Consequence: the cluster gets smaller and more honest. If it cannot be filled to
target, the shortfall is reported, not padded.

## v4 — 2026-09-28. Mobile clustering: mechanical detection abandoned, and why

R7 still failed. Adding `Java` to the mobile language set filled the cluster with
backend infrastructure — `apache/kafka`, `spring-projects/spring-boot`,
`netty/netty`, `google/guava`, `openjdk/jdk`, `jenkinsci/jenkins`,
`keycloak/keycloak`. Java is a backend language; it carries no mobile signal.

Topic matching leaks in the other direction. `react-hook-form` declares
`react-native` because it *supports* React Native; `appwrite` declares `flutter`
because it ships a Flutter SDK; `immich` declares mobile topics because the product
has a mobile client. None of these are mobile-engineering repositories.

**Conclusion: "is this a mobile repo" is not mechanically detectable from GitHub
metadata.** Three attempts failed. Rather than tune a fourth regex, the rule is
now split and the judgement is made explicit:

1. **Mechanical:** `primaryLanguage ∈ {Swift, Kotlin, Dart, Objective-C}`.
2. **Named exception list** (hand-maintained, 5 entries): the canonical
   cross-platform mobile frameworks whose primary language is not a mobile one —
   `react/react-native`, `expo/expo`, `flutter/flutter`,
   `ionic-team/ionic-framework`, `NativeScript/NativeScript`.

Part G forbids replacing a mechanical rule with taste. This is a deliberate,
declared exception to that: the list is 5 named repos, visible in `scripts/03_score.py`,
auditable in one glance, and justified because the alternative was a regex that
demonstrably misclassified in both directions across three revisions. A hidden
heuristic is worse than a visible hand-list.

**Accepted consequence:** the mobile cluster will fall short of its 30 target. The
shortfall is reported in the corpus document, not padded. Mobile repositories at
20k+ stars that also sustain 250+ commits/year are genuinely scarce — that scarcity
is itself a finding about the mobile open-source ecosystem, not a defect in the screen.
