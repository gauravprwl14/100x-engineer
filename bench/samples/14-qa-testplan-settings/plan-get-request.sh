# expect: fail=plan_covers_member_direct_request
# Review F6: "a member opens the page (GET request)" is not a direct request being refused.
bash "$(dirname "$0")/good.sh"
python3 - <<'PY'
from pathlib import Path
plan = Path("TESTPLAN.md")
plan.write_text(plan.read_text().replace(
    "| TC-3 | AC-5 | member sends a direct POST to save and to delete | 403, nothing changes |",
    "| TC-3 | AC-1 | member opens the settings page (GET request) | 200 |"))
PY
