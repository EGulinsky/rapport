"""L1 Unit — _gmail_body() in sync_google.py. Reine Funktion, kein DB-Zugriff."""
import base64

import pytest

from app.routers.sync_google import _gmail_body

pytestmark = pytest.mark.unit


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class TestGmailBody:
    def test_positiv_text_plain_wird_direkt_dekodiert(self):
        payload = {"mimeType": "text/plain", "body": {"data": _b64("Hallo Welt")}}
        assert _gmail_body(payload) == "Hallo Welt"

    def test_positiv_text_html_wird_dekodiert_und_getaggt_entfernt(self):
        payload = {"mimeType": "text/html", "body": {"data": _b64("<p>Hallo <b>Welt</b></p>")}}
        assert "Hallo" in _gmail_body(payload)
        assert "<" not in _gmail_body(payload)

    def test_positiv_multipart_findet_text_teil_rekursiv(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {}},
                {"mimeType": "multipart/mixed", "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("Verschachtelter Text")}},
                ]},
            ],
        }
        assert _gmail_body(payload) == "Verschachtelter Text"

    def test_negativ_ohne_erkennbaren_textteil_liefert_leerstring(self):
        payload = {"mimeType": "application/octet-stream", "body": {"data": _b64("binär")}}
        assert _gmail_body(payload) == ""

    def test_negativ_leeres_payload_liefert_leerstring(self):
        assert _gmail_body({}) == ""
