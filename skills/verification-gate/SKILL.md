---
name: verification-gate
description: >
  Use when about to claim work is done, commit, push, open a PR, tag a release, or
  publish a package — or when setting up the mechanism that proves a change is
  correct before it ships. Covers binding a check's result to the exact code
  content via a receipt, so "tests pass" is evidence, not an assertion, and cannot
  survive a post-verify edit. Not for choosing which language-specific commands to
  run (see typescript-verification, python-verification, go-verification) — this is
  the wrapper and policy file around whichever commands you already chose. Use
  PROACTIVELY before any completion-shaped action, and whenever asked to configure
  required checks, pre-commit gates, or CI blocking.
---

# Verification gate

A claim that work is done is worth exactly as much as the evidence attached to it.
This skill makes that evidence mechanical.

## Trigger

**Fire when:** about to commit / push / open a PR / tag / publish; about to report a
task complete; asked to set up verification, required checks, or CI gating.

**Do not fire when:** exploring, reading, or answering a question with no code
change. A gate on read-only work is pure friction.

## The problem this solves

Measured across the 1124-repo screen and the skills ecosystem (see Sources): the
open-source world has good *documentation* of verification discipline and good
*CI* for catalog quality, but at the moment an agent is tempted to claim "done"
without proof, the only thing standing there is prose. Prose loses.

The specific failure this catches: **run tests → edit a file → commit.** The tests
passed, the statement "tests pass" is technically true, and the committed code was
never tested. Nothing in a normal setup notices.

## Rules

1. Never state that work is complete without naming the command you ran and its
   exit code. "Should work", "looks correct", "tests should pass" are not results.
   *Enforced by:* the plugin's `PreToolUse` hook (denies commit, push, PR, tag and
   publish without a fresh receipt) and its `Stop` hook (blocks ending a turn on
   unverified changes, once)

2. Run checks through the receipt wrapper so the result is bound to file content,
   not to time, and signed. A receipt is invalidated by any content change, staged
   or unstaged, tracked or a new untracked file. Staging and committing do not
   invalidate it, because they move no content, so commit-then-push needs no rerun.
   *Enforced by:* `100x verified --name <label> -- <command>`

3. Never write or edit `.claude/verification-receipt.json` by hand. Entries are
   HMAC-SHA256 signed with `~/.config/100x/receipt.key`; a hand-written, edited or
   foreign-key entry is denied as forged.
   *Enforced by:* signature check in the `PreToolUse` hook

4. Bind every required label to its exact command in
   `.claude/verification-policy.json`, so `--name test -- true` cannot stand in for
   the real suite: `100x verified` refuses it, and the hook denies a receipt whose
   command differs. The old list form still works but checks labels only, and warns.
   If the list departs from the language skill's baseline, record why:
   `100x decide new "Required checks for <repo>" --affects ".claude/**"`.
   *Enforced by:* `100x verified --name <label>` (runs the bound command)

5. A check that cannot fail is not a check. Before trusting a suite, confirm it
   fails when the code is wrong — break something on purpose once and watch it go
   red.
   *Enforced by:* review

6. Bypass explicitly and visibly, never silently. `[skip-verify]` in the message
   asks a human to approve (permission decision `ask`); the agent cannot approve it.
   `--no-verify`, `-n` and `-c core.hooksPath=...` on a commit are denied, because
   they skip git's own hooks without a trace. `VERIFY_SKIP=1` in the environment
   Claude Code starts from is the human-only off switch.
   *Enforced by:* `bash tests/test_verification_gate.sh`

7. Prefer diff-scoped checks over whole-repo checks on an existing codebase. A gate
   that takes 40 minutes gets turned off, and a turned-off gate is worse than none.
   *Enforced by:* convention

## Modes

| policy file | commit / push / PR / publish | Stop |
|---|---|---|
| none | allowed, with a "not configured" warning saying how to enable | never blocks |
| `{"mode": "off"}` | silent | never blocks |
| present (`mode` defaults to `block`) | denied unless a fresh, signed, policy-matching receipt exists | blocks once if uncommitted changes are unverified |
| unparseable or unknown `mode` | denied: the gate will not guess | never blocks |

The committed copy of the policy is enforced whenever the worktree copy differs, so
weakening it (`"off"`, fewer checks, deleting it) only takes effect after a commit
that passed the old policy.

