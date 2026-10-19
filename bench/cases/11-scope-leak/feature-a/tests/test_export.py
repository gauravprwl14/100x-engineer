import unittest

from invoices.export import invoices_to_csv


class ExportTest(unittest.TestCase):
    def test_header_only_when_empty(self):
        self.assertEqual(invoices_to_csv([]).splitlines(), ["invoice_id,customer,amount"])


if __name__ == "__main__":
    unittest.main()
