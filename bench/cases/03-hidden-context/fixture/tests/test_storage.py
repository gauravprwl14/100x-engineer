import unittest
from datetime import date

from services import storage
from todo.models import Todo


class StorageTest(unittest.TestCase):
    def test_due_on_skips_done(self):
        storage.save(Todo(1, "pay rent", "a@example.com", date(2026, 2, 1)))
        storage.save(Todo(2, "file taxes", "a@example.com", date(2026, 2, 1), done=True))
        self.assertEqual([t.todo_id for t in storage.todos_due_on(date(2026, 2, 1))], [1])


if __name__ == "__main__":
    unittest.main()
