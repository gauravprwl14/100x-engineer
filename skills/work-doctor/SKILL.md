---
name: work-doctor
description: >
  Session brief not showing, wrong workstream, "is my work record backed up", "work doctor",
  "why didn't the hold block the push", after switching laptops: run `100x work doctor`,
  explain each finding plainly, apply the safe repairs, re-run until clean.
---

# Work doctor

The work record (`100x work`) only helps when a session actually receives its brief, and when
it fails it fails silently: the hook fails open, a stale plugin copy runs old hooks, a branch
maps to no workstream, a backup stops pushing. Guessing which one costs a session. `100x work
doctor` checks each in turn and prints, per problem, what is wrong, the likely cause and the
exact fix. Think of it as a car's diagnostic port: one reading names the faulty part, so
nobody has to take the engine apart.

## Trigger

**Fire when:** the session brief is not showing or shows the wrong workstream; the user asks
whether the work record is backed up, says "work doctor", or asks why a hold did not block a
push; after switching laptops or reinstalling the plugin; a work command says "no workstream
matches" or "several workstreams".

**Do not fire when:** the question is about PR state (CI, reviews, merged), which the record
never stores: read it live. Finding which past session did something is `session-find`.

## Steps

| # | step |
|---|---|
| 1 | Run `100x work doctor`; if the problem is about another worktree, add `--cwd <that dir>`. Use `--json` when you need to branch on finding ids |
| 2 | Read the header first: `session brief here: yes/no` is a dry run of the SessionStart hook for that directory, and `cwd: ... -> <workstream>` is what it matched |
| 3 | Take findings in order (error, warn, info). Explain each in one plain sentence: what broke, why, what the fix does |
| 4 | Apply, without asking, only `chmod 700 <record dir>` |
| 5 | Show the exact command and ask first before every other fix: the `claude plugin uninstall / marketplace update / install` chain for a stale config dir (it can stop halfway: when uninstall succeeds and install fails, that config dir has no plugin until install is run again), editing a backup tool's file list, adding a git remote, finishing or aborting the backup repo's rebase or merge, and any record change that alters meaning (`release-hold`, `start --pr`, a handoff's text) |
| 6 | Re-run `100x work doctor` after each fix until it exits 0: no error or warning. `info` findings the user accepts (no backup configured, a stale hold, no record yet) are fine; state each once, plainly |

"Why didn't the hold block the push": in this version a hold is recorded and shown in the
brief, but no hook blocks a push on it; that check is PRD phase P2
(`prds/work-continuity/prd.md` §11). Say so; doctor's D-holds lists every active hold's age.

## Rules

1. Diagnose with doctor before changing anything; never infer "the hook isn't firing" from a
   missing brief alone. The dry run feeds `hooks/work_brief.py` the SessionStart payload for
   `--cwd`, so "would a session here get the brief" has a yes/no answer without starting one.
   *Enforced by:* `bash tests/test_work.sh` ("hook dry run" and "dry run says no" cases)

2. Doctor is read-only: no write, no fetch, no `gh`. A fix is always a command the agent or
   user runs afterwards, never a side effect of the diagnosis.
   *Enforced by:* `bash tests/test_work.sh` ("doctor wrote nothing ..." cases)

3. Exit 0 means no error or warning; exit 1 means at least one; exit 2 is a usage error. "Done"
   is a doctor run that exits 0, shown, not a claim that the fix was applied.
   *Enforced by:* `bash tests/test_work.sh` ("exit 0", "exits 1", "exit 2" cases)

4. Ask before any fix other than `chmod 700` on the record dir, including a plugin reinstall,
   and before any record change that alters what it says. Releasing a hold is the user's
   decision even when doctor calls it stale. Never move, edit or delete an event file: doctor
   reports an unreadable or malformed event, the brief already skips it, and anything it held
   is recorded again as a new event.
   *Enforced by:* review

5. Report backup state as doctor measured it: commits ahead of upstream are counted from
   local refs, so "pushed" means "as of the last fetch". Never fetch to check.
   *Enforced by:* `bash tests/test_work.sh` (D-backup "counts commits ahead from local refs")

6. Never paste findings that quote record text (hold reasons, notes) into commits, PR text or
   review comments; the record is private (`docs/SAFETY.md`, ADR-0006).
   *Enforced by:* review

## Verify

```bash
100x work doctor ; echo "exit $?"                 # <2s; 0 = no error or warning
100x work doctor --cwd "$(git rev-parse --show-toplevel)" --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["ok"], [c for c in d["checks"] if c["id"]=="D-brief"])'
bash "$(100x root)/tests/test_work.sh"           # ~15s; every check's detection and clean case
```

## Failure modes

This skill rejects:

- **"The hook must be broken"** when the dry run says `no` because the branch maps to no
  workstream: D-lookup names the missing `--pr` and pre-fills the `100x work start` command.
- **Reinstalling the plugin in the wrong config dir**: the fix carries `CLAUDE_CONFIG_DIR=<dir>`
  for the exact dir whose cached copy lacks the work hooks.
- **Editing the backup's file list, reinstalling the plugin, or releasing a hold, without
  asking**: rule 4.
- **Moving or deleting an event file to make D-events clean**: rule 4; the brief already skips it.
- **"Backed up" said on a hint file alone** while the backup repo is days ahead of its upstream
  or stopped mid-rebase, merge or cherry-pick: D-backup reports each.
- **Stopping after the first fix** without a clean re-run: rule 3.

**Honest limitations:**
- Doctor cannot see whether a hook ran in a past session; it can only dry-run it now.
- Everything is local state: it does not fetch, so a push made elsewhere since the last fetch is
  not seen, and a remote-side failure of the backup is invisible.
- `.state/remote-sync-failed` is an optional convention a backup tool may follow; a tool that
  records failures elsewhere is not read.
- It does not check whether the plugin is enabled in each config dir's settings, only whether
  the installed copy registers the hooks.

## Scale

`solo`. The record and its backup belong to one person's machines; there is no shared or
multi-tenant state to check.

## Sources

`SOURCE: original`. The checks follow this plugin's own work record design
(`prds/work-continuity/prd.md` §9, §9b, §15; ADR-0006) and two Claude Code files as found on
the owner's machines: `<config dir>/plugins/installed_plugins.json` (the `installPath` per
`<plugin>@<marketplace>`, which D-hooks checks) and the cache layout
(`<config dir>/plugins/cache/<marketplace>/<plugin>/<version>/`, its fallback when that file is
missing or unreadable). No published schema for either was found.
