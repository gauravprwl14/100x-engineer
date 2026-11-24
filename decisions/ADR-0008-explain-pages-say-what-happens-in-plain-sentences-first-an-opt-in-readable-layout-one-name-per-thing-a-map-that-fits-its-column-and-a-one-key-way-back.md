# ADR-0008: Explain pages say what happens in plain sentences first: an opt-in readable layout, one name per thing, a map that fits its column, and a one-key way back

```json meta
{
  "id": "ADR-0008",
  "title": "Explain pages say what happens in plain sentences first: an opt-in readable layout, one name per thing, a map that fits its column, and a one-key way back",
  "status": "proposed",
  "date": "2026-11-24",
  "decided_by": "gaurav",
  "tags": [
    "explain",
    "readability"
  ],
  "affects": [
    "skills/explain/**",
    "scripts/flow.py",
    "tests/flow/**"
  ],
  "commit": "d2962a3",
  "assumptions": [
    {
      "id": "A1",
      "claim": "A page with no `layout` key builds exactly as it did before this change: same explain.md bytes and same rendered page",
      "verify": "python3 scripts/flow.py build skills/explain/assets/examples/stale-writeback.json --tier heavy --out \"${TMPDIR:-/tmp}/adr8-classic\" >/dev/null 2>&1 && ! grep -q 'in plain words' \"${TMPDIR:-/tmp}/adr8-classic/explain.md\" && grep -q '# step 1' \"${TMPDIR:-/tmp}/adr8-classic/explain.md\"",
      "revisit_when": "the classic outline or journey markdown is changed on purpose",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "A readable page is rejected by `flow check` when an outline line has no `says`, a journey step has no `why`, a sentence holds an undefined identifier or a bare number, or a scenario node is not named as the map names it",
      "verify": "bash tests/test_flow.sh 2>&1 | grep -q 'readable/node-not-on-map' && bash tests/test_flow.sh 2>&1 | grep -q 'readable/no-says'",
      "revisit_when": "a new readable field is added without a seeded defect case",
      "confidence": "high"
    },
    {
      "id": "A3",
      "claim": "On every committed classic/readable pair the readable page shows no less explanation and no more code without a click, has no more bare step numbers, does not scroll its map and keeps its text at 9px or more; with a journey it explains at least twice as much",
      "verify": "bash tests/test_flow.sh 2>&1 | grep -q 'bench: after is better than before on every pair'",
      "revisit_when": "a new subject kind is added to bench-cases.json and the gate fails, or the layout is changed",
      "confidence": "medium"
    },
    {
      "id": "A4",
      "claim": "No label or route is clipped by the picture: every tag and every route point lies inside the svg's viewBox, wide and narrow, on 300 random subjects",
      "verify": "node --test tests/flow/system.test.mjs 2>&1 | grep -q 'every label and every route point is inside the picture'",
      "revisit_when": "the label placement or the routing changes",
      "confidence": "high"
    },
    {
      "id": "A5",
      "claim": "A reader understands a system faster from a readable page than from a classic one. The bench measures proxies (words of explanation visible, code and step numbers hidden, a map that fits), not comprehension",
      "verify": "",
      "revisit_when": "two readers who have not seen the subject answer three questions about how it works from each page; compare time and correctness",
      "confidence": "low"
    }
  ],
  "options": [
    {
      "name": "change the classic page for everyone: replace the outline with sentences, make the player article-first",
      "fit": "pass",
      "chosen": false,
      "why_not": "changes 128 pages already on one machine without being asked, and a layout that reads worse cannot be put back page by page; the old pages are a fixed point worth keeping"
    },
    {
      "name": "leave the classic page and add a better `tldr` and longer step text",
      "fit": "fail",
      "chosen": false,
      "why_not": "the real page already had good step prose (15 to 67 words each) that sat behind a one-step-at-a-time player; the failure was where it was shown and how it was numbered, not how much was written"
    },
    {
      "name": "a second output file (a reading page) beside the animated page",
      "fit": "pass",
      "chosen": false,
      "why_not": "two files to keep in step, and the reader who opens the animated one still meets the problem; the readable layout keeps both views in one page and one scenario.json"
    },
    {
      "name": "an opt-in `layout: readable` key per page, with the old behaviour as the default",
      "fit": "pass",
      "chosen": true,
      "why": "zero change to existing pages (verified on 128), one line to put a page back, `git revert -m 1` to put the whole layout back, and the new pages are the ones the updated skill writes with the key set"
    }
  ],
  "supersedes": null,
  "revisit_by": null
}
```

