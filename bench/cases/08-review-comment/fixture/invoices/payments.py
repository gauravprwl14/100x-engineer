from dataclasses import replace
from datetime import date

from invoices.models import Invoice


class PaymentError(Exception):
    pass


def mark_paid(invoice: Invoice, paid_on: date) -> Invoice:
    if invoice.paid_on is not None:
        raise PaymentError(f"{invoice.invoice_id} is already paid")
    return replace(invoice, paid_on=paid_on)
