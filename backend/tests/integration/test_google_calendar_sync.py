"""L3 Integration — _do_gcal() in sync_google.py end-to-end.

Mockt an der Netzwerkgrenze (googleapiclient.discovery.build, siehe
tests/integration/conftest.py::fake_google_calendar), nicht die eigene
Sync-Logik — testet damit Kontakt-Matching, Änderungserkennung und die
Löschung verwaister Termine als vollständigen Fluss. Kalender-Events werden
laut _classify_deterministic() immer deterministisch (kein AI-Call) als
"gespräch" klassifiziert, sobald ein Kontakt-Match existiert.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_google import _do_gcal
from tests.factories import application_factory, contact_factory, seed_floor

pytestmark = pytest.mark.integration


def _cal_event(event_id: str, summary: str, organizer_email: str, days_from_now: int = 0) -> dict:
    dt = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    return {
        "id": event_id,
        "summary": summary,
        "description": "",
        "location": "",
        "start": {"dateTime": dt.isoformat()},
        "organizer": {"email": organizer_email, "displayName": "Recruiterin"},
        "attendees": [],
    }


class TestDoGcalNichtVerbunden:
    async def test_negativ_keine_google_konfiguration_liefert_klaren_fehler(self, db_session):
        # Bewusst kein google_sync-Fixture — es existiert keine GoogleSync-Zeile.
        result = await _do_gcal(1)

        assert result["errors"] == ["Nicht mit Google verbunden."]
        assert result["created"] == 0

    async def test_corner_case_konfiguration_ohne_refresh_token_gilt_als_nicht_verbunden(self, db_session):
        db_session.add(models.GoogleSync(client_id="x", client_secret_enc="y", refresh_token_enc=None))
        db_session.commit()

        result = await _do_gcal(1)

        assert result["errors"] == ["Nicht mit Google verbunden."]


class TestDoGcalNeueTermine:
    async def test_positiv_termin_mit_bekanntem_kontakt_wird_als_gespraech_angelegt(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session, firma="Contoso AG")
        seed_floor(db_session, app)
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        fake_google_calendar([_cal_event("evt-1", "Interview Runde 1", "recruiterin@contoso.com")])

        result = await _do_gcal(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="gcal", external_id="evt-1").one()
        assert event.typ == "gespräch"
        assert event.titel == "Interview Runde 1"
        assert event.application_id == app.id
        # Organizer (see _cal_event()) ends up in Event.autor via the
        # "Teilnehmer: ..." line -- lets a contact's Calendar tab
        # (ContactModal.tsx) match this event back to them by email address.
        assert event.autor == "Recruiterin <recruiterin@contoso.com>"

    async def test_negativ_termin_ohne_kontakt_match_wird_uebersprungen(self, db_session, google_sync, fake_google_calendar):
        application_factory(db_session)
        db_session.commit()  # _do_gcal() öffnet eine eigene Session — ohne Commit blockiert SQLite bis busy_timeout
        fake_google_calendar([_cal_event("evt-2", "Zahnarzttermin", "praxis@unbekannt.de")])

        result = await _do_gcal(1)

        assert result["created"] == 0
        assert result["skipped"] == 1
        assert db_session.query(models.Event).filter_by(source="gcal", external_id="evt-2").first() is None

    async def test_negativ_calendar_api_fehler_liefert_sauberen_fehler_statt_crash(
        self, db_session, google_sync, fake_google_calendar
    ):
        service = fake_google_calendar([])

        def _raise(**kwargs):
            raise RuntimeError("503 Service Unavailable")

        service.execute = _raise

        result = await _do_gcal(1)

        assert result["created"] == 0
        assert any("Calendar API Fehler" in e for e in result["errors"])


class TestDoGcalAenderungserkennungUndVerwaisteTermine:
    async def test_positiv_geaenderter_titel_wird_bei_bereits_synctem_termin_aktualisiert(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session, datum_bewerbung=date.today() - timedelta(days=30))
        existing = models.Event(
            application_id=app.id, typ="gespräch", titel="Altes Thema",
            datum=date.today(), source="gcal", external_id="evt-3", user_id=1,
        )
        db_session.add(existing)
        db_session.add(models.SyncedItem(source="gcal", external_id="evt-3", user_id=1))
        db_session.commit()

        fake_google_calendar([_cal_event("evt-3", "Neues Thema (verschoben)", "irrelevant@x.de")])

        result = await _do_gcal(1)

        assert result["skipped"] == 1  # bereits synced, aber Titel wird trotzdem aktualisiert
        db_session.refresh(existing)
        assert existing.titel == "Neues Thema (verschoben)"

    async def test_positiv_verwaister_termin_ausserhalb_des_aktuellen_kalenders_wird_geloescht(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session, datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        orphan = models.Event(
            application_id=app.id, typ="gespräch", titel="Abgesagter Termin",
            datum=date.today(), source="gcal", external_id="evt-orphan", user_id=1,
        )
        db_session.add(orphan)
        db_session.add(models.SyncedItem(source="gcal", external_id="evt-orphan", user_id=1))
        db_session.commit()

        # Aktueller Kalenderabruf enthält "evt-orphan" nicht mehr (z.B. gelöscht/verschoben) —
        # uid_set ist trotzdem nicht leer, da ein anderer Termin zurückkommt.
        fake_google_calendar([_cal_event("evt-1", "Interview Runde 1", "recruiterin@contoso.com")])

        await _do_gcal(1)

        assert db_session.query(models.Event).filter_by(external_id="evt-orphan").first() is None
        assert db_session.query(models.SyncedItem).filter_by(source="gcal", external_id="evt-orphan").first() is None
