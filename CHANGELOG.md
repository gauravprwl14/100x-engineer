# Changelog

All notable changes to this plugin. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
`.claude-plugin/plugin.json`'s `version`, which is what decides when an installed copy
updates.

## [0.3.0] - Unreleased

Engineer agents now apply the coding and writing standards while they write, not only at
review. Every new check warns and never blocks.

### Added

| what | where |
|---|---|
| One writing standard for PR descriptions, commits, review comments, replies, docs, chat answers and code comments: size proportional to the change, claims next to their proof, one evidence vocabulary and one severity scheme | `docs/WRITING.md` |
| `prose_check`: 15 text rules (body budget, long paragraph, claim without evidence, filler, self-ticked box, review comment without severity or scenario, reply without a sha, and more) | `scripts/prose_check.py` |
| `pr-description` skill | `skills/pr-description/` |
| `pr_scope`: files outside a PR's declared scope, or also changed on a sibling branch of a stack | `scripts/pr_scope.py` |
| `fails_without_fix`: reverts the source change in a throwaway worktree (repo hooks off) and checks the new tests fail; `--link-deps` links gitignored `node_modules`/`.venv`/`vendor/bundle` | `scripts/fails_without_fix.py` |
| Engineer standards card read at write time | `reviewers/_engineer-standards.md` |
| Rails, Django/FastAPI, Express/Node and Go reviewers; insecure IaC defaults; Ruby, Kotlin and Swift in `language-verification` | `reviewers/`, `skills/language-verification/` |
| Output benchmark: 12 scenarios run through `claude plugin eval` against no plugin, the previous version and this one | `bench/` |
| `explain` skill: on-demand visual step-through of a PR, file or concept — map, flow, what can go wrong, each fix replayed as its own scenario, the decision, an evidence tag per claim; light (static step cards + `.md` export) or `--heavy` (animated, compare tab, en + ja); project settings read from the target's `CLAUDE.md`/`AGENTS.md` | `skills/explain/` |
| `flow`: checks a walkthrough's `scenario.json` against the code (anchors at the pinned SHA, `git grep` absence counts, tagged numbers, a fix or `open` per issue, tier budgets, reducer expectations) and builds it into one offline HTML page | `scripts/flow.py`, `tests/test_flow.sh` |
| `explain` pages say what the PR is for before they animate it: `context` (a purpose a newcomer follows, in and out of scope, which entry points are animated), `terms`, an `origin` on every issue (`in-code`, `found-in-review`, `what-if`), a pseudocode `outline` with each line citing its real line, per-step `code`, and a code pane beside the diagram showing pseudocode or the real lines `flow build` reads from git at the pinned commit; `flow check` flags identifiers in step titles that are not terms; research reuses a pr-review run's `1-context.md` | `skills/explain/`, `scripts/flow.py` |
| `comprehension-mapper` preloads `explain`; the router's understand row names it for walkthroughs | `agents/comprehension-mapper.md`, `skills/100x/SKILL.md` |
| `pr-review` Design and Scenario lenses: conditional agents that challenge the PR's 1–3 decisions (one-way door, no alternative, recurring cost) and list inputs neither code nor tests handle; ≤ 5 items each, unproved ones become questions; `--design`, `--scenarios`; gate G15-lens | `skills/pr-review/`, `scripts/data/pr_review_{design,scenario}_fragment.json` |

### Changed

| what | before | now |
|---|---|---|
| `craft_check` naming | generic-noun stoplist | adds `short-names`, `abbreviations`, `boolean-predicate`, `function-verb`, `method-names`, `magic-number`; a repo allowlist in `.100x.json` `craft_allow_names`; unsupported languages are named, not passed silently |
| backend, frontend and mobile engineers | no `code-craft`/`test-design`; Verify ran task commands and `bloat_check` | preload both; a context card before the first edit; `craft_check`, `perf_check`, `appsec_check` in Verify; behaviour evidence for user-visible `done` |
| router | single-agent changes skipped review | `code-reviewer` on any 2+ file change, `security-reviewer` when routes, auth, input, tenancy, uploads or infra change |
| `code-reviewer` | naming skipped once a higher blocking finding stopped the widening | naming and readability is a separate pass |
| recheck on subagents | off unless configured | on for the three engineer agents by default |
| `agent_report` | — | optional evidence `kind` (`build`, `test`, `behaviour`); warnings for UI/API `done` without behaviour evidence, source without tests, and no context card |
| commit and PR gate | — | adds `prose_check` and `pr_scope` findings to the hook's context on `git commit` and `gh pr create/edit`; the allow or deny decision is unchanged |
| recheck's closing line | `verified <what>` | `verified <what> (<file:line or command>)` |
| `function-verb` length | counted the docstring, so a documented 6-line `overdue_invoices` was flagged | counts code lines only |
| session start | docs rule only | adds the chat rule: the first sentence is the answer, not a heading |
| bench | one strict LLM rubric each for 07 and 09; verb-first names required; ran with git blocked | single-criterion graders; verb-first only past 10 code lines; `run.sh` stops when agents would get the blocked `/usr/bin/git` shim |

