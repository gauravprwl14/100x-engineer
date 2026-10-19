import unittest
from datetime import date

from invoices.models import Invoice
from invoices.reports import total_outstanding_cents


class TotalOutstandingTest(unittest.TestCase):
    def test_sums_only_unpaid_invoices(self):
        invoices = [
            Invoice("inv-1", "cus-1", 1000, date(2026, 1, 10)),
            Invoice("inv-2", "cus-1", 500, date(2026, 1, 10), paid_on=date(2026, 1, 9)),
        ]
        self.assertEqual(total_outstanding_cents(invoices), 1000)


if __name__ == "__main__":
    unittest.main()
