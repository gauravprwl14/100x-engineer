# Safety

What this plugin can and cannot change on your machine, verified by reading the code
and by `tests/test_safety.sh`.

**Threat model:** you run `claude --dangerously-skip-permissions`. Nothing prompts.
Every mutation happens silently, so the only protection is what the code refuses to do.

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [What this plugin never does](#what-this-plugin-never-does) | the destructive operations it contains zero instances of, and the one GitHub write | 23 lines |
| 2 | [The complete mutation surface](#the-complete-mutation-surface) | every write, where it lands (under the records root, or the PR review root), what guards it, how writes stay inside the repo, and when `pr-review` posts to GitHub | 62 lines |
| 3 | [Operations that require --yes](#operations-that-require---yes) | the operations that move or rewrite existing files, or run a plan's declared commands | 32 lines |
| 4 | [Refusals](#refusals) | path traversal, a records root outside the repo, and non-git directories | 25 lines |
| 5 | [The hooks](#the-hooks) | what the gate is for, what it parses and refuses, push binding, signed receipts, the bypass classes it does not close, Stop, the Stop re-check, SessionStart and the PostToolUse index nudge, fail-open | 97 lines |
| 6 | [Keeping this true](#keeping-this-true) | the audit that stops the boundary decaying | 15 lines |
| 7 | [Residual risks](#residual-risks) | what is still on you | 23 lines |

## What this plugin never does

Verified by `scripts/safety_audit.py`, which **fails the build** if any of these
appears outside a documented allowlist:

| operation | instances |
|---|---|
| `shutil.rmtree` — recursive delete | 0 |
| `os.remove` / `os.unlink` / `.unlink()` — file delete | 0 |
| `os.rmdir` — directory delete | 0 |
| `git rm` | 0 |
| `git checkout` — discards working-tree changes | 0 |
| `git reset` | 0 |
| `git clean` | 0 |
| `git stash` — moves your uncommitted work | 0 |
| `git push` — sends data off the machine | 0 |
| shell `rm -…` | 0 |

**This plugin deletes nothing.** It never runs git commands that discard your work, and
no tool in it sends anything off your machine. The one exception is a skill step, not a
tool: `pr-review`'s `post` command runs `gh api … /pulls/<n>/reviews` to create a **draft**
review, and only after it has shown you the exact payload and you answered yes (see
"GitHub writes" below). Its tools' only network use is `git fetch` in `pr_snapshot`. If something on your system deleted a file
after you installed a plugin, it was not this one — check your other installed plugins.

The one apparent exception is a false positive worth knowing about:
`hooks/require_verification.py` contains the *string* `git push`, because it must
**recognise** that command in order to gate it. The auditor distinguishes a regex that
detects a command from a call that runs one.

## The complete mutation surface

Every path this plugin writes to. Nothing else is touched.

`<root>` is the records root, resolved by `scripts/_paths.py`, first match wins:

| order | source | example |
|---|---|---|
| 1 | `.100x.json` at the git root | `{"root": "docs/engineering"}`; this plugin's own repo commits `{"root": "."}` |
| 2 | env `HUNDREDX_ROOT_DIR` | a one-off run or CI |
| 3 | default | `docs/engineering` |

A repo that already holds top-level `prds/`, `specs/`, `decisions/`, `rca/`, `lessons/`,
`reviews/` or `ledger/` records, with no config and no `docs/engineering/`, keeps using
them, with a warning that says how to settle it.

| tool | writes | where | guard |
|---|---|---|---|
| `verified.py` | `verification-receipt.json` | `100x/` in the per-worktree git directory (`git rev-parse --git-path 100x/verification-receipt.json`), never the worktree | scope: one known file; written via `safe_write_text` contained in the resolved git directory, refused when `100x/` or the receipt is a symlink; a leftover `.claude/verification-receipt.json` is ignored with a note, never deleted |
| `verified.py` (first run only) | `receipt.key`, a random HMAC key | `~/.config/100x/` (or `$HUNDREDX_KEY_FILE`) | created `0600` with `O_EXCL`, never overwritten |
| `plan_feature.py new` | `spec.md`, `INDEX.md` | `<root>/specs/<name>/` | `--dry-run`, name validation |
| `prd.py new` | `prd.md`, `INDEX.md` | `<root>/prds/<name>/` | `--dry-run`, name validation |
| `testplan.py new --out` | a test plan | the path given, or bare `--out` → `<root>/specs/<feature>/testplan.md`, beside the spec | `--dry-run`, refuses to overwrite without `--force`, git root required; stops when a plan exists at the old `<root>/testplans/<feature>.md` unless `--force` |
| `plan_dag.py stamp` | adds `spec`, `spec_sha256` and `base` to an existing plan.json | the plan file given | git repository required; refuses a spec that fails `plan_feature audit` or is not `ready`; written via `safe_write_text`, contained in the repository |
| `decide.py new` | `ADR-NNNN-*.md`, `INDEX.md` | `<root>/decisions/` | `--dry-run`, name validation |
| `rca.py new` / `link` | `RCA-NNNN-*.md`, `INDEX.md` | `<root>/rca/` | `--dry-run`, name validation |
| `learn.py add` | `LESSON-NNNN-*.md`, `INDEX.md` | `<root>/lessons/` | scope: one directory |
| `learn.py promote` | **appends a lesson to an existing file** | `AGENTS.md` (else `CLAUDE.md`, or `--file`) | **requires `--yes`** |
| `ledger.py index` / `map` | `INDEX.md`, `MAP.md` | `<root>/ledger/` | generated files only |
| `ledger.py shard` | **moves existing records** | `<root>/decisions/YYYY/QN/` etc. | **requires `--yes`** |
| `check_index.py --register` | one catalogue row | `<root>/INDEX.md` (or `--index`) | adds or updates one row |
| `check_index.py --gen-collections` | `INDEX.md` | `research/`, `reviewers/`, `skills/` | generated files only |
| `check_index.py --gen-terms` | `TERMS.md` | the git root (or `--terms-out`) | generated file only |
| `check_index.py --fix-stubs` | **rewrites existing docs in place** | matched markdown | **requires `--yes`** |
| `agent_report.py extract -o` | one report JSON | the path given (may sit outside the repo, next to a worktree) | scope: one named file; a symlink planted at the path cannot redirect the write |
| `diagram_from_code.py` | a `.mmd` file | `tempfile.mkdtemp()` | temp dir, removed |
| `run_evals.py` | scratch repos | `tempfile.TemporaryDirectory()` | temp dir, removed |
| `pr_review.py` (`init`, `render`, `feature`, `merge`, `mark-posted`, `index`, `context --refresh`) | `CONTEXT.md`, `INDEX.md`, `_meta/*` (created only when missing), rendered review files, `review.json` | the review root `CR` resolved by `pr_review out-dir`: by default `<parent of the clone>/code-review/<repo>/`, else `~/.config/pr-review/reviews/…` — outside the reviewed repo, so the records-root containment above does not apply | scope: the folder it is pointed at; `init` never overwrites; `context --refresh` rewrites only the `<!-- auto -->` blocks |
| `pr_snapshot.py` | exported head/base trees, `.diff`, `PINS.md` | `--dest` | scope: one directory; the clone only receives `git fetch` (objects and remote refs), never a checkout |
| `pr_suggest.py` | `suggestion-checks.json`; with `--write`, `review.json` | the PR folder given | work copy in `tempfile.TemporaryDirectory()`; `--cmd` runs as argv, no shell |
| everything else | nothing | — | read-only |

**Every record write is contained.** Writers go through `_paths.safe_write_text`: the
target's symlinks are resolved first, a write that would land outside the repository is
refused with exit 2, and the bytes go to a no-follow temp file renamed over the target, so
a link planted at the destination is replaced, never written through. `learn promote`
also refuses a lesson containing control or line-separator characters, which would
otherwise start a line of its own in `AGENTS.md`.

All record paths resolve from the **git root**, not from the plugin directory, so
records land in your project and travel with it.

### GitHub writes

Only the `pr-review` skill talks to GitHub, through `gh`, from its own steps
(`decisions/ADR-0002-gh-cli-for-pr-review-confined-to-skill-steps.md`); no script does. Reviewing
and `adjust` only read (`gh pr view`, `gh pr checks`, `gh issue view`, `gh api` GET). `post` is
the single write: it checks the PR head still matches the reviewed SHA, shows the payload, asks
once per PR, and on anything but an explicit yes posts nothing. It creates a draft review unless
you say `submit`, and never approves or requests changes unless you name that event. This
boundary is a skill instruction: `safety_audit` cannot see it and the commit gate does not
intercept `gh api … /reviews`.

## Operations that require `--yes`

These change files that already exist, or run commands a record names, so each prints
a plan and does nothing without explicit consent:

```bash
100x ledger shard              # prints the moves, changes nothing
100x ledger shard --yes        # performs them

100x check_index --fix-stubs           # lists what it would rewrite
100x check_index --fix-stubs --yes     # rewrites in place

100x learn promote LESSON-0001         # shows the lines it would append
100x learn promote LESSON-0001 --yes   # appends them to AGENTS.md

100x agent_report replay report.json --graph plan.json        # prints what it would run
100x agent_report replay report.json --graph plan.json --yes  # runs them, compares exit codes
```

`replay` never executes a report's evidence text. It runs only the commands `plan.json`
declares as that task's `verify` list (required: no `--graph`, exit 2), as argv without a
shell; a `sh -c '…'` script is printed before it runs. Evidence for any other command is
listed `not replayed (undeclared)` and the run exits 3. A declared command the
verification hook classes as a commit, push, tag or publish is refused, judged on the
exact argv replay would execute (and an `sh -c` script with `#` read literally), and a
timeout kills the command's whole process group. Evidence matches a declared command by
argv equality, and `100x verified [--name X] -- <cmd>` evidence matches `<cmd>`; replay
runs the plan's plain form, never the wrapper.

`shard` moves records into date directories once a folder exceeds 40 entries. Ids live
in the filenames and do not change, so links keep working — but it is still a file
move, and under `--dangerously-skip-permissions` nothing else would ask.

Every record-creating tool also accepts `--dry-run`, which prints a unified diff of
what would be written and exits without touching anything.

## Refusals

**Path traversal.** A crafted record name cannot escape the records directory:

```
$ plan_feature.py new "../../etc/passwd" --kind crud
refusing name '../../etc/passwd' -- record names may contain only letters, digits,
'.', '_', '-', and cannot start with '.' or contain a path separator.
```

**Outside a git repository.** Records resolve from the git root. With no git root the
only fallback is the current directory, which could be `$HOME` or anywhere the shell
happened to be — too easy to litter by accident, so the tools refuse and say so. Run
`git init`, or `cd` into your project.

**A records root outside the repository.** A `.100x.json` root or `HUNDREDX_ROOT_DIR`
that is absolute or contains `..` is refused with exit 2, so a committed config file
cannot make the record writers write outside the project.

## The hooks

Five hooks, registered in `hooks/hooks.json`, all run as `python3` scripts from
`${CLAUDE_PLUGIN_ROOT}/hooks/`.

| hook | event | what it can do |
|---|---|---|
| `require_verification.py` | `PreToolUse` (Bash) | `deny`, `ask`, or nothing; never `allow` |
| `stop_gate.py` | `Stop` | block ending a turn once; never twice in a row |
| `recheck_gate.py` | `Stop`, `SubagentStop` (opt-in) | block ending a substantive turn (a file edit, or a final answer of 1500+ chars) once, with the re-check prompt from `skills/recheck/references/recheck-prompt.md` as the reason; on `SubagentStop` only when `subagents` is `all` or lists the agent type; skipped under `stop_hook_active`, `HUNDREDX_RECHECK=manual\|off` or `~/.config/100x/recheck.json`; reads the transcript's last 2 MB (a subagent's own file when it has one), its `.meta.json`, and that file, writes nothing, runs no subprocess |
| `session_start.py` | `SessionStart` | add six lines of context naming `/100x:100x`, `100x list`, the operating model, the receipt rule and the generated-docs index rule; reads nothing in your repo |
| `index_check.py` | `PostToolUse` (Write, Edit, MultiEdit) | add context only, never blocks: after a `.md` write, warns when a long multi-section file lacks `## Contents`, when its folder has 2+ docs and no `INDEX.md`, or when the folder's `INDEX.md` does not list it (OPERATING-MODEL §9); reads that file and lists its folder, writes nothing, runs no subprocess |

**What the gate is.** An integrity aid against a confused agent and against casual
evasion: every natural way of phrasing a commit, push, PR or publish is meant to be
caught, and where the parser cannot tell what a command does it gates rather than
guesses. It is **not** a security boundary against an agent that deliberately sets out
to defeat it; the classes it does not close are listed below, so nobody over-trusts it.

**When the PreToolUse gate acts.** `hooks.json` routes any Bash command containing
`git`, `gh`, `commit`, `push`, `merge`, `publish`, `twine` or `upload` as a bare
substring, so `$(echo git) commit` still reaches the script, which returns at once when
nothing is gated. The script parses the command line the way one shell would run it:

| construct | example |
|---|---|
| compound commands, keywords, subshells | `a && b`, `{ git push; }`, `if …; then git push; fi`, `for …; do git push; done`, `(cd x); …` |
| words as the shell reads them | a backslash-newline joins lines; `#` is a comment only at the start of a word (`issue#12`, `$#`, `page#top` are words); `<<` opens a heredoc only unquoted and outside `(( ))`, ends at the whole delimiter word, and one with no terminator drops nothing |
| where it runs | `cd` (including `"$PWD"`), `git -C`, `--git-dir`, `GIT_DIR` exported earlier in the line; an unresolvable directory falls back to the session's repository |
| wrappers, with their option arities | `env -u X`/`-S`/`-C`, `sudo -u`, `doas`, `timeout`, `nice -n`, `stdbuf`, `xargs`, `watch`, `eval`, `command`, `bash -c` (with `-o`/`-O` values, `-euo pipefail` clusters), `npm`/`pnpm`/`yarn`/`uv` `exec`, `dlx`, `x`, `run` |
| indirection | `G=git; $G commit`, command substitution, `-c alias.ci=commit`, `GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n`, repo and global aliases, `git config alias.ci …` earlier in the same line; `GIT commit` on macOS, whose filesystem ignores case |
| programs that run their arguments | `find -exec git commit`, `docker run img git push`: an unrecognised program's argv is scanned |
| a program name it cannot resolve | `$X commit`, `$(…) push`: gated on the words that follow |
| a git subcommand it cannot resolve | `git ${C:-commit}`, `git $'commit'`, `git "$(…)"`: denied, since what runs is unknown |
| text it cannot see | `echo … \| bash`, `bash <(…)`, `source <(…)`: the whole line is word-matched |

It acts on `git commit`, `git merge`, `git push` and `send-pack` (not `--dry-run`), tag
creation, `commit-tree` and `update-ref`, `gh pr create|merge|ready`, `gh api …/merge`,
`gh release create` and the publishers (`npm`/`pnpm`/`yarn publish`, `twine upload`,
`uv publish`, `poetry publish`, `hatch publish`, `cargo publish`, `gem push`, and any
`<program> publish`), against the repository each one targets.

| repository state | result |
|---|---|
| no `.claude/verification-policy.json` | **warn**: passes, with a warning that the gate is not configured |
| policy `{"mode": "off"}` | silent |
| policy present | **block**: denied unless a fresh, **signed** receipt covers every required check with the command the policy binds to it |
| `[skip-verify]` in the command | `ask`: a human approves or refuses; the agent cannot approve its own bypass |
| `--no-verify` (or an abbreviation), `commit -n`, `core.hooksPath` via `-c` or `GIT_CONFIG_*` | denied (they skip git's own hooks silently) |
| an earlier part of the same command can change files (`echo x >> f && git commit -am x`) | denied: the gate checks before the line runs, so run edits and verification first, then commit **in a separate command**. A read-only git command stops counting as read-only with `--output` or any `-c`, which can name a program git runs |
| a push or `gh pr create` after a commit in the same command | denied: that commit has not happened when the gate judges, so the tree the push sends is unknown (a pathspec, `GIT_INDEX_FILE` or a hook can change it) |
| `git push` / `gh pr create` | each ref sent must be the checked-out commit, and HEAD's tree must equal the verified content: `git push origin other-branch` or a push with uncommitted verified edits is denied. `git push origin :`, `push.default=matching` and `remote.<name>.mirror` (from `-c` or config) count as sending every branch; `remote.<name>.push` refspecs as refs it cannot tell |
| a commit that changes `.claude/verification-policy.json` | needs a receipt recorded with that policy in place |

**Why it never says `allow`.** An `allow` decision also skips the user's own `ask`
permission rules for that command. A gate whose job is to refuse has no business
granting, so a passing gate stays silent and your normal permissions apply.

**What a receipt proves, and against whom.** Entries are HMAC-SHA256 signed with a key
in `~/.config/100x/`, so a hand-written or edited receipt is rejected. The agent runs as
you, so an agent that deliberately reads the key can still sign; add a deny rule for
`~/.config/100x/**` (Read and Bash) or run sandboxed if that matters to you. A key that
others can read or write is refused outright.

**What `100x verified` refuses** (exit 2, nothing recorded): a run with
`PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `NODE_OPTIONS`, `GOFLAGS`, `LD_PRELOAD`,
`DYLD_INSERT_LIBRARIES`, `BASH_ENV`, `ENV` or any `npm_config_*shell*` set, since each
can turn a suite into a passing no-op without changing the command the receipt records;
a program, or the interpreter its `#!/usr/bin/env` line names, found first in a PATH
entry inside the repository or a temp directory (the repository's own virtualenv or
`node_modules/.bin` is exempt, the same names in a temp directory are not, and a symlink
there to a system binary is fine); and a symlinked `100x/` directory or receipt
in the git directory. The receipt records the real path of the executable that ran. It
lives in the per-worktree git directory, so it is never a change in the worktree and
`git add -A` cannot commit it; each linked worktree has its own.

**The committed policy wins.** When the worktree copy of the policy differs from the
committed one, the committed one is enforced, so the agent cannot switch the gate off
by editing or deleting the file.

**Residual bypass classes.** Stated so nobody mistakes the gate for a boundary:

- **Forgery by reading the key.** An agent that reads `~/.config/100x/receipt.key` can
  sign anything. Close it with a permission deny rule in `settings.json`, or run
  sandboxed:

  ```json
  {"permissions": {"deny": ["Read(~/.config/100x/**)", "Edit(~/.config/100x/**)",
                            "Bash(*.config/100x*)"]}}
  ```
- **Code the parser never sees as a command line**: a script file, `make`, `npm run`,
  `npx`, `python -c "os.system(...)"`, `bash < file`, or `eval "$X"` where `$X` was not
  assigned in the same command line.
- **Anything not modelled**: shell functions and aliases defined in rc files, a fake
  `HOME` supplying a global git alias, `PYTHONPATH`/`sitecustomize` shaping a check,
  `source file` (a script file, like `bash file`), a push target chosen through
  `include.path` config. Program names fold case only on macOS. `100x verified` checks
  the program it runs and one `env` shebang interpreter, not every program a test
  script later finds on PATH.
  History commands that make commits (`rebase`, `cherry-pick`, `revert`, `am`, `pull`)
  are not gated; the push that ships their result is, and is bound to HEAD's content.

**The Stop hook** blocks only when the repository is in block mode, has uncommitted
changes, and no signed receipt matches the current content. It respects
`stop_hook_active`, so it blocks at most once per stop attempt and cannot loop.

**Fails open, needs `python3`.** Any internal error in any hook produces no decision.
If `python3` is missing, the hook command itself fails, which Claude Code treats as a
non-blocking error. In both cases the gate goes quiet: it never strands your shell, but
a quiet gate is also not evidence that anything was verified. `ask` relies on a human
being there to answer; in a headless run, what an unanswered `ask` does is up to the host.

## Keeping this true

A safety claim in a README decays the moment someone adds a line, so the boundary is
executable:

```bash
100x safety_audit     # fails if a destructive primitive appears
bash tests/test_safety.sh           # includes a planted rmtree the audit must catch
```

The suite plants a `shutil.rmtree` into a script and asserts the audit catches it, so
the audit itself is tested rather than trusted.

## Residual risks

Honest list of what is still on you:

- **The checks run commands you name.** `verified.py --name test -- <cmd>` runs whatever
  you pass. The plugin does not vet your command.
- **`decide.py verify` executes the `verify` field of your own decision records.** That
  field is a shell command. Treat a record from an untrusted source as untrusted code —
  which is what `untrusted-agent-config` is for.
- **`--dangerously-skip-permissions` disables every other protection Claude Code has.**
  This plugin's refusals are narrow and specific; they are not a substitute for
  permission prompts.
- **Commands the parser cannot see are not gated**: a script file that runs
  `git commit`, `eval "$X"` with `$X` set elsewhere, and the other classes listed under
  "Residual bypass classes" above. The gate stops the shortcut, not an agent determined
  to evade it.
- **Nothing here protects against the model's own edits.** The gates check *evidence*
  before a commit; they do not review the diff. That is what `diff-review` and the
  stack reviewers are for, and they are advisory.
- **`pr-review`'s post boundary is an instruction, not code.** An agent that ignores the
  skill could run `gh api -X POST` itself; the draft default means a mistaken post is
  visible only to you until you submit it.
- **Generated indexes overwrite.** `INDEX.md` and `MAP.md` are outputs; hand edits are
  lost on regeneration. They say so in their headers.
