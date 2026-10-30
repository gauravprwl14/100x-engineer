---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Add a settings page for a workspace at /workspaces/<id>/settings. Everyone in the workspace can view the settings; admins can also rename the workspace, change its default timezone and delete the workspace. Add tests.
