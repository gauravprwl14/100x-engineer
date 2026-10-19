cat >> bookings/api.py <<'PY'


def get_booking(request: Request, booking_id: int) -> dict:
    if request.user is None:
        raise Unauthorized("sign in required")
    booking = BOOKINGS.get(booking_id)
    # Another tenant's booking answers exactly like a missing one, so ids cannot be probed.
    if booking is None or booking["tenant_id"] != request.user.tenant_id:
        raise NotFound(f"booking {booking_id} not found")
    return {"status": 200, "body": booking}
PY
sed -i.bak 's/from bookings.http import Request, Unauthorized/from bookings.http import NotFound, Request, Unauthorized/' bookings/api.py && rm bookings/api.py.bak
cat >> tests/test_api.py <<'PY'


class GetBookingTest(unittest.TestCase):
    def test_other_tenant_is_not_found(self):
        from bookings.api import get_booking
        from bookings.http import NotFound
        with self.assertRaises(NotFound):
            get_booking(Request(User("u-1", "t-1")), 3)
PY
