cat > bookings/cancellation.py <<'PY'
from datetime import date

from bookings.models import Booking
from bookings.utils.dates import business_days_between

FULL_REFUND_DAYS = 5
HALF_REFUND_DAYS = 2


def can_cancel(booking: Booking, today: date) -> bool:
    """A booking can be cancelled until the day it starts."""
    return today < booking.start_date


def refund_percentage(booking: Booking, cancelled_on: date) -> int:
    notice_days = business_days_between(cancelled_on, booking.start_date)
    if notice_days >= FULL_REFUND_DAYS:
        return 100
    if notice_days >= HALF_REFUND_DAYS:
        return 50
    return 0
PY
cat > tests/test_cancellation.py <<'PY'
import unittest
from datetime import date

from bookings.cancellation import refund_percentage
from bookings.models import Booking

BOOKING = Booking("b1", "g1", date(2026, 2, 16), date(2026, 2, 18))


class RefundTest(unittest.TestCase):
    def test_four_business_days_is_half(self):
        self.assertEqual(refund_percentage(BOOKING, date(2026, 2, 10)), 50)
PY
