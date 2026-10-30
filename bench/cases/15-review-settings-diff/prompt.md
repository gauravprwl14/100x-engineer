---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Review pull request #57 (PR.md) as a reviewer would. Its changes are in PR.diff, and the files on disk are the PR's head. Write your review comments to REVIEW.md, one comment per finding, each naming the file and line. Do not change the code.
