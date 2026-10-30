"""Bench arm hook: inject the hand-written workstream brief as SessionStart context."""
import json, os

brief = os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "..", "brief.md")
with open(brief, encoding="utf-8") as f:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": f.read()}}))
