cat >> invoices/reports.py <<'PY'


def find_overdue_invoices(invoices: list[Invoice], as_of: date) -> list[Invoice]:
    """Unpaid invoices whose due date is before as_of; due today is not overdue yet."""
    return [invoice for invoice in invoices
            if invoice.paid_on is None and invoice.due_date < as_of]
PY
sed -i.bak '1i\
from datetime import date
' invoices/reports.py && rm invoices/reports.py.bak
cat >> tests/test_reports.py <<'PY'


class FindOverdueInvoicesTest(unittest.TestCase):
    def test_due_today_is_not_overdue(self):
        from invoices.reports import find_overdue_invoices
        due_today = Invoice("inv-3", "cus-1", 100, date(2026, 1, 10))
        self.assertEqual(find_overdue_invoices([due_today], date(2026, 1, 10)), [])
PY
