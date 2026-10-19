def subtotal_cents(line_items: list[tuple[int, int]]) -> int:
    """Sum of quantity * unit price, in cents."""
    return sum(quantity * unit_cents for quantity, unit_cents in line_items)
