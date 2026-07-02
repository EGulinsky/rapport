"""L1 Component — backup.py: Backup/Restore muss die DB *und* fernet.key
bündeln, sonst sind verschlüsselte Felder nach einem Restore auf eine neue
Maschine/ein frisches Volume dauerhaft nicht mehr entschlüsselbar (siehe
Docstring in backup.py). httpx-Aufrufe an die host-seitige files_bridge
werden gemockt; DB_PATH/FERNET_KEY_PATH werden auf ein temporäres
Verzeichnis umgebogen.
"""
import io
import sqlite3
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.routers import backup as backup_module
from app import models

pytestmark = pytest.mark.component


def _make_sqlite_file(path, rows=("hallo",)):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x TEXT)")
    for r in rows:
        conn.execute("INSERT INTO t (x) VALUES (?)", (r,))
    conn.commit()
    conn.close()


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_module, "DB_PATH", str(tmp_path / "jobtracker.db"))
    monkeypatch.setattr(backup_module, "FERNET_KEY_PATH", str(tmp_path / "fernet.key"))
    return tmp_path


def _enable_backup(db_session, folder="/backups"):
    db_session.add(models.BackupConfig(enabled=True, backup_folder=folder, keep_count=7))
    db_session.commit()


class TestDoBackup:
    async def test_positiv_zip_enthaelt_db_und_fernet_key(self, db_session, tmp_path):
        _make_sqlite_file(backup_module.DB_PATH)
        (tmp_path / "fernet.key").write_bytes(b"super-secret-fernet-key")
        _enable_backup(db_session)

        captured = {}

        async def fake_post(self, url, json=None, **kwargs):
            captured["json"] = json
            return _mock_response({"success": True, "filename": json["filename"]})

        with patch("httpx.AsyncClient.post", new=fake_post):
            result = await backup_module.do_backup()

        assert result["success"] is True
        assert result["filename"].endswith(".zip")
        zip_bytes = __import__("base64").b64decode(captured["json"]["data_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "jobtracker.db" in names
            assert "fernet.key" in names
            assert zf.read("fernet.key") == b"super-secret-fernet-key"

    async def test_corner_case_fehlender_fernet_key_bricht_backup_nicht(self, db_session, tmp_path):
        # Frischinstallation: noch nie ein Secret verschlüsselt → kein fernet.key
        # vorhanden. Backup muss trotzdem funktionieren, nur ohne Key-Eintrag.
        _make_sqlite_file(backup_module.DB_PATH)
        assert not (tmp_path / "fernet.key").exists()
        _enable_backup(db_session)

        captured = {}

        async def fake_post(self, url, json=None, **kwargs):
            captured["json"] = json
            return _mock_response({"success": True, "filename": json["filename"]})

        with patch("httpx.AsyncClient.post", new=fake_post):
            result = await backup_module.do_backup()

        assert result["success"] is True
        zip_bytes = __import__("base64").b64decode(captured["json"]["data_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert zf.namelist() == ["jobtracker.db"]

    async def test_negativ_backup_deaktiviert_wird_nicht_ausgefuehrt(self, db_session):
        db_session.add(models.BackupConfig(enabled=False, backup_folder="/backups"))
        db_session.commit()

        result = await backup_module.do_backup()

        assert result["success"] is False


class TestRestoreBackup:
    async def test_positiv_zip_backup_stellt_db_und_fernet_key_wieder_her(self, db_session, tmp_path):
        # Ursprungszustand vor dem Restore: andere DB, kein/anderer Key.
        _make_sqlite_file(backup_module.DB_PATH, rows=("alter_zustand",))

        src_db = tmp_path / "src.db"
        _make_sqlite_file(src_db, rows=("wiederhergestellt",))
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.write(src_db, "jobtracker.db")
            zf.writestr("fernet.key", b"restaurierter-schluessel")
        data_b64 = __import__("base64").b64encode(zip_buf.getvalue()).decode()

        async def fake_get(self, url, params=None, **kwargs):
            if url.endswith("/backups"):
                return _mock_response([{"name": "backup.zip", "path": "/backups/backup.zip"}])
            if url.endswith("/backup-read"):
                return _mock_response({"data_b64": data_b64})
            raise AssertionError(f"unerwarteter GET: {url}")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await backup_module.restore_backup(
                backup_module.RestoreRequest(filename="backup.zip", folder="/backups"), db=db_session,
            )

        assert result["success"] is True
        conn = sqlite3.connect(backup_module.DB_PATH)
        rows = conn.execute("SELECT x FROM t").fetchall()
        conn.close()
        assert rows == [("wiederhergestellt",)]
        assert open(backup_module.FERNET_KEY_PATH, "rb").read() == b"restaurierter-schluessel"

    async def test_positiv_alte_db_backups_ohne_zip_bleiben_restorebar(self, db_session, tmp_path):
        # Rückwärtskompatibilität: Backups von vor dem Zip-Bundle-Wechsel sind
        # rohe .db-Dateien ohne Key — dürfen weiterhin restorebar sein.
        _make_sqlite_file(backup_module.DB_PATH, rows=("alter_zustand",))
        (tmp_path / "fernet.key").write_bytes(b"unveraenderter-key")

        src_db = tmp_path / "legacy.db"
        _make_sqlite_file(src_db, rows=("legacy_wiederhergestellt",))
        data_b64 = __import__("base64").b64encode(src_db.read_bytes()).decode()

        async def fake_get(self, url, params=None, **kwargs):
            if url.endswith("/backups"):
                return _mock_response([{"name": "old_backup.db", "path": "/backups/old_backup.db"}])
            if url.endswith("/backup-read"):
                return _mock_response({"data_b64": data_b64})
            raise AssertionError(f"unerwarteter GET: {url}")

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await backup_module.restore_backup(
                backup_module.RestoreRequest(filename="old_backup.db", folder="/backups"), db=db_session,
            )

        assert result["success"] is True
        conn = sqlite3.connect(backup_module.DB_PATH)
        rows = conn.execute("SELECT x FROM t").fetchall()
        conn.close()
        assert rows == [("legacy_wiederhergestellt",)]
        # Alter Key bleibt unangetastet, da das Legacy-Backup keinen enthält.
        assert open(backup_module.FERNET_KEY_PATH, "rb").read() == b"unveraenderter-key"

    async def test_negativ_unbekannte_datei_liefert_404(self, db_session):
        async def fake_get(self, url, params=None, **kwargs):
            return _mock_response([])

        with patch("httpx.AsyncClient.get", new=fake_get):
            with pytest.raises(Exception) as exc_info:
                await backup_module.restore_backup(
                    backup_module.RestoreRequest(filename="nicht_da.zip", folder="/backups"), db=db_session,
                )
        assert "404" in str(exc_info.value) or getattr(exc_info.value, "status_code", None) == 404


class TestRestoreFromFile:
    """Manueller Restore-Weg (Datei-Picker) — muss ohne jede BackupConfig
    funktionieren, insbesondere ohne enabled=True/backup_folder gesetzt."""

    async def test_positiv_restore_funktioniert_ohne_backup_config_ueberhaupt(self, db_session, tmp_path):
        # Bewusst: kein BackupConfig-Eintrag angelegt, kein _enable_backup() Aufruf.
        assert db_session.query(models.BackupConfig).count() == 0
        _make_sqlite_file(backup_module.DB_PATH, rows=("alter_zustand",))

        src_db = tmp_path / "irgendwo.db"
        _make_sqlite_file(src_db, rows=("manuell_wiederhergestellt",))
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.write(src_db, "jobtracker.db")
            zf.writestr("fernet.key", b"manueller-schluessel")
        data_b64 = __import__("base64").b64encode(zip_buf.getvalue()).decode()

        async def fake_get(self, url, params=None, **kwargs):
            assert url.endswith("/backup-read")
            assert params == {"path": "/Users/test/Desktop/mein_backup.zip"}
            return _mock_response({"data_b64": data_b64})

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await backup_module.restore_from_file(
                backup_module.RestoreFileRequest(path="/Users/test/Desktop/mein_backup.zip"),
            )

        assert result["success"] is True
        assert result["filename"] == "mein_backup.zip"
        conn = sqlite3.connect(backup_module.DB_PATH)
        rows = conn.execute("SELECT x FROM t").fetchall()
        conn.close()
        assert rows == [("manuell_wiederhergestellt",)]
        assert open(backup_module.FERNET_KEY_PATH, "rb").read() == b"manueller-schluessel"

    async def test_negativ_leerer_pfad_liefert_400(self):
        with pytest.raises(Exception) as exc_info:
            await backup_module.restore_from_file(backup_module.RestoreFileRequest(path=""))
        assert getattr(exc_info.value, "status_code", None) == 400

    async def test_negativ_bridge_nicht_erreichbar_liefert_500(self, db_session, tmp_path):
        _make_sqlite_file(backup_module.DB_PATH)

        async def fake_get(self, url, params=None, **kwargs):
            return _mock_response({"error": "not found"}, status=404)

        with patch("httpx.AsyncClient.get", new=fake_get):
            with pytest.raises(Exception) as exc_info:
                await backup_module.restore_from_file(
                    backup_module.RestoreFileRequest(path="/does/not/exist.zip"),
                )
        assert getattr(exc_info.value, "status_code", None) == 500
