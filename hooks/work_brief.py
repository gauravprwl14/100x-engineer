#!/usr/bin/env python3
"""SessionStart: inject the private work brief when this directory belongs to a workstream.

A session that starts, resumes or is summarised otherwise knows nothing of the PRs,
holds and decisions that other sessions recorded, and the human restates them. The
brief comes from `100x work brief` (scripts/work.py), matched on the session's
`origin` remote and branch, so any worktree of a workstream's repos gets it.

Reads local files and runs `git remote`/`git rev-parse` only; writes nothing, no
network. Prints nothing when no workstream matches, when HUNDREDX_WORK=off, and on
any error, because a SessionStart hook must never break a session.
"""
import json, os, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))


def main(payload):
    import work
    if work.disabled() or not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return None
    matches = work.lookup(cwd)
    if len(matches) != 1:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": work.brief_for(matches[0])}}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw) if raw.strip() else None
        except ValueError:
            payload = None
        out = main(payload)
        if out:
            print(json.dumps(out))
    except Exception:  # fail-open: no brief is better than a broken session start
        pass
    sys.exit(0)
