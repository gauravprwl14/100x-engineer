# screen-patterns — contract

Pinned before parallel work (solution-architect review, 2026-10-30). Consumers read this file; only T0 edits it.

## `scripts/data/edge_cases_ui.json`

```json
{
  "_doc": "...",
  "_planned": ["feed-browse", "..."],
  "_roles": [["Role {role}: ...", "why missed", "test with {role}"], ...],
  "<family>": [["what", "why it gets missed", "the test that catches it"], ...]
}
```

- 9 families (`settings` holds settings-specific rows and builds on `form`; a pattern with editable settings lists both): `settings`, `destructive-action`, `form`, `list-table`, `detail-view`, `auth-screens`, `scheduling`, `checkout`, `money-transfer`; 6-10 entries each, every entry exactly 3 non-empty strings.
- Keys starting with `_` are not kinds. Family names never collide with `edge_cases.json` or `edge_cases_infra.json` kinds; no `what` repeats across the three catalogues (`gather()` drops repeats silently).
- `_roles`: exactly 3 templates; `{role}` is the only placeholder and appears in every `what`.

## `scripts/data/screen_patterns.json`

```json
{
  "_doc": "...",
  "_source": "...",
  "patterns": [
    {"name": "Settings", "category": "Account",
     "aliases": ["settings", "preferences"], "families": ["settings", "form"]}
  ]
}
```

- The plugin file holds a generic vocabulary (47 patterns, `_source` `SOURCE: original`). A project may add `<records root>/screen_patterns.json` (same shape, located with `_paths.resolve`) for its own taxonomy: its patterns are added to the plugin's, and on a normalised name or alias clash the project's entry wins (the plugin entry loses that name or alias). `cases` and `new` both read it; a malformed project file exits 2 naming the file.
- Normalise = NFKC, casefold, `&` -> ` and `, collapse whitespace, strip. Normalised names and aliases are unique within each file; none contains `,` or `|`.
- `families`: a non-empty list of catalogue kinds (any of the three catalogues) or `_planned` names; or exactly `["baseline"]`; or exactly `["none"]`.
- Any pattern listing `checkout`, `money-transfer` or `subscription` also lists `payment`; any listing `auth-screens` also lists `auth`.

## `plan_feature`

| surface | behaviour |
|---|---|
| `new --screens "<a>, <b>"` | split on `,`; each name resolved exactly (normalised) against names and aliases; unknown -> exit 2, stderr `unknown screen '<x>'; closest: <up to 3 names>`. Built families merge into `--kind` (order: `--kind` first, then screens' families in order, deduped). Planned, `baseline` or `none` families -> stderr `not yet checked: <name> (<families>)`; still exit 0. If the resolved kinds raise the risk floor, stderr `risk raised to <r> by kind <k>` |
| `new --roles a,b` | each role matches `^[a-z][a-z0-9-]{0,31}$` else exit 2. After the family rows, 3 rows per role in `--roles` order from `_roles` with `{role}` replaced, source `role:<name>` |
| header | `\| screens \| <canonical names joined by ", "> \|` right after `\| kinds \|`, then `\| roles \| <names joined by ", "> \|`; each row omitted when its flag is absent |
| audit | `kinds` stays authoritative for seeded family rows; `roles` is re-expanded and its rows join the deleted-row check; `screens` is a record only, never re-resolved |
| `cases [--kind k,..] [--screens ..] [--roles ..] [--json]` | at least one of `--kind`/`--screens`; resolution and stderr notes as `new`; no `universal` rows unless `--kind universal` is given; writes nothing. Markdown: `\| # \| source \| edge case \| why it gets missed \| test \|`, `#` = `C<n>` (checklist-local, not the spec's `E<n>`). JSON: list of `{"id": "C<n>", "source", "what", "why", "test"}` |

## `testplan new`

For each §7 row with status `TODO` or `covered` and source a UI family or `role:*`: case id `TC-E<n>-1`, AC column `<feature>/E<n>`, level `e2e` for `role:*` and `destructive-action`, else `component`, technique `edge case` (`role` for role rows), input = edge case text, expected = the row's test text with any `_suggested:_ ` prefix removed, automated `yes`. `--all-edge-cases` adds every other source. `trace` is unchanged.
