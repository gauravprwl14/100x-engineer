# 100x-engineer

A Claude Code plugin of **verification-enforced** engineering skills for backend,
frontend and mobile across TypeScript, Python and Go.

Every rule ships a runnable check. Rules that cannot be checked are labelled as
such, capped at three per skill, or deleted.

## Why this exists

AI agents do not mostly write wrong code. They write **too much** code — extra
files, extra layers, extra docs, tests that cannot fail — and then report success
without evidence. Both problems are mechanical, so both get mechanical answers.

This plugin was built from measurement, not opinion. 1,431 GitHub repositories were
screened down to a 223-repo corpus of production software (≥20k stars, ≥250
commits/year, ≥2 years old, licensed, tested, with converging evidence of real
users). Their actual CI, test, lint, type, security and agent configurations were
read and counted. The screening contract, every revision to it, and the full funnel
are in [`research/`](research/).

## The gap this fills

Surveying the Claude Code skills ecosystem and 61 production agent-instruction
files produced one clear result:

- **Skill-catalog quality** is well solved — several projects lint and eval their
  skills in CI.
- **Verification discipline in prose** is well written — "always verify before
  claiming done" appears in many good instruction files.
- **Mechanical enforcement at the moment of the claim** existed nowhere. Of 25
  agentic-development repositories, 3 wire any hook at all, and **none** block a
  completion on test results.

So the centrepiece here is the part nobody had: a gate the model cannot talk itself
past.

## Install

```bash
claude plugin marketplace add /path/to/100x-engineer-research
claude plugin install 100x-engineer@100x-local
```

The skills are available immediately. **The commit gate is opt-in per project** —
the plugin installs at user scope, so it deliberately does nothing until a project
asks for it. Opt in by creating a policy file:

```bash
mkdir -p .claude
cat > .claude/verification-policy.json <<'JSON'
{ "required_checks": ["test", "typecheck", "lint"], "max_age_minutes": 120 }
JSON
echo ".claude/verification-receipt.json" >> .gitignore
```

With no policy file the hook passes every command through untouched. `required_checks`
may be `[]` to require only that *something* passed against the current content.

## The verification receipt

Run your real checks through a wrapper that records the result **bound to a hash of
the exact file content it verified**:

```bash
python3 scripts/verified.py --name test -- npm test
```

A `PreToolUse` hook then blocks `git commit`, `git push`, `gh pr create`, `git tag`
and `npm publish` unless a receipt exists, covers the required checks, passed, and
matches the current content.

This is what makes it different from an instruction: the classic failure is *run
tests → edit a file → commit*. The tests passed, the sentence "tests pass" is true,
and the committed code was never tested. Editing anything — tracked, staged, or a
stray untracked file — invalidates the receipt.

`git commit --no-verify` is **denied**, not honoured: it silently skips git's own
hooks, so it is an evasion signal. To bypass deliberately, put `[skip-verify]` in
the commit message; that is recorded in the transcript where a reviewer can see it.

Independent convergence worth noting: `bluesky-social/social-app` fingerprints its
native modules and refuses an over-the-air update when they drift. Same mechanism,
found in production, for the same reason.

## Skills

| skill | what it rejects |
|---|---|
| `verification-gate` | "done" with no evidence; verify-then-edit-then-commit; failing or missing required checks |
| `minimal-diff` | new files that should be edits; dead and commented-out code; assertion-free and focused tests; single-use abstractions; unrequested docs |
| `untrusted-agent-config` | third-party agent configs and hooks auto-loading unreviewed; approval-steering and instruction-override text |
| `typescript-verification` | loose `tsconfig`; whole-repo coverage gates that get disabled; `eslint` without `--max-warnings=0`; unbounded bundle growth |
| `python-verification` | type checkers configured but never gating; `select=["ALL"]`; coverage offered as proof |
| `go-verification` | codegen drift gates that miss new files; tests without `-race`; stale `go.mod`; dependency bans that live only in prose |
| `mobile-release-safety` | schema changes with no migration test; OTA pushes after native drift; 100% releases with no staged rollout |
| `security-baseline` | public repos with no private reporting channel; tag-pinned actions in secrets-bearing workflows; fixed bugs with no regression test |
| `review-gates` | PR checkboxes nobody parses; one-line CODEOWNERS; a `merge_group:` trigger that does not work; AI policies with no parser |
| `agent-instructions` | instruction files with no named prove-it command; `CLAUDE.md` as a second document; "keep it small" with no number |

