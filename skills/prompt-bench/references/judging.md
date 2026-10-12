# Judging

One fresh subagent per task, given exactly the prompt `100x prompt_bench judge-plan <bench>
--task <id>` prints. It sees only `blind/<task>/`, the fixture and that task's ground truth.

## Rubric (0–10 integers)

| dim | scores |
|---|---|
| correctness | claims and code are right; a failing probe caps it at 4 |
| recall | finds what the ground truth requires |
| precision | no false alarms, no noise |
| surgical | no scope beyond what is needed |
| usefulness | a reader can act on it as written |
| concision | no padding, no process narration |
| overall | holistic, not an average; this drives the verdict |

Plus `wrong_claims` (one entry per factually wrong statement) and, for code, `probe_failures`.

## Rules for the judge

- Score each label alone against the ground truth; never guess the arm or v1/v2.
- **Process leakage** — "Changed after re-check", "What I verified", audit logs — costs
  concision, and overall when it buries the answer. A reader wants the final answer; a prompt
  that makes answers narrate their own checking is worse for the reader, even if the
  narration is true.
- Run `probe` for every code label; do not infer behaviour from reading.
- Write `scores/<task>.json` with one entry per label; `aggregate` refuses an unknown label
  and a missing `overall`.

## Leaks to fix before judging

`blind` warns when a blind file contains an arm name (≥ 4 chars) or the first 40 chars of an
arm's prompt. Typical cause: an arm asked for a section with a fixed heading, and v2 answers
carry it. Edit the blind file (rename the heading to something neutral) and note it in
`REPORT.md`; do not re-blind after judges start (`blind --force` relabels everything).

## Reading the result

| aggregate says | meaning | do |
|---|---|---|
| better than placebo | p < 0.05 and ≥ +0.5 points vs placebo | place it per `categories.md` |
| no better than placebo (within noise) | the gain, if any, is indistinguishable from the placebo's | prefer the placebo/shortest wording |
| worse | p < 0.05 and ≤ −0.5 points | do not use |
| `ceiling` warning | baseline ≥ 8.5 on that task | rebuild the task; its rows are uninformative |
| `n=… (< 6)` warning | sign test cannot reach significance | directional only; add reps |
| `length … > 25%` | answers grew a lot | check judges did not reward volume |
