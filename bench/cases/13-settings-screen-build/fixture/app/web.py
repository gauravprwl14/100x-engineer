import re

from app import views
from app.http import HttpError, Request, Response
from app.templates import esc, page

ROUTES = [
    ("GET", r"/workspaces/(?P<workspace_id>[\w-]+)/members", views.members_page),
]


def handle(request: Request) -> Response:
    for method, pattern, view in ROUTES:
        match = re.fullmatch(pattern, request.path)
        if match and method == request.method:
            try:
                return view(request, **match.groupdict())
            except HttpError as error:
                return Response(error.status, page("Error", f"<p>{esc(error.message)}</p>"))
    return Response(404, page("Not found", "<p>Not found</p>"))
