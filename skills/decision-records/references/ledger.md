# The whole ledger — detail

Reference for `decision-records` (loaded on demand). The numbered rules and the Verify block live in `../SKILL.md`; rule numbers below refer to that file.

A flat `<root>/decisions/` directory is fine at 10 records and unusable at 300. Nobody
browses it, so nobody reads it, so writing to it stops paying — and the whole
discipline quietly dies. Three mechanisms prevent that.

## The scheme

Every path is under the records root `<root>`: `docs/engineering/` by default, or
`.100x.json` `{"root": "..."}` at the git root, or `HUNDREDX_ROOT_DIR`
(`docs/OPERATING-MODEL.md` §8). This plugin's own repo pins `{"root": "."}`.

```
<root>/prds/<feature>/prd.md          why we are building it
<root>/specs/<feature>/spec.md        what we are building
<root>/specs/<feature>/plan.json      the task graph, stamped against the spec
<root>/specs/<feature>/testplan.md    the test plan (`testplan new --out`)
<root>/specs/<feature>/reports/       one agent report per task
<root>/decisions/ADR-NNNN-slug.md     why it is built this way
<root>/rca/RCA-NNNN-slug.md           why it broke
<root>/reviews/REV-NNNN-slug.md       what a review concluded
<root>/ledger/INDEX.md                generated: every record, by type
<root>/ledger/MAP.md                  generated: the traceability matrix
<root>/INDEX.md                       catalogue (`check_index --register`)
```

**1. Typed, prefixed, monotonic ids.** `ADR-0007`, `RCA-0002`. The id is in the
filename, so it is greppable, and a link to it survives the file moving.

**2. Date sharding at a threshold.** Past 40 records in one directory, `ledger.py
shard` moves them to `<root>/decisions/YYYY/QN/` and writes a per-shard index. The master
index links to shards instead of listing 300 rows. **Ids do not change**, so nothing
that referenced a record breaks.

**3. A traceability matrix**, because the question people actually ask is not "what
records exist" but "is there a decision behind this spec?" `<root>/ledger/MAP.md` is a
feature × record-type grid, and `ledger.py gaps` reports the missing cells that
matter.

## Failure modes

This skill rejects:

- **A spec with no decision record.** Either no non-obvious choice was made — say so —
  or the reasoning is undocumented.
- **A PRD with no spec** — nothing turns it into work.
- **An RCA with no linked decision**, when an assumption being violated is one of the
  most common root causes.
- **A decision with no `affects` glob and no linked feature** — unreachable from the
  code it governs, so nobody will ever find it from the place it matters.
- **A record with a malformed meta block**, reported as an ERROR rather than silently
  skipped.
- **40+ records in one flat directory**, which is the point at which browsing stops.
- **A hand-edited index**, which will be overwritten and meanwhile lies.

**Honest limitations:**
- Feature attachment is **inferred** when not explicit: from `links.feature`, then a
  tag matching a spec directory, then the last non-glob segment of an `affects` path.
  That last heuristic is weak — prefer `links.feature`.
- `find` is substring matching over ids, titles and bodies. There is no semantic
  search, so a question phrased differently from the record will not match.
- **Nothing forces a record to exist.** The gate is on quality and linkage, not
  existence. The mitigation is upstream: `plan_feature.py` generates the decision table
  with the choices already listed, so not recording one is a visible omission.

No diagram step here — this skill indexes and searches text records, it does not
represent a flow. If `find` surfaces a spec or decision whose flow is unclear, the
diagram is generated where that flow lives (`codebase-comprehension`, `feature-planning`).

## Next

For creating or checking one record, hand off to the skill that owns it:
record mode (ADRs), `root-cause-analysis` (RCAs), `feature-planning` (specs/PRDs).
This skill is where you come back to after, to confirm linkage (`ledger.py check`)
or to search before re-deriving an answer (`ledger.py find`).

## Scale

`solo`: the index alone, no sharding. The value is that in six months you will not
remember, and `find` beats archaeology.
`small-team (2-10)`: add `gaps` to CI. This is where "is there a decision behind this?"
starts getting asked in review.
`org (10+)`: sharding and the traceability matrix become load-bearing, because the
records outlive the people who wrote them.

## Sources
- ADR/RFC directory conventions and the practice of recording rejected proposals:
  `research/37-findings-review-governance.md`.
- `docs/adr`, `rfcs/`, `proposals/` layouts observed across the corpus and scored as
  D6/D7 signals: `research/10-repo-corpus.md`, `research/00-signal-rubric.md`.
- Incident-to-regression-test linkage, which is why RCAs point at decisions:
  `research/35-findings-security-reliability.md`.
- The id scheme, the 40-record sharding threshold, the traceability matrix and the
  linkage audit: `SOURCE: original`.
