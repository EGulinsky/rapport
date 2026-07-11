"""L1 Unit — send_verification_code() in app/auth/email.py. Mockt smtplib.SMTP
an der Netzwerkgrenze, patcht die modulweiten SMTP_*-Konstanten direkt."""
from unittest.mock import MagicMock

import pytest

import app.auth.email as email_module
from app.auth.email import EmailNotConfigured, send_verification_code

pytestmark = pytest.mark.unit


class TestSendVerificationCode:
    def test_negativ_ohne_smtp_konfiguration_wirft_emailnotconfigured(self, monkeypatch):
        monkeypatch.setattr(email_module, "SMTP_HOST", None)
        monkeypatch.setattr(email_module, "SMTP_USER", None)
        monkeypatch.setattr(email_module, "SMTP_PASSWORD", None)

        with pytest.raises(EmailNotConfigured):
            send_verification_code("user@example.com", "123456", "verify_email")

    def test_negativ_teilweise_konfiguration_wirft_ebenfalls(self, monkeypatch):
        monkeypatch.setattr(email_module, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(email_module, "SMTP_USER", None)
        monkeypatch.setattr(email_module, "SMTP_PASSWORD", "secret")

        with pytest.raises(EmailNotConfigured):
            send_verification_code("user@example.com", "123456", "verify_email")

    def test_positiv_sendet_verifizierungs_mail(self, monkeypatch):
        monkeypatch.setattr(email_module, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(email_module, "SMTP_USER", "bot@example.com")
        monkeypatch.setattr(email_module, "SMTP_PASSWORD", "secret")
        monkeypatch.setattr(email_module, "SMTP_FROM", "bot@example.com")

        fake_server = MagicMock()
        fake_smtp_cls = MagicMock()
        fake_smtp_cls.return_value.__enter__.return_value = fake_server
        monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_cls)

        send_verification_code("user@example.com", "123456", "verify_email")

        fake_server.starttls.assert_called_once()
        fake_server.login.assert_called_once_with("bot@example.com", "secret")
        fake_server.send_message.assert_called_once()
        sent_msg = fake_server.send_message.call_args[0][0]
        assert sent_msg["To"] == "user@example.com"
        assert "bestätigen" in sent_msg["Subject"]
        assert "123456" in sent_msg.get_content()

    def test_positiv_reset_password_verwendet_anderen_betreff(self, monkeypatch):
        monkeypatch.setattr(email_module, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(email_module, "SMTP_USER", "bot@example.com")
        monkeypatch.setattr(email_module, "SMTP_PASSWORD", "secret")
        monkeypatch.setattr(email_module, "SMTP_FROM", "bot@example.com")

        fake_server = MagicMock()
        fake_smtp_cls = MagicMock()
        fake_smtp_cls.return_value.__enter__.return_value = fake_server
        monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_cls)

        send_verification_code("user@example.com", "654321", "reset_password")

        sent_msg = fake_server.send_message.call_args[0][0]
        assert "zurücksetzen" in sent_msg["Subject"]

    def test_positiv_ui_language_en_sendet_englische_mail(self, monkeypatch):
        monkeypatch.setattr(email_module, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(email_module, "SMTP_USER", "bot@example.com")
        monkeypatch.setattr(email_module, "SMTP_PASSWORD", "secret")
        monkeypatch.setattr(email_module, "SMTP_FROM", "bot@example.com")

        fake_server = MagicMock()
        fake_smtp_cls = MagicMock()
        fake_smtp_cls.return_value.__enter__.return_value = fake_server
        monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_cls)

        send_verification_code("user@example.com", "123456", "verify_email", ui_language="en")

        sent_msg = fake_server.send_message.call_args[0][0]
        assert "Verify your email" in sent_msg["Subject"]
        assert "123456" in sent_msg.get_content()
        assert "bestätigen" not in sent_msg["Subject"]

    def test_positiv_ui_language_en_reset_password_verwendet_englischen_betreff(self, monkeypatch):
        monkeypatch.setattr(email_module, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(email_module, "SMTP_USER", "bot@example.com")
        monkeypatch.setattr(email_module, "SMTP_PASSWORD", "secret")
        monkeypatch.setattr(email_module, "SMTP_FROM", "bot@example.com")

        fake_server = MagicMock()
        fake_smtp_cls = MagicMock()
        fake_smtp_cls.return_value.__enter__.return_value = fake_server
        monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_cls)

        send_verification_code("user@example.com", "654321", "reset_password", ui_language="en")

        sent_msg = fake_server.send_message.call_args[0][0]
        assert "Reset your password" in sent_msg["Subject"]

    def test_corner_case_unbekannte_sprache_faellt_auf_deutsch_zurueck(self, monkeypatch):
        monkeypatch.setattr(email_module, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(email_module, "SMTP_USER", "bot@example.com")
        monkeypatch.setattr(email_module, "SMTP_PASSWORD", "secret")
        monkeypatch.setattr(email_module, "SMTP_FROM", "bot@example.com")

        fake_server = MagicMock()
        fake_smtp_cls = MagicMock()
        fake_smtp_cls.return_value.__enter__.return_value = fake_server
        monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_cls)

        send_verification_code("user@example.com", "123456", "verify_email", ui_language="fr")

        sent_msg = fake_server.send_message.call_args[0][0]
        assert "bestätigen" in sent_msg["Subject"]
