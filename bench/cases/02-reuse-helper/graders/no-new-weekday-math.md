---
type: regex
target: {source: file, path: bookings/cancellation.py}
pattern: "weekday\\(|isoweekday\\(|timedelta\\(days=1\\)"
match: not_contains
---
