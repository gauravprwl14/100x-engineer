"""Development server: python -m app.wsgi, then open http://localhost:8000/workspaces/w-1/members.

The signed-in user comes from the `user_id` cookie (u-1 admin, u-2 member of w-1).
"""
from http.cookies import SimpleCookie
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from app import store
from app.http import Request
from app.web import handle

REASONS = {200: "OK", 303: "See Other", 400: "Bad Request", 401: "Unauthorized",
           403: "Forbidden", 404: "Not Found", 409: "Conflict"}


def application(environ, start_response):
    cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    user = store.USERS.get(cookie["user_id"].value) if "user_id" in cookie else None
    form = {}
    if environ["REQUEST_METHOD"] == "POST":
        size = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ["wsgi.input"].read(size).decode()
        form = {key: values[0] for key, values in parse_qs(raw).items()}
    response = handle(Request(user, environ["REQUEST_METHOD"], environ["PATH_INFO"], form))
    headers = [("Content-Type", "text/html; charset=utf-8"), *response.headers.items()]
    start_response(f"{response.status} {REASONS.get(response.status, '')}", headers)
    return [response.body.encode()]


if __name__ == "__main__":
    make_server("localhost", 8000, application).serve_forever()
