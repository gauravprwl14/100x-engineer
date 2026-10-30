"""In-memory data for the workspace app. Tests call reset() to start from the seed data."""
import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    user_id: str
    name: str
    workspace_id: str
    role: str  # "admin" or "member"


USERS = {
    "u-1": User("u-1", "Ada Lovelace", "w-1", "admin"),
    "u-2": User("u-2", "Grace Hopper", "w-1", "member"),
    "u-3": User("u-3", "Linus Torvalds", "w-2", "admin"),
}

_SEED = {
    "w-1": {"id": "w-1", "name": "Acme Design", "timezone": "Europe/London"},
    "w-2": {"id": "w-2", "name": "Globex", "timezone": "America/New_York"},
}
WORKSPACES: dict[str, dict] = copy.deepcopy(_SEED)


def reset() -> None:
    WORKSPACES.clear()
    WORKSPACES.update(copy.deepcopy(_SEED))
