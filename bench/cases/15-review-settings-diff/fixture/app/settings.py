"""Workspace settings page: view for everyone in the workspace, changes for admins."""
from zoneinfo import available_timezones

from app import store
from app.http import BadRequest, Forbidden, Request, Response, redirect
from app.templates import esc, page
from app.views import member_of

TIMEZONES = sorted(available_timezones())
MAX_NAME_LENGTH = 60


def require_admin(request: Request, workspace_id: str) -> dict:
    workspace = member_of(request, workspace_id)
    if request.user.role != "admin":
        raise Forbidden("only admins can change workspace settings")
    return workspace


def settings_page(request: Request, workspace_id: str) -> Response:
    workspace = member_of(request, workspace_id)
    base = f"/workspaces/{esc(workspace_id)}"
    controls = ""
    if request.user.role == "admin":
        options = "\n".join(
            f'<option value="{esc(zone)}"{" selected" if zone == workspace["timezone"] else ""}>'
            f"{esc(zone)}</option>" for zone in TIMEZONES)
        controls = f"""<form method="post" action="{base}/settings/name">
  <label>Name <input name="name" value="{esc(workspace['name'])}" maxlength="{MAX_NAME_LENGTH}" required></label>
  <button type="submit">Rename</button>
</form>
<form method="post" action="{base}/settings/timezone">
  <label>Default timezone <select name="timezone">{options}</select></label>
  <button type="submit">Save timezone</button>
</form>"""
    body = f"""<h1>{esc(workspace['name'])}: settings</h1>
<dl>
  <dt>Name</dt><dd>{esc(workspace['name'])}</dd>
  <dt>Default timezone</dt><dd>{esc(workspace['timezone'])}</dd>
</dl>
{controls}
<form method="post" action="{base}/delete">
  <button type="submit">Delete workspace</button>
</form>"""
    return Response(200, page(f"{workspace['name']} settings", body))


def rename_workspace(request: Request, workspace_id: str) -> Response:
    workspace = member_of(request, workspace_id)
    name = request.form.get("name", "").strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise BadRequest(f"name must be 1-{MAX_NAME_LENGTH} characters")
    workspace["name"] = name
    return redirect(f"/workspaces/{workspace_id}/settings")


def set_timezone(request: Request, workspace_id: str) -> Response:
    workspace = require_admin(request, workspace_id)
    timezone = request.form.get("timezone", "")
    if timezone not in TIMEZONES:
        raise BadRequest(f"unknown timezone {timezone!r}")
    workspace["timezone"] = timezone
    return redirect(f"/workspaces/{workspace_id}/settings")


def delete_workspace(request: Request, workspace_id: str) -> Response:
    require_admin(request, workspace_id)
    del store.WORKSPACES[workspace_id]
    return redirect("/")
