"""Workspace settings: everyone in the workspace can view them; only admins change them."""
from zoneinfo import available_timezones

from app import store
from app.http import Forbidden, Request, Response, redirect
from app.templates import esc, page
from app.views import member_of

TIMEZONES = sorted(available_timezones())
MAX_NAME_LENGTH = 60

# Marks the form dirty on input, enables Save, and asks before leaving with unsaved edits.
GUARD = """<script>
const form = document.getElementById("settings-form");
let dirty = false;
form.addEventListener("input", () => {
  dirty = true;
  form.querySelector("button[type=submit]").disabled = false;
});
form.addEventListener("submit", () => { dirty = false; });
window.addEventListener("beforeunload", (event) => {
  if (dirty) { event.preventDefault(); event.returnValue = ""; }
});
</script>"""


def require_admin(request: Request, workspace_id: str) -> dict:
    workspace = member_of(request, workspace_id)
    if request.user.role != "admin":
        raise Forbidden("only admins can change workspace settings")
    return workspace


def settings_url(workspace_id: str) -> str:
    return f"/workspaces/{workspace_id}/settings"


def render(request: Request, workspace: dict, errors=(), values=None, status=200) -> Response:
    title = f"{workspace['name']} settings"
    heading = f"<h1>{esc(workspace['name'])}: settings</h1>"
    if request.user.role != "admin":
        body = f"""{heading}
<dl>
  <dt>Name</dt><dd>{esc(workspace['name'])}</dd>
  <dt>Default timezone</dt><dd>{esc(workspace['timezone'])}</dd>
</dl>
<p>Only admins can change these settings.</p>"""
        return Response(status, page(title, body))
    values = values or workspace
    notes = "".join(f"<li>{esc(error)}</li>" for error in errors)
    options = "\n".join(
        f'<option value="{esc(zone)}"{" selected" if zone == values["timezone"] else ""}>{esc(zone)}</option>'
        for zone in TIMEZONES)
    body = f"""{heading}
{f'<ul role="alert">{notes}</ul>' if notes else ''}
<form id="settings-form" method="post" action="{esc(settings_url(workspace['id']))}">
  <input type="hidden" name="version" value="{workspace.get('version', 0)}">
  <label>Name <input name="name" value="{esc(values['name'])}" maxlength="{MAX_NAME_LENGTH}" required></label>
  <label>Default timezone <select name="timezone">{options}</select></label>
  <p>The default timezone applies to every member of the workspace.</p>
  <button type="submit" disabled>Save changes</button>
</form>
<section>
  <h2>Delete workspace</h2>
  <form method="post" action="/workspaces/{esc(workspace['id'])}/delete">
    <p>Deleting {esc(workspace['name'])} removes it and its data for every member. This cannot be undone.</p>
    <label>Type <strong>{esc(workspace['name'])}</strong> to confirm
      <input name="confirm_name" autocomplete="off"></label>
    <button type="submit">Delete workspace</button>
  </form>
</section>
{GUARD}"""
    return Response(status, page(title, body))


def settings_page(request: Request, workspace_id: str) -> Response:
    return render(request, member_of(request, workspace_id))


def save_settings(request: Request, workspace_id: str) -> Response:
    workspace = require_admin(request, workspace_id)
    name = request.form.get("name", "").strip()
    timezone = request.form.get("timezone", "")
    values = {"name": name, "timezone": timezone}
    if request.form.get("version") != str(workspace.get("version", 0)):
        conflict = "Someone else saved these settings while you were editing. Check them and save again."
        return render(request, workspace, [conflict], values, 409)
    errors = []
    if not name:
        errors.append("Name is required.")
    elif len(name) > MAX_NAME_LENGTH:
        errors.append(f"Name must be at most {MAX_NAME_LENGTH} characters.")
    if timezone not in TIMEZONES:
        errors.append(f"Timezone '{timezone}' is not a known timezone.")
    if errors:
        return render(request, workspace, errors, values, 400)
    if values != {"name": workspace["name"], "timezone": workspace["timezone"]}:
        workspace.update(values, version=workspace.get("version", 0) + 1)
    return redirect(settings_url(workspace_id))


def delete_workspace(request: Request, workspace_id: str) -> Response:
    workspace = member_of(request, workspace_id)  # the delete form is only shown to admins
    if request.form.get("confirm_name", "").strip() != workspace["name"]:
        return render(request, workspace, ["Type the workspace name exactly to delete it."], status=400)
    del store.WORKSPACES[workspace_id]
    return redirect("/")
