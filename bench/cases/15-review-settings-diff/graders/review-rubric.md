---
type: llm
focus: {source: file, path: REVIEW.md}
---
Hidden ground truth: the diff adds a workspace settings page (app/settings.py) with exactly four defects:
1. `delete_workspace` deletes on one click: no confirmation naming the workspace, no typed name, no second step. A confirmation that names "Acme Design" and the consequence is expected for an irreversible delete.
2. `settings_page` renders the delete form outside the `if request.user.role == "admin"` block, so members see a Delete button (the server refuses them, but the control must be hidden or disabled with a reason).
3. `rename_workspace` uses `member_of`, not `require_admin`, so any member can rename the workspace with a direct POST. This is blocking.
4. The edit forms have no unsaved-changes guard: leaving the page after editing loses the input without a warning.
Everything else is fine: values are escaped with `esc()`, outsiders get 404 through `member_of`, the timezone is validated against `available_timezones()`, and POSTs redirect.

Pass only if ALL hold:
1. Each of the four defects has its own comment naming app/settings.py and a line inside the function concerned.
2. The rename defect is marked blocking (or must-fix).
3. No comment marks fine code as blocking (for example claims of XSS or injection on escaped values, or of outsiders reaching the page).
