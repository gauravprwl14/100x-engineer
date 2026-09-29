def get_invoice(invoice_id, user):
    return db.invoices.find(invoice_id)
