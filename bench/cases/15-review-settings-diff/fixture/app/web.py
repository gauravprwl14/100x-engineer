import re

from app import settings, views
from app.http import HttpError, Request, Response
from app.templates import esc, page

WORKSPACE = r"/workspaces/(?P<workspace_id>[\w-]+)"
ROUTES = [
    ("GET", WORKSPACE + "/members", views.members_page),
    ("GET", WORKSPACE + "/settings", settings.settings_page),
    ("POST", WORKSPACE + "/settings/name", settings.rename_workspace),
    ("POST", WORKSPACE + "/settings/timezone", settings.set_timezone),
    ("POST", WORKSPACE + "/delete", settings.delete_workspace),
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
