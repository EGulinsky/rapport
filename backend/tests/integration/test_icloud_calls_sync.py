"""L3 Integration — _do_icloud_calls() in sync_icloud.py end-to-end.

Wie beim Notizen-Sync (test_icloud_notes_sync.py) läuft die Anrufliste NICHT
über IMAP/CalDAV, sondern über den lokalen Rapport-Agenten
(app.agent_client.agent_get, GET /calls) — dieselbe httpx.AsyncClient.get-
Mocking-Grenze. Ein Anruf wird nur übernommen, wenn er sich per Telefonnummer
oder (Fallback) per Namens-Tokens einem bestehenden Kontakt zuordnen lässt,
UND dieser Kontakt an mindestens eine Bewerbung verlinkt ist.
"""
from datetime import date
from unittest.mock import MagicMock

import pytest

from app import models
from app.routers.sync_icloud import _do_icloud_calls
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.integration


def _mock_response(json_data, status=200, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


def _calls_cfg(db_session, enabled=True) -> models.CallsConfig:
    cfg = models.CallsConfig(enabled=enabled, user_id=1)
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestDoIcloudCallsDeaktiviert:
    async def test_negativ_deaktivierter_sync_liefert_klaren_hinweis(self, db_session):
        _calls_cfg(db_session, enabled=False)

        result = await _do_icloud_calls(1)

        assert result["errors"] == ["Anrufliste-Sync deaktiviert"]
        assert result["created"] == 0


class TestDoIcloudCallsNeueAnrufe:
    async def test_positiv_anruf_matcht_kontakt_per_telefonnummer_und_wird_angelegt(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        # datum_bewerbung pinned explicitly, safely before the call's own
        # date below — application_factory()'s random default (0-60 days
        # back) could otherwise land after it and make this test flaky now
        # that calls sync is date-filtered (see _predates_bewerbung).
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date(2026, 1, 1))
        contact = contact_factory(db_session, name="Erika Musterfrau", telefon="+49 172 1234567")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-1", "phone": "0172 1234567", "name": "", "date": "2026-07-01T10:00:00",
            "duration_s": 125, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_calls").one()
        assert event.typ == "anruf"
        assert "Erika Musterfrau" in event.titel
        assert "2:05 min" in event.notiz

    async def test_negativ_anruf_vor_bewerbungsdatum_wird_ausgefiltert(self, db_session, monkeypatch):
        # Regression test for the #230 incident (2026-07-16): bulk calls
        # sync had NO date filtering at all before this — any call, ever,
        # matching a contact's phone/name got attributed to every
        # application that contact links to. datum_bewerbung is left unset
        # here (a real, reachable state — see create_application()'s
        # docstring) and letztes_update is the fallback floor.
        _calls_cfg(db_session)
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=None, letztes_update=date(2026, 6, 1))
        contact = contact_factory(db_session, name="Erika Musterfrau", telefon="+49 172 1234567")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-old", "phone": "0172 1234567", "name": "", "date": "2026-01-01T10:00:00",
            "duration_s": 60, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["errors"] == []
        assert result["created"] == 0
        assert db_session.query(models.Event).filter_by(source="icloud_calls").first() is None

    async def test_positiv_ausgehender_verpasster_anruf_hat_eigenen_titel(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date(2026, 1, 1))
        contact = contact_factory(db_session, name="Erika Musterfrau", telefon="+49 172 1234567")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-2", "phone": "0172 1234567", "name": "", "date": "2026-07-01T10:00:00",
            "duration_s": 0, "direction": "outgoing", "answered": False,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_calls").one()
        assert "Verpasst" in event.titel
        assert "↗" in event.titel

    async def test_positiv_anruf_ohne_telefon_match_faellt_auf_namens_match_zurueck(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date(2026, 1, 1))
        contact = contact_factory(db_session, name="Erika Musterfrau", telefon=None)
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-3", "phone": "", "name": "Erika Musterfrau", "date": "2026-07-01T10:00:00",
            "duration_s": 30, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["created"] == 1

    async def test_negativ_anruf_ohne_kontaktmatch_wird_uebersprungen(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        calls = [{
            "id": "call-4", "phone": "0151 00000000", "name": "Unbekannt", "date": "2026-07-01T10:00:00",
            "duration_s": 10, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_negativ_kontakt_ohne_bewerbungsverknuepfung_wird_uebersprungen(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        contact_factory(db_session, name="Erika Musterfrau", telefon="+49 172 1234567")
        db_session.commit()

        calls = [{
            "id": "call-5", "phone": "0172 1234567", "name": "", "date": "2026-07-01T10:00:00",
            "duration_s": 10, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_negativ_bereits_synctes_liefert_skip_ohne_erneute_verarbeitung(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        app = application_factory(db_session, firma="Contoso AG")
        contact = contact_factory(db_session, name="Erika Musterfrau", telefon="+49 172 1234567")
        app.contacts.append(contact)
        db_session.add(models.SyncedItem(source="icloud_calls", external_id="icloud_calls:call-6", user_id=1))
        db_session.commit()

        calls = [{
            "id": "call-6", "phone": "0172 1234567", "name": "", "date": "2026-07-01T10:00:00",
            "duration_s": 10, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_corner_case_ungueltiges_datum_wird_ohne_absturz_ignoriert(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        app = application_factory(db_session, firma="Contoso AG")
        contact = contact_factory(db_session, name="Erika Musterfrau", telefon="+49 172 1234567")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-7", "phone": "0172 1234567", "name": "", "date": "kein-datum",
            "duration_s": 10, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_calls").one()
        assert event.datum is None


    async def test_negativ_unerwarteter_fehler_wird_gesammelt_statt_absturz(self, db_session, monkeypatch):
        _calls_cfg(db_session)
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date(2026, 1, 1))
        contact = contact_factory(db_session, name="Erika Musterfrau", telefon="+49 172 1234567")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-boom", "phone": "0172 1234567", "name": "", "date": "2026-07-01T10:00:00",
            "duration_s": 10, "direction": "incoming", "answered": True,
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
        monkeypatch.setattr(
            "app.routers.sync_icloud._mark_synced",
            lambda db, source, external_id, user_id=None: (_ for _ in ()).throw(RuntimeError("mark-synced-boom")),
        )

        result = await _do_icloud_calls(1)

        assert any("mark-synced-boom" in e for e in result["errors"])


class TestDoIcloudCallsFehler:
    async def test_negativ_agent_nicht_erreichbar_liefert_sauberen_fehler(self, db_session, monkeypatch):
        _calls_cfg(db_session)

        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        monkeypatch.setattr("httpx.AsyncClient.get", raise_conn_error)

        result = await _do_icloud_calls(1)

        assert result["created"] == 0
        assert any("Rapport Agent nicht erreichbar" in e for e in result["errors"])

    async def test_negativ_agent_http_fehler_liefert_sauberen_fehler(self, db_session, monkeypatch):
        _calls_cfg(db_session)

        async def fake_get(self, url, **kw):
            return _mock_response({"error": "kaputt"}, status=500, text="kaputt")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_icloud_calls(1)

        assert result["created"] == 0
        assert any("Rapport Agent nicht erreichbar" in e for e in result["errors"])
