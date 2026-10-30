import unittest

from app import store
from app.http import Request
from app.web import handle


class MembersPageTest(unittest.TestCase):
    def setUp(self):
        store.reset()

    def test_lists_the_workspace_members(self):
        response = handle(Request(store.USERS["u-2"], "GET", "/workspaces/w-1/members"))
        self.assertEqual(response.status, 200)
        self.assertIn("Grace Hopper", response.body)

    def test_outsider_gets_not_found(self):
        response = handle(Request(store.USERS["u-3"], "GET", "/workspaces/w-1/members"))
        self.assertEqual(response.status, 404)

    def test_signed_out_user_is_refused(self):
        response = handle(Request(None, "GET", "/workspaces/w-1/members"))
        self.assertEqual(response.status, 401)


if __name__ == "__main__":
    unittest.main()
