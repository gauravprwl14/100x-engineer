def total_price(items):
    s = 0
    for i in items:
        s += i.price * i.qty
    return s
