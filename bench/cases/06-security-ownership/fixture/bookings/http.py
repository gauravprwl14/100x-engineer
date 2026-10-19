from dataclasses import dataclass, field


@dataclass(frozen=True)
class User:
    user_id: str
    tenant_id: str


@dataclass
class Request:
    user: User | None
    json: dict = field(default_factory=dict)


class HttpError(Exception):
    status = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequest(HttpError):
    status = 400


class Unauthorized(HttpError):
    status = 401


class NotFound(HttpError):
    status = 404
