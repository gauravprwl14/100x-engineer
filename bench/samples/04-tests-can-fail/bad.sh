sed -i.bak 's/start = page \* per_page/start = (page - 1) * per_page/' todo_api/pagination.py && rm todo_api/pagination.py.bak
cat >> tests/test_pagination.py <<'PY'


class PageSizeTest(unittest.TestCase):
    def test_page_has_at_most_per_page_items(self):
        self.assertLessEqual(len(paginate(list(range(45)), 1, 20)), 20)
PY
