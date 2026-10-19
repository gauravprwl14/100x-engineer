import unittest
from datetime import date

from invoices.late_fees import late_fee_cents
from invoices.models import Invoice

DUE = date(2026, 1, 10)


class LateFeeTest(unittest.TestCase):
    def test_no_fee_inside_grace_period(self):
        self.assertEqual(late_fee_cents(Invoice("i1", "c1", 10000, DUE), date(2026, 1, 17)), 0)

    def test_two_percent_after_grace_period(self):
        self.assertEqual(late_fee_cents(Invoice("i1", "c1", 10000, DUE), date(2026, 1, 18)), 200)

    def test_fee_is_capped(self):
        self.assertEqual(late_fee_cents(Invoice("i1", "c1", 900000, DUE), date(2026, 2, 1)), 5000)

    def test_paid_invoice_has_no_fee(self):
        paid = Invoice("i1", "c1", 10000, DUE, paid_on=date(2026, 1, 20))
        self.assertEqual(late_fee_cents(paid, date(2026, 2, 1)), 0)


if __name__ == "__main__":
    unittest.main()
