---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Write the pull request description for the current branch (feature/late-fee, to be merged into main). Save it to PR_BODY.md. Do not open the PR.
