cat > REVIEW.md <<'MD'
[MUST] app/settings.py:49: `rename_workspace` calls `member_of`, not `require_admin`, so any member can rename the workspace with a direct POST.
Could you use `require_admin` here, as `set_timezone` does, and add a test that a member gets 403?

[MUST] app/settings.py:68: `delete_workspace` deletes on one click, with no confirmation naming the workspace.
Could you ask the admin to type "Acme Design" and refuse the delete when it does not match?

[SHOULD] app/settings.py:42: the delete form sits outside the admin block, so members see a Delete button they cannot use.
Could you move it inside `if request.user.role == "admin"`?

[SHOULD] app/settings.py:28: the edit forms have no unsaved-changes guard, so leaving the page drops typed edits without a warning.
Could you add a `beforeunload` handler that fires while a form is dirty?
MD
