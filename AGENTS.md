# AGENTS.md

Instructions for AI agents working in this repository. `CLAUDE.md` is a pointer to
this file: `research/21-findings-agent-instruction-corpus.md` found that 23 of 28
`CLAUDE.md` files in production repos are pointers to a canonical `AGENTS.md`, and
two documents drift while one does not.

This file summarises but does not replace `research/01-skill-contract.md` (the
contract every skill must meet) and `research/00-signal-rubric.md` (how evidence is
admitted). Those are authoritative; if this file disagrees with them, they win.

## What this repo is

A Claude Code plugin. `skills/` holds SKILL.md files; `scripts/` and `hooks/` hold
the tools those skills invoke; `tests/` holds their regression suites; `research/`
holds the evidence every claim is sourced from.

## Prove-it command

```bash
bash tests/run_all.sh
```

Four suites (68 assertions) plus the skill-contract lint. It must pass before any
commit. Run the narrowest check first and broaden only if needed:

```bash
python3 scripts/lint_skills.py            # ~0.1s, after editing any SKILL.md
bash tests/test_verification_gate.sh      # ~5s, after touching hooks/ or verified.py
bash tests/run_all.sh                     # ~15s, before committing
```

## Rules

1. **Every claim in a skill needs a citation** — `owner/repo@ref:path`, or the label
   `SOURCE: original`. Unsourced assertions are the failure mode this repo exists to
   avoid. `[review]`

2. **Every numbered rule needs an `Enforced by:` tag.** At most three `convention`
   rules per skill. `[lint: lint_skills.py]`

3. **Never edit a findings document to agree with a skill.** Findings are evidence;
   skills are derived from them. If they conflict, the skill is wrong. `[review]`

4. **Retract false findings in place, never silently delete them.** See the corrected
   Anomalies section in `research/21-findings-agent-instruction-corpus.md` for the
   expected form. `[review]`

5. **Absence is a finding.** If a practice is missing from the corpus, record the
   number. Never fill a gap with invention presented as observation. `[review]`

6. **Every new tool ships a regression suite** asserting both detection and the
   absence of false positives on clean input. A checker that never rejects anything
   is the thing this repo is against. `[lint: tests/run_all.sh]`

7. **Never change a rubric threshold without adding a revision entry** to
   `research/00-signal-rubric.md` naming the repos that motivated it. `[review]`

8. **Keep diffs scoped.** No drive-by refactors, reformatting, or unrelated
   dependency updates. Do not edit files the task does not require.
   `[lint: bloat_check.py --only file-creation-ratio]`

9. **Prefer editing an existing file over creating a new one.** A new file needs a
   reason statable in one sentence. `[lint: bloat_check.py]`

10. **Do not create documentation that was not asked for.** No summaries of your own
    work. `[lint: bloat_check.py --only new-docs]`

11. **Comments explain why, never what.** Delete narration.
    `[lint: bloat_check.py --only commented-code]`

12. **Never add a dependency.** This plugin deliberately uses only the Python
    standard library and git, so it runs anywhere with no install step. If you
    believe a dependency is required, stop and ask. `[review]`

13. **Never suppress a check to make it pass** — no `# type: ignore`, no
    `|| true`, no `continue-on-error` on a gate. Fix the root cause. The repo ships
    `scripts/audit_ci_gates.py` specifically to find this pattern in other people's
    projects; do not commit it here. `[lint: audit_ci_gates.py]`

14. **No AI attribution and no process narration in commits or code.** Do not
    mention discarded alternatives, intermediate edits, tool usage, or this
    conversation in commit messages, PR bodies, or comments. `[review]`

15. **Numeric budgets:** SKILL.md ≤ 250 lines. Findings documents ≤ 1000 lines. A
    single commit should not exceed ~10 files without a stated reason.
    `[lint: lint_skills.py]`

Rule tags follow `PostHog/posthog`'s scheme — `[lint: id]` for mechanically enforced,
`[review]` for human judgement — which that repo arrived at independently and which
is the same idea as the skill contract's `Enforced by:` tags.

## Nested overrides

There are none today. If a subdirectory ever gains its own `AGENTS.md`, it wins
locally and you should read the closest applicable file before working in that tree.

## Re-running the research

```bash
python3 scripts/01_harvest_candidates.py   # GitHub search -> candidates (search API, throttled)
python3 scripts/02_enrich_gql.py           # GraphQL enrichment, checkpointed, resumable
python3 scripts/03_score.py                # gates + D1-D7 scoring + cluster allocation
python3 scripts/04_corpus_doc.py           # render research/10-repo-corpus.md
```

Use the GraphQL path, not REST. A REST run of this work exhausted the 5,000/hour
quota in 13 minutes and produced nothing, because it wrote results only at the end.
`02_enrich_gql.py` costs ~343 GraphQL points for 1,124 repos and checkpoints every
batch. Do not trust `/rate_limit` — it reported `used: 0` while the quota drained;
read the `x-ratelimit-remaining` response header instead.
