---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Add input validation to the create booking endpoint in bookings/api.py, with tests.
