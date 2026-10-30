# expect: fail=finds_member_sees_delete,finds_rename_missing_role_check,rename_marked_blocking,rename_cites_its_line,finds_no_unsaved_guard
# Review F3: the one-click-delete comment alone mentions "role" and "form"; it must not
# earn the member-sees-delete finding.
cat > REVIEW.md <<'MD'
[MUST] app/settings.py:68: `delete_workspace` deletes on one click after the role check, with no confirmation naming the workspace.
Could you add a confirmation form that asks the admin to type "Acme Design"?
MD
