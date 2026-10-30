import unittest

from app import store
from app.http import Request
from app.web import handle

ADMIN, MEMBER = store.USERS["u-1"], store.USERS["u-2"]


class SettingsTest(unittest.TestCase):
    def setUp(self):
        store.reset()

    def test_member_can_view_settings(self):
        response = handle(Request(MEMBER, "GET", "/workspaces/w-1/settings"))
        self.assertEqual(response.status, 200)
        self.assertIn("Europe/London", response.body)

    def test_admin_renames_workspace(self):
        handle(Request(ADMIN, "POST", "/workspaces/w-1/settings/name", {"name": "Acme Studio"}))
        self.assertEqual(store.WORKSPACES["w-1"]["name"], "Acme Studio")

    def test_admin_changes_timezone(self):
        handle(Request(ADMIN, "POST", "/workspaces/w-1/settings/timezone", {"timezone": "Europe/Berlin"}))
        self.assertEqual(store.WORKSPACES["w-1"]["timezone"], "Europe/Berlin")

    def test_member_cannot_change_timezone(self):
        response = handle(Request(MEMBER, "POST", "/workspaces/w-1/settings/timezone", {"timezone": "Europe/Berlin"}))
        self.assertEqual(response.status, 403)

    def test_admin_deletes_workspace(self):
        handle(Request(ADMIN, "POST", "/workspaces/w-1/delete"))
        self.assertNotIn("w-1", store.WORKSPACES)


if __name__ == "__main__":
    unittest.main()
