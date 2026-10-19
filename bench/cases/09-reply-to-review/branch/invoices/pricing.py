def subtotal_cents(line_items: list[tuple[int, int]]) -> int:
    """Sum of quantity * unit price, in cents."""
    return sum(quantity * unit_cents for quantity, unit_cents in line_items)


def apply_discount(total_cents: int, percent: int) -> int:
    """Total after a percentage discount, rounded down to the cent."""
    return total_cents * (100 - percent) // 100
