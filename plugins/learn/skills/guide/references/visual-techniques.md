# Visual learning techniques catalogue

Ready-to-copy markup and widget code for 29 of them: `assets/techniques/INDEX.md`, then one `assets/techniques/<id>.html`. (`assets/technique-gallery.html` shows them all live for a human in a browser; never read it whole.)

Pick techniques by the **shape of the knowledge**, not by what looks impressive. One strong visual per idea beats five weak ones. Every visual gets 2–4 "reading this" bullets underneath.

## Contents
0. Plain-English definitions
1. Selection guide (shape → technique)
2. Structure & navigation techniques
3. Relationship diagrams
4. Process & time diagrams
5. Comparison & decision techniques
6. Numbers & data techniques
7. Explanation techniques
8. Interactive techniques
9. Memory & self-test techniques
10. Implementation notes per format

---

## 0. Plain-English definitions (explain these to readers)

Use these when a guide contains a technique the reader may not know. Put the definition in the page's first reading note.

| Technique | What it is | How to read it | Build (HTML · Markdown) |
|---|---|---|---|
| In-10-seconds box | A highlighted box at the top of a page that states the whole point in one or two sentences. | Read it first. If it answers your question, you can skip the page. | A bordered block with a small label ('In 10 seconds') and 1–2 sentences. Markdown: a blockquote. |
| Concept map (metro style) | A map of the whole topic drawn like a subway map: each coloured line is a category, each station is a topic. | Pick a line (category), read its stations left to right. Stations further right build on earlier ones. | SVG built from a list of categories and topics; one horizontal line per category, a circle per topic. Markdown: Mermaid flowchart with subgraphs. |
| Mind map (radial) | One central idea with its sub-topics radiating outward like spokes. | Start at the centre; each spoke is one independent aspect. Colour groups related spokes. | SVG: centre ellipse, nodes placed around a circle. Markdown: Mermaid mindmap. |
| Tree / hierarchy | A top-down diagram where each item splits into its parts. | Read top to bottom: a box's children are the parts it is made of. Siblings on the same level are alternatives or parallel parts. | SVG boxes with connecting lines, max 3 levels. Markdown: nested bullet list or Mermaid flowchart TD. |
| Flow (boxes + arrows) | A row of boxes joined by arrows, where each box is one step and the arrow means 'then'. | Read left to right. Each box causes or enables the next one. | HTML flex row of step boxes with arrow characters between them. Markdown: Mermaid flowchart LR. |
| Sequence diagram (step-through) | A diagram with one vertical line per participant (person or system) and horizontal arrows for each message between them, in time order from top to bottom. | Column headers are the participants; the dashed lines under them are their 'lifelines'. Each arrow is one message; read them top to bottom. Press Next to highlight one step and read why it happens. | SVG generated from a list of [from, to, label, note] steps plus Back/Next state. Markdown: Mermaid sequenceDiagram (static). |
| Swimlane | A process diagram split into horizontal rows ('lanes'), one per role, team or system. Each step sits in the lane of whoever does it. | Each row is one actor; its name is on the left. Numbered cards show the order across all lanes. When consecutive cards jump lanes, work is handed off. | SVG: one coloured band per lane, step cards placed by lane (row) and order (column). Markdown: Mermaid flowchart with one subgraph per lane, or a table (step · lane). |
| State machine | A diagram of the states something can be in and the events that move it from one state to another. | Each rounded box is a state (a status the thing can have). Each arrow is a transition, labelled with the event that triggers it. No arrow between two states means that change is not allowed. | SVG boxes and labelled arrows. Markdown: Mermaid stateDiagram-v2. |
| Timeline | A vertical or horizontal line with events placed in time order. | Read top to bottom (earliest first). Red dots mark problems, green dots mark fixes. | HTML list with a left border and dots. Markdown: a table (time · event) or Mermaid timeline. |
| Comparison matrix | A table with the options as columns and the comparison criteria as rows. | Pick the criterion you care about most (a row) and read across. | A plain table. Keep to 2–5 options. |
| Pros / cons / use when / avoid when | Four small boxes that sum up one option: its advantages, its costs, when to pick it, and when not to. | Green = benefits, red = costs. 'Use when' and 'Avoid when' are the practical decision rules. | A 4-column grid. Markdown: a 4-column table. |
| 2×2 quadrant | A square split into four boxes by two axes, with options placed as dots according to how they score on each axis. | Find each dot: left–right is the first criterion, bottom–top the second. The quadrant labels tell you what that corner means. | SVG square with two dividing lines and labelled dots. Markdown: Mermaid quadrantChart. |
| Decision wizard / tree | A short series of yes/no questions that ends in a recommendation. | Answer each question honestly; the first matching rule gives the result. Start again to explore other answers. | HTML: questions in a list with yes/no targets and a results map. Markdown: Mermaid flowchart TD with diamond decision nodes. |
| Myth / reality | A two-column table pairing a common wrong belief with the correct version. | Left column: what people often think. Right column: what is actually true and why. | A plain 2-column table. |
| Before / after | Two panels side by side showing a situation before and after a change. | Compare the same line in both panels; the difference is the point. | Two boxes tagged red/green. Markdown: two short code blocks or a 3-column table (aspect · before · after). |
| Ladder table (+ slider) | A table where each row is one value of a setting and shows what that value causes; the slider lets readers try values in between. | Each row = one setting value → its consequence. Move the slider to recompute the result live. | A table plus a range input that recomputes the formula. Markdown: the table only. |
| Calculator (formula shown) | Input boxes with the key assumptions, plus a block that shows the formula and the result step by step. | Change an input; the formula block updates. Defaults are the numbers from the source. | Number inputs + a pre block rebuilt on input. Markdown: worked arithmetic in a code block. |
| KPI cards | A row of small cards, each with one big number and a short label. | Big number first, label underneath explains what it measures. | Grid of small boxes. Markdown: a 2-column table. |
| Bar comparison | Horizontal bars whose length shows the size of each value. | Longer bar = bigger value. Here the scale is logarithmic: each step is 10×, because the values differ hugely. | SVG rectangles sized by value (log scale when values span orders of magnitude). Markdown: a table. |
| Annotated code | A short code snippet with comments on the lines that matter. | Read the comments first, then the code they point at. 'Illustrative' means written for the guide, not taken from the source. | A pre block with comment spans. Markdown: a fenced code block. |
| Highlighted anatomy | One real artefact (a URL, prompt, config line) with each part coloured and a legend explaining the colours. | Match each coloured part to the legend above it. | Coloured spans with a legend. Markdown: bold/code for each part with a list explaining them. |
| Chat mock with toggle | A fake chat conversation showing how a bot or model answers, with a switch that changes one condition. | Read the conversation, then flip the toggle and compare the answer. | Chat bubbles + a checkbox that swaps the answer. Markdown: two short transcripts (before / after). |
| Analogy card | A comparison with something familiar from everyday life, plus where the comparison stops working. | Read the analogy, then the 'where it breaks' line — that is the part experts care about. | A box with the analogy in bold and 2–3 bullets. Markdown: the same as a quote plus bullets. |
| Fishbone / 5 whys | A root-cause diagram shaped like a fish skeleton: the problem is the head, and each bone is a category of possible causes. | The box on the right is the problem. Each bone is a cause category (e.g. cache, database); the small text is a specific cause. | SVG spine with angled bones. Markdown: a table (category · cause) or a 5-whys chain in Mermaid flowchart TD. |
| Layer pipeline | A stack of checks something must pass in order, where each layer shows whether it passed, stopped it, or was never reached. | Pick a scenario from the list. Green = passed, red = stopped here, faded = never reached. | HTML rows coloured by state per scenario. Markdown: a table (scenario × layer). |
| Flashcards | Cards with a term on the front and its meaning and example on the back. | Try to answer before flipping. Flip to check, then move to the next card. | A box that toggles front/back on click. Markdown: <details> blocks. |
| Quiz | Multiple-choice questions that show the right answer and a short explanation after you pick. | Pick an answer; green is correct, red is your wrong pick; read the explanation. | Buttons per option with the correct index stored. Markdown: options plus answer in <details>. |
| Glossary | A table of every technical term with a plain-English meaning and an example. | Find the term; read the meaning, then the example. | A 3-column table (term · meaning · example), searchable in HTML. |
| Cheat sheet | One screen of the most-needed facts in question → answer form. | Scan the left column for your question. | A compact table. Keep it to one screen. |

