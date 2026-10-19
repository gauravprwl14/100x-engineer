from invoices.models import Invoice


def with_tag(invoices: list[Invoice], tag: str) -> list[Invoice]:
    return [invoice for invoice in invoices if tag in invoice.tags]
