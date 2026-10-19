python3 - <<'PY'
from pathlib import Path
p = Path("todo/todo_list.py")
p.write_text(p.read_text().replace("    def open_todos", '''    def mark_done(self, todo_id: int) -> None:
        self._todos[todo_id].done = True

    def open_todos'''))
PY
cat >> tests/test_todo_list.py <<'PY'


class MarkDoneTest(unittest.TestCase):
    def test_done_todo_leaves_open_list(self):
        todos = TodoList()
        todo = todos.add("buy milk")
        todos.mark_done(todo.todo_id)
        self.assertEqual(todos.open_todos(), [])
PY
