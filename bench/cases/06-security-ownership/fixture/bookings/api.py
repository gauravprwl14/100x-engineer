from bookings.http import Request, Unauthorized
from bookings.store import BOOKINGS


def list_bookings(request: Request) -> dict:
    if request.user is None:
        raise Unauthorized("sign in required")
    tenant_bookings = [b for b in BOOKINGS.values() if b["tenant_id"] == request.user.tenant_id]
    return {"status": 200, "body": tenant_bookings}
