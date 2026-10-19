from dataclasses import dataclass


@dataclass
class Todo:
    todo_id: int
    title: str
    done: bool = False
