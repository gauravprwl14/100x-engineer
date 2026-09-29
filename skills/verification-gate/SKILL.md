---
name: verification-gate
description: >
  Use when about to claim work is done, commit, push, open a PR, tag a release, or
  publish a package — or when setting up how a project proves a change is correct.
  Covers running the project's real checks, binding the result to the exact code
  being shipped, and the receipt mechanism that makes "tests pass" auditable
  instead of asserted. Use PROACTIVELY before any completion-shaped action, and
  whenever asked to configure required checks, pre-commit gates, or CI blocking.
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
   *Enforced by:* `python3 hooks/require_verification.py` (blocks the commit)

2. Run checks through the receipt wrapper so the result is bound to file content,
   not to time. A receipt is invalidated by any edit, staged or unstaged, tracked
   or untracked.
   *Enforced by:* `python3 scripts/verified.py --name <label> -- <command>`

3. Verify the code you are about to ship, not the code you had. If you edit after
   verifying, re-verify. There is no partial credit.
   *Enforced by:* fingerprint comparison in `hooks/verify_fingerprint.py`

4. Declare which checks are mandatory for the repo, so "I ran something" cannot
   substitute for "I ran what matters". This file is also the opt-in switch: without
   it the gate is inactive, which is why installing the plugin does not disrupt
   unrelated repositories.
   *Enforced by:* `.claude/verification-policy.json` `required_checks`

5. A check that cannot fail is not a check. Before trusting a suite, confirm it
   fails when the code is wrong — break something on purpose once and watch it go
   red.
   *Enforced by:* review

6. Bypass explicitly and visibly, never silently. `[skip-verify]` in the commit
   message or `VERIFY_SKIP=1` is acceptable when you mean it; disabling the hook
   is not.
   *Enforced by:* `hooks/require_verification.py` logs every bypass to the transcript

7. Prefer diff-scoped checks over whole-repo checks on an existing codebase. A gate
   that takes 40 minutes gets turned off, and a turned-off gate is worse than none.
   *Enforced by:* convention

## Verify

The gate is **opt-in per project**: with no `.claude/verification-policy.json` the
hook passes everything through. Creating that file is what turns it on.

```bash
# 1. one-time: opt this repo in and declare what it requires
cat > .claude/verification-policy.json <<'JSON'
{ "required_checks": ["test", "typecheck", "lint"], "max_age_minutes": 120 }
JSON
echo ".claude/verification-receipt.json" >> .gitignore

# 2. every change: run the real checks through the wrapper (exit non-zero on failure)
python3 scripts/verified.py --name lint      -- <your lint command>
python3 scripts/verified.py --name typecheck -- <your typecheck command>
python3 scripts/verified.py --name test      -- <your test command>

# 3. confirm the gate agrees before you claim anything
python3 hooks/verify_fingerprint.py                     # current content hash
cat .claude/verification-receipt.json                   # what was actually proven

# 4. prove the gate itself still works (25 assertions, ~5s)
bash tests/test_verification_gate.sh
```

Runtime: steps 2-3 cost whatever your checks cost, plus <1s. Step 4 is ~5s.

## Failure modes

This skill rejects:

- **"I ran the tests and they pass"** with no receipt → blocked, no evidence.
- **Verify, then edit, then commit** → blocked as stale. This is the central case
  and the one no prose instruction reliably prevents.
- **A passing suite where the required check never ran** — e.g. `test` passed but
  policy also demands `typecheck` → blocked, names the missing check.
- **An agent creating an untracked file after verifying** (a stray `NOTES.md`, a
  scratch script) → blocked; the new file is part of what would be committed.
- **Staged-only changes** — `git add` after verifying → blocked.
- **A green suite that cannot fail** — rule 5. The gate cannot catch this; it
  confirms a command exited 0, not that the command was meaningful. Mutation
  testing or a deliberate break is the only real answer.

Known gap, stated plainly: the gate proves *a command exited zero against this
exact content*. It does not prove the command was worth running. Pair it with
`test-that-can-fail` for that half of the problem.

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
- Content-fingerprint design, bypass semantics, and the 19-assertion regression
  suite: `SOURCE: original`.
