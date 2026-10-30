# Workspace app

A small server-rendered app: `app/web.py` routes requests to views in `app/views.py`,
which render HTML with `app/templates.py`. Data lives in memory in `app/store.py`.

- Run it: `python -m app.wsgi`, then set the cookie `user_id=u-1` (admin) or `u-2` (member).
- Test it: `python -m unittest`
