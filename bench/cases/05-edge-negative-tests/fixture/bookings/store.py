import itertools

BOOKINGS: dict[int, dict] = {}
_ids = itertools.count(1)


def next_id() -> int:
    return next(_ids)
