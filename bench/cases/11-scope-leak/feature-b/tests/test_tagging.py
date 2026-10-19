import unittest

from invoices.models import Invoice
from invoices.tagging import add_tag


class TaggingTest(unittest.TestCase):
    def test_adds_tag_once(self):
        tagged = add_tag(add_tag(Invoice("i1", "acme", 100), "vip"), "vip")
        self.assertEqual(tagged.tags, ("vip",))


if __name__ == "__main__":
    unittest.main()
