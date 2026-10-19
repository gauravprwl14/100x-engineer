import unittest
from datetime import date

from bookings.utils.dates import business_days_between


class BusinessDaysTest(unittest.TestCase):
    def test_skips_weekend(self):
        # Friday 2026-01-09 to Tuesday 2026-01-13: Fri and Mon count.
        self.assertEqual(business_days_between(date(2026, 1, 9), date(2026, 1, 13)), 2)


if __name__ == "__main__":
    unittest.main()
