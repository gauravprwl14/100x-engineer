from datetime import date, timedelta

SATURDAY = 5


def business_days_between(start: date, end: date) -> int:
    """Count Monday-to-Friday days in [start, end). Zero when end is not after start."""
    days = 0
    current = start
    while current < end:
        if current.weekday() < SATURDAY:
            days += 1
        current += timedelta(days=1)
    return days


def nights_between(check_in: date, check_out: date) -> int:
    return max((check_out - check_in).days, 0)
