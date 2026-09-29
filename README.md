# 100x-engineer

A Claude Code plugin of **verification-enforced** engineering skills for backend,
frontend and mobile across TypeScript, Python and Go.

Every rule ships a runnable check. Rules that cannot be checked are labelled as such,
capped at three per skill, or deleted.

## Contents

| # | section | what it answers |
|---|---------|-----------------|
| 1 | [Why this exists](#why-this-exists) | the two failure modes it targets, and how the corpus was built |
| 2 | [Does it actually work?](#does-it-actually-work) | the measured numbers, and the claim I explicitly do **not** make |
| 3 | [Install](#install) | one command, plus the per-project opt-in for the commit gate |
| 4 | [The verification receipt](#the-verification-receipt) | the mechanism nobody else had |
| 5 | [Skills](#skills) | all 29, in pipeline order, with what each rejects |
| 6 | [Stack reviewers](#stack-reviewers) | framework-specific failure modes |
| 7 | [Tools](#tools) | the 30 checkers and what they catch |
| 8 | [Index discipline](#index-discipline) | how this stays navigable at hundreds of records |
| 9 | [Honest limitations](#honest-limitations) | what it misses, measured not guessed |
| 10 | [Research](#research) | the evidence every skill cites |

## Why this exists

AI agents do not mostly write wrong code. They write **too much** code — extra files,
extra layers, extra docs, tests that cannot fail — and then report success without
evidence. Both problems are mechanical, so both get mechanical answers.

Built from measurement, not opinion. **1,431 repositories screened to a 223-repo
corpus** of production software (≥20k stars, ≥250 commits/year, ≥2 years old, licensed,
tested, with converging evidence of real users). Their actual CI, test, lint, type,
security and agent configurations were read and counted. The screening contract, all
four revisions to it, and the full funnel are in [`research/`](research/INDEX.md).

**The gap it fills.** Surveying the Claude Code skills ecosystem and 61 production
agent-instruction files produced one clear result: skill-catalogue quality is well
solved, verification discipline is well *written*, and mechanical enforcement at the
moment of the claim existed nowhere. Of 25 agentic-development repositories, 3 wire any
hook at all and **none** block a completion on test results.

## Does it actually work?

Two separate questions, answered separately.

**Do the checks catch what they claim?** Measured:

```bash
python3 scripts/run_evals.py
```

19 seeded defects, one per class the plugin claims to catch — **19/19 caught**. 4 clean
controls — **0 false positives**. The same harness records **6 defect classes it does
not catch**, as eval cases, so the scope claim is testable rather than rhetorical.

**Does using this make someone dramatically more productive?** Unknown. Nothing here
measures that and "100x" is a name, not a claim. The defensible version is narrower:
these defect classes get caught before review, and the eval says exactly which.

Skill routing is measured too — `scripts/skill_triggers.py`, gated on top-3 ≥85%.
Top-1 is reported as a diagnostic and deliberately not gated; the reasoning, and four
failed attempts to improve it, are in [`evals/GRADER-CHANGELOG.md`](evals/GRADER-CHANGELOG.md).

## Install

```bash
claude plugin marketplace add ./100x-engineer
claude plugin install 100x-engineer@100x-local
```

Skills are available immediately. **The commit gate is opt-in per project** — the plugin
installs at user scope, so it deliberately does nothing until a project asks:

```bash
mkdir -p .claude
cat > .claude/verification-policy.json <<'JSON'
{ "required_checks": ["test", "typecheck", "lint"], "max_age_minutes": 120 }
JSON
echo ".claude/verification-receipt.json" >> .gitignore
```

With no policy file the hook passes every command through untouched.

## The verification receipt

Run your real checks through a wrapper that records the result **bound to a hash of the
exact file content it verified**:

```bash
python3 scripts/verified.py --name test -- npm test
```

A `PreToolUse` hook then blocks `git commit`, `git push`, `gh pr create`, `git tag` and
`npm publish` unless a receipt exists, covers the required checks, passed, and matches
current content.

This is what separates it from an instruction. The classic failure is *run tests → edit
a file → commit*: the tests passed, "tests pass" is true, and the committed code was
never tested. Editing anything — tracked, staged, or a stray untracked file —
invalidates the receipt.

`git commit --no-verify` is **denied**, not honoured: it silently skips git's own hooks,
so it is an evasion signal. To bypass deliberately, put `[skip-verify]` in the commit
message, where a reviewer can see it.

Independent convergence: `bluesky-social/social-app` fingerprints its native modules and
refuses an over-the-air update when they drift. Same mechanism, found in production, for
the same reason.

## Skills

29 skills in pipeline order — full table with triggers in
[`skills/INDEX.md`](skills/INDEX.md).

**Before code**

| skill | what it rejects |
|---|---|
| `solution-architecture` | a PRD with no measurable success metric; options analysis with no do-nothing option |
| `feature-planning` | code before a spec; edge cases left TODO; "covered" with no test |
| `approach-selection` | a choice with one option recorded; a rejected option with no reason |
| `decision-log` | a decision with no falsifiable assumption; no revisit trigger |
| `data-modeling` | float money; invariants only in application code; a tenant-scoped index missing its tenant column |
| `api-contract` | a breaking change shipped as a minor; errors a client must parse from a string |

**While writing**

| skill | what it rejects |
|---|---|
| `code-craft` | flag parameters; swallowed errors; vague names; Demeter chains; primitive-obsessed money |
| `minimal-diff` | new files that should be edits; assertion-free and focused tests; unrequested docs |
| `test-design` | tests chosen by vibe rather than boundary analysis; mocking what you don't own |
| `distributed-correctness` | "exactly-once"; dual writes; retries with no budget; unstated timeouts |
| `performance-budgets` | N+1 shapes; unbounded queries; missing timeouts; optimising without a measurement |
| `diagramming` | the wrong diagram type; a diagram past its node budget; L3 with no step table |
| `observability-design` | a user id in a metric label; alerts with no action |
| `legacy-change` | refactor and behaviour change in one commit; changing untested code with no characterization test |
| `stack-reviewer` | generic review on framework-specific code |
| `typescript-verification` / `python-verification` / `go-verification` | type checkers configured but never gating; codegen drift gates that miss new files |
| `mobile-release-safety` | schema changes with no migration test; OTA pushes after native drift |

**Before shipping**

| skill | what it rejects |
|---|---|
| `verification-gate` | "done" with no evidence; verify-then-edit-then-commit; `--no-verify` |
| `scoped-review` | "looks good" with in-scope questions unanswered |
| `reviewing-others-code` | critique before understanding intent; unlabelled findings |
| `review-gates` | PR checkboxes nobody parses; a `merge_group:` trigger that does not work |
| `security-baseline` | tag-pinned actions in secrets-bearing workflows; a fixed bug with no regression test |

**When broken, and meta**

| skill | what it rejects |
|---|---|
| `bug-fix` | a fix before a reproduction; the repro not kept as a permanent test |
| `root-cause-analysis` | a root cause identical to the symptom; no regression test named |
| `codebase-comprehension` | inferred claims presented as verified |
| `engineering-ledger` | a spec with no decision behind it; 40+ records in one flat directory |
| `agent-instructions` | an instruction file with no named prove-it command |
| `untrusted-agent-config` | third-party agent configs and hooks auto-loading unreviewed |

## Stack reviewers

Framework-specific failure modes grounded in cloned production code — including defects
found in official reference apps. Catalogue: [`reviewers/INDEX.md`](reviewers/INDEX.md).

NestJS · Next.js/React · React Native + Expo · Flutter · native Android/iOS ·
Kubernetes · AWS/GCP/Terraform, plus shared references for evidence labels, diagram
levels, code craft and latency numbers.

Each carries blocking rules, the AI failure modes specific to that stack, edge cases it
routinely misses, and a **default recommendation** for every recurring architectural
choice — so the agent proceeds without interrogating you.

## Tools

Python standard library and git only — no install step, no dependencies.

| tool | purpose |
|---|---|
| `verified.py` + `hooks/require_verification.py` | content-bound receipt; block completion without one |
| `plan_feature.py` | scaffold a spec seeding **140 edge cases across 19 kinds**; audit it |
| `decide.py` | decision log: verifiable assumptions, revisit triggers, drift, trace, lint |
| `rca.py` | RCA records; rejects a root cause equal to the symptom |
| `prd.py` | PRD scaffold, audit, and PRD↔spec alignment |
| `ledger.py` | index, traceability matrix, linkage gaps, date sharding, search |
| `diagram_from_code.py` | mermaid **from** code at 3 detail levels; round-trips with `design_drift.py` |
| `design_drift.py` / `check_diagrams.py` | diagram↔code drift; diagram type and budget validation |
| `bloat_check.py` / `craft_check.py` | AI bloat; code shape |
| `schema_check.py` / `perf_check.py` / `test_design_check.py` | data modelling; N+1 and budgets; test quality |
| `audit_ci_gates.py` | checks that look like gates but cannot fail; action SHA-pinning |
| `audit_agent_config.py` | a repo's agent config as untrusted input |
| `repo_map.py` / `check_index.py` / `check_claims.py` | orientation; index discipline; evidence labels |
| `run_evals.py` / `skill_triggers.py` / `lint_skills.py` | the measurements, and the contract on our own skills |

```bash
bash tests/run_all.sh    # 462 assertions across 16 suites + 23 eval cases + lints
```

## Index discipline

Two failures appear once a project has more than a handful of records, and both are
enforced:

- **Collection level** — hundreds of specs with no file listing them. Every collection
  carries a generated `INDEX.md`; `ledger.py map` adds a feature × record-type matrix
  answering *"is there a decision behind this spec?"*
- **Document level** — a 500-line findings file with 13 sections and no map, so
  answering "is the answer in here?" costs a full read. Every traversable document over
  150 lines opens with a `## Contents` table saying what each section **answers**.

```bash
python3 scripts/check_index.py                     # audit both levels
python3 scripts/check_index.py --fix-stubs         # scaffold a Contents table
python3 scripts/check_index.py --gen-collections   # regenerate catalogues
python3 scripts/ledger.py check                    # records + traceability + gaps
```

Deliberately **not** applied to files under 150 lines or fixed-structure files like
`SKILL.md` — an index on a short file is ceremony, and ceremony is what gets a
convention abandoned.

## Honest limitations

- **Presence is not quality.** Corpus scores measure whether verification machinery
  exists, not whether it is used well.
- **Production adoption is inferred.** No repo was verified to have real users; we
  verified it has the artifacts of a project that does.
- **The receipt proves a command exited zero against specific content.** It cannot prove
  the command was worth running. Mutation testing is the real answer and was confirmed
  absent in 0/72 JS and 0/50 Python corpus repos — the whole corpus shares this blind spot.
- **Six defect classes have no mechanical detection anywhere**: semantic duplication with
  renamed variables, redundant comments, unnecessary dependencies, tests that assert the
  bug, missing authorization, check-then-act races. `review_scope.py` turns them into
  nine attributed questions.
- **Mobile evidence is thinner** — 11 of a 30 target; supplemented by 20 named
  below-gate repos.
- **Trigger routing is a lexical proxy**, gated on top-3 not top-1. See the changelog.
- **The corpus is a snapshot**, screened 2026-09-28. Re-run
  `scripts/01_harvest_candidates.py` → `04_corpus_doc.py` to refresh.

## Research

16 documents, 8,026 lines — [`research/INDEX.md`](research/INDEX.md). Each carries its
own `## Contents` table.

`00` the screening contract and its four revisions · `01` the skill contract ·
`10` the 223-repo corpus and funnel · `2x` skills ecosystem, agent-instruction corpus,
agent-tool internals, anti-bloat tooling · `3x` per-cluster deep reads: JS, Python, Go,
mobile, agentic, security, anti-bloat, governance.

## Licence

MIT. Adapted material is attributed per-skill under `## Sources`, with upstream licences
recorded in `research/20-findings-ecosystem-skills.md`. Note that
`hesreallyhim/awesome-claude-code` is CC BY-NC-ND and therefore **not** adapted here — it
is referenced as a discovery index only.
