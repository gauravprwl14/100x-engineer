# expect: pass
# Review F7: a build that confirms the all-members timezone change on a second page, and
# answers a member's POST with a redirect that changes nothing, is still a correct build.
bash "$(dirname "$0")/good.sh"
python3 - <<'PY'
from pathlib import Path

path = Path("app/settings.py")
text = path.read_text()
head = "def save_settings(request: Request, workspace_id: str) -> Response:\n"
guard = "    workspace = require_admin(request, workspace_id)\n    name = "
assert text.count(head) == 1 and text.count(guard) == 1
text = text.replace(head, head + """    user = request.user
    if user is not None and user.workspace_id == workspace_id and user.role != "admin":
        return redirect(settings_url(workspace_id))
""")
text = text.replace(guard, """    workspace = require_admin(request, workspace_id)
    if request.form.get("timezone") != workspace["timezone"] and request.form.get("confirmed") != "yes":
        hidden = "".join(f'<input type="hidden" name="{esc(k)}" value="{esc(v)}">'
                         for k, v in request.form.items())
        form = (f'<form method="post" action="{esc(settings_url(workspace_id))}">{hidden}'
                '<input type="hidden" name="confirmed" value="yes">'
                '<button type="submit">Change for everyone</button></form>')
        return Response(200, page("Confirm", "<p>The new timezone applies to every member.</p>" + form))
    name = """)
path.write_text(text)

tests = Path("tests/test_settings.py")
body = tests.read_text()
for old, new in (
        ('timezone="Europe/Berlin")', 'timezone="Europe/Berlin", confirmed="yes")'),
        ('timezone="Mars/Olympus")', 'timezone="Mars/Olympus", confirmed="yes")'),
        ('(403, "Acme Design")', '(303, "Acme Design")')):
    assert body.count(old) == 1, old
    body = body.replace(old, new)
tests.write_text(body)
PY
