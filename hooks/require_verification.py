#!/usr/bin/env python3
"""PreToolUse gate: block completion-shaped actions without fresh verification.

This is the layer-3 mechanism the skills ecosystem does not have (see
research/20-findings-ecosystem-skills.md, Verdict). Instructions asking a model to
"verify before claiming done" are prose the model can talk itself past. This is a
gate it cannot: the receipt is bound to a content fingerprint, so editing a file
after verifying invalidates the proof.

Reads hook JSON on stdin, emits a PreToolUse permission decision on stdout.
Fails OPEN on internal error -- a broken gate must not brick the user's shell.
"""
import json, os, re, subprocess, sys, datetime, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    from verify_fingerprint import fingerprint, repo_root
except Exception:
    print(json.dumps({}))
    sys.exit(0)

RECEIPT = ".claude/verification-receipt.json"
POLICY = ".claude/verification-policy.json"

# Actions that assert "this work is done". Order matters: most specific first.
COMPLETION = [
    (re.compile(r"\bgit\s+(-\S+\s+)*commit\b"), "git commit"),
    (re.compile(r"\bgit\s+(-\S+\s+)*push\b"), "git push"),
    (re.compile(r"\bgh\s+pr\s+(create|merge|ready)\b"), "gh pr"),
    (re.compile(r"\bgit\s+(-\S+\s+)*tag\b"), "git tag"),
    (re.compile(r"\bnpm\s+publish\b|\byarn\s+publish\b|\bpnpm\s+publish\b"), "npm publish"),
    (re.compile(r"\btwine\s+upload\b|\buv\s+publish\b"), "python publish"),
]
# Explicit, audited bypass. Better than users disabling the hook wholesale.
# NOTE: `--no-verify` is deliberately NOT a bypass token. That flag tells git to
# skip its own pre-commit hooks, so it is an evasion signal, not permission.
# Precedent: promptfoo wires a PreToolUse hook that denies `git commit --no-verify`
# outright (research/34-findings-agentic-corpus.md).
BYPASS = re.compile(r"\[skip-verify\]|\[no-verify\]")
EVASION = re.compile(r"--no-verify\b|-n\b(?=.*\bcommit\b)")


def allow(extra=None):
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "allow"}}
    if extra:
        out["systemMessage"] = extra
    return out


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason},
            "systemMessage": "Verification gate: blocked."}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return {}
    if payload.get("tool_name") != "Bash":
        return {}
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    action = next((label for rx, label in COMPLETION if rx.search(cmd)), None)
    if not action:
        return {}

    if EVASION.search(cmd) and not BYPASS.search(cmd):
        return deny(
            f"`{action}` blocked: `--no-verify` skips git's own pre-commit hooks.\n\n"
            f"If the pre-commit checks are wrong, fix them. If you genuinely intend to "
            f"bypass verification, say so explicitly with [skip-verify] in the commit "
            f"message -- that is recorded in the transcript, whereas --no-verify is silent.")

    if BYPASS.search(cmd) or os.environ.get("VERIFY_SKIP") == "1":
        return allow(f"Verification gate BYPASSED for `{action}` (explicit override). "
                     "This bypass is visible in the transcript.")

    root = repo_root()
    if not root:
        return {}                                  # not a git repo: nothing to gate

    # OPT-IN PER PROJECT. The plugin installs at user scope, so without this the gate
    # would block commits in every repository the user touches -- intrusive, and it
    # would get the hook disabled wholesale, which is the outcome this design exists
    # to avoid. A project opts in by creating .claude/verification-policy.json.
    policy_path = pathlib.Path(root) / POLICY
    if not policy_path.exists():
        return {}

    required, max_age_min = [], None
    try:
        pol = json.loads(policy_path.read_text())
        required = pol.get("required_checks") or []
        max_age_min = pol.get("max_age_minutes")
    except Exception:
        return deny(f"`{action}` blocked: {POLICY} exists but is not valid JSON. "
                    f"Fix or delete it -- the gate will not guess your policy.")

    rpath = pathlib.Path(root) / RECEIPT
    if not rpath.exists():
        return deny(
            f"`{action}` blocked: no verification receipt at {RECEIPT}.\n\n"
            f"Run the project's checks through the receipt wrapper first, e.g.\n"
            f"    python3 scripts/verified.py --name test -- <your test command>\n\n"
            f"Then retry. To bypass deliberately, append [skip-verify] to the commit "
            f"message or set VERIFY_SKIP=1.")
    try:
        data = json.loads(rpath.read_text())
        checks = data.get("checks") or {}
    except Exception as e:
        return deny(f"`{action}` blocked: {RECEIPT} is unreadable ({e}). "
                    f"Delete it and re-run verification.")
    if not checks:
        return deny(f"`{action}` blocked: {RECEIPT} contains no checks.")

    current = fingerprint()
    stale = [n for n, c in checks.items() if c.get("fingerprint") != current]
    fresh = {n: c for n, c in checks.items() if c.get("fingerprint") == current}

    if not fresh:
        names = ", ".join(sorted(checks))
        return deny(
            f"`{action}` blocked: the code changed after verification.\n\n"
            f"Receipts on record ({names}) were produced against different file "
            f"content than what you are about to commit. A passing test from before "
            f"an edit proves nothing about the edit.\n\n"
            f"Re-run verification, then retry.")

    failed = {n: c for n, c in fresh.items() if c.get("exit_code") != 0}
    if failed:
        lines = [f"  - {n}: `{c.get('command')}` exited {c.get('exit_code')}"
                 for n, c in sorted(failed.items())]
        return deny(f"`{action}` blocked: verification FAILED.\n\n" + "\n".join(lines) +
                    "\n\nFix the failures and re-run verification.")

    missing = [n for n in required if n not in fresh]
    if missing:
        return deny(
            f"`{action}` blocked: required check(s) not run against current code: "
            f"{', '.join(missing)}.\n"
            f"Policy is declared in {POLICY}. Fresh checks on record: "
            f"{', '.join(sorted(fresh)) or 'none'}.")

    if max_age_min:
        now = datetime.datetime.now(datetime.timezone.utc)
        for n, c in fresh.items():
            try:
                at = datetime.datetime.fromisoformat(c["at"])
                if (now - at).total_seconds() / 60 > max_age_min:
                    return deny(f"`{action}` blocked: check `{n}` is older than "
                                f"{max_age_min} min. Re-run verification.")
            except Exception:
                pass

    passed = ", ".join(f"{n}(ok)" for n in sorted(fresh))
    note = f"Verification gate PASSED for `{action}`: {passed}."
    if stale:
        note += f" Ignored {len(stale)} stale receipt(s)."
    return allow(note)


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception as e:
        print(json.dumps({"systemMessage": f"verification hook error (failing open): {e}"}))
    sys.exit(0)
