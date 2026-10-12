# Accuracy log, privacy and verification

Read at step 6. The evidence-label table itself is in SKILL.md.

## Contents
1. Accuracy rules
2. Privacy
3. Accuracy log template
4. Verification checklist

## 1. Accuracy rules

- Never present an illustrative example, assumption or inference as if it came from the source.
- Never "improve" a number from the source. If it looks wrong, keep it, label it, and explain in the log.
- If the source states something false, show the correct version marked `Corrected` and log it. Don't silently fix or silently repeat it. Legal or policy text: never `Corrected` — mark `Uncertain`, and put a "not legal advice; the source governs" banner on the home page.
- Rumours, speculation and unverifiable anecdotes: label `Speaker's view` or drop them — and log which.
- A garbled passage with two plausible readings: pick the likelier, mark `Uncertain`, log both readings.
- Prefer omission over invention. When in doubt, leave it out and log it.
- With web search, verify version numbers, product names, limits and dates that could have changed — **public facts only**: never put source text, names, internal product names or identifiers into a query. Without search (or for anything private), mark `Uncertain` rather than guessing.

## 2. Privacy

- Remove names of participants, students, customers and colleagues, and private anecdotes (health, family, finances), unless the user says `keep-names` (meetings and incidents: default to roles, "Platform lead").
- Remove credentials, internal URLs, confidential business data.
- Log each removal **by category and count**, without repeating the removed content ("Removed 14 participant names"). Log columns never quote redacted text: write `[redacted: name]`.
- Don't publish, upload or share the guide or the source without the user's explicit approval.

## 3. Accuracy log template

Write `accuracy-log.md` next to the guide (or a final page if only one file is possible). One log per source: if you produce several outputs from it (summary + detail), prefix the "Where" column with `[summary]` or `[guide]`.

The first Summary line is **pasted from** `coverage_check.py` output — never typed from memory. If it reports `missing: N > 0`, fix the guide (add the point and its tag, or mark the item `excluded` with a reason in `inventory.json`) and run it again.

```markdown
# Accuracy log — <guide title>
Source: <file / title> · Generated: <date> · Mode: detail|summary

## Summary
- <paste: "Key points in source: N · covered: N · intentionally excluded: N · missing: 0">
- Corrections: N · Illustrative examples: N · Added facts: N · Uncertain: N · Redactions: N
  (each count = the number of rows of that type in the Changes table below)

## Changes
| # | Where in guide | Type | Source said / situation | What the guide does | Why | Confidence |
|---|---|---|---|---|---|---|
| 1 | Timeouts page | Corrected | "the default timeout is 15 min" (example row) | States the documented default | Verified against public docs | High |
| 2 | Few-shot page | Illustrative | — | Example outputs written for the guide | Explain the pattern | n/a |
| 3 | Q&A | Excluded | Off-topic tangent | Not included (inventory: kp-41, excluded) | Out of scope | n/a |

## Transcription fixes
| Heard | Interpreted as | Confidence |

## Open questions for the author
- <things a human should confirm>
```

## 4. Verification checklist

Mechanical (run them):
- [ ] `coverage_check.py inventory.json <guide>` exits 0 for every output (summary and detail each).
- [ ] The log's coverage line is that command's output, verbatim.
- [ ] HTML: no duplicate ids; every `#link` resolves to an element id; inline scripts pass `node --check` when node is available.
- [ ] No unescaped source text: `grep -n '<script' <guide>` shows only the shell's own scripts and JSON data blocks; no `on…=` attributes inside content sections.

Judgement (read one page as a newcomer):
- [ ] Every number traces to the source, a labelled calculation, or a labelled external fact.
- [ ] Every illustrative example is labelled, in every output that contains it.
- [ ] Every topic page has a "What it is" definition before its tables/diagrams.
- [ ] Every uncommon diagram type is named and explained in its first reading note.
- [ ] Nothing important exists only inside an interactive widget.
- [ ] The source's key terms appear verbatim at least once.
- [ ] Every visual has "reading this" notes; every option has pros, cons, use when.
- [ ] Code snippets use real APIs or are marked pseudocode.
- [ ] No participant names or private details remain (unless `keep-names`).
- [ ] Navigation works: index, prev/next; Markdown pages link back to `INDEX.md` on line 1.
