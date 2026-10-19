## Summary

This PR successfully fixes the reminder bug as requested. I have refactored the scheduler and verified everything works.

## Background and history

Reminders were added in 2020. In 2022 the scheduler moved to a cron worker. In 2023 time zones were added to profiles but the scheduler still read the server time zone, which nobody noticed until a customer in a different region reported reminders arriving an hour early after the clock change, and then we looked into it.

## Changes

- Replaced `server_tz()` with `user.tz` in `schedule.py`, moved the helper into `time_utils.py`, renamed three variables, and updated the docstring for clarity across the module.

## Testing

- [x] Unit tests pass
- [x] Manually tested

## Notes

In conclusion, it's worth noting that the fix is small.
