cat > tests/test_settings.py <<'PY'
import unittest

from app import store
from app.http import Request
from app.web import handle


class SettingsTest(unittest.TestCase):
    def setUp(self):
        store.reset()

    def test_admin_renames_workspace(self):
        handle(Request(store.USERS["u-1"], "POST", "/workspaces/w-1/settings",
                       {"name": "Acme Studio", "timezone": "Europe/London", "version": "0"}))
        self.assertEqual(store.WORKSPACES["w-1"]["name"], "Acme Studio")

    def test_admin_deletes_workspace(self):
        handle(Request(store.USERS["u-1"], "POST", "/workspaces/w-1/delete", {"confirm_name": "Acme Design"}))
        self.assertNotIn("w-1", store.WORKSPACES)


if __name__ == "__main__":
    unittest.main()
PY
cat > TESTPLAN.md <<'MD'
# Test plan

1. Admin renames the workspace and the new name is shown.
2. Admin changes the timezone.
3. Admin deletes the workspace.
MD
