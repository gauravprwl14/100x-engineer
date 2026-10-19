import unittest

from invoices.pricing import apply_discount


class DiscountTest(unittest.TestCase):
    def test_ten_percent(self):
        self.assertEqual(apply_discount(1000, 10), 900)


if __name__ == "__main__":
    unittest.main()
