from app import store
from app.http import NotFound, Request, Response, Unauthorized
from app.templates import esc, page


def member_of(request: Request, workspace_id: str) -> dict:
    """The workspace, if the signed-in user belongs to it.

    Anyone else gets NotFound, the same answer as for a missing id, so workspace ids
    cannot be probed.
    """
    if request.user is None:
        raise Unauthorized("sign in required")
    workspace = store.WORKSPACES.get(workspace_id)
    if workspace is None or request.user.workspace_id != workspace_id:
        raise NotFound("no such workspace")
    return workspace


def members_page(request: Request, workspace_id: str) -> Response:
    workspace = member_of(request, workspace_id)
    rows = "\n".join(f"<li>{esc(user.name)} ({esc(user.role)})</li>"
                     for user in store.USERS.values() if user.workspace_id == workspace_id)
    body = f"<h1>{esc(workspace['name'])}: members</h1>\n<ul>\n{rows}\n</ul>"
    return Response(200, page(f"{workspace['name']} members", body))
