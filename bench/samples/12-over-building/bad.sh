cat > todo/status.py <<'PY'
from enum import Enum


class TodoStatus(Enum):
    OPEN = "open"
    DONE = "done"


class StatusTransitionError(Exception):
    pass


class StatusManager:
    """Manages status transitions for todos."""

    ALLOWED = {TodoStatus.OPEN: {TodoStatus.DONE}, TodoStatus.DONE: {TodoStatus.OPEN}}

    def __init__(self, todo_list):
        self.todo_list = todo_list

    def transition(self, todo_id, status):
        todo = self.todo_list._todos[todo_id]
        current = TodoStatus.DONE if todo.done else TodoStatus.OPEN
        if status not in self.ALLOWED[current]:
            raise StatusTransitionError(f"{current} -> {status}")
        todo.done = status is TodoStatus.DONE
PY
python3 - <<'PY'
from pathlib import Path
p = Path("todo/todo_list.py")
p.write_text(p.read_text().replace("    def open_todos", '''    def mark_done(self, todo_id: int) -> None:
        from todo.status import StatusManager, TodoStatus
        StatusManager(self).transition(todo_id, TodoStatus.DONE)

    def open_todos'''))
PY
cat > CHANGES.md <<'MD'
# Changes
Added a status manager.
MD
