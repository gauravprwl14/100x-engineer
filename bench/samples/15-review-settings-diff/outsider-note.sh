# expect: pass
# Review F4: a correct blocking comment that also notes fine code is not a false alarm.
bash "$(dirname "$0")/good.sh"
python3 - <<'PY'
from pathlib import Path
review = Path("REVIEW.md")
review.write_text(review.read_text().replace(
    "with a direct POST.\n",
    "with a direct POST. (`member_of` correctly 404s outsiders from another workspace; the gap is the role.)\n", 1))
PY
