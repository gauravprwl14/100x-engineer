import csv
import io

from invoices.models import Invoice

HEADER = ["invoice_id", "customer", "amount"]


def invoices_to_csv(invoices: list[Invoice]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    rows = [[inv.invoice_id, inv.customer, f"{inv.amount_cents / 100:.2f}"] for inv in invoices]
    for row in rows[:-1]:
        writer.writerow(row)
    return buffer.getvalue()