## Tools

Python standard library and git only — no install step, no dependencies.

| tool | purpose | tests |
|---|---|---|
| `scripts/verified.py` + `hooks/require_verification.py` | run a check, write a content-bound receipt, block completion without one | 25 |
| `scripts/bloat_check.py` | 7 diff-scoped AI-bloat checks; 4 cover failure modes no production repo catches | 16 |
| `scripts/audit_agent_config.py` | treat a repo's agent config as untrusted input | 15 |
| `scripts/audit_ci_gates.py` | find checks that look like gates but cannot fail; audit action SHA-pinning | 11 |
| `scripts/stack_audit.py` | project layers vs the measured corpus baseline | — |
| `scripts/check_agents_md.py` | check an AGENTS.md against 12 measured corpus patterns | — |
| `scripts/lint_skills.py` | enforce the skill contract on this plugin's own skills | — |

```bash
bash tests/run_all.sh    # 67 assertions across 4 suites, plus the skill-contract lint
```

Footprint when installed: **~1,533 tokens always-on** (about 170 per skill), with each
skill costing ~2.2-3.2k only when it fires. The hook is harness-only and costs no
model context.

## Honest limitations

- **Presence is not quality.** The corpus scores measure whether verification
  machinery exists, not whether it is used well. A tier-1 score licenses a deep
  read; it certifies nothing.
- **Production adoption is inferred.** No repo was verified to have real users; we
  verified it has the artifacts of a project that does.
- **The receipt proves a command exited zero against specific content.** It cannot
  prove the command was worth running. Mutation testing or a deliberate break is
  the only real answer, and mutation testing was confirmed absent in 0 of 50 Python
  repos — the whole corpus shares this blind spot.
- **Five bloat failure modes have no mechanical coverage in any production repo**,
  confirmed by two independent research passes: new-file-instead-of-edit, single-use
  abstractions, semantic duplication with renamed variables, redundant comments, and
  assertion-free tests. `bloat_check.py` covers four of the five (two as advisory
  signals, since they need judgement). Semantic duplication remains uncovered here
  too, along with whether a dependency was necessary and cumulative cross-PR growth.
  Route those to a human or an LLM pass scoped to exactly those questions.
- **Mobile evidence is thinner.** Mobile repos meeting the star and activity bars
  are genuinely scarce (11 of a 30 target), so mobile findings lean on 20 named
  below-gate supplements.
- **The corpus is a snapshot**, screened 2026-09-28. Re-run `scripts/01_harvest_candidates.py`
  through `scripts/04_corpus_doc.py` to refresh it.

## Research

| document | contents |
|---|---|
| `research/00-signal-rubric.md` | the screening contract and all four revisions, with the repos that forced each |
| `research/01-skill-contract.md` | what every SKILL.md must satisfy |
| `research/10-repo-corpus.md` | the 223 repos, the funnel, and per-dimension scores |
| `research/2x-findings-*.md` | skills ecosystem, agent-instruction corpus, agent-tool internals, anti-bloat tooling |
| `research/3x-findings-*.md` | per-cluster deep reads: JS, Python, Go, mobile, agentic, security, anti-bloat, governance |

## Licence

MIT. Adapted material is attributed per-skill under `## Sources`, with upstream
licences recorded in `research/20-findings-ecosystem-skills.md`. Note that
`hesreallyhim/awesome-claude-code` is CC BY-NC-ND and therefore **not** adapted here
— it is referenced as a discovery index only.
