"""L0 — macOS-Provider-Adapter: subprocess/osascript-Aufrufe gemockt, damit
Tests nicht wirklich native Dialoge öffnen oder auf echte Systemdaten
zugreifen."""
import json
from unittest.mock import MagicMock, patch

from agent.providers.mac.calls import MacCallsProvider
from agent.providers.mac.files import MacFilesProvider
from agent.providers.mac.notes import MacNotesProvider


class TestMacFilesProvider:
    def test_positiv_pick_folder_liefert_pfad(self):
        provider = MacFilesProvider()
        result = MagicMock(stdout="/Users/test/Ordner/\n")
        with patch("subprocess.run", return_value=result) as mock_run:
            path = provider.pick_folder("Wähle einen Ordner")
        assert path == "/Users/test/Ordner"
        assert "osascript" in mock_run.call_args[0][0]

    def test_negativ_pick_folder_abgebrochen_liefert_none(self):
        provider = MacFilesProvider()
        result = MagicMock(stdout="\n")
        with patch("subprocess.run", return_value=result):
            assert provider.pick_folder("x") is None

    def test_positiv_pick_file_mit_typfilter(self):
        provider = MacFilesProvider()
        result = MagicMock(stdout="/Users/test/backup.zip\n")
        with patch("subprocess.run", return_value=result) as mock_run:
            path = provider.pick_file("Backup wählen", ["zip", "db"])
        assert path == "/Users/test/backup.zip"
        script = mock_run.call_args[0][0][2]
        assert '"zip"' in script and '"db"' in script

    def test_positiv_open_path_ruft_open_kommando(self):
        provider = MacFilesProvider()
        with patch("subprocess.Popen") as mock_popen:
            provider.open_path("/Users/test/datei.pdf")
        mock_popen.assert_called_once_with(["open", "/Users/test/datei.pdf"])


class TestMacNotesProvider:
    def test_positiv_list_notes_parsed_json(self):
        provider = MacNotesProvider()
        notes = [{"id": "1", "name": "Test", "body": "Inhalt", "date": "", "creationDate": ""}]
        result = MagicMock(returncode=0, stdout=json.dumps(notes))
        with patch("subprocess.run", return_value=result):
            assert provider.list_notes() == notes

    def test_negativ_osascript_fehler_wirft_exception(self):
        provider = MacNotesProvider()
        result = MagicMock(returncode=1, stderr="Notes app nicht erreichbar")
        with patch("subprocess.run", return_value=result):
            try:
                provider.list_notes()
                assert False, "hätte werfen müssen"
            except RuntimeError as e:
                assert "Notes app nicht erreichbar" in str(e)

    def test_positiv_health_ok_bei_returncode_0(self):
        provider = MacNotesProvider()
        result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=result):
            assert provider.health() == {"ok": True}

    def test_negativ_health_nicht_ok_bei_fehler(self):
        provider = MacNotesProvider()
        result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=result):
            assert provider.health() == {"ok": False}


class TestMacCallsProvider:
    def test_negativ_ohne_datenbanken_leere_liste(self, tmp_path, monkeypatch):
        import agent.providers.mac.calls as calls_module
        monkeypatch.setattr(calls_module, "PHONE_DB", str(tmp_path / "nicht_da.db"))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "auch_nicht_da.sqlite"))

        provider = MacCallsProvider()
        assert provider.list_calls(90) == []

    def test_negativ_health_ohne_datenbanken(self, tmp_path, monkeypatch):
        import agent.providers.mac.calls as calls_module
        monkeypatch.setattr(calls_module, "PHONE_DB", str(tmp_path / "nicht_da.db"))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "auch_nicht_da.sqlite"))

        provider = MacCallsProvider()
        health = provider.health()
        assert health == {"ok": False, "phone_accessible": False, "whatsapp_accessible": False}

    def test_negativ_health_datei_existiert_aber_nicht_lesbar(self, tmp_path, monkeypatch):
        """Reproduces the real incident: CallHistory.storedata exists on disk but
        Full Disk Access was revoked, so every read fails — health() must report
        phone_accessible=False (previously it only checked os.path.exists() and
        stayed True, hiding the outage)."""
        import agent.providers.mac.calls as calls_module
        unreadable_db = tmp_path / "existiert_aber_kaputt.db"
        unreadable_db.write_bytes(b"not a valid sqlite file")
        monkeypatch.setattr(calls_module, "PHONE_DB", str(unreadable_db))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "auch_nicht_da.sqlite"))

        provider = MacCallsProvider()
        health = provider.health()
        assert health == {"ok": False, "phone_accessible": False, "whatsapp_accessible": False}

    def test_positiv_health_datei_lesbar(self, tmp_path, monkeypatch):
        import sqlite3
        import agent.providers.mac.calls as calls_module
        readable_db = tmp_path / "lesbar.db"
        conn = sqlite3.connect(str(readable_db))
        conn.execute("CREATE TABLE ZCALLRECORD (ZDATE REAL)")
        conn.commit()
        conn.close()
        monkeypatch.setattr(calls_module, "PHONE_DB", str(readable_db))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "auch_nicht_da.sqlite"))

        provider = MacCallsProvider()
        health = provider.health()
        assert health == {"ok": True, "phone_accessible": True, "whatsapp_accessible": False}
