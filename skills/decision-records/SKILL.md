---
name: decision-records
description: >
  ADR, decision record, assumption — which decision governs this file, why did we choose X:
  record a choice with a falsifiable assumption, trace it, find any record in a big
  decisions/specs/RCA ledger. Not for choosing (→ approach-selection).
---

# Decision records

An agent makes dozens of silent choices per feature: the transaction boundary, the retry policy,
what it decided *not* to handle. None appear in the diff, and a month later nobody can answer "why
is it like this" or "does that still hold". This skill makes each one a file with a falsifiable
assumption attached, and keeps the whole pile — PRDs, specs, decisions, RCAs, reviews — findable
once it grows past what anyone browses. Formerly `decision-log` (one record) and
`engineering-ledger` (the whole ledger).

| mode | when | commands | detail |
|---|---|---|---|
| **record** | you just chose between approaches, assumed something, or left a case unhandled | `100x decide new` / `lint` / `verify` | `references/record.md` |
| **trace** | about to change code an existing decision may govern | `100x decide trace <path>` / `drift` | `references/record.md` |
| **find** | "why is this like this" and you don't know which record or id; a spec may have no decision behind it; a records directory is too big to browse | `100x ledger find` / `gaps` / `check` / `shard` | `references/ledger.md` |

## Trigger

**Fire when:** you chose between approaches; you assumed something about scale, the environment or
the data; you deliberately left something unhandled; you are about to change code an existing
decision governs; you need to know why something is the way it is; you added any record; you want
to check whether a spec, PRD or fix has its reasoning recorded; a records directory has grown large.

**Do not fire when:** the choice is forced (one option), local and trivially reversible (a variable
name, a loop form), or already recorded — check with `trace` first; you are mid-implementation and
the question is "what does this code do" (`codebase-comprehension`); you are still choosing
(`approach-selection` owns the method, then hands the winner here).

## What makes a record worth writing

A record that names the winner and nothing else is a conclusion, not a decision — it cannot be
re-evaluated, which is the only reason to keep it. Every decision record carries: **≥2 options**,
each with `"fit": "pass"` or `"fail"` (at least one passes, the chosen one passes; optional 1-5
`scores` make the chosen one the top fit-passing score unless an `override_reason` says why), each
rejected one with a concrete `why_not`; the **deciding factor**; **assumptions**, each with a
shell command that fails when it stops being true and a `revisit_when` naming the observable event
that invalidates it; **gaps accepted**; and **affects** globs so the record is found from the code.

The ledger scheme (`references/ledger.md`), under the records root `<root>` (`docs/engineering/`
by default, or `.100x.json` `{"root": "..."}` at the git root, or `HUNDREDX_ROOT_DIR`;
`docs/OPERATING-MODEL.md` §8): `<root>/prds/<feature>/prd.md`, `<root>/specs/<feature>/spec.md`,
`<root>/decisions/ADR-NNNN-slug.md`, `<root>/rca/RCA-NNNN-slug.md`, `<root>/reviews/REV-NNNN-slug.md`,
with generated `<root>/ledger/INDEX.md` (every record by type) and `<root>/ledger/MAP.md` (feature ×
record-type matrix). Ids are typed, prefixed and monotonic; past 40 records a directory is
date-sharded and ids never change.

## Rules

### Record and trace

1. Record a decision when the choice was not forced, at the time you make it.
   *Enforced by:* `100x decide new "<title>" --affects "<glob>"`
2. Every assumption needs a verification command; an untestable assumption is a belief.
   *Enforced by:* `100x decide verify` reports unverifiable assumptions explicitly rather than skipping them
3. Every assumption needs a `revisit_when`, or nothing will ever prompt a re-check.
   *Enforced by:* `100x decide lint`
4. Never edit an accepted decision in place; supersede it with a new record and set `supersedes`.
   *Enforced by:* review
5. Check for an existing decision before changing code it governs.
   *Enforced by:* `100x decide trace <path>`
6. Re-verify assumptions and check drift before shipping; moved code needs the record re-read.
   *Enforced by:* `100x decide verify && 100x decide drift`
7. Record what the decision does **not** handle; an empty gaps table claims you thought of everything.
   *Enforced by:* `100x decide lint` warns on an empty gaps table
8. Keep the decisions index generated, never hand-maintained.
   *Enforced by:* `100x decide index`

### Find across the ledger

