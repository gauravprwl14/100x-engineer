# Evidence labels

A shared vocabulary for marking where a statement came from. Used by
`codebase-comprehension`, `reviewing-others-code`, `root-cause-analysis` and every
document under `research/`.

The problem it solves: an inferred claim presented as a fact is the most expensive
kind of wrong, because nothing about its phrasing invites checking. "The retry is
capped at 3" reads identically whether it was read in code or guessed from a variable
name.

## The labels

| label | meaning | when to use |
|---|---|---|
| *(none)* | faithful restatement of the source | you read it and are quoting/paraphrasing it |
| `Verified` | read directly in code or output, with a `file:line` | any claim about behaviour |
| `Inferred` | deduced from naming, structure or convention — not read | you did not open the thing you are describing |
| `Illustrative` | an example written to explain, not taken from the source | teaching a pattern with made-up data |
| `Added` | a standard, checkable fact not present in the source | background the reader needs |
| `Corrected` | the source is wrong; this is the right version | never silently fix, never silently repeat |
| `Uncertain` | you could not resolve it; say what the doubt is | ambiguous code, dynamic dispatch, missing context |

## Rules

1. Never present `Inferred` or `Illustrative` content as if it were `Verified`.
2. A `Verified` claim carries a `file:line`. Without one it is `Inferred`.
3. Never "improve" a number from the source. Keep it, label it, explain it.
4. If the source is wrong, show the correct version as `Corrected` and say so — do not
   silently repair it and do not silently repeat it.
5. Prefer omission over invention. When unsure, leave it out and record why.
6. If a passage has two plausible readings, pick the likelier, mark `Uncertain`, and
   state both.

## Worked example

Bad — three different epistemic states, presented identically:

> The session TTL is 30 days. Sessions are stored in Redis. The cache is warmed on
> boot, which is why the first request is fast.

Good:

> Session TTL is 30 days. `Verified` — `src/auth/session.store.ts:42`
> Sessions are stored in Redis. `Verified` — `src/auth/session.store.ts:11`
> The cache appears to be warmed on boot. `Inferred` from the `onModuleInit` hook name;
> I did not trace what it loads. `Uncertain` whether it affects first-request latency.

The second version is longer and is the only one a reader can act on, because they can
see exactly which sentence to distrust.

## Applies to research too

Every document under `research/` follows this. Where a finding was wrong it is
**retracted in place**, not deleted — see the corrected Anomalies section in
`research/21-findings-agent-instruction-corpus.md`, where two files were initially
misread as prompt-injection attacks and turned out to be deliberate maintainer
controls.

## Source

Adapted from the accuracy-contract section of a user-supplied `visual-learning-guide`
skill bundle (`local: visual-learning-guide/SKILL.md`, not a public repository). Its
label set — `From source` / `Illustrative` / `Added` / `Corrected` / `Speaker's view` /
`Uncertain` — was written for summarising transcripts. `Verified` and `Inferred`
replace `From source` and `Speaker's view` here, because the sources in this project
are code and repositories rather than people talking.
