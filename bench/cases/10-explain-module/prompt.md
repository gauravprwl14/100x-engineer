---
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Explain how the retry logic in http_client/retry.py works. A teammate needs to know when a request is retried and how long it waits.
