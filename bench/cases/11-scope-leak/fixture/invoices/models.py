from dataclasses import dataclass, field


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    customer: str
    amount_cents: int
    tags: tuple[str, ...] = field(default=())
