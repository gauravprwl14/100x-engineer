# ADR-0009: Explain part cards and pages behind them: an about card per map part, a page per part a reader asks about, and a checked way back

```json meta
{
  "id": "ADR-0009",
  "title": "Explain part cards and pages behind them: an about card per map part, a page per part a reader asks about, and a checked way back",
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
  "commit": "5133da0",
  "assumptions": [
    {
      "id": "A1",
      "claim": "A card is rejected unless the page is readable, it has `does`, it cites `ev` or is tagged inferred, and its sentences hold no undefined identifier or bare number",
      "verify": "bash tests/test_flow.sh 2>&1 | grep -q 'readable/about-no-evidence' && bash tests/test_flow.sh 2>&1 | grep -q 'readable/about-jargon'",
      "revisit_when": "a card field is added without a seeded defect case",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "`flow links` finds a card that opens a missing page and a deeper page that does not point back",
      "verify": "bash tests/test_flow.sh 2>&1 | grep -q 'flow links: a page that does not point back is found'",
      "revisit_when": "pages stop being sibling folders (a different layout of the output root)",
      "confidence": "high"
    },
    {
      "id": "A3",
      "claim": "Clicking a mapped part opens its card, a card links to its page, a deeper page links back to the card, and a link to #card-<part> opens that card, in headless Chrome",
      "verify": "bash tests/test_flow.sh 2>&1 | grep -q 'a link to #card-<part> opens that card'",
      "revisit_when": "the player's hash handling changes",
      "confidence": "medium"
    },
    {
      "id": "A4",
      "claim": "A page with no `about` or `parent` builds as before: explain.md bytes and rendered page match the pre-change engine on every page on the machine",
      "verify": "python3 scripts/flow.py build skills/explain/assets/examples/stale-writeback.json --tier heavy --out \"${TMPDIR:-/tmp}/adr9-classic\" >/dev/null 2>&1 && ! grep -q 'The parts' \"${TMPDIR:-/tmp}/adr9-classic/explain.md\"",
      "revisit_when": "the classic markdown is changed on purpose",
      "confidence": "high"
    },
    {
      "id": "A5",
      "claim": "A reader who wants to know how one part works finds it faster with a card and a page than by scrolling one long page. Not measured",
      "verify": "",
      "revisit_when": "the first real set of pages (an overview and one deeper page) is read by someone new to the subject",
      "confidence": "low"
    }
  ],
  "options": [
    {
      "name": "grow one page: more scenarios for each part",
      "fit": "fail",
      "chosen": false,
      "why_not": "this is how the video-downloader page got its second scenario; it made one page long and still gave a reader no way to open a single part"
    },
    {
      "name": "a modal or drawer inside the page, with the part's story as more `about` text",
      "fit": "pass",
      "chosen": false,
      "why_not": "a part with its own flow needs its own map, journey and evidence; stuffing that into a card makes the card a second page without page tools (check, links, export)"
    },
    {
      "name": "cards on the overview, and a full page per part that is linked both ways and checked",
      "fit": "pass",
      "chosen": true,
      "why": "the overview stays short, a deeper page is a normal checked page (its own evidence, journey and markdown), and `flow links` stops a card from opening nothing"
    }
  ],
  "supersedes": null,
  "revisit_by": null
}
```

## Context

After the readable layout (ADR-0008) a reader can follow one page, but still cannot ask "how does the
extractor work" and be taken somewhere. The user said so directly: they wanted to give a reader the
extractor and let them go deeper, with pages that connect to each other. A past session shows the
same need: a follow-up asking how the extractor fetches several videos, what chunks it calls and how
it merges them was answered by adding another scenario to the same page.

## Options considered

### Option A: grow one page
Rejected: the page gets long and no part can be opened alone.

### Option B: a drawer inside the page
Rejected: a part with its own flow needs its own map, journey and evidence; a drawer lacks them.

### Option C: cards plus linked pages
Chosen. `about` on a group or part (what it does, what goes in and out, why, evidence); `about.open`
names a sibling page; that page's `parent` names the card; `flow links` checks both ends.

## Decision

Option C, only on pages that set `"layout": "readable"`. Clicking a mapped box opens its card; the
list under the journey has every card; a deeper page shows a way back that opens the card.

## Consequences

Easy: an overview can stay short and still answer "how does that part work"; each deeper page is
checked and exported like any other. Hard: the author writes a card per part worth opening and keeps
a set of pages in step; `flow links` only checks pages that sit side by side in one folder. Nothing
changes for a page without `about` or `parent`.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| no keyboard focus on map boxes | a keyboard user opens cards from the list under the journey, not the map | accepted: the list is the accessible path | add focus handling if asked |
| `flow links` does not check that a deeper page is about the part its card describes | a card can open an unrelated page that points back | accepted: review | none planned |
| a deeper page is written by hand | more authoring for a big subject | accepted | a helper that splits a scenario into a page |
| no automatic index page for a set of pages | the reader finds the set only through the overview | accepted: `explain/INDEX.md` convention remains | none |
| comprehension is not measured | cards could be skipped | accepted: A5 | ask a cold reader |
