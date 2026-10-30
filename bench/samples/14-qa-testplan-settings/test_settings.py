import unittest

from app import store
from app.http import Request
from app.web import handle

ADMIN, MEMBER, OUTSIDER = store.USERS["u-1"], store.USERS["u-2"], store.USERS["u-3"]
SETTINGS = "/workspaces/w-1/settings"
DELETE = "/workspaces/w-1/delete"


def get(user):
    return handle(Request(user, "GET", SETTINGS))


def save(user, **fields):
    form = {"name": "Acme Design", "timezone": "Europe/London", "version": "0", **fields}
    return handle(Request(user, "POST", SETTINGS, form))


class ViewSettingsTest(unittest.TestCase):
    def setUp(self):
        store.reset()

    def test_member_sees_name_and_timezone(self):
        body = get(MEMBER).body
        self.assertIn("Acme Design", body)
        self.assertIn("Europe/London", body)

    def test_member_page_has_no_change_controls(self):
        body = get(MEMBER).body
        self.assertNotIn("<form", body)
        self.assertIn("Only admins can change these settings.", body)

    def test_outsider_gets_not_found(self):
        self.assertEqual(get(OUTSIDER).status, 404)

    def test_admin_page_warns_before_leaving_with_unsaved_edits(self):
        self.assertIn("beforeunload", get(ADMIN).body)


class SaveSettingsTest(unittest.TestCase):
    def setUp(self):
        store.reset()

    def test_admin_renames_and_changes_timezone(self):
        save(ADMIN, name="Acme Studio", timezone="Europe/Berlin")
        self.assertEqual((store.WORKSPACES["w-1"]["name"], store.WORKSPACES["w-1"]["timezone"]),
                         ("Acme Studio", "Europe/Berlin"))

    def test_member_rename_is_refused_and_changes_nothing(self):
        response = save(MEMBER, name="Hijacked")
        self.assertEqual((response.status, store.WORKSPACES["w-1"]["name"]), (403, "Acme Design"))

    def test_unknown_timezone_is_refused_and_keeps_the_edit_on_screen(self):
        response = save(ADMIN, name="Acme Studio", timezone="Mars/Olympus")
        self.assertEqual((response.status, store.WORKSPACES["w-1"]["timezone"]), (400, "Europe/London"))
        self.assertIn("Acme Studio", response.body)

    def test_name_boundaries(self):
        for name, status in (("", 400), ("x" * 60, 303), ("x" * 61, 400)):
            with self.subTest(length=len(name)):
                store.reset()
                self.assertEqual(save(ADMIN, name=name).status, status)

    def test_stale_version_gets_a_conflict_not_an_overwrite(self):
        save(ADMIN, name="First Admin")
        response = save(ADMIN, name="Second Admin", version="0")
        self.assertEqual((response.status, store.WORKSPACES["w-1"]["name"]), (409, "First Admin"))


class DeleteWorkspaceTest(unittest.TestCase):
    def setUp(self):
        store.reset()

    def delete(self, user, confirm_name):
        return handle(Request(user, "POST", DELETE, {"confirm_name": confirm_name}))

    def test_admin_deletes_after_typing_the_name(self):
        self.delete(ADMIN, "Acme Design")
        self.assertNotIn("w-1", store.WORKSPACES)

    def test_wrong_or_missing_name_keeps_the_workspace(self):
        for typed in ("", "Acme"):
            with self.subTest(typed=typed):
                self.assertEqual(self.delete(ADMIN, typed).status, 400)
                self.assertIn("w-1", store.WORKSPACES)

    def test_member_delete_is_refused_and_keeps_the_workspace(self):
        response = self.delete(MEMBER, "Acme Design")
        self.assertEqual((response.status, "w-1" in store.WORKSPACES), (403, True))


if __name__ == "__main__":
    unittest.main()
