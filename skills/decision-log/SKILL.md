---
name: decision-log
description: >
  Use when a non-obvious choice or assumption is made, and when returning to code
  whose reasoning is unclear — recording an ADR, checking whether past assumptions
  still hold, tracing which decision governs a file, or auditing decisions that have
  gone stale. Use PROACTIVELY after choosing an approach, and before changing code
  that an existing decision governs.
---

# Decision log

An agent makes dozens of silent choices per feature: the transaction boundary, the
retry policy, what it decided *not* to handle. None of them appear in the diff. A
month later nobody can answer "why is it like this" or "does that still hold".

This makes each one a file with a falsifiable assumption attached.

## Trigger

**Fire when:** you chose between approaches; you assumed something about scale, the
environment, or the data; you deliberately left something unhandled; you are about to
change code that an existing decision governs.

**Do not fire when:** the choice is forced (one option), local and trivially
reversible (a variable name, a loop form), or already recorded — check with `trace`
first.

## What makes a record worth writing

A decision record that names the winner and nothing else is a conclusion, not a
decision — it cannot be re-evaluated, which is the only reason to keep it. Every
record carries:

- **≥2 options**, each rejected one with a concrete `why_not`
- the **deciding factor** for the winner
- **assumptions**, each with a shell command that fails when it stops being true, and
  a `revisit_when` describing the observable event that invalidates it
- **gaps accepted** — what this deliberately does not handle
- **affects** globs, so the record can be found from the code

## Rules

1. Record a decision when the choice was not forced. One command, at the time you make
   it — not later, when the reasoning has evaporated.
   *Enforced by:* `python3 scripts/decide.py new "<title>" --affects "<glob>"`

2. Every assumption needs a verification command. An assumption nobody can test is a
   belief, and it will never be revisited.
   *Enforced by:* `python3 scripts/decide.py verify` reports unverifiable assumptions
   explicitly rather than skipping them

3. Every assumption needs a `revisit_when`. Without it nothing will ever prompt a
   re-check.
   *Enforced by:* `python3 scripts/decide.py lint`

4. Never edit an accepted decision in place. Supersede it with a new record and set
   `supersedes`, so the history of the reasoning survives.
   *Enforced by:* review

5. Check for an existing decision before changing code it governs.
   *Enforced by:* `python3 scripts/decide.py trace <path>`

6. Re-verify assumptions and check drift before shipping. A decision whose governed
   code moved underneath it needs re-reading, not just re-running.
   *Enforced by:* `python3 scripts/decide.py verify && python3 scripts/decide.py drift`

7. Record what the decision does **not** handle. An empty gaps table claims you thought
   of everything.
   *Enforced by:* `python3 scripts/decide.py lint` warns on an empty gaps table

8. Keep the index generated, never hand-maintained.
   *Enforced by:* `python3 scripts/decide.py index`

## Verify

```bash
# record a decision at the moment you make it
python3 scripts/decide.py new "Session strategy" --affects "src/auth/**" --tag auth
#   then fill: options with why_not, assumptions with verify + revisit_when, gaps

# the record must be complete enough to re-evaluate later
python3 scripts/decide.py lint       # >=2 options, why_not, falsifiable assumptions

# do past assumptions still hold? (runs each assumption's own command)
python3 scripts/decide.py verify

# has governed code moved since the decision, or is a revisit overdue?
python3 scripts/decide.py drift

# which decision governs this file?
python3 scripts/decide.py trace src/auth/session.ts

# everything, for CI
python3 scripts/decide.py check      # lint + index + drift, exits non-zero on problems
```

Records live in `decisions/` in **your** repo (resolved from the git root, not the
plugin), with a generated table in `decisions/INDEX.md`. A worked example is
`decisions/ADR-0001-session-strategy-for-login.md`.

## Failure modes

This skill rejects:

- **A single-option record** — `decide.py lint` reports "a decision with one option is
  not a decision".
- **A rejected option with no `why_not`.**
- **A record with no assumptions**, claiming the choice rests on nothing.
- **An assumption with no `revisit_when`**, which guarantees it is never revisited.
- **An unverifiable assumption presented as verified** — `verify` reports these as
  `SKIP … unverifiable`, visibly, rather than passing silently.
- **A decision whose code changed underneath it** — `drift` names the files and tells
  you to re-read the record.
- **An overdue `revisit_by`.**
- **An empty gaps table.**

**Honest limitations:**
- `drift` is **path-level**: it knows the governed files changed, not whether the
  change actually contradicts the decision. It tells you to look; it cannot conclude.
- `verify` runs whatever command you wrote. A weak command passes trivially — the tool
  enforces that a command *exists*, never that it is meaningful.
- Nothing forces you to record a decision in the first place. That is the honest hole
  in this design: the gate is on record *quality*, not record *existence*. The
  practical mitigation is rule 1 in `feature-planning`, where the spec's decision table
  is generated with the choices already listed.

## Scale

`solo` and up, and the value inverts from most process: it is highest at `solo`,
because there is no colleague who remembers. At `org` it becomes institutional memory
that outlives the team, which is when rule 4 (supersede, never edit) matters most.

## Sources
- ADR and RFC practice, including recording rejected proposals:
  `research/37-findings-review-governance.md`.
- `docs/adr` / `rfcs` directory conventions observed across the corpus:
  `research/10-repo-corpus.md` (D6/D7 scoring).
- Assumption-with-verification-command, `revisit_when`, path-level drift and the
  completeness lint: `SOURCE: original`.
