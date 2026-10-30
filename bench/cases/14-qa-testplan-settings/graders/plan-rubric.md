---
type: llm
focus: {source: file, path: TESTPLAN.md}
---
Hidden ground truth: beyond the six acceptance criteria, a settings screen with admins and members is expected to be tested for these screen behaviours:
1. Deleting the workspace needs a confirmation that names the workspace: a delete without typing the exact name (or with a wrong name) leaves the workspace intact.
2. Leaving the page with unsaved edits warns the user (the page has a beforeunload guard), and Save stays disabled until something changes.
3. A member is denied twice: the page shows a member no rename, timezone or delete control, AND a member's direct POST to each changing route (rename/timezone save, delete) is refused with 403 or 404 and changes nothing. Hiding the button is not the same test as refusing the request.
4. A partial or invalid save (unknown timezone, empty or 61-character name) is refused, names the field, keeps the user's edits on screen and stores nothing.
5. Two admins saving at once: the second save with a stale version gets a conflict (409), not a silent overwrite.
The implementation has a planted defect: `delete_workspace` checks membership but not the admin role, so a member's direct POST with the right name deletes the workspace.

Pass if at least four of the five behaviours are planned as test cases with an expected result, and the plan covers the member's direct request to delete. Fail if the plan only restates the acceptance criteria.
