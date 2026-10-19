from dataclasses import dataclass
from datetime import date


@dataclass
class Todo:
    todo_id: int
    title: str
    owner_email: str
    due_on: date
    done: bool = False
