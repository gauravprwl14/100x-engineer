cat >> services/config.py <<'PY'
SMTP_HOST = os.environ.get("TODO_SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("TODO_SMTP_PORT", "25"))
SMTP_SENDER = os.environ.get("TODO_SMTP_SENDER", "reminders@example.com")
PY
cat > services/reminders.py <<'PY'
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage

from services import config, storage


def send_due_tomorrow_reminders(today: date, smtp_factory=smtplib.SMTP) -> int:
    todos = storage.todos_due_on(today + timedelta(days=1))
    with smtp_factory(config.SMTP_HOST, config.SMTP_PORT) as smtp:
        for todo in todos:
            message = EmailMessage()
            message["From"], message["To"] = config.SMTP_SENDER, todo.owner_email
            message["Subject"] = f"Due tomorrow: {todo.title}"
            smtp.send_message(message)
    return len(todos)
PY
