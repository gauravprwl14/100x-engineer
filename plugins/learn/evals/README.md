# Evaluating /learn:guide — protocol (TODO, no results yet)

**Status: not run. There are no quality claims for this skill.** An earlier benchmark of the source skill was not imported. Its outputs were hand-written and rendered by a benchmark-owned template, the failing cases were patched by hand, the grader was loosened after its author had seen the outputs, it had no baseline, and the raw input text already scored 97% on its "coverage" check.

## What an honest run needs

| Requirement | Why |
|---|---|
| **Fresh session per case**, with only this plugin installed and only the input file plus a one-line ask | The model must run the skill; no author, answer key or grader in context |
| **Keep full transcripts** (prompt, tool calls, outputs, timings) next to each output | Shows that a model produced the output, not a person or a script |
| **No-skill baseline**: the same ask in the same model, plugin not installed | Without it, any score could be the model's alone |
| **Frozen grader**: committed, with a hash recorded, *before* any output exists; later changes go to a changelog, and old runs are re-scored | Stops a grader being tuned until it passes |
| **3–5 real, long inputs** (≥ 5,000 words: a public conference-talk transcript, a public RFC, a public postmortem, a lecture) with known licences | The old inputs were 100–200 synthetic words with planted defects |
| **Blind judge**: a separate model or human sees baseline and skill outputs in random order, unlabelled, and scores faithfulness, invented claims, usefulness and time-to-answer for 5 questions per input | Keyword presence is not comprehension |
| **Mechanical checks kept separate** from judged quality: `coverage_check.py` exit code, escaping greps, `node --check`, external-request grep | A structural pass says nothing about whether the guide is right |
| **Trigger cases**: ≥ 10 should-fire and ≥ 10 should-not-fire prompts (chat summaries, PRs, code, meeting action items), scored with `scripts/skill_triggers.py --distractors` | The old suite named the command in every case, so it never tested routing |

## Report shape (when run)

| input | words | mode | skill: coverage_check | baseline: judge score | skill: judge score | invented claims (skill / baseline) | transcript |
|---|---|---|---|---|---|---|---|

Leave this table empty until a run produces it.
