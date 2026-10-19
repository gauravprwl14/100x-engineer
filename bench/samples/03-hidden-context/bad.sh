mkdir -p services/email
touch services/email/__init__.py
cat > services/email/reminders.py <<'PY'
import os
import smtplib

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("smtpPort", "25"))


def send_reminders(todos):
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        for todo in todos:
            smtp.sendmail("noreply@example.com", todo.owner_email, todo.title)
PY
