cat >> bookings/api.py <<'PY'


def get_booking(request: Request, booking_id: int) -> dict:
    if request.user is None:
        raise Unauthorized("sign in required")
    return {"status": 200, "body": BOOKINGS[booking_id]}
PY
