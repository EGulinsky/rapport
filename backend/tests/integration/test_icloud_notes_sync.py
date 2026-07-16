"""L3 Integration — _do_icloud_notes() in sync_icloud.py end-to-end.

Anders als noch angenommen (siehe Testkonzept-Historie) läuft der AKTIVE
Notizen-Sync (POST /sync/icloud/notes -> sync_notes() -> _do_icloud_notes())
NICHT mehr über die pyicloud-API/2FA-Login, sondern über den lokalen Rapport-
Agenten (app.agent_client.agent_get) — exakt dasselbe Muster wie bei
sync_targeted.py::_sync_icloud_notes_for_app() (siehe
test_sync_targeted_agent_sources.py). Der pyicloud-basierte Pfad
(_sync_notes_with_api/_get_pyicloud_api/sync_notes_legacy) ist unbenutzter
Alt-Code (Frontend ruft nur noch /sync/icloud/notes auf) und bleibt bewusst
ungetestet.
"""
import hashlib
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import models
from app.ai.provider import AINotConfigured, AIRateLimited
from app.routers.sync_icloud import _do_icloud_notes
from tests.factories import application_factory, seed_floor

pytestmark = pytest.mark.integration


def _mock_response(json_data, status=200, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = text
    return resp


class TestDoIcloudNotesNichtVerbunden:
    async def test_negativ_keine_icloud_konfiguration_liefert_klaren_fehler(self, db_session):
        result = await _do_icloud_notes(1)
        assert result["errors"] == ["Keine iCloud-Credentials gespeichert."]
        assert result["created"] == 0


class TestDoIcloudNotesNeueNotizen:
    async def test_positiv_notiz_mit_firmenbezug_wird_angelegt(self, db_session, icloud_sync, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        notes = [{
            "id": "note-1", "name": "Contoso Vorbereitung", "body": "Fragen für das Interview bei Contoso AG.",
            "creationDate": date.today().isoformat(),
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes(1)

        assert result["errors"] == []
        assert result["created"] == 1
        assert db_session.query(models.Event).filter_by(source="icloud_notes").count() == 1

    async def test_negativ_notiz_ohne_body_wird_uebersprungen(self, db_session, icloud_sync, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        notes = [{"id": "note-2", "name": "Leere Notiz", "body": ""}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_negativ_notiz_ohne_firmenbezug_wird_ohne_ai_aufruf_uebersprungen(self, db_session, icloud_sync, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        notes = [{"id": "note-3", "name": "Einkaufsliste", "body": "Milch, Brot, Eier"}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_positiv_mehrere_notizen_ueber_batch_grenze_werden_alle_verarbeitet(self, db_session, icloud_sync, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        # BATCH-Größe in _do_icloud_notes() ist 5 — 7 Notizen decken einen
        # vollständigen + einen Teil-Batch ab.
        notes = [
            {
                "id": f"note-{i}", "name": f"Contoso Notiz {i}", "body": f"Interview-Vorbereitung Contoso AG #{i}",
                "creationDate": date.today().isoformat(),
            }
            for i in range(7)
        ]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes(1)

        assert result["errors"] == []
        assert result["created"] == 7

    async def test_negativ_bereits_synctes_liefert_skip_ohne_erneute_verarbeitung(self, db_session, icloud_sync, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        note_key = hashlib.md5(b"note-already").hexdigest()[:16]
        db_session.add(models.SyncedItem(source="icloud_notes", external_id=note_key, user_id=1))
        db_session.commit()
        notes = [{"id": "note-already", "name": "Contoso Vorbereitung", "body": "Fragen für das Interview bei Contoso AG."}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_corner_case_kaputtes_datumsfeld_wird_ohne_absturz_uebersprungen(self, db_session, icloud_sync, monkeypatch):
        # An unparseable creationDate means no date at all — "if there is
        # absolutely no date available, do not sync timed events at all"
        # (2026-07-16) — excluded even with a floor present, no crash either.
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        db_session.commit()
        notes = [{
            "id": "note-baddate", "name": "Contoso Vorbereitung",
            "body": "Fragen für das Interview bei Contoso AG.", "creationDate": "kein-gueltiges-datum",
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes(1)

        assert result["errors"] == []
        assert result["created"] == 0
        assert db_session.query(models.Event).filter_by(source="icloud_notes").count() == 0

    async def test_negativ_ai_not_configured_innerhalb_batch_beendet_sync_sauber(
        self, db_session, icloud_sync, monkeypatch
    ):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        notes = [{"id": "note-ai-1", "name": "Contoso Vorbereitung", "body": "Interview bei Contoso AG."}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AINotConfigured("kein Provider konfiguriert")),
        )

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert any("kein Provider konfiguriert" in e for e in result["errors"])

    async def test_negativ_ai_rate_limited_innerhalb_batch_beendet_sync_sauber(
        self, db_session, icloud_sync, monkeypatch
    ):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        notes = [{"id": "note-ai-2", "name": "Contoso Vorbereitung", "body": "Interview bei Contoso AG."}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AIRateLimited("Tageslimit erreicht")),
        )

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert any("AI-Tageslimit" in e for e in result["errors"])

    async def test_negativ_unerwarteter_fehler_innerhalb_batch_stoppt_nicht_den_gesamten_sync(
        self, db_session, icloud_sync, monkeypatch
    ):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        notes = [{"id": "note-ai-3", "name": "Contoso Vorbereitung", "body": "Interview bei Contoso AG."}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=RuntimeError("process-item-boom")),
        )

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert any("process-item-boom" in e for e in result["errors"])


class TestDoIcloudNotesFehler:
    async def test_negativ_agent_nicht_erreichbar_liefert_sauberen_fehler(self, db_session, icloud_sync, monkeypatch):
        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        monkeypatch.setattr("httpx.AsyncClient.get", raise_conn_error)

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert any("nicht erreichbar" in e for e in result["errors"])

    async def test_negativ_agent_http_fehler_liefert_sauberen_fehler(self, db_session, icloud_sync, monkeypatch):
        async def fake_get(self, url, **kw):
            return _mock_response({"error": "kaputt"}, status=500, text="kaputt")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes(1)

        assert result["created"] == 0
        assert any("Agent-Fehler (Notizen)" in e for e in result["errors"])
