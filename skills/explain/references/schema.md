# scenario.json, schema 1

The one file the agent writes. `100x flow check` validates it, `100x flow reduce` replays it,
`100x flow build` renders it. Actions and the reducer are `actions.md`; a worked file is
`../assets/examples/stale-writeback.json`. Every object rejects unknown keys (with a
did-you-mean); "Text" is a string or `{"en": "…", "ja"?: "…"}`.

## Contents

| section | answers | size |
|---|---|---|
| [Top level](#top-level) | which keys exist, which are required, which are heavy-only | ~20 lines |
| [Nodes, numbers, evidence](#nodes-numbers-evidence) | how boxes, tagged numbers and checkable evidence are written | ~45 lines |
| [Scenarios and steps](#scenarios-and-steps) | how a timeline, an issue, a fix branch and a step's `expect` are written | ~45 lines |
| [Decision, checks, compare](#decision-checks-compare) | how the trade-off card and the heavy extras are written | ~20 lines |
| [Rules check enforces](#rules-check-enforces) | every finding `flow check` can raise, and the light/heavy budgets | ~30 lines |
| [Build contract](#build-contract) | what `flow build` reads and writes, the shell tokens, how data is escaped, the page's ready signal | ~20 lines |

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

Light is the subset without `checks`, `compare` and `ja` text; a light check notes and ignores
them, so the same file upgrades with `--tier heavy`. A value in state (`initial`, `cache.set`,
`db.write`, `expect`) is a string, integer, boolean or null: no floats, so the Python and JS
reducers compare values identically.

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
| `bare number` | a word starting with a digit in any prose field (every Text, every language) outside `{{name}}`. Allowed: words starting with a letter (`C3`, `v2`, `sha256`) and, in `reply` labels only, an HTTP status 100-599 |
| `unknown number` | every `{{name}}` is in `numbers` |
| `issue has neither fixed_by nor open: true` | Q4: every issue says what fixes it, or that nothing does yet |
| `expect contradicts reducer` | `expect` and a declared `hazard` match the replay |
| `undeclared hazard` | the reducer produced a hazard the step does not declare |
| `reducer` | an action that cannot apply: pickup from an empty queue or into a full worker, free with nothing held, an unbound `$var`, mark-stale on an absent key |
| `needs a $variable` | `cache.set-if-fresh` was given a literal: it compares against the read a `$var` came from |
| `over budget` | the tier's limits below |

| budget | light | heavy |
|---|---|---|
| nodes | ≤ 8 | ≤ 12 |
| scenarios | ≤ 2 | ≤ 5 |
| steps per scenario, inherited included | ≤ 8 | ≤ 12 |

Exit 0 clean, 1 findings, 2 unreadable file, invalid JSON, `schema` ≠ 1, or evidence with no git
repo. Hazards and notes never change the exit code. `--json` prints
`{file, tier, findings: [{loc, message}], hazards: [str], notes: [str]}`.

## Build contract

`flow build <scenario.json> [--tier] --out <dir> [--assets <dir>]` refuses (exit 1) a file with
structural or reducer findings (run `check` for evidence first), and exits 2 when
`<assets>/shell.html`, `flow-player.js` or `flow-player.css` is missing (default assets:
`skills/explain/assets/`). It writes `<out>/index.html` and `<out>/explain.md`. The HTML is the shell with `{{flow_css}}`,
`{{flow_js}}`, `{{flow_data}}` (all three required) and `{{flow_tier}}`, `{{flow_title}}`
(optional) replaced in one pass. `flow_data` is `{"tier", "scenario"}` as JSON with every `<`
written `<`, for a `<script type="application/json">` block; `</script` in the JS and
`</style` in the CSS are escaped. The player runs its own reducer; `tests/flow/states.json` pins
it to this one. `tier` picks the renderer: `light` draws one static card per step (a small map of
the state after it), `heavy` the animated player. When the engine has rendered it sets
`data-flow-ok` and `data-flow-steps` (`<scenario>:<steps>,…`) on `<html>`, or `data-flow-error`.
`explain.md` is the PR-comment export: the map, a table per scenario (step, what happens, what
the step changed, evidence), the decision and the numbers, with `{{name}}` filled in.
