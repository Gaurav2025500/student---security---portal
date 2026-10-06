"""Sends e-mail. With no SMTP settings the message is printed in the server console (development)."""
import smtplib
from email.message import EmailMessage
import config as cfg


def send_mail(to, subject, body):
    if not cfg.SMTP_HOST:
        print(f"\n[mail to {to}] {subject}\n{body}\n")
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.SMTP_FROM, to, subject
    msg.set_content(body)
    with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=20) as s:
        s.starttls()
        if cfg.SMTP_USER:
            s.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
        s.send_message(msg)
    return True
