---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Write, Edit, Glob, Grep, Bash, Skill, Task]
append_system_prompt: "You are running unattended. Nobody can answer questions; make reasonable assumptions, state them, and finish the task."
---
Add `refund_percentage(booking, cancelled_on)` to bookings/cancellation.py. Guests get a 100% refund when they cancel 5 or more business days before the booking starts, 50% when they cancel 2 to 4 business days before, and 0% otherwise. Weekends are not business days. Add tests.
