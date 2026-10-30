cp "$(dirname "$0")/test_settings.py" tests/
cat > TESTPLAN.md <<'MD'
# Workspace settings: test plan

| id | covers | case | expected |
|---|---|---|---|
| TC-1 | AC-1 | member opens the settings page | 200, name and timezone shown |
| TC-2 | AC-5 | member opens the page | no rename, timezone or delete control is shown; the page says only admins can change settings |
| TC-3 | AC-5 | member sends a direct POST to save and to delete | 403, nothing changes |
| TC-4 | AC-6 | outsider opens the page | 404 |
| TC-5 | AC-2 | name empty, 60 and 61 characters | 400, 303, 400 |
| TC-6 | AC-3 | unknown timezone | 400 naming the field; the typed edits stay on screen |
| TC-7 | AC-4 | delete without typing the exact workspace name | 400, workspace kept |
| TC-8 | AC-4 | delete after typing the name | workspace gone |
| TC-9 | — | edit, then leave the page | beforeunload guard asks before discarding unsaved edits |
| TC-10 | — | two admins save; the second has a stale version | 409 conflict, no silent overwrite |
MD
