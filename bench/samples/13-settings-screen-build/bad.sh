# The naive build: case 15's PR head (one-click delete, Delete shown to members,
# rename open to members, no unsaved-changes guard), with its happy-path tests.
cases="$(dirname "$0")/../../cases"
cp "$cases/15-review-settings-diff/fixture/app/settings.py" "$cases/15-review-settings-diff/fixture/app/web.py" app/
cp "$cases/15-review-settings-diff/fixture/tests/test_settings.py" tests/
