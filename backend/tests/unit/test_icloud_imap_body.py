"""L0 Unit — _imap_body() in sync_icloud.py: reine Extraktion von Klartext aus
einem email.Message-Objekt, ohne DB/Netzwerk."""
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from app.routers.sync_icloud import _imap_body

pytestmark = pytest.mark.unit


class TestImapBody:
    def test_positiv_einfache_nachricht_liefert_text(self):
        msg = EmailMessage()
        msg.set_content("Hallo Welt")

        assert _imap_body(msg) == "Hallo Welt\n"

    def test_positiv_multipart_mit_text_plain_teil_liefert_klartext(self):
        msg = EmailMessage()
        msg.set_content("Klartext-Version")
        msg.add_alternative("<p>HTML-Version</p>", subtype="html")

        assert "Klartext-Version" in _imap_body(msg)

    def test_positiv_multipart_nur_html_wird_von_tags_befreit(self):
        # EmailMessage.set_content(subtype="html") erzeugt eine EINZELTEILIGE
        # Nachricht (is_multipart() == False) — der HTML-Strip-Zweig (81-85)
        # greift nur im echten multipart/alternative-Fall, deshalb hier der
        # klassische MIMEMultipart-Aufbau mit nur einem HTML-Teil.
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("<p>Nur HTML</p>", "html"))

        body = _imap_body(msg)

        assert "Nur HTML" in body
        assert "<p>" not in body

    def test_negativ_leere_nachricht_ohne_payload_liefert_leeren_string(self):
        msg = EmailMessage()

        assert _imap_body(msg) == ""