## [0.2.0] - Unreleased

### BREAKING

Each of these fails quietly for a 0.1 user, so each has a step. The same steps, with
commands, are in the README under "Migrating from 0.1".

| what changed | 0.1 | 0.2 | what to do |
|---|---|---|---|
| plugin name, so the skill prefix and install id | `100x-engineer:<skill>`, `100x-engineer@100x-engineer` | `100x:<skill>`, `100x@100x-engineer` | `claude plugin uninstall 100x-engineer@100x-engineer`, then `claude plugin install 100x@100x-engineer`; rename any hand-written `enabledPlugins` key and `100x-engineer:` references |
| marketplace name, so the install id | `100x-engineer@100x-local` | `100x@100x-engineer` | `claude plugin marketplace remove 100x-local`, then `claude plugin marketplace add gauravprwl14/100x-engineer` and `claude plugin install 100x@100x-engineer`; rename any hand-written `enabledPlugins` key |
| skill | `decision-log` | `decision-records` | update references (`/100x:<skill>`, agent `skills:` lists, notes) |
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
| receipt file location | `.claude/verification-receipt.json` in the worktree | the per-worktree git directory, `git rev-parse --git-path 100x/verification-receipt.json`: never a worktree change, one per linked worktree | nothing to do: the old file is ignored, with a note saying to delete it; no `.gitignore` entry is needed |

### Added

- A second plugin in the marketplace, `learn` 0.1.0 (`plugins/learn/`, install
  `claude plugin install learn@100x-engineer`): `/learn:guide` turns an RFC, design doc,
  finished postmortem, architecture note or talk transcript into a visual HTML/Markdown
  guide. Adapted from the visual-learning-guide skill with its review's fixes: a narrowed
  description and "Not for" routing, `summary` as the no-command default for short asks,
  key-point coverage computed by `plugins/learn/scripts/coverage_check.py` from
  `inventory.json` and `data-kp` tags, an escaping rule for source text, a self-contained
  shell (no web fonts) with print, focus, drawer and `aria-current` fixes, per-technique
  snippets instead of reading the 88 KB gallery, and `INDEX.md` for multi-file Markdown.
  No quality benchmark is claimed (`plugins/learn/evals/README.md`). `100x` does not load
  it, and its skill and test counts exclude it; `tests/run_all.sh` also runs
  `plugins/*/tests/` and lints `plugins/*/skills/`.
- `/100x:100x`, a router that names the intent and tier of a plain-English
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
- Agent reports may carry `findings` (`id`, `severity` critical|major|minor|trivial,
  `confidence` definite|probable|possible, `location`, `issue`, `fix`, `blocking`), and
  each evidence entry an `expect_exit` (default 0) that `done` is judged against; a plan's
  declared verify commands still need exit 0. A blocking finding unblocks `needs-decision`
  like a blocking question, and `agent_report summary` merges findings, blocking first.
  Read-only roles (requirements-analyst, solution-architect, code-reviewer,
  security-reviewer, independent-verifier) may report on their own `task_id`.
- `100x plan_dag stamp plan.json` records the approved spec's path, its sha256 and the
  base commit. `plan_dag lint` then requires that spec to pass `plan_feature audit` with
  status `ready` and to match the stamped hash ("re-plan or re-approve"), defaults
  `--spec` to it, and fails a task that claims an AC the spec does not define.
- A feature's files live together in `<root>/specs/<feature>/`: `spec.md`, `plan.json`,
  `testplan.md` (where bare `testplan new --out` now writes) and `reports/<task>.json`.
- `.100x.json` accepts `"schema": 1`; `"root"` is optional, and any other key is refused
  with a did-you-mean.
