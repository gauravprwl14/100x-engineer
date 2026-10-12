# Content types → recommended structure

Use this after classifying the input (SKILL.md step 2). These are starting points. Mixed inputs are normal (a lecture with a system-design case study and a long Q&A): combine the matching rows.

## Contents
0. Classify the input
1. Quick lookup table
2. Per-type details
3. Handling messy inputs

---

## 0. Classify the input

Decide these five and write them at the top of the outline:

| Dimension | Options (pick one or more) |
|---|---|
| Content type | lecture/course · meeting · interview/podcast · panel/debate · tutorial/how-to · technical doc/RFC/spec · research paper · incident/postmortem · sales/customer call · book/narrative · news/opinion · policy/legal · product demo · brainstorm |
| Knowledge shape | concepts · processes/sequences · systems/architecture · comparisons/trade-offs · decisions · timeline/history · arguments/claims · data/numbers · people/roles · stories/cases |
| Audience | who will read it, their level, what they already know (ask if unclear) |
| Reader goal | understand · decide · do/apply · remember/exam · teach others · reference later |
| Density | how much real content vs filler (sets guide length; never pad) |

Which optional standard pages (catalogue, applications, glossary, quiz) each type gets: `page-template.md` §2.

## 1. Quick lookup table

| Content type | Categories usually look like | Must-have techniques | Special pages |
|---|---|---|---|
| Lecture / course session | Foundations → techniques → failure modes → production → worked case | Concept map, strategy comparison matrix, decision wizard, worked examples, code | Catalogue, glossary, quiz |
| Meeting | Decisions · actions · open questions · context | Decision log table, RACI/owner table, timeline | "What changed" page |
| Interview / podcast | Themes (not chronology) | Theme map, claim/evidence table, quote cards (short), speaker-view labels | "Key takeaways", "disagreements" |
| Panel / debate | Positions per question | Position matrix (speaker × question), argument map, agree/disagree grid | "Where they agree" |
| Tutorial / how-to | Setup → steps → verify → troubleshoot | Step-through, command tables, before/after, troubleshooting tree | Cheat sheet |
| Technical doc / RFC / spec | Problem → design → alternatives → risks | Architecture diagram, sequence diagram, alternatives matrix, state machine | Decision record |
| Research paper | Question → method → results → limits → implications | Method flow, results charts, claim/evidence table, limitation list | "What this does not show" |
| Incident / postmortem | Timeline → impact → root cause → fixes | Timeline, fishbone / 5-whys, sequence diagram, action table | Lessons learned |
| Sales / customer call | Needs · objections · commitments · next steps | Needs/pain table, objection → response table, stakeholder map | Follow-up checklist |
| Book / narrative | Characters · plot · themes · ideas | Character map, plot timeline, theme table, chapter summaries | Discussion questions |
| News / opinion | Claims · evidence · context · counterpoints | Claim/evidence/counter table, timeline, stakeholder map | Fact-check notes |
| Policy / legal | Scope · obligations · exceptions · penalties · dates | Obligation table (who/what/when), decision tree ("does this apply to me?"), timeline | Plain-English glossary |
| Product demo | Problem → features → workflow → limits | Feature matrix, workflow flow, before/after screens | "What it can't do" |
| Brainstorm | Idea clusters → evaluation → chosen | Affinity map, 2×2 (impact × effort), pros/cons | Parking lot |

## 2. Per-type details

### Lecture / course session
- Reorganise by concept, not by the order the speaker said it. Speakers loop back; the guide shouldn't.
- Promote every "strategy", "approach", "pattern", "trick" into the catalogue with pros/cons.
- Demos with numbers → keep exact numbers, label `Live demo`, add a "what to take from the numbers" note.
- Q&A → mine for gotchas, alternatives, production experience; attach each to the topic page it belongs to (don't leave it in a Q&A dump).
- Worked case (e.g. system design) → requirements, numbers/capacity, architecture, sequence, code, failure handling, extensions.
- Instructor's anecdotes → keep the lesson, drop the personal detail, label `Speaker's view` if it's a claim.

### Meeting
- Only when the user wants a *learning* artifact from a meeting (a recorded design walkthrough, a training session). For notes or action items, answer in chat with a decision/action table — not this skill. No quiz, no applications page.
- Lead with decisions and action items (owner, due date) — that's what readers come for.
- Keep discussion only where it explains a decision.
- Open questions get their own list.
- Names: meetings often need owners. Ask the user whether to keep names; default to roles ("Platform lead").

### Interview / podcast
- Cluster by theme. Each theme page: guest's view, supporting examples, counterpoints (if any), your `Added` context.
- Opinions stay labeled as opinions.
- Short quotes only (one line); paraphrase the rest.

### Tutorial / how-to
- Numbered steps are correct here (it's a real sequence).
- Every step: command/action, expected result, common error + fix.
- Add a prerequisites box and a "verify it worked" step.

### Technical doc / RFC
- Problem statement and constraints first.
- Alternatives considered → matrix with the rejection reason.
- Risks and open questions → table with owner if known.

### Research paper
- Separate what was measured from what is claimed.
- Charts for results; note sample size and conditions.
- Explicit "limitations" and "does not show" sections prevent over-reading.

### Incident / postmortem
- Input is a finished RCA/postmortem record; writing the RCA itself is not this skill. No quiz, no applications page.
- Timeline with timestamps is the backbone.
- Blameless: roles, not names.
- Actions table: action · type (prevent/detect/mitigate) · owner role · status.

### Book / narrative
- Character map (relationships), plot timeline, themes table with example scenes.
- Spoiler warnings if the reader may not have finished.

## 3. Handling messy inputs

| Problem | What to do |
|---|---|
| Auto-transcript garbling | Interpret from context; log non-obvious fixes in "Transcription fixes" |
| Speaker corrects themselves later | Use the corrected version; log if the earlier wrong version might confuse readers |
| Contradictions between parts | Show both, label `Uncertain`, add to open questions |
| Very long input | Summary mode first; detail mode split by category |
| Very short / thin input | Fewer pages; don't pad. Add `Added` context only where it genuinely helps, and label it |
| Multiple topics unrelated | One guide per topic, or a top-level index linking separate guides |
| Non-English or mixed language | Write in the user's language; keep original technical terms; add glossary entries |
