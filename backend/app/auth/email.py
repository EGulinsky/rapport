"""
Versand von Bestätigungscodes per E-Mail via SMTP (App-Passwort, analog zum
bestehenden iCloud-App-Passwort-Muster) — reine stdlib (smtplib/email),
kein externer Mailing-Dienst nötig. Konfiguration über Umgebungsvariablen.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from app.logger import get_logger

log = get_logger("auth")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER or ""


class EmailNotConfigured(Exception):
    pass


def send_verification_code(to_email: str, code: str, purpose: str) -> None:
    """purpose: "verify_email" | "reset_password" """
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        raise EmailNotConfigured(
            "SMTP ist nicht konfiguriert (SMTP_HOST/SMTP_USER/SMTP_PASSWORD fehlen)."
        )

    subject = "Passwort zurücksetzen" if purpose == "reset_password" else "E-Mail bestätigen"
    body = (
        f"Dein Bestätigungscode: {code}\n\n"
        "Der Code ist 15 Minuten gültig. Wenn du das nicht angefordert hast, "
        "kannst du diese E-Mail ignorieren."
    )

    msg = EmailMessage()
    msg["Subject"] = f"rapport – {subject}"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
    log.info("Bestätigungscode ({}) gesendet an {}", purpose, to_email)
