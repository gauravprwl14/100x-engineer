---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Add an endpoint `get_booking(request, booking_id)` to bookings/api.py that returns a single booking by its id, in the same response shape as the existing endpoint. Add tests.
