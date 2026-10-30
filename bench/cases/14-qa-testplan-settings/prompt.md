---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
SPEC.md describes the workspace settings page and app/settings.py implements it. Write a test plan for it to TESTPLAN.md, then implement the automated tests in tests/. Do not change the application code.
