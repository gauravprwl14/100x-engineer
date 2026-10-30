# bench: does the plugin improve agent output?

**What it answers:** on 15 synthetic tasks, is the output of a real Claude Code session
better with the NEW plugin than with the OLD one (`--old-ref`, default commit `4c1cd93`) or
with no plugin? Scores come from hidden checks the agents never see, and the bench was
written apart from the agents that changed the plugin. One full run is 135 sessions, about
$33–108 (measured $0.16–0.25 per session on the smallest case).

| Arm | What loads | Source |
|---|---|---|
| none | no plugin | the `with-without` ablation arm of the NEW run |
| old | 100x at `--old-ref` (default `4c1cd93`) | a temporary `git worktree` |
| new | 100x as the working tree is now | an rsync snapshot taken at start |

## What each scenario measures

| Case | Task given to the agent | Hidden check |
|---|---|---|
| 01-naming-overdue | add an overdue-invoices function | `craft_check` naming checks, the bench's own naming rule (verb-first only past 10 code lines, as the fixture's noun-named function shows), and the correct due-date rule |
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
| 13-settings-screen-build | add a workspace settings page: members view, admins rename, change timezone, delete | a probe submits the rendered forms: members see no admin control and are refused (403/404, nothing changes) on direct requests, as is another workspace's admin; delete needs a confirmation that names the workspace; the page has an unsaved-changes guard; judge: confirmation wording plus 2 of save-disabled, field errors, side-effect note, conflict, audit |
| 14-qa-testplan-settings | write TESTPLAN.md and tests for a settings page | the tests fail on the shipped code (delete lacks its admin check) and pass once it is fixed; they kill 6 mutants (no delete confirmation, controls shown to members, rename open to members, no unsaved guard, silent overwrite, bad timezone saved); the plan covers confirmation, unsaved edits, the member's UI and direct request, and conflicts |
| 15-review-settings-diff | review PR #57 from PR.diff and the head files | one comment each for the one-click delete, Delete shown to members, rename without `require_admin` (blocking, cited inside the function) and the missing unsaved guard; no blocking false alarm on the escaped, validated code |

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

Cases 13-15 measure the screen-behaviour checklist (`100x plan_feature cases --kind settings
--roles member`); their ground truth is the `settings`, `destructive-action` and `_roles`
rows of `scripts/data/edge_cases_ui.json`. They share one stdlib-only app (case 13's
fixture), and none of them needs git.

## Run it

```bash
bash bench/test_bench.sh                 # offline: scaffolds build, graders pass good and fail bad samples
bash bench/run.sh                        # prints the cost warning and stops
bash bench/run.sh --yes                  # full bench: 15 cases x 3 runs x 3 arms
bash bench/run.sh --yes --runs 1 --case 12-over-building --arms new   # smoke test, 2 sessions
bash bench/run.sh --yes --old-ref main --case 13-settings-screen-build   # one screen case, OLD = current main
python3 bench/compare.py --new bench/results/<ts>/new.json --old bench/results/<ts>/old.json \
  --tools-root bench/results/<ts>/snapshot-new
```

`--case` goes to `claude plugin eval`, whose glob matched no case for `1[3-5]-*` (run on
2026-10-30, zero sessions started) although the cost warning counted 3; pass one exact
name or a plain `*` pattern per run.

`--old-ref REF` sets OLD to any commit (a branch, tag or sha). It is resolved before the
cost warning, which prints the ref and its sha; an unknown ref exits 2 without starting a
session, and the sha is recorded in `old-ref.txt` beside the results.
`--max-cost-usd` caps each of the two `claude plugin eval` invocations separately.
Results go to `bench/results/<timestamp>/`, which is not meant to be committed. Kept
workspaces (`/private/tmp/e-*`) are read-only; once `compare.py` has cached its scores in
`bench-checks.json`, remove them with `chmod -R u+w` followed by `rm -rf`.

## Git in the sandbox

Cases 09 and 11 need git inside the agent's sandbox. On macOS `/usr/bin/git` is the xcrun
shim, which writes a cache to the per-user temp dir under `/var/folders`. The sandbox denies
that write, so every git command fails with `couldn't create cache file ... Operation not
permitted`. The real binaries (`xcrun --find git`, or
`/Library/Developer/CommandLineTools/usr/bin/git`) run fine. Agents take PATH from your
login shell, and setting `env.PATH` in a case's `.claude/settings.json` does not change it.

| Fix | Effect |
|---|---|
| link the real git into a directory before `/usr/bin` on your login PATH | git works in every arm; `run.sh` checks this before it starts |
| `BENCH_ALLOW_GIT_SHIM=1` | runs anyway; the git checks in 09 and 11 then measure the sandbox |

In the 2026-10-16 run git failed in 105 of 108 sessions, in all three arms.

## Reading the results

- Each cell is `score (llm/det)`: the combined score, then the eval-grader share and the
  `checks.py` share.
- The sign test counts the scenarios where NEW beats OLD, and the ones where it loses; ties
  are dropped. With 15 scenarios, p < 0.05 needs at least 12 wins out of 15 non-tied.
- A subset cannot reach significance alone: 3 wins out of 3 (cases 13-15) give p = 0.25.
  Report such a subset per case, with each case's failed checks, not as a sign test.
- A small p is evidence across scenarios. One scenario moving tells you nothing about the
  others.
- Check the footer. `plugin-load mismatches` must be 0 (it reads `100x:` skills from each
  trace's init event), and `errors` counts runs that timed out or crashed.
  `checklist calls k/n` counts the runs whose trace has a Bash call to the screen checklist
  (`plan_feature cases`, or `plan_feature` with `--screens`/`--roles`), out of the runs with
  a readable trace. It shows whether an arm used the checklist and is
  not part of the score.
- Bias to keep in mind: `prose_check` and the new `craft_check` checks ship with NEW, so
  they share its rules. The rest of the checks belong to the bench alone: behaviour tests,
  git state, size budgets, its own naming rule, and the paragraph and length limits.
