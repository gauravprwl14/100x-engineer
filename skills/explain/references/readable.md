[← INDEX](INDEX.md)

# The readable layout

**In short:** set `"layout": "readable"` and the page explains itself in sentences first: a journey
whose every step says what happens and why, an outline in plain words with the code one click away,
the walkthrough as an article before it is an animation, and one map with one vocabulary. A page
with no `layout` key builds exactly as it always did, so the layout is put back by deleting one line.

## What changes

| | classic (no `layout`) | `"layout": "readable"` |
|---|---|---|
| journey | a title per step | the title, then `why`: what happens and why it matters, in plain words |
| outline | pseudocode with `# step 2, 3, 4` | one sentence per line (`says`), the code behind **Show the code**, a link named by the step's title |
| walkthrough | the animation, one step at a time, playing on load | **Read it** (every step as an article, evidence and code included) or **Watch it animate**; opens on Read, never autoplays |
| terms | a chip list; meanings after a click | the meanings open, under the map |
| map | as wide as its columns; may scroll sideways | redrawn with fewer columns until its text stays at least 9px at the page's width |
| sections | the same set for every subject | for a concept or plan, **Decision**, **Numbers** and **Reference** start closed |
| names | scenario nodes and the map may name one thing two ways | `flow check` rejects a node the map does not name the same way |

## Write it

1. **`why` on every journey step** (≤ 200 characters): what happens, then why a newcomer cares. Say
   it as you would to a colleague: "The service looks in the cache first: a fast store of copies, so
   most reads cost almost nothing." An analogy is welcome; an identifier is not (`getNote`, `a.b`).
2. **`says` on every outline line** (≤ 140 characters): the line as a sentence, not a restatement
   of the code ("Keep that copy in the cache for a while, so the next reader is quick").
3. **Name things once.** A scenario node's `label` is the map's name for it. Put the longer
   explanation in the part's `sub`, not in a second name.
4. **Numbers go through `{{name}}`** here as everywhere; `flow check` rejects a bare digit in
   `says` and `why`, and an identifier that is not a defined term.
5. Keep what already worked: evidence on every claim (it sits behind the chips and **Show the
   code**), the terms table, the tier budgets.

## Put it back

| if | do |
|---|---|
| one page reads worse | delete its `"layout"` line, rebuild: the classic page returns, byte for byte |
| the whole layout reads worse | `git revert -m 1 <merge commit>` of the PR that added it; commit `d2962a3` is the last build before it (tagged `explain-before-readable` on the machine that made it) |
| unsure which is better | build both and compare: `node tests/flow/bench-picture.mjs --cases tests/flow/system/bench-cases.json` |

## Proof, and what it does not prove

`bash tests/test_flow.sh` builds the same subject classic and readable and reads both in headless
Chrome: words of explanation readable with no click, words of code showing, bare step numbers,
whether the map scrolls sideways, the smallest text, and one sentence per journey step. A readable
page must explain at least twice as much without a click and must not scroll its map. A second
check builds every page already on a machine with the old and the new engine and compares
`explain.md` bytes and the rendered page; a page without `layout` must not differ.

It does **not** prove that a person understands faster. Those are measurable proxies. Give the
readable and classic pages to someone who has not seen the subject and ask three questions about
how it works; the page they answer faster and better is the better page.
