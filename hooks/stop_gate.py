#!/usr/bin/env python3
"""Stop gate: do not end a turn on unverified changes.

The PreToolUse gate only fires when the agent tries to ship. An agent that edits and
then simply reports "done" never tries, so the receipt is never asked for. This hook
closes that path: when a repository in block mode has uncommitted changes and no
signed receipt for the current content, the stop is blocked once with instructions.

It never loops: when Claude Code reports stop_hook_active (this hook already blocked
and the agent is stopping again), it lets the stop through. It fails open on any
internal error, because a Stop hook that crashes would wedge every session.
"""
import json, os, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def main():
    from verify_fingerprint import EXCLUDE, _git, repo_root, snapshot
    from receipts import GateError, evaluate, load_key, load_policy, rerun_hint

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return {}
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return {}
    cwd = payload.get("cwd")
    if not (isinstance(cwd, str) and os.path.isdir(cwd)):
        cwd = os.getcwd()
    root = repo_root(cwd)
    if not root:
        return {}
    try:
        policy = load_policy(root)
    except GateError:
        return {}                # the PreToolUse gate reports a broken policy loudly
    if policy is None or policy["mode"] != "block":
        return {}

    status = _git(["status", "--porcelain", "-z", "--untracked-files=all"], root) or ""
    changed = [rec[3:] for rec in status.split("\0") if len(rec) > 3]
    if not [p for p in changed if p not in EXCLUDE]:
        return {}                # nothing uncommitted: nothing left unverified

    snap = snapshot(root)
    if not snap:
        return {}
    try:
        key = load_key()
        result = evaluate(root, policy, snap["fingerprint"], key)
    except GateError:
        result = {"fresh": {}, "missing": sorted(policy["required"])}
    required = sorted(policy["required"])
    stale = (not result["fresh"]) or any(l not in result["fresh"] for l in required)
    if not stale:
        return {}
    return {"decision": "block",
            "reason": "Files changed since the last verification, so the work is not "
                      "proven. Run the required checks against the current content:\n"
                      f"{rerun_hint(policy)}\n"
                      "If they cannot be run, tell the user what was not verified and "
                      "why instead of reporting the work as done."}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception:  # fail-open: a Stop hook that crashes would wedge every session
        print(json.dumps({}))
    sys.exit(0)
