"""L0 Unit — Fernet-Verschlüsselung für gespeicherte API-Keys (app/ai/provider.py).

_DATA_DIR wird pro Test auf ein temporäres Verzeichnis umgebogen, damit weder
der echte fernet.key der Anwendung berührt noch Zustand zwischen Tests geteilt
wird (jeder Test bekommt seinen eigenen, frisch generierten Schlüssel).
"""
import pytest
from cryptography.fernet import InvalidToken

from app.ai import provider

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(provider, "_DATA_DIR", tmp_path)


class TestFernetKeyHandling:
    def test_positiv_encrypt_decrypt_round_trip(self):
        token = provider.encrypt_api_key("sk-super-secret-123")

        assert provider.decrypt_api_key(token) == "sk-super-secret-123"

    def test_positiv_key_datei_wird_beim_ersten_gebrauch_angelegt(self, tmp_path):
        key_file = tmp_path / "fernet.key"
        assert not key_file.exists()

        provider.encrypt_api_key("irgendein-key")

        assert key_file.exists()

    def test_positiv_bestehende_key_datei_wird_wiederverwendet(self, tmp_path):
        # Erster Aufruf legt den Schlüssel an, zweiter muss denselben nutzen —
        # sonst könnten bereits verschlüsselte Werte nicht mehr entschlüsselt werden.
        provider.encrypt_api_key("erster-aufruf")
        key_bytes_after_first = (tmp_path / "fernet.key").read_bytes()

        token = provider.encrypt_api_key("zweiter-aufruf")
        key_bytes_after_second = (tmp_path / "fernet.key").read_bytes()

        assert key_bytes_after_first == key_bytes_after_second
        assert provider.decrypt_api_key(token) == "zweiter-aufruf"

    def test_negativ_falscher_schluessel_kann_nicht_entschluesseln(self, tmp_path, monkeypatch):
        token = provider.encrypt_api_key("geheim")

        # Simuliert einen Fernet-Key-Wechsel (z.B. Datenverlust/Rotation) — alte
        # Tokens dürfen nicht mit einem neuen Schlüssel entschlüsselbar sein.
        (tmp_path / "fernet.key").unlink()
        other_dir = tmp_path / "andere_instanz"
        other_dir.mkdir()
        monkeypatch.setattr(provider, "_DATA_DIR", other_dir)

        with pytest.raises(InvalidToken):
            provider.decrypt_api_key(token)

    def test_fehleingabe_manipuliertes_token_wirft_invalidtoken(self):
        token = provider.encrypt_api_key("geheim")
        kaputt = token[:-4] + "xxxx"

        with pytest.raises(InvalidToken):
            provider.decrypt_api_key(kaputt)

    def test_corner_case_unicode_und_sonderzeichen_round_trip(self):
        plaintext = "Schlüssel-mit-Ümläuten-und-€mojis-🔑"

        token = provider.encrypt_api_key(plaintext)

        assert provider.decrypt_api_key(token) == plaintext

    def test_corner_case_leerer_string_round_trip(self):
        token = provider.encrypt_api_key("")

        assert provider.decrypt_api_key(token) == ""
