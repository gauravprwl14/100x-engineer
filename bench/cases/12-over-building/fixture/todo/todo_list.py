from todo.models import Todo


class TodoList:
    def __init__(self) -> None:
        self._todos: dict[int, Todo] = {}
        self._next_id = 1

    def add(self, title: str) -> Todo:
        todo = Todo(self._next_id, title)
        self._todos[todo.todo_id] = todo
        self._next_id += 1
        return todo

    def remove(self, todo_id: int) -> None:
        if todo_id not in self._todos:
            raise KeyError(todo_id)
        del self._todos[todo_id]

    def open_todos(self) -> list[Todo]:
        return [todo for todo in self._todos.values() if not todo.done]
