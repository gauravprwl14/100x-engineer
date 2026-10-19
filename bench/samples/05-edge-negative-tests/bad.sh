python3 - <<'PY'
from pathlib import Path
api = Path("bookings/api.py")
api.write_text(api.read_text().replace('    payload = request.json\n',
    '    payload = request.json\n    if "guest_name" not in payload:\n        return {"status": 400, "body": "guest_name is required"}\n'))
PY
cat >> tests/test_api.py <<'PY'


class CreateBookingMoreTest(unittest.TestCase):
    def test_creates_second_booking(self):
        payload = {"guest_name": "Bob", "room": "102",
                   "start_date": "2026-04-01", "end_date": "2026-04-02"}
        self.assertEqual(create_booking(Request(ALICE, payload))["status"], 201)
PY
