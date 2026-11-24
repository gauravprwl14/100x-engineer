[← INDEX](INDEX.md)

# The system map

**In short:** the first picture on every explain page. Groups, parts and labelled links that the
agent writes from what it researched, drawn as boxes inside boxes with a numbered journey on top.
The engine knows no subject: it lays out whatever tree it is given, so the same page type
explains a PR, a module, a concept or a business process. Shape: `schema.md` ("System map");
how it is proven better than the old role-column map: the last section here.

## Pick the picture

Intake picks what leads the page from what the reader asked. The step player (scenarios, issues,
fixes) is always there below; the map is what they read first.

| the reader asks | lead with | then |
|---|---|---|
| "how does X work", "what is X made of" (system, module, concept, process) | `system` with a journey; `scenario` for the happy path behind it | outline, one diagram |
| "what does this PR change" | `system` of the touched parts plus the ones around them (`kind: external` for what it does not touch) | context, the happy path, issues |
| "what can go wrong, what fixes it" | issue and fix scenarios; the `system` shows the risky link in style `risk` | before/after toggle, decision |
| "what does each method do" | the `reference` table (Python files) | `system` with the files as parts |
| a lifecycle, a data model, a concept's parts | a `state`, `er` or `mindmap` diagram | `system` only if parts talk to each other |

Not for one function with no shared state (see Trigger). A map with fewer than three parts is a
sentence: write it as one.

## Build it from what you researched

Every name comes from the subject, never from this skill. Work top-down:

| subject | groups are | parts are | links are | the journey is |
|---|---|---|---|---|
| code (PR, module) | the subject's own boundaries: a process, a package, an owner, "touched / around it" | things that exist: a route, a module, a store, a queue, a person | calls and reads you saw at a line (`ev`) | the main entry point, in order |
| concept | roles or phases the idea names | the actors and artefacts it names | who tells whom what | the idea's own sequence |
| business process | teams or departments | people, documents, systems | hand-offs | the steps of the process |
| plan or proposal | today / proposed, or the layers | what is added or changed, and what it touches | the new dependencies | the rollout order |

Then:

1. **Group first.** Draw the boundaries the subject already has; a group a reader would name
   unprompted ("the notes service", "finance") beats a tidy invented one. Nest at most three deep.
2. **Parts are nouns, links are verbs.** A part has a short `label` (28 characters) and, if it
   needs one, a `sub` that says what it is or how it is set up (60 characters, wraps to two lines).
   Fold detail into the `sub` rather than adding a box.
3. **A link per connection you can cite.** `label` is the thing passed or the verb ("read on a
   miss"). `style`: `call` (request), `data` (read or write), `async` (queued, later), `watch`
   (polls, observes), `risk` (the path an issue scenario is about). No `ev`: say `tag: inferred`;
   it is drawn faded and listed as inferred.
4. **Number the journey.** Five to nine steps, one plain sentence each; give every link on that
   step the same `n`. `scenario` on a step adds a "Watch it animated" button. Links with no `n`
   are context.
5. **Size it.** Light: 20 parts, 24 links, 8 journey steps. Heavy: 36, 48, 12. Over that, split
   into two pages (overview, then one page per group) as `research-recipe.md` §12 says.
6. **Set `cols` where the default is wrong.** Default is up to three columns per group. A group
   whose parts are a pipeline reads best as one column.

## Why it adapts to the subject

- Boxes are sized from their own text; a group is as wide as its children need.
- The gap between two groups grows to the widest label that has to cross it.
- A link takes the route that passes the fewest other boxes: straight, one bend, three
  segments, or out to the side and back past everything between.
- Labels are placed on the line where they touch nothing, else beside it. The full list of
  connections is also a table under the picture, and in `explain.md` as a mermaid flowchart.
- On a phone every group is one column.

## Proof that it is better, and the limits of that proof

```bash
node --test tests/flow/system.test.mjs          # 300 random subjects: no overlap, in-group, borders, determinism, escaping
node tests/flow/bench-picture.mjs --cases tests/flow/system/bench-cases.json --shots   # before/after table + PNGs
bash tests/test_flow.sh                          # includes the gate: after must beat before on every pair
```

The bench builds the same subject two ways (the old role-column map; the same page plus a
`system` block) and reads the page in headless Chrome: how far down the first picture is, how
many boxes carry a subtitle, how many links carry a label or a journey number, links passing
through boxes they do not connect, overlapping boxes, label clashes, and the smallest text. It
is offline and calls no model.

What it does **not** prove: that a person understands the system faster. These are measurable
proxies for "I can see the whole thing at once". Judge the real effect by opening the two pages
side by side (`--shots` writes both). The old map shows every link any step uses; the new one
shows the links you chose to cite, so a link you leave out is a link the picture hides. Cite
every connection the journey needs, and leave the rest to the step player.
