from bookings.http import Request
from bookings.store import BOOKINGS, next_id

ROOMS = {"101", "102", "201", "202"}


def create_booking(request: Request) -> dict:
    payload = request.json
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
