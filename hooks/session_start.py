#!/usr/bin/env python3
"""SessionStart: a few lines of standing context.

When many skills are installed the skill menu is truncated, and this plugin's router
can fall out of view. Injecting the entry points at session start keeps them
reachable. Kept to a handful of lines because this text is paid for in every session.
Fails open: any error yields no context rather than a broken session start.
"""
import json, os, pathlib, sys


def main():
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
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": "\n".join(lines)}}


if __name__ == "__main__":
    try:
        sys.stdin.read()
        print(json.dumps(main()))
    except Exception:  # fail-open: an error yields no context, never a broken session start
        print(json.dumps({}))
    sys.exit(0)
