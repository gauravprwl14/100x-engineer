# Page template, standard pages, summary mode, writing rules

Read at step 5 (writing pages). SKILL.md has the short form; this is the full version.

## Contents
1. Topic page template
2. Standard pages by content type
3. Summary mode
4. Writing rules

## 1. Topic page template

Skip a block when it doesn't apply to this page; never fill one with invented content.

| # | Block | Notes |
|---|---|---|
| 1 | Category chip + title | Plain words |
| 2 | "In 10 seconds" box | One or two sentences, the whole point |
| 3 | What it is | 1–3 plain-English bullets that define the concept *before* any table, code or diagram: what it is, what problem it solves, one everyday comparison if it helps |
| 4 | Core explanation | Bullets and tables, not paragraphs |
| 5 | Example | **When the source supports one**: worked numbers, a real input/output, a snippet, a scenario from the source. Otherwise an example written for the guide, labelled `Illustrative`, and only if it genuinely helps. Otherwise none, and the page says nothing about it. A table or diagram is not an example |
| 6 | Visual | The chosen diagram / widget / table, with one sentence saying what it shows. A table counts as the visual for comparison or reference content |
| 7 | "Reading this diagram" notes | 2–4 bullets under every diagram or widget (tables don't need them). If the diagram type may be unfamiliar (sequence, swimlane, state machine, quadrant, fishbone, metro map, mind map), the first bullet says what that type is — definitions in `visual-techniques.md` §0 |
| 8 | Pros / cons / use when / avoid when | For every strategy, approach or option the source presents as a choice |
| 9 | Code or template | Only for technical or procedural content: short, runnable, commented, or marked pseudocode |
| 10 | Where it's used | Real products, jobs or situations — from the source, or labelled `Added` |
| 11 | Prev / next navigation | |

Per-page tick list: In-10-seconds box · What it is · a visual (a table counts) · a 1–4 word map label · every key point on the page carries its `data-kp` / `<!-- kp: -->` tag.

## 2. Standard pages by content type

Home and topic pages are always produced in `detail`. The rest depend on the content type (see `content-types.md`); leave out any page the content can't fill.

| Page | Purpose | Include when |
|---|---|---|
| Home / overview | What this covers, who it's for, the one-line takeaway, **concept map** of all categories with clickable nodes, reading paths by time available | Always |
| Topic pages | One per topic (template above) | Always |
| At a glance / catalogue | Every approach, strategy or idea in one filterable list with pros, cons, use when, example | The source presents several approaches/options (lecture, tutorial, RFC alternatives) |
| Worked case / capstone | Its own pages for a full example | The source walks through one (system design, case study) |
| Applications | Concept → real products / situations | Learning content (lecture, course, paper); not for meetings, incidents, legal |
| Glossary | Plain-English term · meaning · example; searchable | The source uses ≥ 5 terms a newcomer wouldn't know |
| Self-check quiz | 5–10 questions with explanations, drawn only from the content | Study goals (lecture, course, training); never for meetings, retros, incidents, sales calls |
| Accuracy log | `accuracy-log.md` next to the guide (or a final page if only one file is possible) | Always |

## 3. Summary mode

One page (or one screen per category if the input is huge). Must:
- Keep every key point from the inventory — tag each one; `coverage_check.py` proves it.
- Use one line per point, grouped under category headings.
- Keep the single most useful table and the single most useful diagram (usually the concept map + the main comparison table).
- Concept-map nodes are 1–4 word topic names you write for the map — never truncated sentences.
- Keep key numbers. Keep an example only where the source gives one.
- End with "Say `detail <section>` to expand any part."
- Never introduce content that isn't in detail mode.

## 4. Writing rules

The reader is an experienced professional with little time.

- **Explain before you show.** Every concept, term, option and diagram type gets a plain-English "what it is" before it is compared, charted or coded. Test: could a smart reader who has never heard the term follow the page without searching?
- **Plain English.** Short words, short sentences. Define every term on first use, or link to the glossary.
- **Labels are not descriptions.** "Best for: work split across roles" says when, not what. Pair decision labels (best for, avoid when, pros, cons) with a definition.
- **Bullets and tables over paragraphs.** A paragraph longer than three lines is a bug.
- **Examples from the source first.** Numeric concepts get the source's worked numbers; settings get a ladder of values with the output at each when the source provides them. An example you write is labelled `Illustrative`.
- **Show, then tell.** Put the example or diagram next to the explanation, not three screens away.
- **Name trade-offs.** Anything presented as a choice gets pros, cons and "use when".
- **No hype, no filler.** No "in this section we will…", no closing summary of what was just shown.
- **Sentence case** headings. No emoji in content.
- **Consistent vocabulary.** Once you name something, keep the name across pages, diagrams and glossary.
- **Speaker-neutral.** Present ideas, not people: "The session recommends…", not "Rahul said…" (unless `keep-names`).
- **Use the source's key terms verbatim at least once.** Readers search for the words they heard.
- **Static first.** Any fact inside an interactive widget (step notes, tooltips, wizard results) also appears in the page's static text, so readers who print, search or don't click miss nothing.
