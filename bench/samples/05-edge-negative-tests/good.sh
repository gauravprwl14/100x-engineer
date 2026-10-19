cat > bookings/api.py <<'PY'
from datetime import date

from bookings.http import BadRequest, Request, Unauthorized
from bookings.store import BOOKINGS, next_id

ROOMS = {"101", "102", "201", "202"}
MAX_GUEST_NAME_LENGTH = 100


def _parse_date(payload: dict, field: str) -> date:
    try:
        return date.fromisoformat(str(payload.get(field, "")))
    except ValueError:
        raise BadRequest(f"{field} must be an ISO date") from None


def _validate(payload: dict) -> None:
    guest_name = str(payload.get("guest_name", "")).strip()
    if not guest_name:
        raise BadRequest("guest_name is required")
    if len(guest_name) > MAX_GUEST_NAME_LENGTH:
        raise BadRequest("guest_name is too long")
    if payload.get("room") not in ROOMS:
        raise BadRequest("unknown room")
    if _parse_date(payload, "end_date") <= _parse_date(payload, "start_date"):
        raise BadRequest("end_date must be after start_date")


def create_booking(request: Request) -> dict:
    if request.user is None:
        raise Unauthorized("sign in required")
    payload = request.json
    _validate(payload)
    booking = {
        "id": next_id(),
        "tenant_id": request.user.tenant_id,
        "guest_name": payload["guest_name"],
        "room": payload["room"],
        "start_date": payload["start_date"],
        "end_date": payload["end_date"],
    }
    BOOKINGS[booking["id"]] = booking
    return {"status": 201, "body": booking}
PY
cat >> tests/test_api.py <<'PY'


GOOD = {"guest_name": "Ada", "room": "101", "start_date": "2026-03-01", "end_date": "2026-03-03"}


class CreateBookingRejectsTest(unittest.TestCase):
    def test_empty_guest_name(self):
        from bookings.http import BadRequest
        with self.assertRaises(BadRequest):
            create_booking(Request(ALICE, dict(GOOD, guest_name="")))

    def test_guest_name_too_long(self):
        from bookings.http import BadRequest
        with self.assertRaises(BadRequest):
            create_booking(Request(ALICE, dict(GOOD, guest_name="x" * 101)))

    def test_end_before_start(self):
        from bookings.http import BadRequest
        with self.assertRaises(BadRequest):
            create_booking(Request(ALICE, dict(GOOD, end_date="2026-02-27")))

    def test_unauthenticated(self):
        from bookings.http import Unauthorized
        with self.assertRaises(Unauthorized):
            create_booking(Request(None, dict(GOOD)))
PY
