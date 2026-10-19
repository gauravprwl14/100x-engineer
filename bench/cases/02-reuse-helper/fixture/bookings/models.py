from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Booking:
    booking_id: str
    guest_id: str
    start_date: date
    end_date: date