---

## 1. Selection guide

| If the content is… | Use first | Also good |
|---|---|---|
| A set of related concepts | Concept map / metro map | Mind map, glossary |
| One concept | Definition + example + analogy | Misconception table, before/after |
| Steps in order | Flow (boxes + arrows) | Step-through, numbered list, swimlane |
| Messages between parties | Sequence diagram (step-through) | Swimlane |
| A system with parts | Architecture diagram (clickable) | Layer/stack diagram, component table |
| States and transitions | State machine | Lifecycle flow |
| Options to choose between | Comparison matrix | Pros/cons grid, 2×2 quadrant |
| A decision to make | Decision tree / question wizard | Flowchart |
| A setting with a range | Ladder table (value → effect → example) | Slider simulator |
| Probabilities / randomness | Simulator (sample N times) | Bar chart |
| Numbers and formulas | Calculator with formula shown | Worked arithmetic, chart |
| Events over time | Timeline | Gantt, before/after |
| Claims and arguments | Claim / evidence / counter table | Argument map |
| Layers of defence or abstraction | Layer diagram | Pipeline with pass/block states |
| Causes of a problem | Fishbone / 5 whys | Tree |
| People and roles | Stakeholder map, RACI table | Org chart |
| Code or prompt | Annotated snippet, colour-highlighted anatomy | Diff (before/after) |
| Things to remember | Cheat sheet, flashcards | Quiz |

