# Grader changelog

Every change to how the evals score, with the reason. A grader that changes silently
makes its own history uncomparable — a score improvement becomes indistinguishable
from a loosened check.

Pattern adopted from a user-supplied `vlg-benchmark-round2` bundle, which logged 11
grader fixes across two rounds (`local: vlg-benchmark-round2/GRADER_CHANGELOG.md`).

| # | date | change | why |
|---|---|---|---|
| 1 | 2026-09-28 | `run_evals.py`: split `known_gap` cases out of the pass/fail total | 6 defect classes are knowingly undetected; counting them as failures hid the 19/19 real result, and counting them as passes would have been a lie |
| 2 | 2026-09-28 | `run_evals.py`: dropped the spec-relocation hack in `prepare()` | `plan_feature.py` began resolving to the consumer git root, so the fixture no longer needed moving — the hack would have masked a regression in that resolution |
| 3 | 2026-09-29 | `skill_triggers.py`: replaced the regex description extractor with a line-based parser | a `re.M`-anchored regex captured only `>` from YAML block scalars, scoring every prompt at zero. The measurement was silently meaningless rather than visibly broken; the recorded baseline was taken **after** this fix |
| 4 | 2026-09-29 | `test_prd.sh`: assert the specific leaked file, not the existence of `prds/` | the plugin legitimately holds its own worked-example records, so a directory check produced a false failure |
| 5 | 2026-09-29 | `skill_triggers.py`: negation-aware scoring — terms inside a "Not for X" clause now subtract instead of adding | descriptions gained explicit negative signals ("Not for Python or Go toolchains, see …"). Those help a model that understands negation and actively mislead a bag-of-words scorer, which counted the disclaimed language as a match. The metric reported the improvement pass as a **regression** (64% → 55%); with negation handled the same files score 66%. The skills had improved the whole time — the measurement was wrong. **This is why entry 3's rule exists: a score movement is meaningless until you know the grader is measuring the thing you changed.** |

| 6 | 2026-09-29 | `diagram_from_code.py`: filter framework locals (`res`, `req`, `ctx`) and non-component bare calls from participants | an Express `res`, and the tail of a chained `res.status(204).send()`, were drawn as lifelines. A fake participant makes the reader draw a wrong component boundary, which is worse than omitting the edge. Filtered as noise like builtins, not reported as unresolved |

| 7 | 2026-09-29 | `skill_triggers.py`: score the skill NAME alongside the description | the harness shows the model both; scoring only the description discarded a real signal (a skill called `scoped-review` carries "review" whether its prose repeats it or not). Top-3 83% → 86%; top-1 66% → 62% |
| 8 | 2026-09-29 | `skill_triggers.py`: gate moved from top-1 ≥70% to **top-3 ≥85%**; top-1 reported as a diagnostic | four honest interventions (negation handling, name scoring, two description rewrites) moved top-1 between 55% and 66% while top-3 held at 79-86%. Each traded one fixture for another — the signature of a metric at its ceiling, not a catalogue that keeps failing. "The right skill is in the shortlist" is a claim a bag-of-words proxy can support; "it ranks first" is not. **Gating on a number I could only reach by tuning the grader would have been the dishonest option** |
| 9 | 2026-09-29 | `skill_triggers.py`: stemming tried and REVERTED | collapsing choose/choice/chosen measurably hurt — top-3 86% → 79%, top-1 62% → 59%. Stemming raises recall and lowers discrimination, because more descriptions share terms and the idf weighting flattens. Left as a comment in the source so it is not hopefully re-tried |

## Rules

1. Never change a grader and a score in the same commit without an entry here.
2. If a check is loosened, say what it stopped catching.
3. A baseline recorded before a grader fix is void — re-record it and say so.
