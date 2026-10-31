# scenario.json, schema 1

The one file the agent writes. `100x flow check` validates it, `100x flow reduce` replays it,
`100x flow build` renders it. Actions and the reducer are `actions.md`; a worked file is
`../assets/examples/stale-writeback.json`. Every object rejects unknown keys (with a
did-you-mean); "Text" is a string or `{"en": "…", "ja"?: "…"}`.

## Contents

| section | answers | size |
|---|---|---|
| [Top level](#top-level) | which keys exist, which are required, which are heavy-only | ~25 lines |
| [Context, vocabulary, outline](#context-vocabulary-outline) | how the page answers in three lines (`tldr`), says what the PR does, defines its words and sketches the code | ~45 lines |
| [Diagrams](#diagrams) | how a mermaid diagram, mind map included, is written, cited and checked | ~25 lines |
| [Code reference](#code-reference) | how a page lists every function in the files behind it, read from the code | ~20 lines |
| [Nodes, numbers, evidence](#nodes-numbers-evidence) | how boxes, tagged numbers and checkable evidence are written | ~45 lines |
| [Scenarios and steps](#scenarios-and-steps) | how a timeline, an issue and its origin, a fix branch, a step's `expect` and `code` are written | ~50 lines |
| [Decision, checks, compare](#decision-checks-compare) | how the trade-off card and the heavy extras are written | ~20 lines |
| [Rules check enforces](#rules-check-enforces) | every finding `flow check` can raise, and the light/heavy budgets | ~50 lines |
| [Build contract](#build-contract) | what `flow build` reads and writes, the shell tokens, how data is escaped, where real-code snippets come from, the page's ready signal, the `explain.md` sections | ~35 lines |

## Top level

| key | req | type | notes |
|---|---|---|---|
| `schema` | yes | `1` | anything else exits 2 |
| `title` | yes | Text | |
| `subject` | yes | object | `kind` (`pr`\|`concept`\|`plan`, req), `lede` (Text, req), `repo`, `sha`, `base` (hex 7-40), `pr` (int). `kind: pr` requires `sha` |
| `nodes` | yes | list | ≥ 1 |
| `scenarios` | yes | list | ≥ 1 |
| `tier` | no | `light`\|`heavy` | default `light`; `--tier` overrides |
| `numbers` | no | object | name → number |
| `evidence` | no | object | id → evidence |
| `initial` | no | object | `stores` / `caches`: node id → {key: value}; the state before step 0 of every root scenario |
| `decision` | no | object | the trade-off card |
| `checks` | heavy | list | predict-before-reveal prompts |
| `compare` | heavy | list | scenario ids drawn on one clock |
| `context` | pr | object | what the PR does for a user and what it covers; required when `subject.kind` is `pr` |
| `tldr` | no | object | the three-line answer at the top of the page: what, how, watch out |
| `terms` | no | list ≤ 12 | the words a reader outside the module needs |
| `outline` | no | list (light ≤ 1, heavy ≤ 3) | pseudocode of the workflow, lines linked to steps |
| `diagrams` | no | list (light ≤ 2, heavy ≤ 4) | mermaid diagrams drawn beside the outline |
| `reference` | no | list (1-8) | Python files whose functions and classes the page lists; see [Code reference](#code-reference) |

Light is the subset without `checks`, `compare` and `ja` text; a light check notes and ignores
them, so the same file upgrades with `--tier heavy`. A value in state (`initial`, `cache.set`,
`db.write`, `expect`) is a string, integer, boolean or null: no floats, so the Python and JS
reducers compare values identically.

## Context, vocabulary, outline

**`tldr`** — the first thing a reader sees: `what` (Text, req: what it does), `how` (Text, req:
how it works), `watch_out` (Text: the one risk to remember). Each is one plain sentence of at most
200 characters per language; the bare-number and jargon rules apply as they do to a step title.
Optional, so older files still check; a PR page should have one.

```json
"tldr": {"what": "Lets an editor tag an item from the gallery view.",
         "how": "The route checks the editor's role, then rewrites the item's tag list in one write.",
         "watch_out": "Two editors saving at once: the later save wins, with no warning."}
```

**`context`** — read before the player: `purpose` (Text, req: what a user can do, in their
words), `why_now` (Text), `in_scope` (1-8 Text, req), `out_of_scope` (≤ 8 Text), `entry_points`
(≤ 12). Say which entry points are animated and which follow "the same gates".

**Entry point**

| key | req | notes |
|---|---|---|
| `label` | yes | Text, e.g. `PATCH /items/:id/tags` |
| `kind` | no | `route` `job` `event` `command` `function` `screen` |
| `scenario` | no | the scenario that animates it; must exist |
| `note` | no | Text, e.g. "same gates as the route above" |
| `ev` | no | evidence id |

**Term** — `{term, means, example?}`: `term` a string, unique case-insensitively; `means` and
`example` Text. A word listed here may appear in a step title (see `jargon in step title`).

**Outline** — `{title, scenario, lines}`: `title` Text (a signature such as
`reconcile(itemId, add, remove)`), `scenario` an id, `lines` 1-20 of:

| key | req | notes |
|---|---|---|
| `code` | yes | pseudocode string; code, not prose, so the bare-number check skips it |
| `indent` | no | int 0-6 |
| `steps` | no | 0-based indexes into the scenario's visible steps, inherited included |
| `ev` | one of | evidence id |
| `tag` | one of | `inferred`; a line needs `ev` or `tag: inferred`, as a step does |

## Diagrams

**Diagram** — one mermaid diagram, drawn beside the Workflow outline and fenced in `explain.md`.

| key | req | notes |
|---|---|---|
| `id` | yes | `[a-z][a-z0-9_-]*`, unique among diagrams |
| `title` | yes | Text |
| `kind` | yes | `sequence` `flowchart` `state` `er` `class` `mindmap`; must be the type the source declares (`sequenceDiagram`, `flowchart`/`graph`, `stateDiagram`/`stateDiagram-v2`, `erDiagram`, `classDiagram`, `mindmap` as the first line after any frontmatter) |
| `source` | yes | mermaid source string; code, not prose, so the bare-number check skips it. Never HTML: the page hands it to mermaid as text and shows it as text when mermaid cannot load |
| `caption` | no | Text: one or two sentences on how to read it; prose, so bare numbers are checked |
| `ev` | one of | list of evidence ids |
| `tag` | one of | `inferred`; a diagram needs `ev` or `tag: inferred`, as a step does |
| `scenario` | no | the scenario it explains; the page links to it ("Watch it animated") |

`flow check` runs the source through `scripts/check_diagrams.py` (the `diagramming` skill's
checker): every error it reports is a finding, except its level-3 demand for a numbered step table
under the block, which the page's own step cards meet. A sequence participant must be declared
before its first message, a flowchart label holding parentheses is quoted, and no placeholder text
is left in.

A **mind map** (`kind: mindmap`) is for a concept or module overview: the nouns and how they group,
not the order things happen in, e.g. a module's routes, gates, data and risks around one root.
Its source starts with `mindmap`, has exactly one root at the smallest indent, uses one kind of
indentation (all spaces or all tabs), and a line that steps back out lines up with an earlier
sibling. Its node count takes the same level budgets as a flowchart (`%% level: 1` ≤ 12 nodes).

## Code reference

**`reference`** — the drill-down below the walkthrough: what each function and class in the files
behind the page does, and who uses it. The agent names files and writes notes; the inventory
itself is never written by hand. `flow build` reads each file at the page's revision (the same
one evidence resolves against) with `scripts/code_ref.py` and renders a table per file: symbol,
line span, what it does (the note, else the first docstring line, else "no docstring"), used by
(other symbols in the same file whose body names it, matched by name, so a method called `get`
is "used by" anything calling a `.get`; a decorator does not count), and a branch
count (ifs, loops, boolean operators: a rough measure of logic).

| key | req | notes |
|---|---|---|
| `path` | yes | repo-relative `.py` path; unique. Python only in this version |
| `symbols` | no | the names to show, in order (`Class.method` for a method); default every top-level function, class and method |
| `notes` | no | symbol name → Text: a one-line summary for a symbol with no docstring or a misleading one; prose, so the bare-number check applies; a note on a name not in `symbols` is a finding |

With `--repo`, `flow check` fails a file git cannot read or parse at that revision and a symbol or
note naming something the file does not hold (with a did-you-mean), so a page cannot describe a
function that is not there. Like evidence, this runs only on a file with no shape findings.
Without `--repo`, `flow build` leaves the section out and says so on stderr.
`100x code_ref build <file>… --md` prints the same inventory for any file;
`100x code_ref check reference.json` exits 1 once a file has changed since it was read.

## Nodes, numbers, evidence

**Node** — one box on the map; the column comes from `role`, the row from declaration order.

| key | req | type | notes |
|---|---|---|---|
| `id` | yes | `[a-z][a-z0-9_-]*` | unique |
| `role` | yes | enum | `client` `edge` `service` `queue` `worker` `cache` `store` `external` |
| `label` | yes | Text | |
| `ref` | no | string | display only, e.g. `src/notes.js:9` |
| `ev` | no | evidence id | |
| `outside_diff` | no | bool | drawn as context, not part of the change |
| `slots` | no | int 1-12 | worker only; default 1 |

**Number** — every number a reader sees in prose is `{{name}}`, rendered as `v` + `unit`.

| key | req | notes |
|---|---|---|
| `v` | yes | int or float |
| `unit` | yes | free text; `wait` needs `ms`, `s`, `min` or `h` |
| `tag` | yes | `verified` (needs `ev`), `measured` (needs `source`: the command or dashboard), `estimated` (needs `basis`: inputs and arithmetic) |
| `ev` / `source` / `basis` | per tag | evidence id / Text / Text |

**Evidence** — id `[A-Za-z][A-Za-z0-9_.-]*`, one of two shapes, both resolved with git:

| shape | keys | what check does |
|---|---|---|
| anchor | `at`: `path:line` or `path:line@<hex sha>`, `anchor`: token | `git show <rev>:<path>`; the token must appear within ±2 lines of `line` |
| absence | `absent`: Text, `git_grep`: ERE pattern, `path`: pathspec, `hits`: int | `git grep -n -E -e <pattern> <rev> -- <path>`; the line count must equal `hits` |

Paths are relative to the repo root. **Which revision:** the `@sha` on the entry, else
`subject.sha`, else `--rev`, else `HEAD` of `--repo` (default `.`). A PR scenario always pins
`subject.sha`; a concept or plan may leave it out and resolve against whatever clone `--repo`
names. That is how the committed example works: its anchors carry no SHA, and
`tests/test_flow.sh` turns `tests/flow/fixture-app/` into a throwaway repo and checks against its
`HEAD`. Evidence present and `--repo` not a git repo exits 2.

## Scenarios and steps

**Scenario**

| key | req | notes |
|---|---|---|
| `id` | yes | `[a-z][a-z0-9_-]*`, unique |
| `kind` | yes | `happy` `edge` `failure` `race` `load` `issue` `fix` |
| `title` | yes | Text |
| `steps` | yes | ≥ 1 step |
| `severity` | issue | `low` `medium` `high` `critical`. A scenario with a severity **is an issue**; `kind: issue` requires one; `happy` and `fix` may not have one |
| `fixed_by` | issue | non-empty list of `kind: fix` scenario ids |
| `open` | issue | `true` when no fix is shown; an issue needs `fixed_by` or `open: true` |
| `branch` | no | `{"from": <scenario id>, "at": N}`: the scenario starts with the first N steps a reader sees in `from` (inherited ones included; N past the end and cycles are `reducer` findings), then its own |
| `origin` | issue | `in-code` (the code at this commit does it), `what-if` (a counterfactual that shows why the real design is the way it is), `found-in-review`. Required on every issue. A fix of a `what-if` issue cites the real design: at least one of its own steps has `ev` |

A fix is its own scenario branched from the issue at the step where it diverges, so the reader
replays the same timeline with the fix in place. Budgets count the steps a reader sees,
inherited ones included. Step indexes (`#<scenario>.<step>`, `checks[].step`, reducer `step`)
count inherited steps too.

**Step**

| key | req | notes |
|---|---|---|
| `t` | yes | Text, the card title |
| `do` | yes | non-empty list of `[action, …args]` (`actions.md`) |
| `d` | no | Text, one or two sentences of why |
| `time` | no | Text, a clock label |
| `ev` | one of | list of evidence ids |
| `tag` | one of | `verified` \| `inferred`; with no `ev` it must be `inferred` (drawn dashed) |
| `hazard` | no | `"stale-writeback"` or a list; must equal what the reducer produces at this step |
| `expect` | no | asserted against the state after this step |
| `code` | no | 1-8 pseudocode strings for this step; exempt from the bare-number check |

**`expect`** keys, all optional: `hit` (`"hit"`\|`"miss"`\|null, the step's last `cache.get`),
`vars` {name: value}, `cache` {cache id: {key: value, null = absent}}, `stale` {cache id: {key:
bool}}, `store` {store id: {key: value, null = absent}}, `queues` {queue id: length}, `counters`
{name: int}. An inherited step's `expect` and `hazard` are checked once, in the scenario that owns it.

## Decision, checks, compare

**`decision`**: `options` (≥ 2, unique ids), `chosen` (an option id whose `fit` is `pass`),
`deciding_factor` (Text), `revisit_when` (Text), `source` (string: an ADR path, a thread, or
`SOURCE: original`). **Option**: `id`, `label` (Text), `fit` (`pass`\|`fail`: does it solve the
problem at all; the same filter `100x decide lint` applies), `pros` / `cons` (lists of Text),
`scenario` (optional: the scenario that shows it).

**`checks`** (heavy): `[{"scenario", "step", "q", "answer"}]`; the player pauses before `step`
and asks `q`. **`compare`** (heavy): ≥ 2 distinct scenario ids, drawn on one clock.

## Rules check enforces

| finding (prefix of the message) | rule |
|---|---|
| `missing required key` / `unknown key` / `must be …` | shape, per the tables above |
| `unknown node` / `node 'x' is a <role>, <action> needs a <role>` | every action, `initial` and `expect` node ref resolves with the right role |
| `unknown action` / `wrong arity` | the frozen vocabulary in `actions.md` |
| `unknown evidence id` | every `ev` resolves |
| `step has no evidence` | `ev` non-empty or `tag: inferred` |
| `bad anchor` | the revision exists, the file exists at it, the line is in range, the anchor is within ±2 lines |
| `absence contradicted` / `absence: git grep failed` | the stated hit count is the real one |
| `bare number` | a word starting with a digit in any prose field (every Text, every language, `tldr`, `context`, `terms`, outline titles, diagram titles and captions, reference notes; not `code` or a diagram `source`) outside `{{name}}`. Allowed: words starting with a letter (`C3`, `v2`, `sha256`), the subject's PR number, a word of the subject's `repo` name (a project called `100x`), a PR or issue reference (`PR 1497`, `PR #1497`, `#1227`) and, in `reply` labels only, an HTTP status 100-599 |
| `unknown number` | every `{{name}}` is in `numbers` |
| `issue has neither fixed_by nor open: true` | Q4: every issue says what fixes it, or that nothing does yet |
| `expect contradicts reducer` | `expect` and a declared `hazard` match the replay |
| `undeclared hazard` | the reducer produced a hazard the step does not declare |
| `reducer` | an action that cannot apply: pickup from an empty queue or into a full worker, free with nothing held, an unbound `$var`, mark-stale on an absent key |
| `needs a $variable` | `cache.set-if-fresh` was given a literal: it compares against the read a `$var` came from |
| `subject.kind pr needs context` | a PR page says what the PR does for a user and what it covers |
| `issue has no origin` | every issue says whether it is in the code, a what-if, or found in review |
| `fix for what-if issue … cites no evidence` | a counterfactual's fix shows the real design, cited |
| `no symbol '<name>' in <path>` / `reference[i].path: …` | every `reference` file parses at the page's revision and holds every named symbol and note |
| `jargon in step title` / `jargon in tldr` | a camelCase, PascalCase (two capitals), snake_case or dotted (`Promise.all`; both parts ≥ 2 characters) word in a step `t` or a `tldr` line, any language, that is not a word of a `terms[].term`, of a node `label` or a node `id` (case-insensitive). `PATCH`, `ACL`, `postgres`, `e.g.` pass |
| `keep it to one sentence` | each `tldr` line is at most 200 characters in every language |
| `duplicate term` | each term is defined once, case-insensitively |
| `outline line has no evidence` | each outline line has `ev` or `tag: inferred` |
| `diagram has no evidence` | each diagram has `ev` or `tag: inferred` |
| `diagram '<id>': <problem>` | a problem `scripts/check_diagrams.py` reports in the source (undeclared sequence participant, unrecognised arrow, unquoted parentheses in a flowchart label, placeholder text, a declared level's node budget, a level-3 diagram with no shown branch, a mind map with no root, more than one root, inconsistent or mixed indentation, no recognisable diagram type); its level-3 step-table rule does not apply |
| `kind '<kind>' does not match the source` | `kind` names the diagram type check_diagrams reads from the source |
| `duplicate diagram id` | diagram ids are unique |
| `step N is past the end of scenario` | outline `steps` and `checks[].step` index the scenario's visible steps |
| `over budget` | the tier's limits below |

| budget | light | heavy |
|---|---|---|
| nodes | ≤ 8 | ≤ 12 |
| scenarios | ≤ 2 | ≤ 5 |
| steps per scenario, inherited included | ≤ 8 | ≤ 12 |
| outlines | ≤ 1 | ≤ 3 |
| diagrams | ≤ 2 | ≤ 4 |

Exit 0 clean, 1 findings, 2 unreadable file, invalid JSON, `schema` ≠ 1, or evidence with no git
repo. Hazards and notes never change the exit code. `--json` prints
`{file, tier, findings: [{loc, message}], hazards: [str], notes: [str]}`.

## Build contract

`flow build <scenario.json> [--tier] --out <dir> [--assets <dir>]` refuses (exit 1) a file with
structural or reducer findings (run `check` for evidence first), and exits 2 when
`<assets>/shell.html`, `flow-player.js` or `flow-player.css` is missing (default assets:
`skills/explain/assets/`). It writes `<out>/index.html` and `<out>/explain.md`. The HTML is the shell with `{{flow_css}}`,
`{{flow_js}}`, `{{flow_data}}` (all three required) and `{{flow_tier}}`, `{{flow_title}}`
(optional) replaced in one pass. `flow_data` is `{"tier", "scenario", "snippets"}` as JSON with
every `<` written `\u003c`, for a `<script type="application/json">` block; `</script` in the JS and
`</style` in the CSS are escaped. The player runs its own reducer; `tests/flow/states.json` pins
it to this one. `tier` picks the renderer: `light` draws one static card per step (a small map of
the state after it), `heavy` the animated player. When the engine has rendered it sets
`data-flow-ok` and `data-flow-steps` (`<scenario>:<steps>,…`) on `<html>`, or `data-flow-error`.
`snippets` is real code, read by build and never written in the scenario: with `--repo`, for every
anchor evidence entry, `git show <rev>:<path>` at the revision `check` resolves, lines `line-3` to
`line+5` clamped to the file, as `{<evidence id>: {"path", "sha", "start", "lines", "hl"}}` (`start`
and `hl` are 1-based; `hl` is the line within ±2 that holds the anchor, nearest the cited one, so a
citation one line off still highlights the matched code). Without `--repo`, or where git cannot read an entry, the
entry is left out (`{}` with no repo), build still succeeds and prints one stderr note, and the
player shows pseudocode only.

`explain.md` is the PR-comment export: the H1; when `tldr` is present, one blockquote right under it
(`> **What:** …`, `> **How:** …`, `> **Watch out:** …`, one per line); the lede and its table; `## Contents` (one row per `##` section
present below it, in page order: a link to its GitHub anchor and what the section answers);
`## Before you watch` (purpose, why now,
in / not in this PR, entry points with the scenario that animates each), `## Terms`, `## Diagrams`
(per diagram a `###` title, a ```` ```mermaid ```` fence, the caption, the scenario it animates and
its evidence or *inferred*), `## Workflow outline` (each outline fenced, indented, linked lines ending `# step N`, 1-based); the map; a
section per scenario with its kind, `origin:` and severity, a what-if banner, a table (step, what
happens, what the step changed, evidence) and a fenced `Step N:` block per step with `code`; the
decision and the numbers, with `{{name}}` filled in.