## Context

A user shared a real explain page (how a video-downloader site works) and said nobody could learn
from it: the workflow outline was pseudocode with `# step 2, 3, 4` tags, there was no sentence
saying what a part does, and the evidence, numbers and decision sections drowned the story. Reading
the page and the user's past sessions showed three causes. The step numbers meant three different
things on one page (the journey, each scenario and the outline all numbered from 1). The step prose
was good but was only shown one step at a time inside an animation that played on load, below four
screens of structure. And the page drew two maps with two vocabularies for the same parts. The
system map shipped a day earlier made one more thing worse: on a 1280px window the map scrolled
sideways with 7px text, and on a phone 12 of 17 labels fell outside the picture and were clipped.

## Options considered

### Option A: change the classic page for everyone
Rejected: 128 existing pages on one machine would change unasked, and nothing could put a page back.

### Option B: a better `tldr` and longer step text
Rejected: the prose existed; where it was shown was the problem.

### Option C: a separate reading file
Rejected: two files to keep in step; the reader who opens the animated one still meets the problem.

### Option D: an opt-in `layout: readable` key
Chosen. Pages without the key build as before; a page with it asks for `says` on outline lines and
`why` on journey steps, shows the walkthrough as an article with the animation one switch away,
opens the term meanings, and refuses a scenario node the map does not name the same way.

## Decision

Option D. In the engine: `layout` (`classic` default, `readable`), `outline[].lines[].says`,
`system.journey[].why`, the vocabulary check, plain-words tables in `explain.md`, a Read / Watch
switch, a map that is redrawn with fewer columns until its text stays at 85% of its size or more,
and a viewBox that always holds every label and route. Safety: the old behaviour is the default and
is compared byte for byte (`explain.md`) and by rendered page against the pre-change engine on every
page found on the machine (128 pages: 127 identical, 1 refused by both, 0 different); the commit
before this change is `d2962a3` (tag `explain-before-readable` on the machine that made it).

## Consequences

Easy: a new page explains itself in sentences first; a reader can see all steps without a click;
code and animation are still there; one page goes back by deleting one line, the whole layout by
reverting one merge. Measured on the real page that prompted this (headless Chrome, 1280px): words
of explanation readable with no click 134 to 1711, words of code showing 151 to 0, bare step numbers
17 to 0, map scrolls sideways yes to no, smallest text 7px to 10px. The count rises mostly because
prose that already existed is no longer hidden. Hard: the author writes two more fields per page
(`says`, `why`), and a map whose natural width does not fit is drawn taller.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| comprehension is not measured, only proxies for it | a page could show more words and teach no faster | accepted: A5 says to ask two cold readers | do it on the next real page |
| the readable layout is opt-in, so an old page stays classic until its key is added | the user's earlier pages keep the old problem | accepted: the alternative changes pages unasked | add the key and the two fields page by page |
| the pre-change tag exists only on the machine that made it | nobody else can check out the tag | accepted: the commit `d2962a3` is in main's history | none |
| `says` and `why` are checked for length, jargon and numbers, not for being plain or true | a sentence can pass and still be vague | accepted: review (SKILL.md rule 22) | none planned |
| part cards and per-part deeper pages are not in this change | a reader still cannot open "the extractor" into its own page | accepted: next change, same flag | PR B |
| the real page's mermaid diagrams were measured offline (source shown) | the offline screenshot is not what a connected reader sees | accepted | open the page online once |
