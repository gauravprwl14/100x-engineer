cat > REVIEW.md <<'MD'
[MUST] app/settings.py:38: the workspace name is interpolated into HTML, an XSS risk. Please sanitize it.

[MUST] app/settings.py:49: `rename_workspace` lacks the admin role check that `set_timezone` has.

[NIT] app/settings.py:9: consider caching the timezone list.
MD
