# One decision record — detail

Reference for `decision-records` (loaded on demand). The numbered rules and the Verify block live in `../SKILL.md`; rule numbers below refer to that file.

An agent makes dozens of silent choices per feature: the transaction boundary, the
retry policy, what it decided *not* to handle. None of them appear in the diff. A
month later nobody can answer "why is it like this" or "does that still hold".

This makes each one a file with a falsifiable assumption attached.

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

No diagram step here, deliberately — a decision record is a table of options and an
assumption with a falsification command, not a flow. If the decision concerns a
flow worth drawing, the diagram lives where the flow does (`feature-planning`,
`codebase-comprehension`), and the record's `affects` glob points at it.

## Next

Once recorded: continue whatever triggered this (`feature-planning`,
`approach-selection`, `bug-fix`, `root-cause-analysis`). Periodically, or before a
release, find mode's `check`/`gaps` catch records this skill's per-record
lint cannot — an orphaned decision, or a spec with none behind it.

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
