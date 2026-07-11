"""L1 Component — _background_sync_loop() in main.py.

Die Schleife läuft endlos (asyncio.sleep(_BG_INTERVAL_MINUTES * 60) am Ende
jeder Iteration) — asyncio.sleep wird gepatcht, damit der zweite Aufruf
(die Schlaf-Anweisung am Iterationsende) eine Exception wirft und die
Funktion nach genau einem Durchlauf verlässt. Die eigentlichen _do_*-Sync-
Funktionen werden gemockt (ihre Sync-Logik ist bereits anderweitig getestet);
hier geht es nur um die Verkabelung: welche Quellen werden je nach
SyncSettings aufgerufen, Backup-Fälligkeit, Fehler-Resilienz.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app import models
from app.main import _background_sync_loop

pytestmark = pytest.mark.component


class _StopLoop(Exception):
    pass


def _fake_sleep_stop_after_second_call(monkeypatch):
    calls = {"n": 0}

    async def fake_sleep(seconds):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise _StopLoop()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return calls


class TestBackgroundSyncLoop:
    async def test_negativ_kein_registriertes_konto_wartet_ohne_sync(self, db_session, monkeypatch):
        _fake_sleep_stop_after_second_call(monkeypatch)

        with pytest.raises(_StopLoop):
            await _background_sync_loop()

    async def test_positiv_ruft_aktivierte_quellen_auf(self, db_session, monkeypatch):
        db_session.add(models.User(id=1, email="user@example.com", password_hash="x", email_verified=True))
        db_session.add(models.SyncSettings(
            user_id=1, google_enabled=True, gmail_enabled=True, gcal_enabled=False,
            icloud_enabled=False, files_enabled=False,
        ))
        db_session.commit()

        _fake_sleep_stop_after_second_call(monkeypatch)

        fake_do_gmail = AsyncMock(return_value={"created": 0})
        monkeypatch.setattr("app.routers.sync_google._do_gmail", fake_do_gmail)
        monkeypatch.setattr("app.routers.sync_google._do_gcal", AsyncMock())
        monkeypatch.setattr("app.routers.sync_icloud._do_icloud_mail", AsyncMock())
        monkeypatch.setattr("app.routers.sync_icloud._do_icloud_cal", AsyncMock())
        monkeypatch.setattr("app.routers.sync_icloud._do_icloud_notes", AsyncMock())
        monkeypatch.setattr("app.routers.sync_icloud._do_icloud_reminders", AsyncMock())
        monkeypatch.setattr("app.routers.sync_icloud._do_icloud_calls", AsyncMock())
        monkeypatch.setattr("app.routers.sync_files._do_local_files", AsyncMock())

        with pytest.raises(_StopLoop):
            await _background_sync_loop()

        fake_do_gmail.assert_called_once_with(1)

    async def test_positiv_faellige_backup_wird_ausgefuehrt(self, db_session, monkeypatch):
        db_session.add(models.User(id=1, email="user@example.com", password_hash="x", email_verified=True))
        db_session.add(models.SyncSettings(
            user_id=1, google_enabled=False, icloud_enabled=False, files_enabled=False,
        ))
        db_session.add(models.BackupConfig(
            user_id=1, enabled=True, backup_folder="/tmp/backup", frequency_hours=24,
            last_backup=datetime.now(timezone.utc) - timedelta(hours=48),
        ))
        db_session.commit()

        _fake_sleep_stop_after_second_call(monkeypatch)

        fake_do_backup = AsyncMock()
        monkeypatch.setattr("app.routers.backup.do_backup", fake_do_backup)

        with pytest.raises(_StopLoop):
            await _background_sync_loop()

        fake_do_backup.assert_called_once_with(1)

    async def test_negativ_nicht_faellige_backup_wird_uebersprungen(self, db_session, monkeypatch):
        db_session.add(models.User(id=1, email="user@example.com", password_hash="x", email_verified=True))
        db_session.add(models.SyncSettings(
            user_id=1, google_enabled=False, icloud_enabled=False, files_enabled=False,
        ))
        db_session.add(models.BackupConfig(
            user_id=1, enabled=True, backup_folder="/tmp/backup", frequency_hours=24,
            last_backup=datetime.now(timezone.utc),
        ))
        db_session.commit()

        _fake_sleep_stop_after_second_call(monkeypatch)

        fake_do_backup = AsyncMock()
        monkeypatch.setattr("app.routers.backup.do_backup", fake_do_backup)

        with pytest.raises(_StopLoop):
            await _background_sync_loop()

        fake_do_backup.assert_not_called()

    async def test_negativ_fehler_in_iteration_wird_geschluckt_und_naechste_iteration_erreicht(self, db_session, monkeypatch):
        db_session.add(models.User(id=1, email="user@example.com", password_hash="x", email_verified=True))
        db_session.commit()

        calls = {"n": 0}

        async def fake_sleep(seconds):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise _StopLoop()

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        def _raise(*a, **kw):
            raise RuntimeError("kaputte Query")

        monkeypatch.setattr("app.database.get_first_user_id", _raise)

        with pytest.raises(_StopLoop):
            await _background_sync_loop()  # darf trotz Fehler bis zum finalen sleep() kommen
