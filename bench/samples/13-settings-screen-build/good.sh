# The reference build: case 14's settings page with its planted defect fixed, plus tests.
cases="$(dirname "$0")/../../cases"
cp "$cases/14-qa-testplan-settings/fixture/app/settings.py" "$cases/14-qa-testplan-settings/fixture/app/web.py" app/
python3 - <<'PY'
from pathlib import Path
path = Path("app/settings.py")
path.write_text(path.read_text().replace(
    "    workspace = member_of(request, workspace_id)  # the delete form is only shown to admins\n",
    "    workspace = require_admin(request, workspace_id)\n"))
PY
cp "$(dirname "$0")/../14-qa-testplan-settings/test_settings.py" tests/
