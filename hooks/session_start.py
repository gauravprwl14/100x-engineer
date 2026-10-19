#!/usr/bin/env python3
"""SessionStart: a few lines of standing context.

When many skills are installed the skill menu is truncated, and this plugin's router
can fall out of view. Injecting the entry points at session start keeps them
reachable. Kept to a handful of lines because this text is paid for in every session.
Fails open: any error yields no context rather than a broken session start.
"""
import json, os, pathlib, subprocess, sys

POLICY = ".claude/verification-policy.json"
NO_POLICY = "100x: no verification policy here — commit/PR checks only warn."


def _has_policy(cwd):
    """True when the session's repository has a policy, or when there is no repository
    to speak of (a line about one would be noise)."""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return True
    if top.returncode != 0:
        return True
    return (pathlib.Path(top.stdout.strip()) / POLICY).is_file()


def main(payload=None):
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or \
        str(pathlib.Path(__file__).resolve().parent.parent)
    lines = [
        "The 100x-engineer plugin is installed.",
        "Start any engineering task with the `/100x:100x` router skill; it "
        "picks the skills the task needs.",
        "Plugin tools run as `100x <tool>`; `100x list` shows them.",
        f"Agent protocol and report contract: {root}/docs/OPERATING-MODEL.md",
        "Commit, push, PR and publish commands need a fresh signed receipt from "
        "`100x verified` in repositories that configure .claude/verification-policy.json.",
        "Generated docs: summary first, Contents table on long files, INDEX.md for "
        "multi-file output — see OPERATING-MODEL §9.",
    ]
    cwd = (payload or {}).get("cwd") if isinstance(payload, dict) else None
    if isinstance(cwd, str) and os.path.isdir(cwd) and not _has_policy(cwd):
        lines.append(NO_POLICY)
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": "\n".join(lines)}}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        print(json.dumps(main(payload)))
    except Exception:  # fail-open: an error yields no context, never a broken session start
        print(json.dumps({}))
    sys.exit(0)
