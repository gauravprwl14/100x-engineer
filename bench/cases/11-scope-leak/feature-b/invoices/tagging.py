from dataclasses import replace

from invoices.models import Invoice


def add_tag(invoice: Invoice, tag: str) -> Invoice:
    if tag in invoice.tags:
        return invoice
    return replace(invoice, tags=invoice.tags + (tag,))
