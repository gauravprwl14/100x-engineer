import os

DB_HOST = os.environ.get("TODO_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("TODO_DB_PORT", "5432"))
