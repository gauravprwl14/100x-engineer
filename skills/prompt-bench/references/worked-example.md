# Worked example: the two studies behind this skill

Both studies tested follow-up prompts after a first answer (`paired-followup`), with
in-session subagents as runners and judges. They were run by hand; `prompt_bench` now does
the bookkeeping. Scores are blind 0–10 overall.

## Round 1 — four easy tasks, two arms, no placebo

Tasks: PR review (3 seeded bugs + decoy), stale README vs a pnpm repo, a rounding fix,
over-engineering bait. 16 runs, n = 8 per arm.

| arm | v1 → v2 | Δ | improved/same/worse | wrong claims |
|---|---|---|---|---|
| generic "Please double-check your answer" | 7.12 → 8.38 | +1.26 | 5/3/0 | 2 → 1.5 |
| audit (user's long prompt) | 6.88 → 8.25 | +1.37 | 7/1/0 | 2 → 1.25 |

Lessons: first answers were already 7+ (one task at 8.5 mean) — a ceiling, so a better
wording had nowhere to show. The "generic" arm was in effect a placebo, and it got almost
the same gain: the second pass, not the wording, did the work.

## Round 2 — three hard tasks, four arms incl. placebo

Tasks: `task-design.md` (h1 coupon review, h2 PG 11 migration, h3 money parser with probes).
24 runs, n = 6 per arm.

| arm | v1 → v2 | Δ | vs placebo | sign test p | wrong claims | length | follow-up time |
|---|---|---|---|---|---|---|---|
| placebo | 5.92 → 7.42 | +1.50 | – | – | 2.17 → 1.83 | +16% | 91 s |
| user (audit prompt) | 5.50 → 7.92 | +2.42 | +0.92 | 0.375 | 2.5 → 1.33 | +7% | 110 s |
| A (5-point checklist) | 6.00 → 7.50 | +1.50 | +0.00 | 1.0 | 2 → 1.5 | +32% | 118 s |
| B (falsify: "assume a mistake") | 5.92 → 7.83 | +1.92 | +0.42 | 0.22 | 2.17 → 1.0 | −1% | 104 s |

Lessons:
- The second pass is the big lever: on h3 0/8 first answers were safe, 7/8 after any follow-up.
- Wording adds a smaller, noisy effect; no arm beat placebo at n = 6. Honest verdict for all
  three: "no better than placebo (within noise)".
- A made answers 32% longer for the placebo's gain; B was the only arm that got shorter and had
  the fewest wrong claims.
- Process sections ("Changed after re-check") were penalised by judges as leakage.

These numbers are the `evals/fixtures/prompt-bench/round2` fixture; `tests/test_prompt_bench.sh`
asserts `aggregate` reproduces them.

## What changed in the method between rounds

| round 1 | round 2 / this skill |
|---|---|
| easy tasks | tasks with a hidden trap; ceiling warning at 8.5 |
| no placebo | placebo arm required |
| read the code | executable probes per code task |
| one judge per task, free-form | rubric + process-leakage penalty + wrong-claim list |
| mean Δ only | per-run Δ, matched pairs, exact sign test, verdict |
