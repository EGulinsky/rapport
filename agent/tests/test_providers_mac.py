"""L0 — macOS-Provider-Adapter: subprocess/osascript-Aufrufe gemockt, damit
Tests nicht wirklich native Dialoge öffnen oder auf echte Systemdaten
zugreifen."""
import datetime
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

    def _make_phone_db(self, path, rows):
        """rows: list of (zdate, zduration, zaddress, zname, zoriginated, zanswered)."""
        import sqlite3
        conn = sqlite3.connect(str(path))
        conn.execute("""
            CREATE TABLE ZCALLRECORD (
                ZDATE REAL, ZDURATION REAL, ZADDRESS TEXT, ZNAME TEXT,
                ZORIGINATED INTEGER, ZANSWERED INTEGER,
                ZSERVICE_PROVIDER TEXT, ZCALLTYPE INTEGER
            )
        """)
        for zdate, zduration, zaddress, zname, zoriginated, zanswered in rows:
            conn.execute(
                "INSERT INTO ZCALLRECORD (ZDATE, ZDURATION, ZADDRESS, ZNAME, ZORIGINATED, ZANSWERED) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (zdate, zduration, zaddress, zname, zoriginated, zanswered),
            )
        conn.commit()
        conn.close()

    def test_positiv_zanswered_explizit_gesetzt_wird_direkt_uebernommen(self, tmp_path, monkeypatch):
        import agent.providers.mac.calls as calls_module
        db_path = tmp_path / "calls.db"
        recent_zdate = (
            datetime.datetime.now() - calls_module._EPOCH
        ).total_seconds() - 60
        self._make_phone_db(db_path, [(recent_zdate, 120, "+491234", "Alice", 1, 1)])
        monkeypatch.setattr(calls_module, "PHONE_DB", str(db_path))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "keine_wa.sqlite"))

        calls = MacCallsProvider().list_calls(90)

        assert len(calls) == 1
        assert calls[0]["answered"] is True
        assert calls[0]["direction"] == "outgoing"

    def test_negativ_zanswered_explizit_null_und_keine_dauer_bleibt_verpasst(self, tmp_path, monkeypatch):
        import agent.providers.mac.calls as calls_module
        db_path = tmp_path / "calls.db"
        recent_zdate = (
            datetime.datetime.now() - calls_module._EPOCH
        ).total_seconds() - 60
        self._make_phone_db(db_path, [(recent_zdate, 0, "+491234", "Bob", 0, 0)])
        monkeypatch.setattr(calls_module, "PHONE_DB", str(db_path))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "keine_wa.sqlite"))

        calls = MacCallsProvider().list_calls(90)

        assert len(calls) == 1
        assert calls[0]["answered"] is False
        assert calls[0]["direction"] == "incoming"

    def test_positiv_zanswered_none_aber_echte_dauer_gilt_als_beantwortet(self, tmp_path, monkeypatch):
        """Reproduces the real bug: calls relayed to the Mac via Continuity
        commonly leave ZANSWERED as SQL NULL rather than 0/1 -- bool(None)
        is False, which previously mislabeled a real, completed call as
        missed. ZDURATION > 0 is the reliable signal that the call connected."""
        import agent.providers.mac.calls as calls_module
        db_path = tmp_path / "calls.db"
        recent_zdate = (
            datetime.datetime.now() - calls_module._EPOCH
        ).total_seconds() - 60
        self._make_phone_db(db_path, [(recent_zdate, 245, "+491234", "Carol", 0, None)])
        monkeypatch.setattr(calls_module, "PHONE_DB", str(db_path))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "keine_wa.sqlite"))

        calls = MacCallsProvider().list_calls(90)

        assert len(calls) == 1
        assert calls[0]["answered"] is True
        assert calls[0]["duration_s"] == 245

    def test_negativ_zanswered_none_und_keine_dauer_bleibt_verpasst(self, tmp_path, monkeypatch):
        """Same NULL-ZANSWERED case as above, but a genuinely missed call
        (ZDURATION 0) must still be reported as missed, not flipped to
        answered just because ZANSWERED is NULL."""
        import agent.providers.mac.calls as calls_module
        db_path = tmp_path / "calls.db"
        recent_zdate = (
            datetime.datetime.now() - calls_module._EPOCH
        ).total_seconds() - 60
        self._make_phone_db(db_path, [(recent_zdate, 0, "+491234", "Dave", 0, None)])
        monkeypatch.setattr(calls_module, "PHONE_DB", str(db_path))
        monkeypatch.setattr(calls_module, "WA_CALLS", str(tmp_path / "keine_wa.sqlite"))

        calls = MacCallsProvider().list_calls(90)

        assert len(calls) == 1
        assert calls[0]["answered"] is False
