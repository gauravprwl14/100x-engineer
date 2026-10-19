from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    amount_cents: int
    paid_on: date | None = None
    refunded_cents: int = 0
