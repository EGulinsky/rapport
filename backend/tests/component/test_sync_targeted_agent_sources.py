"""L1 Component — _sync_icloud_notes_for_app()/_sync_calls_for_app() in
sync_targeted.py. Beide sprechen nicht direkt mit iCloud, sondern über den
lokalen Rapport-Agenten (`app.agent_client.agent_get`) — dieselbe Mocking-
Grenze wie in tests/unit/test_agent_client.py (httpx.AsyncClient.get direkt
patchen, keine IMAP/CalDAV-Infrastruktur nötig).
"""
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app import models
from app.routers.sync_targeted import _sync_calls_for_app, _sync_icloud_notes_for_app
from tests.factories import application_factory, contact_factory, event_factory

pytestmark = pytest.mark.component


def _mock_response(json_data, status=200, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = text
    return resp


class TestSyncIcloudNotesForApp:
    async def test_positiv_textmatch_note_wird_angelegt(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        event_factory(db_session, app, datum=date.today() - timedelta(days=10), source="icloud_mail")
        db_session.commit()
        notes = [{
            "id": "note-1", "name": "Contoso Vorbereitung", "body": "Fragen für das Interview bei Contoso.",
            "creationDate": date.today().isoformat(),
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_icloud_notes_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG", "Contoso"], db_session,
        )

        assert errors == []
        assert created == 1
        assert total == 1
        db_session.flush()
        ev = db_session.query(models.Event).filter_by(source="icloud_notes").one()
        assert ev.application_id == app.id

    async def test_negativ_note_ohne_textmatch_wird_nicht_beruecksichtigt(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        notes = [{"id": "note-1", "name": "Einkaufsliste", "body": "Milch, Brot, Eier"}]

        async def fake_get(self, url, **kw):
            return _mock_response(notes)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_icloud_notes_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG", "Contoso"], db_session,
        )

        assert (created, total, errors) == (0, 0, [])

    async def test_negativ_agent_nicht_erreichbar_liefert_sauberen_fehler(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")

        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        monkeypatch.setattr("httpx.AsyncClient.get", raise_conn_error)

        created, total, errors = await _sync_icloud_notes_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG"], db_session,
        )

        assert created == 0
        assert any("nicht erreichbar" in e for e in errors)

    async def test_negativ_agent_http_fehler_liefert_sauberen_fehler(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")

        async def fake_get(self, url, **kw):
            return _mock_response({}, status=500, text="Internal Server Error")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_icloud_notes_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG"], db_session,
        )

        assert created == 0
        assert any("Agent (Notizen)" in e for e in errors)


class TestSyncCallsForApp:
    async def test_negativ_ohne_kontakte_wird_uebersprungen_ohne_agent_aufruf(self, db_session, monkeypatch):
        app = application_factory(db_session)
        called = False

        async def fake_get(self, url, **kw):
            nonlocal called
            called = True
            return _mock_response([])

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_calls_for_app(app, {"id": app.id}, db_session)

        assert (created, total, errors) == (0, 0, [])
        assert called is False

    async def test_positiv_anruf_von_bekannter_telefonnummer_wird_angelegt(self, db_session, monkeypatch):
        app = application_factory(db_session)
        # Anchor predates the hardcoded call date below (2026-07-01).
        event_factory(db_session, app, datum=date(2026, 1, 1), source="icloud_mail")
        contact = contact_factory(db_session, telefon="0151 2345678", name="Erika Musterfrau")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-1", "phone": "+491512345678", "direction": "incoming",
            "answered": True, "duration_s": 125, "date": "2026-07-01T10:00:00+00:00",
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_calls_for_app(app, {"id": app.id}, db_session)

        assert errors == []
        assert created == 1
        db_session.flush()
        ev = db_session.query(models.Event).filter_by(source="icloud_calls", application_id=app.id).one()
        assert "Erika Musterfrau" in ev.titel

    async def test_positiv_datum_zeit_wird_aus_anruf_zeitstempel_gesetzt(self, db_session, monkeypatch):
        # Event.datum stays date-only; datum_zeit carries the full call
        # timestamp so same-day calls sort in real chronological order
        # instead of by coincidental sync/insertion order.
        from datetime import datetime as dt

        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 1, 1), source="icloud_mail")
        contact = contact_factory(db_session, telefon="0151 2345678", name="Erika Musterfrau")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-3", "phone": "+491512345678", "direction": "incoming",
            "answered": True, "duration_s": 60, "date": "2026-07-01T14:32:00+00:00",
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        await _sync_calls_for_app(app, {"id": app.id}, db_session)

        ev = db_session.query(models.Event).filter_by(source="icloud_calls", application_id=app.id).one()
        assert ev.datum == date(2026, 7, 1)
        assert ev.datum_zeit == dt(2026, 7, 1, 14, 32, 0)

    async def test_positiv_anruf_titel_zeigt_vornamen_bei_getrenntem_kontaktnamen(self, db_session, monkeypatch):
        # Regression: contacts with a structured vorname/name split (the
        # common case, e.g. from vCard imports) only showed the surname in
        # the call event title — the title was built from the bare Contact.name
        # column instead of the combined display name.
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 1, 1), source="icloud_mail")
        contact = contact_factory(db_session, telefon="0151 2345678", name="Zoch", vorname="Niklas")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-2", "phone": "+491512345678", "direction": "incoming",
            "answered": True, "duration_s": 90, "date": "2026-07-01T10:00:00+00:00",
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_calls_for_app(app, {"id": app.id}, db_session)

        assert errors == []
        assert created == 1
        db_session.flush()
        ev = db_session.query(models.Event).filter_by(source="icloud_calls", application_id=app.id).one()
        assert "Niklas Zoch" in ev.titel

    async def test_positiv_anruf_titel_bevorzugt_kontaktnamen_vor_unvollstaendigem_agentennamen(self, db_session, monkeypatch):
        # Regression: even after the previous fix, an incomplete raw name
        # supplied by the OS/agent (e.g. the phone's local address book only
        # has a surname saved) still won over our own, more complete contact
        # record — live-reported: "Anruf von Fallnich" instead of
        # "Fallnich Bjoern" despite the contact having vorname="Bjoern".
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 1, 1), source="icloud_mail")
        contact = contact_factory(db_session, telefon="0151 2345678", name="Fallnich", vorname="Bjoern")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{
            "id": "call-3", "phone": "+491512345678", "direction": "incoming",
            "answered": True, "duration_s": 30, "date": "2026-07-01T10:00:00+00:00",
            "name": "Fallnich",  # incomplete raw name from the OS/agent
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_calls_for_app(app, {"id": app.id}, db_session)

        assert errors == []
        assert created == 1
        db_session.flush()
        ev = db_session.query(models.Event).filter_by(source="icloud_calls", application_id=app.id).one()
        assert "Bjoern Fallnich" in ev.titel

    async def test_negativ_anruf_vor_fruehestem_ereignis_wird_ausgefiltert(self, db_session, monkeypatch):
        # Regression test for the #230 incident (2026-07-16): calls sync had
        # NO date filtering at all before this. Revised the same day: the
        # floor is now the earliest DATED EVENT already in the timeline
        # (not datum_bewerbung) — an existing event establishes it, and a
        # call from well before that must be excluded.
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date.today() - timedelta(days=10), source="icloud_mail")
        contact = contact_factory(db_session, telefon="0151 2345678", name="Erika Musterfrau")
        app.contacts.append(contact)
        db_session.commit()

        old_call_date = date.today() - timedelta(days=60)
        calls = [{
            "id": "call-old", "phone": "+491512345678", "direction": "incoming",
            "answered": True, "duration_s": 60, "date": f"{old_call_date.isoformat()}T10:00:00+00:00",
        }]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_calls_for_app(app, {"id": app.id}, db_session)

        assert errors == []
        assert created == 0
        assert db_session.query(models.Event).filter_by(source="icloud_calls").first() is None

    async def test_negativ_anruf_von_unbekannter_nummer_wird_uebersprungen(self, db_session, monkeypatch):
        app = application_factory(db_session)
        contact = contact_factory(db_session, telefon="0151 2345678")
        app.contacts.append(contact)
        db_session.commit()

        calls = [{"id": "call-1", "phone": "+490000000000", "direction": "incoming", "answered": True}]

        async def fake_get(self, url, **kw):
            return _mock_response(calls)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        created, total, errors = await _sync_calls_for_app(app, {"id": app.id}, db_session)

        assert created == 0
        assert db_session.query(models.Event).filter_by(source="icloud_calls").first() is None

    async def test_negativ_agent_nicht_erreichbar_liefert_sauberen_fehler(self, db_session, monkeypatch):
        app = application_factory(db_session)
        contact = contact_factory(db_session, telefon="0151 2345678")
        app.contacts.append(contact)
        db_session.commit()

        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        monkeypatch.setattr("httpx.AsyncClient.get", raise_conn_error)

        created, total, errors = await _sync_calls_for_app(app, {"id": app.id}, db_session)

        assert created == 0
        assert any("nicht erreichbar" in e for e in errors)
