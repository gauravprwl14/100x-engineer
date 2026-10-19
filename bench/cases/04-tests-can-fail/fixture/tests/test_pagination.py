import unittest

from todo_api.pagination import page_count, paginate


class PaginationTest(unittest.TestCase):
    def test_rejects_page_zero(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 0)

    def test_page_count_rounds_up(self):
        self.assertEqual(page_count(41, 20), 3)


if __name__ == "__main__":
    unittest.main()
