---
name: approach-selection
description: >
  Use when a problem has several defensible solutions and one must be chosen — which
  database, session strategy, state manager, queue, deployment model, sync vs async,
  library vs hand-rolled, monolith vs service. Gives a weighted scoring method (not
  a record format), a default bias toward reversible choices, and a rule for the
  rare case worth escalating to a human. Use PROACTIVELY whenever you notice you
  are picking between options rather than implementing a known one. Not for writing
  up a choice already made (that's decision-log, which this skill hands off to) and
  not for a feature-kind decision already pre-answered in
  `scripts/data/decisions_required.json` — check there first.
---

# Approach selection

An agent asked to "add caching" will pick something and implement it confidently. The
risk is not that it picks badly — most options work — but that it picks without
recording why, so nobody can tell later whether the constraint that justified it still
holds.

This makes the choosing explicit, cheap, and re-examinable.

## Trigger

**Fire when:** you are about to choose between two or more approaches that both work;
adding a dependency, a datastore, a protocol, an architectural boundary.

**Do not fire when:** the codebase already made this choice — follow it. Consistency
beats a marginally better option, and re-deciding a settled question is how codebases
end up with three HTTP clients.

## The method

Score each option 1-5 on these, in this order of weight:

| weight | criterion | the question |
|--:|---|---|
| ×3 | **reversibility** | if this is wrong in 3 months, what does undoing it cost? |
| ×3 | **blast radius** | when it fails, who is affected and how badly? |
| ×2 | **moving parts** | how many new things can now break or need operating? |
| ×2 | **already in use** | does this repo/team already run it in production? |
| ×1 | **exit cost** | how much of the design leaks into the rest of the system? |
| ×1 | **fit** | does it actually solve the stated problem, not a bigger one? |

Highest weighted score wins. On a tie, apply the tie-breaks in order:

1. The **reversible** option.
2. The option with **fewer moving parts**.
3. The option **already running** in this codebase.
4. The **more boring** option — longer track record, more people who know it.

## The default bias

Absent a specific reason, prefer: **the boring, reversible, already-present option
with the fewest new moving parts.** State the reason when you depart from it. This
bias exists because the failure mode of agent-chosen architecture is uniformly
*over*-selection — a queue where a function call works, a service where a module works.

## Rules

1. Record every choice with at least two options, and a concrete reason each rejected
   option lost. An option listed with no downside was not considered.
   *Enforced by:* `python3 scripts/decide.py lint`

2. Name the single deciding factor for the winner. If you cannot name one, the options
   were equivalent — take the default bias and say so.
   *Enforced by:* `python3 scripts/decide.py lint` (chosen option requires `why`)

3. Record the assumption the choice rests on, with what would falsify it.
   *Enforced by:* `python3 scripts/decide.py lint` (requires `revisit_when`)

4. Do not choose for a requirement nobody stated. Scale, multi-region and
   extensibility are requirements only if written down.
   *Enforced by:* review — the spec's scope table is the authority

5. Escalate to a human only when the choice is **both** hard to reverse **and** high
   blast radius **and** has no clear winner. Otherwise take the default and record it.
   *Enforced by:* review

6. When the repo already made this choice, follow it. Departing needs an ADR that
   supersedes the earlier one.
   *Enforced by:* `python3 scripts/decide.py trace <path>` before choosing

7. Prefer the option you can verify. An approach you cannot test is worse than a
   slightly weaker one you can.
   *Enforced by:* the spec's verification plan must name a command for the chosen path

## Verify

```bash
# has this already been decided here?
python3 scripts/decide.py trace src/<area>/<file>
grep -rniE "redis|kafka|rabbit|postgres|mysql|mongo" --include="*.json" --include="*.toml" . | head

# record the decision with its options and scores
python3 scripts/decide.py new "Cache layer for product reads" --affects "src/catalog/**" --tag backend

# the record must survive lint: >=2 options, why_not on every reject, falsifiable assumption
python3 scripts/decide.py lint

# recurring stack-level choices already have defaults — check before deriving one
ls reviewers/                       # per-stack "Approach selection" tables
grep -A3 "Approach selection" reviewers/<stack>.md
```

Feature-level choices also have pre-answered defaults: `scripts/data/decisions_required.json`
carries 24 recurring decisions across 8 feature kinds, each with a recommendation and
the factor that would change it.

## Failure modes

This skill rejects:

- **A choice with one option recorded.** `decide.py lint` calls this "not a decision"
  and exits non-zero.
- **A rejected option with no `why_not`** — it was listed, not considered.
- **A winner with no deciding factor.**
- **An assumption with no `revisit_when`**, so nothing will ever prompt a re-check.
- **Choosing for unstated scale.** A queue introduced for throughput nobody specified
  is three new failure modes bought with imaginary money.
- **Silently re-deciding a settled question**, producing a second way to do the same
  thing in one codebase.
- **Asking the human** about a cheap, reversible choice. That is what defaults are for,
  and an agent that asks constantly is not working independently.

**Honest limitation:** the scoring is a structured judgement, not a measurement. Two
engineers will score the same options differently and both be defensible. What the
method guarantees is that the reasoning is *written down and falsifiable* — not that
it is optimal. The enforcement is on the record's completeness, never on the choice.

**No diagram step here, deliberately.** A choice between options is compared on the
scoring table, not a flow — a sequence diagram of "call Redis vs call Postgres" adds
nothing a table row doesn't already say. If the *chosen* approach turns out to have
a non-obvious flow worth drawing, that happens downstream in `feature-planning`
(rule 5) or `codebase-comprehension`, once there is code or a planned flow to diagram.

## Next

Record the winner with `decision-log` (`decide.py new` already opened the record —
fill it in). If the choice was made mid-feature-plan, return to `feature-planning`'s
edge-case table. Implementation then follows the normal path to `scoped-review` and
`verification-gate`.

## Scale

`solo` and up. At `solo` the value is memory: you will not remember in six months why
you picked this. At `small-team` it is alignment. At `org` the decision log outlives
the people, which is when rule 3 becomes the important one.

## Sources
- Per-stack approach-selection tables with defaults: `reviewers/*.md`
  (`## Approach selection` in each).
- Per-feature-kind decision defaults: `scripts/data/decisions_required.json`.
- Precedent for recording rejected proposals rather than only accepted ones:
  `research/37-findings-review-governance.md` (ADR/RFC practice).
- The reversibility-first weighting and the default bias: `SOURCE: original`.
