def sum_cost(rows):
    acc = 0
    for r in rows:
        acc += r.price * r.qty
    return acc
