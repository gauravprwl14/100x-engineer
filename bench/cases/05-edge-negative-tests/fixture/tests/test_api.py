import unittest

from bookings.api import create_booking
from bookings.http import Request, User
from bookings.store import BOOKINGS

ALICE = User("u-1", "t-1")


class CreateBookingTest(unittest.TestCase):
    def test_creates_booking(self):
        payload = {"guest_name": "Ada", "room": "101",
                   "start_date": "2026-03-01", "end_date": "2026-03-03"}
        response = create_booking(Request(ALICE, payload))
        self.assertEqual(response["status"], 201)
        self.assertIn(response["body"]["id"], BOOKINGS)


if __name__ == "__main__":
    unittest.main()
