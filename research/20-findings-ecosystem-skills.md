# Ecosystem Findings: Claude Code Skills, Agents, Commands, Hooks, Plugins

Scope: this file screens the public Claude Code skills/plugins/agents ecosystem on its
own terms (per-repo engineering quality, not the 20k-star corpus admission gate in
`00-signal-rubric.md`). Part G anti-goals were applied throughout: no cargo-culting, no
advice without a runnable command, every claim cited `owner/repo@sha:path`, absence
reported as a finding rather than papered over.

11 repositories were shallow-cloned (`git clone --depth 1`) into a scratch directory and
read directly (not summarized from READMEs). Star/push/contributor numbers pulled live via
`gh api` on 2026-09-28. Commit SHAs below are the exact clone heads.

| repo | clone HEAD sha |
|---|---|
| anthropics/skills | `3337550` |
| obra/superpowers | `8ca22db` |
| obra/superpowers-skills | `cdcd624` |
| wshobson/agents | `9b15b34` |
| trailofbits/skills | `0cc1c73` |
| microsoft/skills | `23d0dac` |
| davila7/claude-code-templates | `6ced43a` |
| alirezarezvani/claude-skills | `19392f7` |
| VoltAgent/awesome-claude-code-subagents | `82b7382` |
| disler/claude-code-hooks-mastery | `052ad1c` |
| hesreallyhim/awesome-claude-code | `97e2763` |

---

