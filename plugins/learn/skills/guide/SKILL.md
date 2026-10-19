---
name: guide
description: "Visual learning guide, walkthrough or cheat sheet from an RFC, design doc, postmortem, architecture note or talk transcript: scannable HTML/Markdown pages, glossary, quiz, accuracy log. Not for one diagram (→ diagramming)."
---

# Visual learning guide

Turn a long source into pages a busy reader can scan in 10 seconds, understand in 10 minutes and apply the same day — with every key point provably covered and every non-source claim labelled.

## Trigger

**Fire when:** the user wants a built learning artifact (visual guide, study guide, onboarding walkthrough, cheat sheet, course notes) from a long source: an RFC, design doc, finished postmortem, architecture note, lecture, talk or podcast transcript, paper or book chapter.

**Not for:** a chat summary ("summarize this", "tl;dr") → answer in chat, no skill · a PR → `100x:pr-review` (your own diff → `100x:diff-review`) · explaining code → `100x:codebase-comprehension` · meeting notes or action items → not this skill; answer in chat with a decision/action table · one diagram → `100x:diagramming` · writing the postmortem itself → `100x:root-cause-analysis`.

## Commands

The first word after `/learn:guide` may be a command. **No command:** `summary` when the ask is short or says summarize/notes/recap; `outline` (then `detail` after approval) only when the user asks for a full guide, site or walkthrough.

| Command | Output |
|---|---|
| `summary` | One page; every key point, one line each. |
| `outline` | Classification + proposed pages + chosen techniques. No build; wait for approval. |
| `detail` / `detail <section>` | Full multi-page guide / expand one section. |
| `summary <section>` | Compress one section to its scan layer. |
| `visual <concept>` | One diagram or widget for a single concept. |
| `quiz` · `flashcards` · `cheatsheet` | Self-test or one-screen reference, from the content only. |
| `log` | Show the accuracy log. |
| `format <html\|react\|md>` | Re-emit in another format. |

Flags: `keep-names` (keep participant names; default is roles), `md` / `html` / `react`.

## Workflow

Steps 1–4 are thinking; do them before writing any page.

1. **Read everything** before deciding. Separate main content · Q&A · tangents · logistics · anecdotes. Fix transcription errors from context and note each non-obvious fix for the log. Mine the Q&A: it holds the gotchas.
2. **Classify** content type, knowledge shape, audience, reader goal, density → `references/content-types.md`.
3. **Write `inventory.json`** next to the output: every distinct idea, claim, number, example, option, warning, question and answer, each with an id (`kp-1`…), one line, an evidence label and a target page. Excluded items stay in the file with an `"excluded": "<reason>"`. Schema: `references/output-formats.md` §2. `summary` and `detail` share it.
4. **Design the structure**: 4–9 categories named by what the reader learns, each building on the last; one page per topic. Pick visuals by knowledge shape (`references/visual-techniques.md` §1). For widget code read `assets/techniques/INDEX.md`, then only the `assets/techniques/<id>.html` you use. Never read `assets/technique-gallery.html` (88 KB, for humans in a browser).
5. **Write pages** with the template in `references/page-template.md` (standard pages depend on the content type there). Tag each element that states a key point: `data-kp="kp-N"` in HTML/JSX, `<!-- kp:kp-N -->` in Markdown.
6. **Build, check, log**: format rules and escaping in `references/output-formats.md` (HTML starts from `assets/html-shell.html`; multi-file Markdown uses `INDEX.md`). Run `coverage_check.py` (Verify), then write `accuracy-log.md` from `references/accuracy-log.md`.

## Evidence labels

Show these visibly (a small badge, `.lbl-src` in the shell) on anything that isn't a plain restatement of the source:

| Label | Meaning |
|---|---|
| (none) | Faithful restatement of the source |
| `From source` / `Live demo` | Exact numbers, results or quotes from the input |
| `Illustrative` | Written for the guide to explain a point; not from the source |
| `Added` | Standard, verifiable fact not in the source |
| `Corrected` | Source was wrong or garbled; guide shows the correct version |
| `Speaker's view` | Opinion, anecdote or unverified claim from the source |
| `Uncertain` | Unclear or unverifiable; say what the doubt is |

## Rules

1. Every inventory item is tagged in each output, or marked `excluded` with a reason; nothing is silently dropped.
   *Enforced by:* `coverage_check.py inventory.json <guide>` (exit 1 names each missing id)
2. The log's "Key points … covered … excluded" line is `coverage_check.py`'s output, pasted, never typed from memory.
   *Enforced by:* `coverage_check.py` — rerun it and compare with the log
3. All source-derived text inserted into HTML is escaped: `& < > " '` in markup and attributes; widget data as JSON in a `type="application/json"` script element with `</` written `<\/`; render with `textContent`/`esc()`, never raw `innerHTML`.
   *Enforced by:* the shell's text-only render path + the `grep` in Verify
4. The guide is self-contained: no web fonts, CDN scripts or analytics unless the user asks.
   *Enforced by:* the `grep` for external URLs in Verify
5. An example appears when the source supports one; otherwise an example labelled `Illustrative`, or none. Never invent an unlabelled one to fill a page.
   *Enforced by:* convention (the log counts every `Illustrative` row)
6. Never "improve" a source number; a wrong fact is kept, shown `Corrected` (legal text: `Uncertain`) and logged.
   *Enforced by:* convention
7. Names, private anecdotes, credentials and internal URLs are removed unless `keep-names`; removals are logged by category and count, never quoted.
   *Enforced by:* convention

## Verify

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_check.py" inventory.json guide.html   # or the guide/ dir
grep -nE '<(link|script|img)[^>]+(href|src)="?https?:' guide.html                     # expect no output
grep -nE '<[^>]+ on[a-z]+=' guide.html                                                # expect no inline handlers
```

The script sits at `scripts/coverage_check.py` in this plugin (two levels above this skill folder) if `CLAUDE_PLUGIN_ROOT` is unset. Then the judgement items in `references/accuracy-log.md` §4 (read one page as a newcomer).

## Failure modes

| Bad output | What stops it |
|---|---|
| "Key points: 42 · covered: 42" typed from memory while three points are missing | Rule 2: the line comes from `coverage_check.py`, which exits 1 and names `kp-17` |
| A transcript about XSS renders `<img onerror=…>`, or a closing script tag in a quote breaks every widget | Rule 3: escaping + JSON data blocks + `textContent` |
| A thin source padded with invented, unlabelled examples on every page | Rule 5: example only when supported, else labelled or omitted |
| "Summarize this" answered with a classification table and a pause | Commands: no-command default is `summary` |
| A quiz and glossary bolted onto a retro | Standard pages depend on content type (`page-template.md` §2) |
| A private meeting's guide pings a font CDN on open | Rule 4 |

## Scale

| Input | Output |
|---|---|
| < 1,500 words, or a short ask | `summary` only (one page) |
| A talk, RFC or chapter | `outline` → `detail`, typically 6–12 pages |
| > 20,000 words or several topics | `summary` first; `detail` one category at a time, or one guide per topic |

A full `detail` HTML guide is 60–150 KB of output; offer `summary` or `cheatsheet` first when the user hasn't asked for the full guide.

## Sources

SOURCE: original — adapted from the author's visual-learning-guide prompt (v1.3) and its review; WCAG 2.2 contrast (4.5:1) for the shell's colour tokens.

## Delivery message (chat)

Title line · a table of pages and what's interactive · the coverage line and label counts from the log · anything that needs the user's confirmation · "Say `detail <section>` or `summary` for other views." Don't publish, upload or share anything externally without explicit approval.
