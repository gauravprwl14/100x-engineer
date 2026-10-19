from datetime import date

from bookings.models import Booking


def can_cancel(booking: Booking, today: date) -> bool:
    """A booking can be cancelled until the day it starts."""
    return today < booking.start_date