**No repo in the sample achieves end-to-end "verification-enforced agentic engineering": catalog-quality tooling and prompt-level verification discipline (Iron Law-style rules) are both solved well, but mechanical, unbypassable enforcement at the tool-call boundary is solved only narrowly, by one repo's hard-block hook — see Verdict.**

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Inventory](#inventory) | table of the 11 cloned repos with skill/agent/command/hook counts and a STRONG/MIXED/WEAK verdict per repo, plus why star count is untrustworthy here | 24 lines |
| 2 | [What the good ones do right](#what-the-good-ones-do-right) | 11 concrete patterns harvested verbatim — eval-driven skill development, TDD's Iron Law ported as a skill contract, verification-before-completion, rationalization tables, the deterministic PreToolUse hard-block hook — the bulk of this file's harvestable content; start here | 178 lines |
| 3 | [What the ecosystem gets wrong](#what-the-ecosystem-gets-wrong) | 7 named failure patterns — god-skills up to 1,576 lines, capability-list "agents" with zero verification, multi-harness duplication inflating catalog counts, a non-derivable CC BY-NC-ND license | 18 lines |
| 4 | [SKILL.md authoring mechanics (evidence-based)](#skillmd-authoring-mechanics-evidence-based) | which frontmatter fields are actually used in the wild, description-writing patterns that trigger reliably, and measured skill-length data across repos | 49 lines |
| 5 | [Directly reusable assets](#directly-reusable-assets) | table of specific harvestable artifacts (eval harnesses, lint rule sets, skill triads) with source repo and SPDX license for each | 19 lines |
| 6 | [Verdict](#verdict) | the closing synthesis stated above — three non-overlapping partial solutions to verification-enforced engineering, and the gap between them | 13 lines |

## Inventory

Counts are `find . -not -path '*/.git/*'` over the cloned tree: `SKILL.md` files anywhere;
`.md` files under any directory literally named `agents/` or `commands/`; files under any
directory named `hooks/`. Star/push/license from `gh api repos/<owner>/<repo>`.

| repo | stars | last push | #skills | #agents | #commands | #hooks | verdict | one-line reason |
|---|---|---|---|---|---|---|---|---|
| anthropics/skills | 178,738 | 2026-09-24 | 20 | 3 | 0 | 0 | **STRONG** | official; ships a real eval harness (held-out test set, grading, benchmark diffing) with `skill-creator`, not just prose |
| obra/superpowers | 292,344 | 2026-09-27 | 15 | 0 | 0 | 5 | **STRONG** | TDD-as-methodology enforced by named "Iron Law" gates + a documented 94% PR-rejection policy against AI slop |
| obra/superpowers-skills | 748 | 2025-10-14 | 31 | 0 | 0 | 1 | **MIXED** | same philosophy, "community-editable" companion repo, but stale 11.5 months (fails its own project's cadence) |
| wshobson/agents | 40,051 | 2026-09-28 | 183 | 202 | 105 | 6 | **STRONG** | ships `plugin-eval`: a CI-gated static lint + committed snapshot-regression test over every skill's score |
| trailofbits/skills | 7,276 | 2026-09-25 | 85 | 33 | 8 | 26 | **STRONG** | professional security shop; CODEOWNERS, a 3-tier reference-skill ladder, rationalization-rejection tables in-skill |
| microsoft/skills | 3,060 | 2026-09-28 | 205 | 14 | 13 | 43 | **STRONG** | CI harness actually generates code with an LLM and grades it against `acceptance-criteria.md` patterns before merge |
| davila7/claude-code-templates | 32,036 | 2026-09-28 | 914 | 454 | 391 | 306 | **MIXED** | huge template aggregator/CLI; real CI on the *CLI tool*, zero quality gate on the *skill content* it distributes (skills up to 1,576 lines) |
| alirezarezvani/claude-skills | 26,709 | 2026-08-30 | 846 (437 unique) | 232 | 286 | 20 | **MIXED** | large AI-scaled multi-domain catalog; has CI quality-gate + VirusTotal scan workflows, but ~48% of "skills" are cross-harness (`.codex/`, `.gemini/`, `.hermes/`) duplicates of the same 437 |
| VoltAgent/awesome-claude-code-subagents | 25,373 | 2026-09-21 | 0 | 161 | 0 | 0 | **WEAK** | 161 pure capability-list prompts; no scripts, no tests, no verification step anywhere in the repo |
| disler/claude-code-hooks-mastery | 3,928 | 2026-03-04 | 0 | 19 | 21 | 25 | **STRONG** (hooks pattern only) | best pedagogical reference for all 9 Claude Code hook events, including a real deterministic hard-block `PreToolUse` gate |
| hesreallyhim/awesome-claude-code | 54,736 | 2026-09-28 | 0 | 0 | 0 | 0 | **WEAK** (by design) | pure curated link list, CC BY-NC-ND licensed — no shippable content of its own, and legally non-derivable |

**Star-count sanity check (why this table doesn't sort by stars):** `gh search repos "claude code skills"` surfaced `virgiliojr94/book-to-skill` at 32,846 stars and `op7418/Humanizer-zh` at 18,638 — both single-purpose, freshly-pushed repos with star trajectories inconsistent with organic adoption at this stack size. `wshobson/agents` has 40,051 stars against only 8 open issues, a ratio that is itself a signal worth flagging, not proof of fraud. Per rubric Part B3: *"Judge the repo's own engineering, never its topic [or star count]."* All verdicts above are read from file content, CI config, and commit cadence — not from stars.

---

## What the good ones do right

### 1. Eval-driven skill development with a held-out test set
**Why it works:** prevents the single most common failure mode — a skill description tuned until it "feels right" on the 2 examples the author tried, then silently mis-triggering (or failing to trigger) on everything else. Anthropic's own `skill-creator` treats trigger-phrase tuning as a train/test-split ML problem, not a vibe check.

```
This handles the full optimization loop automatically. It splits the eval
set into 60% train and 40% held-out test, evaluates the current
description (running each query 3 times to get a reliable trigger rate),
then calls Claude to propose improvements based on what failed. It
re-evaluates each new description on both train and test, iterating up
to 5 times. ... It ... returns JSON with `best_description` — selected
by test score rather than train score to avoid overfitting.
```
Citation: `anthropics/skills@3337550:skills/skill-creator/SKILL.md` (Description Optimization § Step 3)

### 2. TDD's Iron Law, ported verbatim as a skill contract
**Why it works:** "write tests eventually" degrades under time pressure; a hard rule with zero named exceptions and a rationalization-rejection table survives it. The skill explicitly defines what counts as cheating ("keep as reference", "adapt while writing tests") — a failure mode list, not just happy-path guidance.

```
## The Iron Law

NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST

Write code before the test? Delete it. Start over.

**No exceptions:**
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Don't look at it
- Delete means delete
```
Citation: `obra/superpowers@8ca22db:skills/test-driven-development/SKILL.md`

### 3. Verification-before-completion as its own standalone skill
**Why it works:** separates "did you build it" from "did you prove it," and gives a mechanical gate function instead of a value statement. Explicitly rejects the specific hedge-words models use to dodge verification ("should", "probably", "seems to").

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```
Citation: `obra/superpowers@8ca22db:skills/verification-before-completion/SKILL.md`

### 4. Skill authoring itself treated as TDD (pressure-test before you write the doc)
**Why it works:** most skill collections write instructions and hope they're followed. This repo requires running a baseline subagent *without* the skill first, recording the exact rationalization it used to cut corners, then writing the skill to close that specific loophole — i.e., the skill's own existence has a failure mode it was built to catch.

```
You write test cases (pressure scenarios with subagents), watch them
fail (baseline behavior), write the skill (documentation), watch tests
pass (agents comply), and refactor (close loopholes).

**Core principle:** If you didn't watch an agent fail without the
skill, you don't know if the skill teaches the right thing.
```
Citation: `obra/superpowers@8ca22db:skills/writing-skills/SKILL.md`

### 5. CI-gated static lint with committed snapshot-regression tests over every skill
**Why it works:** turns "is this skill well-formed" from a one-time human review into a repeatable, diffable CI artifact. The snapshot test specifically distinguishes "a skill's content changed" (expected drift, skipped) from "the scoring code changed and silently reshuffled every skill's grade" (real regression, failed) — a subtlety most lint setups miss.

```
`static-score-snapshot.json` records how the plugin-eval static layer
scores every skill at quick depth. ... `make test` runs two tests ...
- The first test scores every skill again and compares the numbers with
  the snapshot. It fails when a skill's files did not change but its
  numbers did, which means the scoring code changed.
- The second test checks that the snapshot is fresh. It fails when
  fewer than half of the entries still match the skills in the
  repository.
```
Citation: `wshobson/agents@9b15b34:evals/README.md`

### 6. Prose rules turned into grep-able CI lints, not just documentation
**Why it works:** this is the direct antidote to rubric anti-goal G2 ("no advice without a command"). Every stylistic rule in the authoring guide names the exact lint that enforces it, so a contributor can't silently ignore the guide.

```
**Description triggers.** Include a recognized phrase: `Use when …`,
`Use this skill when …`, `Use PROACTIVELY when …`, `Use after …`,
`Trigger when …`, `Auto-loads when …`. The `MISSING_TRIGGER` lint fires
without one.
...
Codex hard-truncates `SKILL.md` bodies at 8 KB and warns. ... The
`SKILL_OVER_CODEX_CAP` lint fires for any skill above 8 KB that has no
`references/` directory.
...
CI runs `tools/check_agent_name_collisions.py --fail-on-duplicates` to
keep the source tree collision-free.
```
Citation: `wshobson/agents@9b15b34:docs/authoring.md`

### 7. LLM-generated code graded against acceptance criteria, in CI, before merge
**Why it works:** this is the only repo in the sample that closes the full loop — generate real output with a real model, then mechanically check it against pass/fail patterns, on every PR, with a CI badge. It is a genuine automated verification stack for skill quality, not a lint on the skill's prose.

```
1. Load acceptance criteria from `tests/scenarios/<skill>/acceptance-criteria.md`
2. Run test scenarios from `tests/scenarios/<skill>/scenarios.yaml`
3. Generate code using [GitHub Copilot SDK] (or mock responses)
4. Evaluate code against correct/incorrect patterns
5. Report results via console, markdown, or JSON
```
Citation: `microsoft/skills@23d0dac:tests/README.md` ("Overview")

Its smoke-test CI job runs this on every PR at mock speed and a nightly job runs it with the real SDK — an explicit two-speed strategy (`disler`-style hooks don't have an equivalent):
```
# Fast, deterministic testing for PRs and pushes
# Full evaluation with real SDK runs nightly via skill-evaluation.yml
```
Citation: `microsoft/skills@23d0dac:.github/workflows/test-harness.yml`

### 8. Rationalization tables inside the skill body, naming the excuse and the required action
**Why it works:** models (and humans) don't skip verification by announcing "I will skip verification" — they skip it via a specific self-talk pattern. Naming the pattern in advance makes it recognizable and interruptible.

```
| Rationalization | Why It's Wrong | Required Action |
|---|---|---|
| "Rapid analysis of remaining bugs" | Every bug gets full verification | Return to task list, verify next bug through all phases |
| "This pattern looks dangerous, so it's a vulnerability" | Pattern recognition is not analysis | Complete data flow tracing before any conclusion |
| "Similar code was vulnerable elsewhere" | Each context has different validation, callers, and protections | Verify this specific instance independently |
```
Citation: `trailofbits/skills@0cc1c73:plugins/fp-check/skills/fp-check/SKILL.md` ("Rationalizations to Reject")

### 9. A written, enforced gate against AI-generated slop contributions
**Why it works:** the ecosystem's biggest risk isn't bad skills, it's bad *contributions* to good skill repos, drowning maintainers. This is the only repo in the sample that states its rejection rate and requires agents to disclose their own harness/model before submitting.

```
This repo has a 94% PR rejection rate. Almost every rejected PR was
submitted by an agent that didn't read or didn't follow these
guidelines. ... **Submitters MUST identify themselves.** Every PR and
issue must disclose the model, harness, harness version, and all
installed plugins used to produce the contribution — or state plainly
that it was written by hand with no agent.
```
Citation: `obra/superpowers@8ca22db:AGENTS.md`

### 10. A deterministic, unbypassable hard-block hook (not a suggestion)
**Why it works:** everything above is the model choosing to follow written instructions. This is the one example in the sample of a rule the model *cannot* talk itself past — a `PreToolUse` hook returning a blocking exit code before a dangerous `rm -rf` or `.env` read ever reaches the shell.

```python
def is_dangerous_rm_command(command):
    normalized = ' '.join(command.lower().split())
    patterns = [
        r'\brm\s+.*-[a-z]*r[a-z]*f',
        r'\brm\s+.*-[a-z]*f[a-z]*r',
        r'\brm\s+--recursive\s+--force',
        r'\brm\s+--force\s+--recursive',
        r'\brm\s+-r\s+.*-f',
        r'\brm\s+-f\s+.*-r',
    ]
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True
```
Citation: `disler/claude-code-hooks-mastery@052ad1c:.claude/hooks/pre_tool_use.py`

### 11. A graduated reference-skill ladder for onboarding contributors
**Why it works:** three concrete example skills, tagged by complexity, each demonstrating one added structural concept — cheaper for a new contributor to copy-and-adapt than to read a spec.

```
| Complexity | Skill | What It Demonstrates |
|------------|-------|---------------------|
| **Basic** | [git-cleanup](plugins/git-cleanup/) | Single self-contained SKILL.md, `allowed-tools` scoping |
| **Intermediate** | [constant-time-analysis](plugins/constant-time-analysis/) | Python package, references/, language-specific docs |
| **Advanced** | [culture-index](plugins/culture-index/) | Scripts, workflows/, templates/, PDF extraction, multiple entry points |

**When in doubt, copy one of these and adapt it.**
```
Citation: `trailofbits/skills@0cc1c73:AGENTS.md`

---

## What the ecosystem gets wrong

**1. God-skills that are reference dumps, not skills.** `davila7/claude-code-templates` ships 914 `SKILL.md` files with a median length of 261 lines and a **maximum of 1,576 lines** — over 3x Anthropic's own "<500 lines ideal" guidance (`anthropics/skills@3337550:skills/skill-creator/SKILL.md`). The worst offender bundles six unrelated OWASP standards (web, ASVS, mobile, API, Kubernetes, agentic-AI) into one file with unchecked `☐` checklist boxes — prose that cannot fail, per rubric anti-goal G2. Citation: `davila7/claude-code-templates@6ced43a:.claude-plugin/skills/owasp-security/SKILL.md`.

**2. Capability-list "agents" with zero verification anywhere in the file.** Both `wshobson/agents` (which is otherwise Tier-1 on tooling) and `VoltAgent/awesome-claude-code-subagents` ship dozens of agent prompts that are pure enumerated-knowledge dumps — "Core concepts: Resources, data sources, variables..." — with no runnable check, no failure mode, no rejection criteria. Example: a 100+-line Terraform specialist agent whose entire body is capability bullet lists (`wshobson/agents@9b15b34:plugins/deployment-strategies/agents/terraform-specialist.md`); VoltAgent's `electron-pro.md` is the same pattern (`VoltAgent/awesome-claude-code-subagents@82b7382:categories/01-core-development/electron-pro.md`). Per rubric G3 ("if a rule never rejects anything, cut it"), these rules should be cut, not harvested.

**3. Multi-harness duplication inflates catalog size without inflating content.** `alirezarezvani/claude-skills` reports 846 `SKILL.md` files but only **437 unique `name:` values** — nearly half the count is the same skill mirrored into `.codex/skills/`, `.gemini/skills/`, `.hermes/skills/`, and `.vibe/skills/`. Anyone citing "380+ skills" from this repo's README is citing a number roughly 2x the real content size.

**4. Curated meta-lists ship zero runnable content, and some are legally non-derivable.** `hesreallyhim/awesome-claude-code` (54,736 stars, the single highest-starred repo in this domain) contains no `SKILL.md`, no agent, no hook — it is a generated README of links. Worse for reuse purposes: it is licensed **CC BY-NC-ND 4.0**, which explicitly forbids derivative works. It is useful only as a discovery index, never as a source of harvestable text.

**5. Star count and engagement can diverge sharply from engineering discipline.** `gh search repos "claude code skills"` surfaced `virgiliojr94/book-to-skill` at 32,846 stars — higher than `davila7/claude-code-templates` (32,036) or `alirezarezvani/claude-skills` (26,709) — for a single-purpose repo with a star count still climbing the day it was queried. `wshobson/agents` sits at 40,051 stars against only 8 open issues. Neither observation proves fraud, but both are exactly the kind of star/engagement mismatch rubric Part B3 warns about: *"Star count measures attention. We are buying evidence of engineering discipline, and those correlate weakly."*

**6. Sibling repos under the same brand drift out of sync.** `obra/superpowers` (the plugin, 292,344 stars) pushed **2026-09-27**; its declared companion, `obra/superpowers-skills` ("community-editable skills for Claude Code's superpowers plugin"), last pushed **2025-10-14** — stale by the project's own 90-day-alive bar, despite sharing a philosophy and license with an actively maintained sibling.

**7. Even the best eval frameworks in the sample self-report their hardest layer as unvalidated.** `wshobson/agents`'s own docs state plainly that the LLM-judge and Monte Carlo scoring layers of `plugin-eval` are *"experimental, not validated against human labels"* (`wshobson/agents@9b15b34:docs/plugin-eval.md`) — only the deterministic static-lint layer is trustworthy. This is an honest admission, and also a finding: nobody in the sample has a validated LLM-judge for skill quality, including the most sophisticated eval framework in the corpus.

---

## SKILL.md authoring mechanics (evidence-based)

**Frontmatter fields actually used in the wild** (from `anthropics/skills` validator's `ALLOWED_PROPERTIES` set, cross-checked against every sampled repo):
```python
ALLOWED_PROPERTIES = {'name', 'description', 'license', 'allowed-tools', 'metadata', 'compatibility'}
```
Citation: `anthropics/skills@3337550:skills/skill-creator/scripts/quick_validate.py`. In practice: `name` + `description` are the only fields present in nearly all skills sampled; `allowed-tools` appears in security-sensitive skills (`trailofbits/skills` fp-check); `license` appears per-skill in `anthropics/skills` (each skill ships its own `LICENSE.txt`, all Apache-2.0, independent of any repo-root license); `compatibility` and `metadata` are rare. `alirezarezvani/claude-skills` adds non-spec fields (`version`, `author`, `tags`, `compatible_tools`) that the official validator would reject as "unexpected keys."

**Description-writing patterns that trigger reliably:**
- *Be "pushy."* Anthropic explicitly instructs authors to over-signal, because under-triggering is the observed failure mode: *"instead of 'How to build a simple fast dashboard...', you might write '...Make sure to use this skill whenever the user mentions dashboards, data visualization, internal metrics, or wants to display any kind of company data, even if they don't explicitly ask for a "dashboard."'"* — `anthropics/skills@3337550:skills/skill-creator/SKILL.md`.
- *Require a literal trigger phrase, lint for its absence.* `wshobson/agents` requires one of `Use when…`, `Use PROACTIVELY when…`, `Trigger when…`, etc., enforced by the `MISSING_TRIGGER` CI lint — turning Anthropic's stylistic advice into a mechanical gate (`wshobson/agents@9b15b34:docs/authoring.md`).
- *Describe only triggering conditions, never the workflow.* `obra/superpowers` states the opposite emphasis from Anthropic — "NEVER summarize the skill's process or workflow" in the description — because a description that reads as documentation doesn't discriminate on when to fire (`obra/superpowers@8ca22db:skills/writing-skills/SKILL.md`). This is a genuine, cited disagreement between two Tier-1 sources — record both, don't average them away.
- *Test trigger accuracy adversarially.* Anthropic's negative-example guidance: "the most valuable [should-not-trigger cases] are the near-misses... Bad: 'Write a fibonacci function' as a negative test for a PDF skill is too easy" (`anthropics/skills@3337550:skills/skill-creator/SKILL.md`).

**Progressive disclosure, done well:**
```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```
Citation: `anthropics/skills@3337550:skills/skill-creator/SKILL.md` ("Anatomy of a Skill"). Concrete enforcement of the boundary: Codex hard-truncates skill bodies at 8KB, so `wshobson/agents` pushes overflow into `references/` and lints for it (`SKILL_OVER_CODEX_CAP`); Anthropic's own pattern for domain-variant skills routes to per-provider reference files (`cloud-deploy/references/{aws,gcp,azure}.md`) so "Claude reads only the relevant reference file."

**Scripts bundled as opaque black boxes, deliberately not read into context:**
```
**Always run scripts with `--help` first** to see usage. DO NOT read
the source until you try running the script first and find that a
customized solution is absolutely necessary. These scripts can be very
large and thus pollute your context window. They exist to be called
directly as black-box scripts rather than ingested into your context
window.
```
Citation: `anthropics/skills@3337550:skills/webapp-testing/SKILL.md`.

**Typical good length (measured, not asserted):**

| repo | skills sampled | median lines | max lines |
|---|---|---|---|
| anthropics/skills | 18 (excl. template) | ~144 | 572 |
| davila7/claude-code-templates | 914 | 261 | 1,576 |

Anthropic's own stated target is "<500 lines ideal"; only one Anthropic skill (`claude-api`, 572 lines) exceeds it, and it's the one with the most inherent API-surface reference material. `davila7`'s median already exceeds most of Anthropic's *maximums*, and its catalog max is >3x the guideline — direct, measured evidence for finding #1 above.

---

## Directly reusable assets

| asset | source | what it is | SPDX |
|---|---|---|---|
| `skill-creator` eval harness (`run_loop.py`, `aggregate_benchmark.py`, `grader.md`/`comparator.md`/`analyzer.md` subagent specs, `references/schemas.md`) | `anthropics/skills@3337550:skills/skill-creator/` | held-out train/test description optimizer + human-in-the-loop benchmark viewer; lift near-wholesale as our own skill QA pipeline | Apache-2.0 (per-skill `LICENSE.txt`) |
| `quick_validate.py` frontmatter validator | `anthropics/skills@3337550:skills/skill-creator/scripts/quick_validate.py` | deterministic CI-able check of `SKILL.md` frontmatter shape (allowed keys, kebab-case name, length limits) | Apache-2.0 |
| TDD / systematic-debugging / verification-before-completion skill triad | `obra/superpowers@8ca22db:skills/{test-driven-development,systematic-debugging,verification-before-completion}/SKILL.md` | Iron-Law-style engineering discipline skills with rationalization tables; adopt directly as our core engineering skills | MIT (Jesse Vincent, 2025) |
| `writing-skills` meta-skill (TDD-for-documentation authoring method) | `obra/superpowers@8ca22db:skills/writing-skills/SKILL.md` | the *method* of pressure-testing a skill against a baseline-failing subagent before shipping it | MIT |
| `plugin-eval` static-lint architecture + CI snapshot-regression pattern | `wshobson/agents@9b15b34:plugins/plugin-eval/`, `evals/README.md`, `.github/workflows/eval-report.yml` | reuse the *architecture* (deterministic lint + committed score snapshot + CI diff-on-drift) for gating our own skill catalog | MIT |
| Portability lint rule set (`MISSING_TRIGGER`, `SKILL_OVER_CODEX_CAP`, `ARGUMENTS_UNFRAMED`, agent-name-collision checker) | `wshobson/agents@9b15b34:docs/authoring.md`, `tools/check_agent_name_collisions.py` | adopt as our own lint rules even if we target Claude Code only, since they're really about prompt-injection-via-`$ARGUMENTS` and file-size hygiene, not just portability | MIT |
| `fp-check` rationalization-rejection table + Standard/Deep verification routing pattern | `trailofbits/skills@0cc1c73:plugins/fp-check/skills/fp-check/SKILL.md` | pattern for any skill that needs to resist the model's own shortcut-seeking; adapt the *structure*, not the security-specific content | CC BY-SA-4.0 (attribution + share-alike required on any derivative) |
| Reference-skill complexity ladder (basic/intermediate/advanced onboarding examples) | `trailofbits/skills@0cc1c73:AGENTS.md` | onboarding pattern for our own skill-authoring contributors | CC BY-SA-4.0 |
| LLM-graded acceptance-criteria test harness + two-speed CI (mock on PR, real SDK nightly) | `microsoft/skills@23d0dac:tests/`, `.github/workflows/test-harness.yml` | reference architecture for grading generated output in CI; would need reimplementing against Claude Agent SDK instead of Copilot SDK | MIT |
| `AGENTS.md` anti-slop contributor gate (disclosure requirement, duplicate-PR search, human-diff-review requirement) | `obra/superpowers@8ca22db:AGENTS.md` | directly adoptable text for our own contributor guidelines if/when this repo accepts external contributions | MIT |
| `pre_tool_use.py` dangerous-command hard-block hook | `disler/claude-code-hooks-mastery@052ad1c:.claude/hooks/pre_tool_use.py` | reference implementation only — **no LICENSE file found in this repo**; do not vendor verbatim, reimplement the pattern | none found — treat as all-rights-reserved until confirmed otherwise |
| `awesome-claude-code` curated link index | `hesreallyhim/awesome-claude-code@97e2763` | useful as a *discovery* pointer only | CC BY-NC-ND 4.0 — **no derivative works permitted**; link to it, never copy its text or structure |

---

## Verdict

**No repo in this sample achieves full "verification-enforced agentic engineering" end-to-end**, where "full" means: a rule is stated, and the harness — not the model's discretion — mechanically prevents the rule from being violated during a live session.

What exists instead is three different, non-overlapping partial solutions, and the gap between them is the headline finding:

1. **Verification of the skill catalog itself, in CI, before merge** — this is solved, and solved well, by three independent repos converging on the same idea (`anthropics/skills` eval harness, `wshobson/agents` plugin-eval static lint + snapshot regression, `microsoft/skills` LLM-graded acceptance-criteria harness). This layer answers "is this skill well-built" mechanically and automatically.

2. **Verification discipline *inside* a skill's instructions** — solved at the prompt-engineering level by `obra/superpowers` (Iron Laws, rationalization tables, the `verification-before-completion` gate function) and `trailofbits/skills` (rationalization-rejection tables, standard/deep verification routing). This is real craft, but it is still **the model choosing to comply** with written text. Nothing in `obra/superpowers`'s own hook config (`obra/superpowers@8ca22db:hooks/hooks.json`) enforces the TDD Iron Law mechanically — the only wired hook is `SessionStart`, which can inject reminders but cannot block a tool call. A sufficiently rushed or context-degraded agent can still skip straight to "tests pass" without running them, and nothing in the repository stops it.

3. **Mechanical, unbypassable enforcement at the tool-call boundary** — solved only narrowly, by `disler/claude-code-hooks-mastery`'s `PreToolUse` hard-block hook, and only for a small, hand-enumerated set of dangerous patterns (`rm -rf`, `.env` access). No repo in the sample ships a hook that verifies "the test suite was actually run and passed before this commit/PR-creation tool call" — the exact claim `verification-before-completion` asks the model to police in itself. That would require a `PreToolUse` hook on `Bash(git commit*)`/PR-creation tools that checks for fresh, matching test-run evidence (e.g., a timestamped exit-code artifact) — nobody in this corpus builds that.

**The gap, stated plainly:** the ecosystem has excellent *documentation* of verification discipline (layer 2) and excellent *catalog-quality* tooling (layer 1), but the actual moment where an agent is tempted to claim "done" without proof is still guarded by prose, not by a hook. Closing that gap — a `PreToolUse`/`Stop` hook that mechanically requires fresh verification-command evidence before a completion-shaped tool call succeeds — is a real, unclaimed opportunity, not a reinvention of something this ecosystem already has.
