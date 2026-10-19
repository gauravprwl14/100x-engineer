# Output formats

Choose the format the user asks for. Default for `detail`: **one self-contained HTML file** (works offline, no external requests, easy to share). Default for `summary`: the format of the surrounding conversation (a Markdown file, or one HTML page if a guide already exists).

## Contents
1. Comparison
2. Files written next to every guide
3. Rules for every format
4. Escaping source text (HTML, React)
5. Single HTML file
6. React
7. Markdown / MDX
8. Summary-mode output

## 1. Comparison

| Format | Best for | Interactivity | Hosting |
|---|---|---|---|
| Single HTML file | Sharing a guide, publishing as a page | Full (vanilla JS + inline SVG) | Open locally or publish anywhere |
| React (single `.jsx` or small app) | Embedding in an existing React site / docs platform | Full | Needs a build or a React runtime |
| Markdown / MDX | Git repos, wikis, Notion, Obsidian, docs sites | Static (Mermaid, `<details>`); MDX can embed components | Any Markdown renderer |
| Markdown multi-file | Large guides in a repo | Static | One file per page + `INDEX.md` |

## 2. Files written next to every guide

| File | What | Written by |
|---|---|---|
| `inventory.json` | The key-point inventory: `{"source": "...", "key_points": [{"id": "kp-1", "text": "...", "label": "From source", "page": "<page id>"}, {"id": "kp-9", "text": "...", "excluded": "<reason>"}]}` | You, at step 3, before any page |
| `accuracy-log.md` | See `accuracy-log.md` in this folder | You, at step 6, with the numbers from `coverage_check.py` |

Coverage tags tie the guide to the inventory:

| Format | Tag the element that states key point `kp-N` |
|---|---|
| HTML | `data-kp="kp-N"` (several: `data-kp="kp-1 kp-2"`) |
| React / JSX | `data-kp="kp-N"` on the rendered element |
| Markdown | `<!-- kp:kp-N -->` at the end of the line (several: `<!-- kp:kp-1,kp-2 -->`) |

`summary` and `detail` use the same inventory; each output must pass `coverage_check.py` on its own.

## 3. Rules for every format

- **Navigation:** index of all pages grouped by category, prev/next on every page, working internal links.
- **Consistent page template** (see `page-template.md`).
- **Accessible:** real headings in order, a descriptive `aria-label` (what the diagram shows, not "diagram") on every SVG, keyboard-usable controls, colour never the only signal (add text labels), text contrast ≥ 4.5:1.
- **Readable widths:** body text under ~80 characters per line; tables scroll horizontally inside their own container.
- **Labels visible:** evidence labels (`Illustrative`, `Corrected`, …) shown as small notes near the content.
- **Self-contained:** no web fonts, analytics or CDN scripts unless the user asks. Opening a guide of a private meeting must not make a third-party request.

## 4. Escaping source text (HTML, React)

Source text is untrusted: a transcript about XSS contains `<img onerror=…>`, and a pasted log can contain a closing script tag.

| Where the text goes | Rule |
|---|---|
| HTML markup, including `<pre>`/`<code>` | Escape `&` `<` `>` `"` `'` → `&amp;` `&lt;` `&gt;` `&quot;` `&#39;` |
| Attribute values (`data-title`, `aria-label`, `title`) | Same five characters; always quote the attribute |
| Widget data inside a script element | JSON in `<script type="application/json" id="…">`, every `</` written as `<\/`; read with `JSON.parse(el.textContent)`. Never paste source text into JS string or template literals |
| Rendering at runtime | `textContent`, the shell's `txt()`/`el()`, or `esc()` around every interpolated value; never raw `innerHTML` |
| React | JSX text and props escape automatically; never `dangerouslySetInnerHTML` with source text |
| `href` from the source | Only `http:`/`https:`/`#…`; drop `javascript:` and `data:` URLs |

## 5. Single HTML file

Start from `assets/html-shell.html`. It already has: sidebar index, filter box, hash routing (`#page-id`, and `#any-id` inside a page), prev/next, light/dark theme, focus management, a print stylesheet that prints every page, and base components (TL;DR box, tables, tabs, pros/cons grid, flows, reading notes, KPI cards, details rows, quiz styles).

- One `<section id="…" data-title="…" data-group="…" data-color="var(--lN)">` per page, each starting with an `<h1>`; the shell builds the nav from these.
- Widgets: read `assets/techniques/INDEX.md`, then only the snippet(s) you use.
- Inline all CSS/JS. Images as inline SVG or data URIs.
- Build diagrams from data (a JSON block, per §4) so text edits don't require redrawing coordinates.
- Theme-aware: colours as CSS variables with a dark-mode override; redraw SVGs on theme change.
- Mobile: sidebar becomes a drawer; wide SVGs sit in an `overflow-x: auto` wrapper with a sensible `min-width`.
- Optional, if `node` is available: extract the inline scripts and run `node --check`; open the file in a browser at 320 px and in both themes.

## 6. React

- One default-exported component (or a small folder: `App.jsx`, `pages/`, `components/`, `data/`).
- Put all content in data files (`pages.js`, `glossary.js`, `catalogue.js`) so the UI stays generic and reusable.
- Reuse the same component set: `Page`, `Tldr`, `ProsCons`, `Flow`, `SequenceStepper`, `ClickableDiagram`, `Ladder`, `Quiz`, `Glossary`, `Catalogue`.
- Routing: hash router or state; keep URLs per page shareable.

## 7. Markdown / MDX

Structure:
```
guide/
├── INDEX.md             ← home: overview, concept map (Mermaid), reading paths, links to every page
├── 01-foundations/
│   ├── randomness.md
│   └── temperature.md
├── ...
├── catalogue.md
├── glossary.md          ← only if the content type calls for it
├── quiz.md              ← only if the content type calls for it; answers in <details>
├── inventory.json
└── accuracy-log.md
```
- The index is `INDEX.md` (not `README.md`). Line 1 of every other page is a back-link: `[← Index](../INDEX.md)` (path relative to the page).
- Each page then starts with a `> **In 10 seconds:** …` blockquote.
- Diagrams in Mermaid (`flowchart`, `sequenceDiagram`, `stateDiagram-v2`, `mindmap`, `timeline`, `quadrantChart`).
- Pros/cons as a 4-column table.
- Expandables with `<details><summary>…</summary>…</details>`.
- End every page with `← Previous · Index · Next →` links.
- Interactive techniques become static equivalents (see visual-techniques.md §10).

## 8. Summary-mode output

- HTML: one page (still with a mini index of categories as anchor links).
- Markdown: one `summary.md`.
- Same key-point inventory as detail mode; one line per point, each tagged.