**Fails open, needs `python3`.** Every hook exits 0 with no decision on an internal
error, and a missing `python3` makes the hook command fail, which Claude Code treats
as a non-blocking error. Either way the gate goes quiet rather than stranding the
shell, so a quiet gate is not proof that a commit was verified: check the receipt.

## Verify

```bash
# 1. one-time: turn the gate on and bind each label to its exact command
mkdir -p .claude && cat > .claude/verification-policy.json <<'JSON'
{ "required_checks": { "test": "npm test", "typecheck": "npx tsc --noEmit" },
  "max_age_minutes": 120 }
JSON
echo ".claude/verification-receipt.json" >> .gitignore

# 2. every change: run the bound commands through the wrapper (exits non-zero on failure)
100x verified --name typecheck
100x verified --name test

# 3. confirm what was proven matches the current content
100x verify_fingerprint                                 # current content hash
cat .claude/verification-receipt.json                   # fingerprint, command, exit code

# 4. prove the gate itself still works (~10s)
bash tests/test_verification_gate.sh && bash tests/test_hooks_stop_session.sh
```

Runtime: steps 2-3 cost whatever your checks cost, plus <1s. Step 4 is ~10s.

## Failure modes

This skill rejects:

- **"I ran the tests and they pass"** with no receipt → denied, no evidence.
- **Verify, then edit, then commit** → denied as stale. This is the central case
  and the one no prose instruction reliably prevents.
- **Edit, then say "done"** without trying to commit → the `Stop` hook blocks once
  and names the commands to run.
- **A hand-written or edited receipt** → denied; the signature does not verify.
- **`100x verified --name test -- true`** when policy binds `test` to the real suite
  → refused at record time, and denied at the gate if it got in another way.
- **A required check that never ran** → denied, naming the missing label.
- **An untracked file created after verifying** (a stray `NOTES.md`) → denied.
- **`git -C ../repo commit`, `cd repo && git commit`, `git -c k=v commit`, an alias
  for `commit -n`** → parsed as the commit it is, against the repository it targets.
- **A green suite that cannot fail** — rule 5. The gate cannot catch this; it
  confirms a command exited 0, not that the command was meaningful.

Known gaps, stated plainly: the gate proves *a command exited zero against this
exact content*, not that the command was worth running (pair it with `minimal-diff`).
The signing key is readable by anything running as you, so an agent that sets out to
read it can still forge; the signature stops the easy shortcut, an OS-level deny rule
on the key path stops the deliberate one. Commands hidden behind `eval` or a script
file are not parsed. See `docs/SAFETY.md`.

## Next

Pick the commands to run *before* this gate: `typescript-verification`,
`python-verification`, or `go-verification` for the language's real baseline.
Wrap them with `100x verified` here, then hand off to `review-gates` for how the
result gets merged. A diagram is ceremony for this skill — there is no flow to
orient on, only a pass/fail receipt — so none is included.

## Scale

`solo` and up. Unusually, this pays off **most** for a solo developer working with
an agent, because there is no reviewer to catch an unverified claim. Team and org
value is additive (CI already catches some of this), so the marginal gain is
largest at the smallest scale — the inverse of most process.

## Sources

- Gap analysis establishing that no surveyed repo wires a blocking verification
  hook: `research/20-findings-ecosystem-skills.md` (Verdict section), covering
  `anthropics/skills@3337550`, `obra/superpowers@8ca22db`,
  `wshobson/agents@9b15b34`, `trailofbits/skills@0cc1c73`, `microsoft/skills@23d0dac`,
  `disler/claude-code-hooks-mastery@052ad1c`.
- Prose-level precedent adapted here: `obra/superpowers@8ca22db:skills/verification-before-completion/SKILL.md`
  (MIT) — the Iron-Law framing. This skill's contribution is moving it from
  instruction to enforcement.
- Human-attestation canary, an independent route to the same goal:
  `zed-industries/zed:.rules` line 16 — a README marker only a human may remove.
  See `research/21-findings-agent-instruction-corpus.md`.
- Hook decision semantics (`deny`/`ask`, `allow` skipping ask rules, Stop's
  `stop_hook_active`, SessionStart `additionalContext`, per-subcommand `if` matching):
  https://code.claude.com/docs/en/hooks.md
- Content-fingerprint design, signed receipts, policy command binding, bypass
  semantics, and the regression suites: `SOURCE: original`.
