cat >> bookings/cancellation.py <<'PY'


def refund_percentage(booking, cancelled_on):
    from datetime import timedelta
    days, current = 0, cancelled_on
    while current < booking.start_date:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return 100 if days >= 5 else 50 if days >= 2 else 0
PY
