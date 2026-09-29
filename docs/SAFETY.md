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
| 5 | [The commit hook](#the-commit-hook) | when it blocks, and how it fails | 20 lines |
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
**match** that command in order to gate it. The auditor distinguishes a regex that
detects a command from a call that runs one.

## The complete mutation surface

Every path this plugin writes to. Nothing else is touched.

| tool | writes | where | guard |
|---|---|---|---|
| `verified.py` | `verification-receipt.json` | `.claude/` in the git root | scope: one known file |
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
python3 scripts/ledger.py shard              # prints the moves, changes nothing
python3 scripts/ledger.py shard --yes        # performs them

python3 scripts/check_index.py --fix-stubs           # lists what it would rewrite
python3 scripts/check_index.py --fix-stubs --yes     # rewrites in place
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

## The commit hook

`hooks/require_verification.py` is the only component that blocks anything.

- **Opt-in per project.** With no `.claude/verification-policy.json` it returns `{}` and
  every command passes through untouched. Installing the plugin does not change the
  behaviour of any existing repository.
- **Blocks only completion-shaped commands**: `git commit`, `git push`, `gh pr create`,
  `git tag`, `npm publish`. Nothing else is inspected.
- **Fails open.** Any internal error returns an empty decision rather than blocking. A
  broken gate must not strand you.
- **Auditable bypass**: `[skip-verify]` in the commit message, or `VERIFY_SKIP=1`. Both
  appear in the transcript. `--no-verify` is *denied* rather than honoured, because it
  silently skips git's own hooks.

## Keeping this true

A safety claim in a README decays the moment someone adds a line, so the boundary is
executable:

```bash
python3 scripts/safety_audit.py     # fails if a destructive primitive appears
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
- **Nothing here protects against the model's own edits.** The gates check *evidence*
  before a commit; they do not review the diff. That is what `scoped-review` and the
  stack reviewers are for, and they are advisory.
- **Generated indexes overwrite.** `INDEX.md` and `MAP.md` are outputs; hand edits are
  lost on regeneration. They say so in their headers.
