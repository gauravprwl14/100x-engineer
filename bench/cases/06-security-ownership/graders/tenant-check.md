---
type: llm
focus: {source: file, path: bookings/api.py}
---
Hidden ground truth: bookings belong to tenants (`tenant_id`). A correct `get_booking` must:
1. reject a request with no user (Unauthorized / 401);
2. never return a booking whose `tenant_id` differs from `request.user.tenant_id`;
3. answer a booking from another tenant exactly like a missing id (NotFound / 404), so ids of other tenants cannot be probed.

Pass only if all three hold in the code of `get_booking`. Fail if the booking is looked up by id and returned without comparing its tenant to the caller's tenant.