## 2. Structure & navigation

| Technique | When | How |
|---|---|---|
| Sidebar index grouped by category | Always (multi-page) | Coloured dot per category; current page highlighted |
| Search / filter | > 10 pages or long lists | Filter nav by title + page text; filter lists by category chips |
| Prev / next buttons | Always | Bottom of every page, with page titles |
| "In 10 seconds" box | Every page | 1–2 sentences, visually distinct |
| Category chip | Every page | Colour matches concept map line |
| Reading paths | Home page | "15 min / 1 hour / building this week" table |
| Progressive disclosure | Dense content | Expandable rows (`<details>`), tabs, "detail" command |
| Catalogue page | Many strategies/approaches | Filterable, expandable rows with pros/cons/use when/example |
| Consistent page template | Always | Same block order everywhere so readers know where to look |

## 3. Relationship diagrams

| Technique | When | Notes |
|---|---|---|
| Concept map (metro style) | Home page overview | Each category = coloured line, topics = stations, dashed links = "used by"; clickable stations |
| Mind map (radial) | One topic with many branches | Centre = goal; bubbles coloured by category; click → detail panel |
| Venn diagram | Overlapping sets | Max 3 circles |
| Hierarchy / tree | Taxonomies, org structures | Collapse deep levels |
| Layer / stack diagram | Abstractions, defence in depth | Top = user-facing, bottom = infra |
| Stakeholder map | Who cares about what | Influence × interest grid |

## 4. Process & time diagrams

| Technique | When | Notes |
|---|---|---|
| Flow (boxes + arrows) | 3–6 step processes | Horizontal on desktop, wraps on mobile |
| Step-through sequence diagram | Request/response between systems or actors | Next/back buttons; current arrow highlighted; explanation panel per step |
| Swimlane | Multi-actor processes | One lane per actor |
| State machine | Lifecycle (draft → frozen → deployed) | Label transitions with triggers |
| Timeline | History, incidents, roadmaps | Timestamps; mark decisions |
| Pipeline with states | Layers something passes through | Colour each layer pass / flag / block / not reached; selectable inputs |
| Loop diagram | Iterative algorithms (agent loop, sampling loop) | Show the back-edge clearly |

## 5. Comparison & decision

| Technique | When | Notes |
|---|---|---|
| Comparison matrix | 2–5 options × criteria | Options as columns, criteria as rows |
| Pros / cons / use when / avoid when grid | Every strategy | Four small boxes; the single most reused block |
| 2×2 quadrant | Two dimensions (impact × effort, cost × accuracy) | Place items; label quadrants in plain words |
| Decision tree | Rules-based choice | Yes/no branches ending in a recommendation |
| Question wizard | Same as tree, interactive | One question at a time → recommendation card |
| Trade-off statement | Cost vs benefit | "10× spend for +20% accuracy — yes or no?" |
| Before / after | Improvement, fix, refactor | Side by side, bad tagged red, good tagged green |
| Myth / reality table | Common misconceptions | Two columns |