9. Record at the moment — decisions and RCAs alike; reasoning evaporates within days.
   *Enforced by:* `100x decide new` / `100x rca new`
10. Every record needs a stable id and a date, from the scaffolding tools, never hand-created.
    *Enforced by:* `100x ledger index` (records without a parseable id surface as unattached)
11. Attach every record to a feature via `links.feature`, a tag matching a spec directory, or an `affects` glob.
    *Enforced by:* `100x ledger map` lists unattached records separately
12. Never hand-edit a generated index; `<root>/ledger/INDEX.md` and `<root>/ledger/MAP.md` are outputs.
    *Enforced by:* both carry a "regenerated by" header; `100x ledger index` overwrites them
13. Shard before a directory becomes unbrowsable, not after.
    *Enforced by:* `100x ledger gaps` warns past 40 records per directory
14. Search the ledger before asking a human or re-deriving an answer.
    *Enforced by:* `100x ledger find <term>`
15. Run the linkage audit in CI so gaps surface while the context is fresh.
    *Enforced by:* `100x ledger check`

## Verify

```bash
# record: at the moment you choose, then make it re-evaluable (~0.2s)
100x decide new "Session strategy" --affects "src/auth/**" --tag auth
100x decide lint       # >=2 options, fit on each, why_not, falsifiable assumptions, revisit_when

# trace: which decision governs this file, and does it still hold?
100x decide trace src/auth/session.ts
100x decide verify     # runs each assumption's own command
100x decide drift      # governed code moved, or a revisit is overdue

# find: across every record type (~0.5s)
100x ledger find "session"       # ids, titles and bodies
100x ledger gaps                  # specs with no decision, PRDs with no spec, ...
100x ledger stats                 # volume per month, sharding threshold
100x ledger shard                 # ids stay stable; links keep working

# CI
100x decide check && 100x ledger check
```

Records live in **your** repo under `<root>` (resolved from the git root, not the plugin). A worked
example is this repo's `decisions/ADR-0001-session-strategy-for-login.md` (this repo pins
`{"root": "."}`).

## Failure modes

This skill rejects:

- **A single-option record** — `decide lint`: "a decision with one option is not a decision".
- **A rejected option with no `why_not`**, or a record with no assumptions.
- **An assumption with no `revisit_when`**, or an unverifiable one presented as verified —
  `verify` prints `SKIP … unverifiable` visibly.
- **A decision whose code changed underneath it** — `drift` names the files; an overdue `revisit_by`.
- **An empty gaps table.**
- **A spec with no decision record**, a PRD with no spec, an RCA with no linked decision.
- **A decision with no `affects` glob and no linked feature** — unreachable from the code.
- **A malformed meta block**, reported as an ERROR rather than silently skipped.
- **40+ records in one flat directory**, or a hand-edited index that will be overwritten.

**Honest limitations:** `drift` is path-level — it knows governed files changed, not whether the
change contradicts the decision. `verify` runs whatever command you wrote; a weak one passes. `find`
is substring matching, not semantic search. Feature attachment is inferred when not explicit, and the
`affects`-path heuristic is weak — prefer `links.feature`. Nothing forces a record to exist; the
mitigation is upstream, where `100x plan_feature new` lists the choices in the spec's decision table.

## Next

Continue whatever triggered this (`feature-planning`, `approach-selection`, `bug-fix`,
`root-cause-analysis`). RCAs are written by `root-cause-analysis` and specs by `feature-planning`;
come back here to confirm linkage (`ledger check`) or search before re-deriving an answer.

## Scale

`solo` and up — the value is highest at `solo`, because there is no colleague who remembers; the
index alone, no sharding. `small-team (2-10)`: add `ledger gaps` to CI, when "is there a decision
behind this?" starts getting asked in review. `org (10+)`: sharding, the traceability matrix and
rule 4 (supersede, never edit) become load-bearing, because records outlive their authors.

## Sources

- ADR/RFC practice, including recording rejected proposals: `research/37-findings-review-governance.md`.
- `docs/adr`, `rfcs/`, `proposals/` layouts scored as D6/D7 signals: `research/10-repo-corpus.md`,
  `research/00-signal-rubric.md`.
- Incident-to-regression-test linkage, why RCAs point at decisions: `research/35-findings-security-reliability.md`.
- Assumption-with-verification-command, `revisit_when`, path-level drift, the completeness lint, the id
  scheme, the 40-record sharding threshold and the traceability matrix: `SOURCE: original`.
