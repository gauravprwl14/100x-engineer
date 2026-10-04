# Changelog

All notable changes to this plugin. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
`.claude-plugin/plugin.json`'s `version`, which is what decides when an installed copy
updates.

## [0.2.0] - Unreleased

### BREAKING

Each of these fails quietly for a 0.1 user, so each has a step. The same steps, with
commands, are in the README under "Migrating from 0.1".

| what changed | 0.1 | 0.2 | what to do |
|---|---|---|---|
| marketplace name, so the install id | `100x-engineer@100x-local` | `100x-engineer@100x-engineer` | `claude plugin marketplace remove 100x-local`, then `claude plugin marketplace add gauravprwl14/100x-engineer` and `claude plugin install 100x-engineer@100x-engineer`; rename any hand-written `enabledPlugins` key |
| skill | `decision-log` | `decision-records` | update references (`/100x-engineer:<skill>`, agent `skills:` lists, notes) |
| skill | `engineering-ledger` | `decision-records` | as above |
| skill | `typescript-verification` | `language-verification` | as above |
| skill | `python-verification` | `language-verification` | as above |
| skill | `go-verification` | `language-verification` | as above |
| skill | `scoped-review` | `diff-review` | as above |
| skill | `reviewing-others-code` | `diff-review` | as above |
| tool invocation | `python3 scripts/<tool>.py` | `100x <tool>` | the old form resolved only inside this repo |
| tier on `prd new` and `plan_feature new` | `--scale`, defaulted when omitted | `--tier <prototype\|small\|growth\|scale>`, required | add `--tier`; `--scale` remains an alias |
| record location | top-level `prds/`, `specs/`, `decisions/`, `rca/`, `lessons/`, `ledger/` | under the records root: `.100x.json` `{"root": "<dir>"}`, then `HUNDREDX_ROOT_DIR`, then `docs/engineering` | nothing to do to keep working (existing top-level collections are used, with a warning); set `.100x.json` to settle it |
| verification receipt | unsigned | HMAC-signed with a key in `~/.config/100x/` | re-run each check through `100x verified`; 0.1 receipts are rejected |
| commit gate with no policy file | silent | warns | add `.claude/verification-policy.json`, or `{"mode": "off"}` to silence it |
| receipt file location | `.claude/verification-receipt.json` in the worktree | inside the repository's git directory, never in the worktree | nothing to do; delete the old `.claude/verification-receipt.json` and its `.gitignore` line |

### Added

- `/100x-engineer:100x`, a router that names the intent and tier of a plain-English
  request, applies built-in defaults and asks at most five questions.
- Eleven specialist agents in `agents/`, with the contract in `docs/OPERATING-MODEL.md`.
- Skills: `100x`, `orchestrate`, `requirements-intake`, `app-security`, `data-lifecycle`,
  `qa-strategy`, `release-rollout`, `ui-baseline`.
- `bin/100x`, one entry point for every tool from any project. `100x list` shows the tools
  for your project; `100x list --all` adds the maintainer tools (`agents_lint`,
  `lint_skills`, `run_evals`, `safety_audit`, `skill_triggers`), which check this plugin
  itself.
- Tools: `baseline` (defaults by work type, tier and risk), `plan_dag` (task-graph lint),
  `agent_report` (agent report lint and replay), `testplan` (QA test plans and AC
  traceability), `appsec_check`, `ui_baseline_check`, `agents_lint`, `verify_fingerprint`.
- `AC-<n>` acceptance-criterion ids carried from PRD to spec to test. A test counts for a
  criterion only when tagged `<feature>/AC-<n>`, for example `test('tagging/AC-1 …')`.
- `100x agent_report lint <report> --graph plan.json --cwd <worktree>` checks git's changed
  files against the task's declared files; `100x agent_report replay <report> --graph
  plan.json --cwd <worktree> --yes` re-runs only the plan's declared verify commands and
  compares exit codes. Reports declare `"schema": 1`.
- Agent reports carry a `findings` list, and declared verify commands an `expect_exit`.
- `SessionStart` hook naming the router and `100x list`; `Stop` hook that, in block mode,
  stops a turn ending with changes and no matching receipt.
- Policy `required_checks` as an object binding each label to its command,
  `{"test": "npm test"}`; the gate requires the receipt to have run that command.

### Changed

- The commit gate parses the command line instead of matching its first words, so it
  catches the phrasings of a commit, push, PR or publish that 0.1 let through; it also
  gates `gh release create`, and enforces the committed policy when the worktree copy
  differs from it. Its remaining bypass classes are listed in `docs/SAFETY.md`.
- `prd new` and `plan_feature new` require `--tier`.
- `plan_feature audit` blocks on any malformed `AC-<n>` line and on a deleted seeded edge-case
  or decision row.
- `decide lint` treats each option's `fit` as pass/fail before weighted scoring.
- Marketplace renamed from `100x-local` to `100x-engineer`. Its plugin entry sets no
  description or version of its own, so both come from `.claude-plugin/plugin.json`, the
  one place to bump.
- The list form of `required_checks` (`["test"]`) still loads, with a note that it checks
  labels, not commands.

### Removed

- Skills `decision-log`, `engineering-ledger`, `typescript-verification`,
  `python-verification`, `go-verification`, `scoped-review` and `reviewing-others-code`,
  merged into `decision-records`, `language-verification` and `diff-review` (see BREAKING).

## [0.1.0]

First release: verification-enforced engineering skills with runnable checks, the
`PreToolUse` commit gate, and the research corpus they cite.
