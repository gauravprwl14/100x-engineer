---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Review the changes on branch feature/refunds against main, as a reviewer would on the pull request. Write your review comments to REVIEW.md, one comment per finding, each naming the file and line. Do not change the code.
