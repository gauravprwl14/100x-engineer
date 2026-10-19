from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    customer_id: str
    amount_cents: int
    due_date: date
    paid_on: date | None = None
