from invoices.models import Invoice


def total_outstanding_cents(invoices: list[Invoice]) -> int:
    """Sum of unpaid invoice amounts, in cents."""
    return sum(invoice.amount_cents for invoice in invoices if invoice.paid_on is None)
