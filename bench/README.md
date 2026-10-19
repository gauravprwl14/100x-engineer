# bench: does the plugin improve agent output?

**What it answers:** on 12 synthetic tasks, is the output of a real Claude Code session
better with the NEW plugin than with the OLD one (commit `4c1cd93`) or with no plugin?
Scores come from hidden checks the agents never see, and the bench was written apart from
the agents that changed the plugin. One full run is 108 sessions, about $30–90 (measured $0.16–0.25 per session on the
smallest case).

| Arm | What loads | Source |
|---|---|---|
| none | no plugin | the `with-without` ablation arm of the NEW run |
| old | 100x at `4c1cd93` | a temporary `git worktree` |
| new | 100x as the working tree is now | an rsync snapshot taken at start |

## What each scenario measures

| Case | Task given to the agent | Hidden check |
|---|---|---|
| 01-naming-overdue | add an overdue-invoices function | `craft_check` naming checks, the bench's own naming rule, and the correct due-date rule |
| 02-reuse-helper | refund % by business days | calls the existing `business_days_between`; no copied weekday loop |
| 03-hidden-context | SMTP reminder service | follows `services/AGENTS.md`: `TODO_` env prefix, env read only in `config.py`, flat `services/` |
| 04-tests-can-fail | fix the pagination off-by-one, add tests | the new tests fail once the fix is reverted |
| 05-edge-negative-tests | validate the create-booking input | tests cover 3 of 4 rejection paths; bad input is refused and nothing is stored |
| 06-security-ownership | `get_booking` by id | another tenant's booking returns 404, the same as a missing id |
| 07-pr-description | write PR_BODY.md | `prose_check --kind pr` clean, under max(600, 8×diff lines) chars, #42 linked |
| 08-review-comment | review a refund diff | finds the over-refund bug, marks it blocking, `prose_check --kind review-comment` clean |
| 09-reply-to-review | fix it, commit, reply | the commit sha is in the reply, `prose_check --kind reply` is clean, the fix is correct |
| 10-explain-module | explain the retry logic | summary first, no paragraph over 3 lines, at least 6 of 8 facts |
| 11-scope-leak | fix feature-a while feature-b, with uncommitted work, is checked out | feature-a touches only export files; feature-b and its uncommitted file are untouched |
| 12-over-building | "mark a todo as done" | no new source file or class, ≤ 20 added source lines |

## Graders

- **Inside the eval** (`cases/*/graders/*.md`): `regex` on a named file or the final message,
  `file_exists`, and `llm` (haiku judge) with the ground truth written into the rubric. The
  judge sees it; the agent never does.
- **After the eval** (`checks.py`): `claude plugin eval` has no script grader, so code that
  must run (hidden behaviour tests, tests with the fix reverted, `craft_check`,
  `prose_check`, git branch state) runs over the workspaces `--keep-temp` preserves. Each run
  is diffed against a pristine copy rebuilt from the same `scaffold.sh`.
- **Run score** = passed weight / total weight over both sets. A scenario's score is the mean
  over its runs.

## Run it

```bash
bash bench/test_bench.sh                 # offline: scaffolds build, graders pass good and fail bad samples
bash bench/run.sh                        # prints the cost warning and stops
bash bench/run.sh --yes                  # full bench: 12 cases x 3 runs x 3 arms
bash bench/run.sh --yes --runs 1 --case 12-over-building --arms new   # smoke test, 2 sessions
python3 bench/compare.py --new bench/results/<ts>/new.json --old bench/results/<ts>/old.json \
  --tools-root bench/results/<ts>/snapshot-new
```

`--max-cost-usd` caps each of the two `claude plugin eval` invocations separately.
Results go to `bench/results/<timestamp>/`, which is not meant to be committed. Kept
workspaces (`/private/tmp/e-*`) are read-only; once `compare.py` has cached its scores in
`bench-checks.json`, remove them with `chmod -R u+w` followed by `rm -rf`.

## Reading the results

- Each cell is `score (llm/det)`: the combined score, then the eval-grader share and the
  `checks.py` share.
- The sign test counts the scenarios where NEW beats OLD, and the ones where it loses; ties
  are dropped. With 12 scenarios, p < 0.05 needs at least 10 wins out of 12 non-tied.
- A small p is evidence across scenarios. One scenario moving tells you nothing about the
  others.
- Check the footer. `plugin-load mismatches` must be 0 (it reads `100x:` skills from each
  trace's init event), and `errors` counts runs that timed out or crashed.
- Bias to keep in mind: `prose_check` and the new `craft_check` checks ship with NEW, so
  they share its rules. The rest of the checks belong to the bench alone: behaviour tests,
  git state, size budgets, its own naming rule, and the paragraph and length limits.
