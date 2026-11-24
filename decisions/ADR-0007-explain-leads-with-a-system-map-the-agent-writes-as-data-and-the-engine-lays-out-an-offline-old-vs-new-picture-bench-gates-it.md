# ADR-0007: Explain leads with a system map the agent writes as data and the engine lays out; an offline old-vs-new picture bench gates it

```json meta
{
  "id": "ADR-0007",
  "title": "Explain leads with a system map the agent writes as data and the engine lays out; an offline old-vs-new picture bench gates it",
  "status": "proposed",
  "date": "2026-11-24",
  "decided_by": "gaurav",
  "tags": [
    "explain",
    "visualization"
  ],
  "affects": [
    "skills/explain/**",
    "scripts/flow.py",
    "tests/flow/**"
  ],
  "commit": "d4d5053",
  "assumptions": [
    {
      "id": "A1",
      "claim": "The layout engine knows no subject: no product, team or project name is written into system-map.js, so the same code draws a PR, a module, a concept and a process",
      "verify": "! grep -iE '100x|tunag|stmn|grok|codex|gemini|opus' skills/explain/assets/system-map.js",
      "revisit_when": "a layout rule is added that is only right for one kind of subject",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "A page with no `system` does not carry the layout code, so existing pages only grow by the player's panel code and CSS",
      "verify": "python3 scripts/flow.py build skills/explain/assets/examples/stale-writeback.json --tier heavy --out \"${TMPDIR:-/tmp}/adr7-nosystem\" >/dev/null 2>&1 && ! grep -q 'const SystemMap' \"${TMPDIR:-/tmp}/adr7-nosystem/index.html\"",
      "revisit_when": "the player's inlined size matters (offline pages near a size limit)",
      "confidence": "high"
    },
    {
      "id": "A3",
      "claim": "On every committed before/after pair the new picture sits higher, labels more links, ties links to the journey, is no smaller and sends no link through a box (headless Chrome)",
      "verify": "bash tests/test_flow.sh 2>&1 | grep -q 'bench: after is better than before on every pair'",
      "revisit_when": "a new subject kind is added to bench-cases.json and the gate fails, or the layout is changed",
      "confidence": "medium"
    },
    {
      "id": "A4",
      "claim": "Headless Chrome is installed where the gate must run; without it the gate is skipped, not passed",
      "verify": "test -x \"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome\"",
      "revisit_when": "CI runs on a machine without Chrome, so the gate never runs there",
      "confidence": "medium"
    },
    {
      "id": "A5",
      "claim": "A reader understands a system faster with the map than with the role map. The bench measures proxies for it (position, labels, journey, legibility), not comprehension",
      "verify": "",
      "revisit_when": "the first real PR or module explained with it: ask the reader and compare against the old page",
      "confidence": "low"
    }
  ],
  "options": [
    {
      "name": "the agent places every box (x, y) in the scenario",
      "fit": "pass",
      "chosen": false,
      "why_not": "puts layout work on the agent per subject, drifts when a label changes, and a page that was right stops being right; nothing checks overlap"
    },
    {
      "name": "a third-party layout library (an ELK-style engine)",
      "fit": "pass",
      "chosen": false,
      "why_not": "a new dependency inlined into every offline page (size, licence not checked here) for a result the tree-plus-grid layout already meets on the benchmark; revisit if subjects outgrow it"
    },
    {
      "name": "mermaid flowchart with subgraphs as the picture",
      "fit": "fail",
      "chosen": false,
      "why_not": "no control over placement, labels or the numbered journey; the page already loads mermaid from a CDN and falls back to source offline, so the main picture would be missing offline. Kept as the markdown export"
    },
    {
      "name": "a tree of groups and parts plus labelled links; the engine lays it out and routes the links",
      "fit": "pass",
      "chosen": true,
      "why": "the agent writes only what it knows (what is inside what, what talks to what); sizes, gaps, routes and label spots are computed from the text, so one engine fits any subject and a property test can prove it"
    }
  ],
  "supersedes": null,
  "revisit_by": null
}
```

## Context

The explain page's first picture was a map of boxes in eight fixed columns by role (client, edge,
service, queue, worker, cache, store, external) that only shows links some step uses, unlabelled,
about 3,500 to 4,000 px down a heavy page, with text rendered at 4.9 to 6.9 px. A reader could not
see what holds what or how the parts connect, and real subjects (a plugin, an orchestration, a
gate) had to call a receipt a "cache" and a plan a "store" to fit. The user wants one overview
that works for anything they explain (a PR, a module, a new concept) and wants proof it is
better, not a feeling.

## Options considered

### Option A: the agent places every box
Rejected: layout work per subject that nothing checks and that rots when a label changes.

### Option B: a layout library
Rejected for now: a dependency in every offline page for a gain the benchmark does not show a
need for. Licence not checked.

### Option C: mermaid subgraphs as the picture
Rejected as the picture (no placement control, missing offline); kept as the `explain.md` export.

### Option D: a tree plus labelled links, laid out and routed by the engine
Chosen. Group sizes come from their children, the gap between groups from the widest label that
crosses it, each link takes the route that passes the fewest other boxes, each label goes where it
touches nothing. `flow check` refuses what cannot be drawn (a label that does not fit, a link to
nothing, a journey step no link carries).

## Decision

Option D, in `skills/explain/assets/system-map.js` with the `system` block in `scenario.json`.
Deciding factor: the engine holds no subject, so it is tested on 300 random subjects as well as
real ones. It is gated by an offline benchmark (`tests/flow/bench-picture.mjs`): the same subject
drawn the old way and with a map, read in headless Chrome. No model is called.

## Consequences

Easy: one overview for any subject; the markdown export carries it too; a change to the layout
cannot make the picture worse without `tests/test_flow.sh` failing, and two deliberate breakages
were confirmed to be caught. Hard: the map shows only the links the agent cites, so a link left
out is hidden (the step player still shows every link a step uses); the player and CSS grew every
page by about 10 KB (4.5%); the layout is another file to keep in step with the CSS.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| comprehension is not measured, only proxies for it | the map could look better and teach no faster | accepted: A5 says to ask a reader on first real use | none planned |
| no code map (who calls whom across files, any language) | "what does each method do" still leans on the Python-only reference table | accepted, not planned in this change | next step if the map proves out |
| a very wide map shrinks to 70% then scrolls sideways | a 27-part map is readable but not in one glance | accepted: the budgets (20 parts light, 36 heavy) push the agent to split | split-by-group pages (recipe section 12) |
| 3 of 25 links in the 27-part stress map still pass through a box | a reader may misread which boxes a link joins | accepted; the gate allows 15% | smarter routing if a real page hits it |
| text width is estimated (about 0.58 em per Latin character, 1 em per CJK) | a font that is wider than the estimate clips a label | accepted: labels are limited to 28 characters with slack in the box | measure in the page if it bites |
| no hover or focus highlight of a part's links | in a dense map the eye must follow a line | accepted, not planned | cheap to add later |
