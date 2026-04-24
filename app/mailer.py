import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(subject: str, body: str, to_addr: str):
    from_addr = os.getenv("GMAIL_FROM")
    app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not from_addr or not app_password:
        raise RuntimeError("GMAIL_FROM and GMAIL_APP_PASSWORD must be set in .env")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(from_addr, app_password)
        server.sendmail(from_addr, to_addr, msg.as_string())
