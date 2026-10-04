# Safety

What this plugin can and cannot change on your machine, verified by reading the code
and by `tests/test_safety.sh` (22 assertions).

**Threat model:** you run `claude --dangerously-skip-permissions`. Nothing prompts.
Every mutation happens silently, so the only protection is what the code refuses to do.

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [What this plugin never does](#what-this-plugin-never-does) | the destructive operations it contains zero instances of | 20 lines |
| 2 | [The complete mutation surface](#the-complete-mutation-surface) | every write, where it lands, and what guards it | 30 lines |
| 3 | [Operations that require --yes](#operations-that-require---yes) | the two that move or rewrite existing files | 20 lines |
| 4 | [Refusals](#refusals) | path traversal and non-git directories | 20 lines |
| 5 | [The hooks](#the-hooks) | when each hook blocks, what it trusts, and how it fails | 45 lines |
| 6 | [Keeping this true](#keeping-this-true) | the audit that stops the boundary decaying | 15 lines |
| 7 | [Residual risks](#residual-risks) | what is still on you | 20 lines |

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
it never sends anything off your machine. If something on your system deleted a file
after you installed a plugin, it was not this one — check your other installed plugins.

The one apparent exception is a false positive worth knowing about:
`hooks/require_verification.py` contains the *string* `git push`, because it must
**recognise** that command in order to gate it. The auditor distinguishes a regex that
detects a command from a call that runs one.

## The complete mutation surface

Every path this plugin writes to. Nothing else is touched.

| tool | writes | where | guard |
|---|---|---|---|
| `verified.py` | `verification-receipt.json` | `.claude/` in the git root | scope: one known file |
| `verified.py` (first run only) | `receipt.key`, a random HMAC key | `~/.config/100x/` (or `$HUNDREDX_KEY_FILE`) | created `0600` with `O_EXCL`, never overwritten |
| `plan_feature.py new` | `spec.md`, `INDEX.md` | `specs/<name>/` | `--dry-run`, name validation |
| `prd.py new` | `prd.md`, `INDEX.md` | `prds/<name>/` | `--dry-run`, name validation |
| `decide.py new` | `ADR-NNNN-*.md`, `INDEX.md` | `decisions/` | `--dry-run`, name validation |
| `rca.py new` / `link` | `RCA-NNNN-*.md`, `INDEX.md` | `rca/` | `--dry-run`, name validation |
| `learn.py add` | `LESSON-NNNN-*.md`, `INDEX.md` | `lessons/` | scope: one directory |
| `ledger.py index` / `map` | `INDEX.md`, `MAP.md` | `ledger/` | generated files only |
| `ledger.py shard` | **moves existing records** | `decisions/YYYY/QN/` etc. | **requires `--yes`** |
| `check_index.py --gen-collections` | `INDEX.md` | `research/`, `reviewers/`, `skills/` | generated files only |
| `check_index.py --fix-stubs` | **rewrites existing docs in place** | matched markdown | **requires `--yes`** |
| `diagram_from_code.py` | a `.mmd` file | `tempfile.mkdtemp()` | temp dir, removed |
| `run_evals.py` | scratch repos | `tempfile.TemporaryDirectory()` | temp dir, removed |
| everything else | nothing | — | read-only |

All record paths resolve from the **git root**, not from the plugin directory, so
records land in your project and travel with it.

## Operations that require `--yes`

Two operations change files that already exist, so both print a plan and do nothing
without explicit consent:

```bash
100x ledger shard              # prints the moves, changes nothing
100x ledger shard --yes        # performs them

100x check_index --fix-stubs           # lists what it would rewrite
100x check_index --fix-stubs --yes     # rewrites in place
```

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

## The hooks

Three hooks, registered in `hooks/hooks.json`, all run as `python3` scripts from
`${CLAUDE_PLUGIN_ROOT}/hooks/`.

| hook | event | what it can do |
|---|---|---|
| `require_verification.py` | `PreToolUse` (Bash) | `deny`, `ask`, or nothing; never `allow` |
| `stop_gate.py` | `Stop` | block ending a turn once; never twice in a row |
| `session_start.py` | `SessionStart` | add five lines of context; reads nothing in your repo |

**When the PreToolUse gate acts.** `hooks.json` routes any Bash command mentioning
`git`, `gh`, or a publisher (`npm`/`pnpm`/`yarn publish`, `twine upload`,
`uv publish`), because its `if` patterns cannot see past `git -C <path>` or
`git -c k=v`. The script then parses the command (compound commands, `cd`, `-C`,
`--git-dir`, `env`/`bash -c` wrappers, git aliases) and acts only on `git commit`,
`git push` (not `--dry-run`), tag creation, `gh pr create|merge|ready`,
`gh release create` and the publishers, against the repository each one targets.

| repository state | result |
|---|---|
| no `.claude/verification-policy.json` | passes, with a warning that the gate is not configured |
| policy `{"mode": "off"}` | silent |
| policy present | denied unless a fresh, **signed** receipt covers every required check with the command the policy binds to it |
| `[skip-verify]` in the command | `ask`: a human approves or refuses; the agent cannot |
| `--no-verify`, `commit -n`, `-c core.hooksPath=` | denied (they skip git's own hooks silently) |

**Why it never says `allow`.** An `allow` decision also skips the user's own `ask`
permission rules for that command. A gate whose job is to refuse has no business
granting, so a passing gate stays silent and your normal permissions apply.

**What a receipt proves, and against whom.** Entries are HMAC-SHA256 signed with a key
in `~/.config/100x/`, so a hand-written or edited receipt is rejected. The agent runs as
you, so an agent that deliberately reads the key can still sign; add a deny rule for
`~/.config/100x/**` (Read and Bash) or run sandboxed if that matters to you. A key that
others can read or write is refused outright.

**The committed policy wins.** When the worktree copy of the policy differs from the
committed one, the committed one is enforced, so the agent cannot switch the gate off
by editing or deleting the file.

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
bash tests/test_safety.sh           # 22 assertions, including a planted rmtree
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
- **Commands the parser cannot see are not gated**: `eval "$X"`, a script file that
  runs `git commit`, or a heredoc piped into a shell. The gate stops the shortcut, not
  an agent determined to evade it.
- **Nothing here protects against the model's own edits.** The gates check *evidence*
  before a commit; they do not review the diff. That is what `scoped-review` and the
  stack reviewers are for, and they are advisory.
- **Generated indexes overwrite.** `INDEX.md` and `MAP.md` are outputs; hand edits are
  lost on regeneration. They say so in their headers.
