import unittest
from datetime import date

from invoices.models import Invoice
from invoices.payments import PaymentError, refund

PAID = Invoice("i1", 10000, paid_on=date(2026, 1, 5))


class RefundTest(unittest.TestCase):
    def test_partial_refund(self):
        self.assertEqual(refund(PAID, 2500).refunded_cents, 2500)

    def test_unpaid_invoice_cannot_be_refunded(self):
        with self.assertRaises(PaymentError):
            refund(Invoice("i2", 10000), 100)


if __name__ == "__main__":
    unittest.main()