- `SessionStart` hook naming the router and `100x list`; `Stop` hook that, in block mode,
  stops a turn ending with changes and no matching receipt.
- Policy `required_checks` as an object binding each label to its command,
  `{"test": "npm test"}`; the gate requires the receipt to have run that command.
- Skill `pr-review`: `/pr-review <pr-url>` reviews a GitHub or GitHub Enterprise PR into one
  `review.json` per PR and SHA-pinned rendered files under a review root outside the repo
  (`code-review/<repo>/` beside the clone, or `~/.config/pr-review/reviews/…`); `init`
  scaffolds that root with `CONTEXT.md` and `_meta/`; `adjust` edits the comments; `post` sends a
  draft review only after an explicit yes. Tools `pr_review`, `pr_review_gate`, `pr_snapshot`,
  `pr_suggest`. Judgement comes from `diff-review` and `stack-reviewer`.
- `gh` is an allowed dependency of the `pr-review` skill's steps only, never of `scripts/`
  (`decisions/ADR-0002-gh-cli-for-pr-review-confined-to-skill-steps.md`); `docs/SAFETY.md`
  names `post` as the plugin's one GitHub write.
- Generated-documents rule, `docs/OPERATING-MODEL.md` §9: summary first, a `## Contents`
  table on long multi-section files, one `INDEX.md` per multi-file folder. The
  `SessionStart` context points at it, and a `PostToolUse` hook (`hooks/index_check.py`,
  `Write|Edit|MultiEdit`) warns after a `.md` write that breaks it; it adds context only,
  never blocks, writes nothing and fails open.

- Skill `recheck` and a `Stop`/`SubagentStop` hook (`hooks/recheck_gate.py`): once per
  substantive turn (files edited, or an answer of 1,500+ characters) Claude re-audits its own
  answer with one shared prompt (`skills/recheck/references/recheck-prompt.md`). Modes
  `auto|manual|off` via `~/.config/100x/recheck.json` or `HUNDREDX_RECHECK`; subagents are
  opt-in (`subagents: "all"` or an agent-type list). Evidence from two blind A/B rounds is in
  `skills/recheck/references/evidence.md`; `docs/OPERATING-MODEL.md` §10.
- Skill `prompt-bench` and tool `prompt_bench` (`init`, `record`, `snapshot`, `blind`,
  `judge-plan`, `probe`, `aggregate`, `report`): evaluate a prompt or instruction against a
  placebo arm with hidden-ground-truth tasks, isolated subagent runs and blind judges; reports a
  sign-test verdict, ceiling and small-n warnings, cost, and where the prompt belongs.

### Changed

- The commit gate parses the command line instead of matching its first words, so it
  catches the phrasings of a commit, push, PR or publish that 0.1 let through; it also
  gates `gh release create`, and enforces the committed policy when the worktree copy
  differs from it. Its remaining bypass classes are listed in `docs/SAFETY.md`.
- `prd new` and `plan_feature new` require `--tier`; `plan_feature new --kind` is optional
  (default `universal`).
- `plan_feature new` seeds a spec's open questions with at most five class C asks, blocking
  first, then one-way doors; the rest are listed "Deferred to next batch". Baseline items
  gain `when_any` (ask only for the kinds, work, tier or risk named) and `door`.
- `plan_feature audit` requires `covered`/`applied` evidence to be proof: a test or file
  path, a `<feature>/AC-<n>` tag, a runnable command, an ADR id or a §8 `V<n>` row. A
  pasted seeded suggestion is an error; `review` alone passes, counted unverified. It also
  runs `prd audit` on the linked PRD: errors from the `growth` tier, warnings below, and
  `| prd | none |` unlinks it.
- `agent_report lint` diffs against `--base`, else plan.json's `"base"`, else the
  worktree's fork point, else HEAD; requires the report's `agent` to be the task's owner;
  rejects unknown top-level keys; and matches evidence to declared commands by argv, with
  `100x verified [--name X] -- <cmd>` counting as `<cmd>`. `replay` screens the exact argv
  it runs.
- The commit gate also gates `poetry publish`, `hatch publish`, `cargo publish`, `gem push`
  and any `<program> publish`.
- Commit and push are separate commands: a push or `gh pr create` after a commit in the
  same command line is denied, and a `remote.<name>.push` refspec makes a plain push's refs
  unknown, so it is denied too.
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
