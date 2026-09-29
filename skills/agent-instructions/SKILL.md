---
name: agent-instructions
description: >
  Use when creating or improving an AGENTS.md, CLAUDE.md, .cursorrules, or
  copilot-instructions file for a repository — deciding what to tell AI agents, how
  to structure it, which rules actually change behaviour, and how to keep it from
  drifting. Use PROACTIVELY when onboarding a repo to AI-assisted development, when
  asked to write repo conventions for agents, or when an agent keeps making the same
  mistake in a codebase.
---

# Agent instructions

How 48 production repositories actually instruct AI agents, measured from a 61-repo
probe. The finding that matters most: **quality tracks structure, not length.**
`kubernetes/kubernetes` (38 lines) and `appwrite/appwrite` (308 lines) are both
high-density; unstructured length is the defect, not length itself.

## Trigger

**Fire when:** writing or revising an agent instruction file; setting up a repo for
AI-assisted work; an agent repeats a mistake that a rule could prevent.

**Do not fire when:** the request is to write human-facing docs (README,
CONTRIBUTING) — those have different readers and different failure modes.

## Use AGENTS.md as the real file

`AGENTS.md` is now canonical: 412 of 1,124 active 20k+ star repos have one (36.7%)
versus 290 with `CLAUDE.md` (25.8%), and **23 of 28 `CLAUDE.md` files are pointers**
to `AGENTS.md` — via `@AGENTS.md` import, a symlink, or byte-identical duplication.

```
CLAUDE.md:  @AGENTS.md
```

Two documents drift. One does not.

## Rules

1. Name **one command** that proves a change works. This is the most common rule in
   the corpus (30+ repos) and the highest-value line in the file.
   *Enforced by:* `python3 scripts/check_agents_md.py` (required check)

2. Demand scoped diffs: no drive-by refactors, reformatting, or unrelated dependency
   bumps.
   *Enforced by:* `python3 scripts/check_agents_md.py` (required check)

3. Tag every rule by how it is enforced — a lint rule id, or human review. An
   untagged rule is indistinguishable from a wish.
   *Enforced by:* `[lint: <id>]` / `[review]` tags, checked by review

4. Use numbers, not adjectives. "Keep PRs small" is unenforceable; ">500 lines or
   >10 files" is.
   *Enforced by:* `python3 scripts/check_agents_md.py` numeric-budget check

5. Forbid hand-editing generated files, and name the regeneration command.
   *Enforced by:* `python3 scripts/check_agents_md.py` generated-code check

6. State that the narrowest check runs first. A fast first gate is the one that
   actually gets run.
   *Enforced by:* `python3 scripts/check_agents_md.py` narrowest-check check

7. Defer to authoritative docs instead of duplicating them. Copied details drift.
   *Enforced by:* `python3 scripts/check_agents_md.py` deference check

8. Ban process narration and AI attribution in commits, PR bodies and comments — no
   discarded alternatives, no tool-usage logs, no co-author footers.
   *Enforced by:* `python3 scripts/check_agents_md.py` attribution check

9. In a monorepo, say that the closest `AGENTS.md` wins locally.
   *Enforced by:* `python3 scripts/check_agents_md.py` nested-override check

10. Remember the file is untrusted input to anyone who clones you. Do not put
    secrets, egress commands, or review-steering instructions in it.
    *Enforced by:* `python3 scripts/audit_agent_config.py .`

## Verify

```bash
# check a file against the 12 measured corpus patterns (~0.2s)
python3 scripts/check_agents_md.py .

# confirm CLAUDE.md is a pointer rather than a second document
cat CLAUDE.md          # expect a one-line @AGENTS.md reference

# audit your own file the way someone cloning you would
python3 scripts/audit_agent_config.py .

# the rules are only real if the commands in them run
bash -c "$(grep -A3 '```bash' AGENTS.md | sed -n '2p')"
```

## Failure modes

This skill rejects:

- **A file with no named prove-it command.** The most common corpus rule, and its
  absence makes every other rule unverifiable.
- **`CLAUDE.md` as a second full document.** It drifts from `AGENTS.md` and agents
  get contradictory instructions.
- **"Keep changes small"** with no number.
- **Untagged rules**, where a reader cannot tell what a lint will catch and what
  needs judgement.
- **A 300-line unstructured wall.** Length is fine; length without headings is not.
- **Instructions that duplicate CONTRIBUTING.md**, guaranteeing one goes stale.
- **Review-steering or egress content**, which turns your repo into a hazard for
  anyone who clones it (rule 10).

**A genuine disagreement in the sources, recorded rather than averaged away:**
Anthropic's skill-authoring guidance says to be "pushy" in a description and
over-signal when the skill should fire, because under-triggering is the observed
failure. `obra/superpowers` says the opposite for its own files — "NEVER summarize
the skill's process or workflow" in a description, because a description that reads
like documentation does not discriminate on *when* to fire. Both are Tier-1 sources.
They are optimising different things: recall versus precision. Pick per file and know
which you chose.

**Known gap:** none of this measures whether the rules are *followed*. The corpus
shows what repos ask for; only a hook shows what happened. That is what
`verification-gate` is for.

## Scale

`solo`: rules 1, 2, 4 — one command, scoped diffs, one number. A 20-line file
outperforms a 300-line one.
`small-team (2-10)`: add 3, 5, 7, 8.
`org`: add 6, 9, 10, and a review step when the file changes — `PostHog/posthog` is
the only corpus repo that systematically tags every convention `[lint: id]` vs
`[review]`, which is a template worth copying.
Note that `ray-project/ray` and `vllm-project/vllm` share verbatim policy language
banning pure-agent PRs entirely: "A human submitter must understand and defend the
change end-to-end." That is an org-scale position, and a defensible one.

## Sources

- Adoption statistics, the 15 most recurring rules with per-rule repo counts, the
  length-versus-quality analysis, and the structural patterns of the strongest files:
  `research/21-findings-agent-instruction-corpus.md` (61 repos probed, 48 with files).
- Corpus-wide artifact counts: `research/10-repo-corpus.md`.
- `kubernetes/kubernetes:AGENTS.md`, `elastic/elasticsearch:AGENTS.md` — generated-file
  prohibition (rule 5).
- `calcom/cal.com:AGENTS.md` (">500 lines or >10 files"), `openai/codex:AGENTS.md`
  ("under 500 LoC… changed lines should not exceed 800") — numeric budgets (rule 4).
- `PostHog/posthog:AGENTS.md` — `[lint: id]` vs `[review]` tagging (rule 3); arrived
  at independently of this plugin's `Enforced by:` scheme.
- `appwrite/appwrite:AGENTS.md`, `vercel/next.js:AGENTS.md` — narrowest-check-first
  (rule 6).
- `astral-sh/ruff:AGENTS.md`, `astral-sh/uv:AGENTS.md` — no process leakage (rule 8).
- `cloudflare/workers-sdk:AGENTS.md`, `PostHog/posthog:AGENTS.md` — nested overrides
  (rule 9).
- The Anthropic / superpowers disagreement on description style:
  `research/20-findings-ecosystem-skills.md`.
- `scripts/check_agents_md.py` and its 12 pattern checks: `SOURCE: original`.
