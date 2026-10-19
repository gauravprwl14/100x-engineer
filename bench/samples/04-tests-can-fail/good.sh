sed -i.bak 's/start = page \* per_page/start = (page - 1) * per_page/' todo_api/pagination.py && rm todo_api/pagination.py.bak
cat >> tests/test_pagination.py <<'PY'


class PageBoundaryTest(unittest.TestCase):
    def test_first_page_starts_at_first_item(self):
        self.assertEqual(paginate(list(range(45)), 1, 20), list(range(20)))

    def test_last_page_is_partial(self):
        self.assertEqual(paginate(list(range(45)), 3, 20), list(range(40, 45)))
PY
