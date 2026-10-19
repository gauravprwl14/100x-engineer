from datetime import date

from services import config
from todo.models import Todo

_TODOS: list[Todo] = []


def connection_label() -> str:
    return f"{config.DB_HOST}:{config.DB_PORT}"


def save(todo: Todo) -> None:
    _TODOS.append(todo)


def todos_due_on(day: date) -> list[Todo]:
    return [todo for todo in _TODOS if todo.due_on == day and not todo.done]
