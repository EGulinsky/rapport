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
from unittest.mock import MagicMock

import pytest

from app import models
from app.routers.sync_icloud import _do_icloud_notes
from tests.factories import application_factory

pytestmark = pytest.mark.integration


def _mock_response(json_data, status=200, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = text
    return resp


class TestDoIcloudNotesNichtVerbunden:
    async def test_negativ_keine_icloud_konfiguration_liefert_klaren_fehler(self, db_session):
        result = await _do_icloud_notes()
        assert result["errors"] == ["Keine iCloud-Credentials gespeichert."]
        assert result["created"] == 0


class TestDoIcloudNotesNeueNotizen:
    async def test_positiv_notiz_mit_firmenbezug_wird_angelegt(self, db_session, icloud_sync, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        notes = [{"id": "note-1", "name": "Contoso Vorbereitung", "body": "Fragen für das Interview bei Contoso AG."}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes()

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

        result = await _do_icloud_notes()

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_negativ_notiz_ohne_firmenbezug_wird_ohne_ai_aufruf_uebersprungen(self, db_session, icloud_sync, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        notes = [{"id": "note-3", "name": "Einkaufsliste", "body": "Milch, Brot, Eier"}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes()

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_positiv_mehrere_notizen_ueber_batch_grenze_werden_alle_verarbeitet(self, db_session, icloud_sync, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        # BATCH-Größe in _do_icloud_notes() ist 5 — 7 Notizen decken einen
        # vollständigen + einen Teil-Batch ab.
        notes = [
            {"id": f"note-{i}", "name": f"Contoso Notiz {i}", "body": f"Interview-Vorbereitung Contoso AG #{i}"}
            for i in range(7)
        ]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes()

        assert result["errors"] == []
        assert result["created"] == 7


class TestDoIcloudNotesFehler:
    async def test_negativ_agent_nicht_erreichbar_liefert_sauberen_fehler(self, db_session, icloud_sync, monkeypatch):
        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        monkeypatch.setattr("httpx.AsyncClient.get", raise_conn_error)

        result = await _do_icloud_notes()

        assert result["created"] == 0
        assert any("nicht erreichbar" in e for e in result["errors"])

    async def test_negativ_agent_http_fehler_liefert_sauberen_fehler(self, db_session, icloud_sync, monkeypatch):
        async def fake_get(self, url, **kw):
            return _mock_response({"error": "kaputt"}, status=500, text="kaputt")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_notes()

        assert result["created"] == 0
        assert any("Agent-Fehler (Notizen)" in e for e in result["errors"])
