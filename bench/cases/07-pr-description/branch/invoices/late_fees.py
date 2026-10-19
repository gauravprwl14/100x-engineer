from datetime import date

from invoices.models import Invoice

LATE_FEE_RATE = 0.02
GRACE_DAYS = 7
MAX_LATE_FEE_CENTS = 5000


def late_fee_cents(invoice: Invoice, today: date) -> int:
    """2% of the amount once an unpaid invoice is more than 7 days late, capped at 50.00."""
    if invoice.paid_on is not None:
        return 0
    days_late = (today - invoice.due_date).days
    if days_late <= GRACE_DAYS:
        return 0
    return min(round(invoice.amount_cents * LATE_FEE_RATE), MAX_LATE_FEE_CENTS)
