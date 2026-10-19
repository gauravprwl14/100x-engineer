# services/ conventions

- Settings come from environment variables, read in `services/config.py` and nowhere else.
- Env var names are UPPER_SNAKE_CASE with the `TODO_` prefix, for example `TODO_DB_HOST`.
- One module per service, directly in `services/`. No sub-packages and no other folders.
