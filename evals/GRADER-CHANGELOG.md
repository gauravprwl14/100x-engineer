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

## Rules

1. Never change a grader and a score in the same commit without an entry here.
2. If a check is loosened, say what it stopped catching.
3. A baseline recorded before a grader fix is void — re-record it and say so.