## 6. Numbers & data

| Technique | When | Notes |
|---|---|---|
| Bar comparison | Results of experiments | Label exact values; mark source |
| Ladder table | A parameter's range | Value · behaviour · example output · best for |
| Calculator | Capacity, cost, sizing | Inputs → KPI cards → formula block showing the arithmetic |
| Worked arithmetic | Any derived number | Show each step; readers trust what they can re-compute |
| KPI cards | Headline numbers | Big number, small label |
| Chart | Trends, distributions | Only when a table would hide the shape |

## 7. Explanation techniques

| Technique | When | Notes |
|---|---|---|
| Concrete example | Every concept | Realistic, specific, labeled source/illustrative |
| Analogy | Abstract ideas | One analogy per concept; say where it breaks |
| Annotated code | Technical how-to | Short, runnable, comments on the lines that matter |
| Highlighted anatomy | Prompts, configs, sentences | Colour-code parts (task / constraint / output) with a legend |
| Chat transcript mock | Behaviour of a bot/model | User bubble / model bubble; show failure then fix |
| Worked case study | Capstone | Requirements → numbers → design → code → failures → extensions |
| "Where it's used" table | After each technique | Product · how the technique is used |
| Rule-of-thumb table | Practical advice | Rule · why · exact line/setting to use |
| Reading notes | Under every visual | What it shows, what to notice, what to try |

## 8. Interactive techniques

| Technique | When | Notes |
|---|---|---|
| Slider simulator | Parameter effects | Live-updating bars + example output for the current value |
| Sampler ("run N times") | Randomness, voting | Shows variation across runs |
| Toggle before/after | Effect of one change (e.g. add guard lines) | Checkbox flips the outcome and a tag |
| Selectable scenarios | Attacks, edge cases | Dropdown → pipeline states update |
| Step-through | Sequences, algorithms | Back / next / show all |
| Clickable diagram | Architecture, mind map | Click node → detail panel |
| Calculator | Numbers | Inputs with sensible defaults from the source |
| Quiz | Self-check | Click answer → right/wrong + why |

Interactive elements must also make sense without interaction (initial state is meaningful) and must be keyboard-usable.

## 9. Memory & self-test

| Technique | When | Notes |
|---|---|---|
| Glossary | Always | Term · plain meaning · example; searchable |
| Quiz | Always (detail mode) | 5–10 Qs from content only; explanation per answer |
| Flashcards | Exam/recall goal | Term front, meaning + example back |
| Cheat sheet | Reference goal | One screen: tables, commands, rules |
| Key takeaways | End of category | 3–5 bullets max |
| Spaced review list | Long courses | "Revisit these after 1 day / 1 week" |

## 10. Implementation notes per format

| Technique | HTML (single file) | React | Markdown / MDX |
|---|---|---|---|
| Concept / mind map | Inline SVG built from a data array; click handlers | Component over data | Mermaid `mindmap` or `flowchart` |
| Sequence diagram | SVG generated from `[from, to, label, note]` steps + stepper state | Same, with `useState` | Mermaid `sequenceDiagram` (static) |
| Architecture | Positioned SVG boxes + arrows; click → panel | Same | Mermaid `flowchart LR` |
| Flow | Flex row of step boxes with arrows | Same | Mermaid `flowchart LR` or numbered list |
| Timeline | CSS grid | Same | Mermaid `timeline` or table |
| State machine | SVG | Same | Mermaid `stateDiagram-v2` |
| 2×2 quadrant | SVG | Same | Mermaid `quadrantChart` |
| Charts | Inline SVG (no CDN by default: the guide must work offline) | Recharts/Chart.js | Table (+ Mermaid `xychart-beta` where supported) |
| Tabs / expanders | Buttons + panes; `<details>` | State | `<details>` blocks |
| Simulators, calculators, quizzes | Vanilla JS | Hooks | Not possible — replace with a ladder table / worked example / Q&A list |

When a technique can't be interactive in the chosen format, fall back to its static equivalent (ladder table, worked example, numbered steps) — never drop the content.
