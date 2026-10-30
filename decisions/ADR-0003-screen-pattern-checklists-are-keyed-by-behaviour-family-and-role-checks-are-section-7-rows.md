# ADR-0003: screen-pattern checklists are keyed by behaviour family, and role checks are section 7 rows

```json meta
{
  "id": "ADR-0003",
  "title": "screen-pattern checklists are keyed by behaviour family, and role checks are section 7 rows",
  "status": "accepted",
  "date": "2026-10-30",
  "decided_by": "gaurav porwal (scope), claude (shape)",
  "tags": [
    "screen-patterns"
  ],
  "affects": [
    "scripts/data/edge_cases_ui.json",
    "scripts/data/screen_patterns.json",
    "scripts/plan_feature.py"
  ],
  "commit": "3e3baca",
  "assumptions": [
    {
      "id": "A1",
      "claim": "every product screen-pattern name maps to a family that exists or is listed as planned, so no name is silently unchecked",
      "verify": "bash tests/test_screen_patterns.sh",
      "revisit_when": "the product taxonomy gains names, or a planned family is still unbuilt after two releases",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "every catalogue reader unpacks entries as exactly [what, why missed, test], so a 4th field (platform) would break them",
      "verify": "sh -c \"grep -q 'for i, (kind, what, why, test) in enumerate(edges' scripts/plan_feature.py\"",
      "revisit_when": "a mobile-only or web-only entry is needed",
      "confidence": "high"
    }
  ],
  "options": [
    {
      "name": "do nothing: rely on reviewers and the existing ui-baseline rules",
      "fit": "fail",
      "chosen": false,
      "why_not": "the reported misses (a settings delete with no confirmation, controls shown to roles that cannot use them) recur because no checklist any agent reads holds them"
    },
    {
      "name": "one checklist per screen pattern (152 lists)",
      "fit": "fail",
      "chosen": false,
      "why_not": "the same confirmation and unsaved-changes items would be copied into dozens of lists and drift apart"
    },
    {
      "name": "behaviour families plus a name-to-family map; role checks as a new spec section with its own audit rule",
      "fit": "pass",
      "chosen": false,
      "why_not": "a second table needs its own status vocabulary, evidence rules and deleted-row rule that section 7 already has"
    },
    {
      "name": "behaviour families plus a name-to-family map; role checks as section 7 rows with source role:<name>",
      "fit": "pass",
      "chosen": true,
      "why": "reuses section 7's statuses, evidence checks and deleted-row protection, and testplan picks the rows up with the edge cases"
    }
  ],
  "supersedes": null,
  "revisit_by": null
}
```

## Context

QA and review agents missed expectations such as a confirmation before deleting a workspace, because the only feature-kind checklists (`edge_cases.json`, `edge_cases_infra.json`) cover backend failure modes and reach `plan_feature new` alone. The product team names screens with its own 152-name taxonomy, and many names share one behaviour (a delete, a block and a cancel all need the same confirmation). The taxonomy stays in the team's own projects: this public plugin ships a generic vocabulary, and a project's `screen_patterns.json` adds to it.

## Options considered

### Option 0 — do nothing
Out on fit: the misses come from no checklist holding these items, which reviewers alone have not fixed.

### Option A — one checklist per screen pattern
Out on fit: 152 lists repeating the same few behaviours would drift.

### Option B — families, roles as a new spec section
Works, but duplicates the status, evidence and deleted-row rules section 7 already enforces.

### Option C — families, roles as section 7 rows
Chosen. A role row is an edge case with source `role:<name>`.

## Decision

Option C. Deciding factor: the existing section 7 machinery (status allowlist, evidence-is-proof, deleted seeded row) already does what role checks need, and `testplan new` reads the same table.

## Consequences

Easy: adding a family is data only; a new name is one map entry. Hard: an item that applies only on mobile or only on web cannot say so until entries gain a platform field, which means changing every catalogue reader.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| 15 families mapped as planned, not written | names such as Comments or Chat get no checklist yet; `--screens` says so on stderr | yes | second batch PR |
| no platform field | a mobile-only item would show on web specs | yes | revisit when the first such item is needed (A2) |
| domain modules (appointments, prescriptions) | domain rules stay in the spec author's head | accepted, not planned | — |
