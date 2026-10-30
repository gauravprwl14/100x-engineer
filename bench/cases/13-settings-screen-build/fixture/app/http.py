from dataclasses import dataclass, field

from app.store import User


@dataclass
class Request:
    user: User | None
    method: str = "GET"
    path: str = "/"
    form: dict = field(default_factory=dict)


@dataclass
class Response:
    status: int
    body: str = ""
    headers: dict = field(default_factory=dict)


def redirect(location: str) -> Response:
    return Response(303, "", {"Location": location})


class HttpError(Exception):
    status = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequest(HttpError):
    status = 400


class Unauthorized(HttpError):
    status = 401


class Forbidden(HttpError):
    status = 403


class NotFound(HttpError):
    status = 404
