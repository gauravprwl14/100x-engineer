import unittest

from bookings.api import list_bookings
from bookings.http import Request, Unauthorized, User


class ListBookingsTest(unittest.TestCase):
    def test_lists_only_own_tenant(self):
        response = list_bookings(Request(User("u-1", "t-1")))
        self.assertEqual({b["id"] for b in response["body"]}, {1, 2})

    def test_requires_user(self):
        with self.assertRaises(Unauthorized):
            list_bookings(Request(None))


if __name__ == "__main__":
    unittest.main()
