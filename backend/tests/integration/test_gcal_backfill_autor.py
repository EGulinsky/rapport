"""L3 Integration — backfill_gcal_autor() in sync_google.py.

Mocks at the network boundary (googleapiclient.discovery.build, via
fake_google_calendar's get_events/batch_errors params), not the sync logic
itself. Only the batched events().get() path is exercised here -- no
.list() call, since the backfill already knows which event IDs to
re-fetch from Event.external_id.
"""
from datetime import date

import pytest

from app import models
from app.routers.sync_google import backfill_gcal_autor
from tests.factories import application_factory

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """backfill_gcal_autor() sleeps between batches/retries to stay under
    Google's per-user concurrent-request limit -- irrelevant against the
    fake service, so skip the real delay to keep the suite fast."""
    monkeypatch.setattr("app.routers.sync_google.time.sleep", lambda _seconds: None)


def _gcal_event(db, app, external_id, autor=None):
    event = models.Event(
        application_id=app.id, typ="gespräch", datum=date(2026, 7, 14),
        titel="Kennen lernen", source="gcal", external_id=external_id, autor=autor,
        user_id=app.user_id,
    )
    db.add(event)
    db.flush()
    return event


class TestBackfillGcalAutorNichtVerbunden:
    def test_negativ_keine_google_konfiguration_liefert_klaren_fehler(self, db_session):
        result = backfill_gcal_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": ["Nicht mit Google verbunden."]}


class TestBackfillGcalAutorKeineBetroffenenEvents:
    def test_negativ_kein_api_aufruf_wenn_nichts_zu_tun_ist(self, db_session, google_sync):
        result = backfill_gcal_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}


class TestBackfillGcalAutorPositiv:
    def test_positiv_autor_wird_aus_organizer_und_attendees_gesetzt(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session, firma="Qorix")
        db_session.commit()
        event = _gcal_event(db_session, app, "evt-1")

        get_events = {"evt-1": {
            "id": "evt-1",
            "organizer": {"email": "organizer@qorix.ai", "displayName": "Organizer"},
            "attendees": [{"email": "eugen@example.com", "displayName": "Eugen Gulinsky"}],
        }}
        fake_google_calendar([], get_events=get_events)

        result = backfill_gcal_autor(db_session, user_id=1)

        assert result["errors"] == []
        assert result["updated"] == 1
        db_session.refresh(event)
        assert event.autor == "Organizer <organizer@qorix.ai>, Eugen Gulinsky <eugen@example.com>"

    def test_negativ_kein_autor_ohne_organizer_oder_attendees(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session, firma="Qorix")
        db_session.commit()
        event = _gcal_event(db_session, app, "evt-2")

        fake_google_calendar([], get_events={"evt-2": {"id": "evt-2"}})

        result = backfill_gcal_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        db_session.refresh(event)
        assert event.autor is None

    def test_negativ_bereits_gesetztes_autor_bleibt_unveraendert(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session)
        db_session.commit()
        event = _gcal_event(db_session, app, "evt-3", autor="Old <old@example.com>")

        fake_google_calendar([], get_events={})

        result = backfill_gcal_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        db_session.refresh(event)
        assert event.autor == "Old <old@example.com>"

    def test_negativ_icloud_cal_events_werden_nicht_angefasst(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session)
        db_session.commit()
        event = models.Event(
            application_id=app.id, typ="gespräch", datum=date(2026, 7, 14),
            titel="Termin", source="icloud_cal", external_id="evt-4", autor=None,
            user_id=app.user_id,
        )
        db_session.add(event)
        db_session.commit()

        fake_google_calendar([], get_events={})

        result = backfill_gcal_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        db_session.refresh(event)
        assert event.autor is None

    def test_corner_case_zweiter_lauf_findet_nichts_mehr(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session, firma="Qorix")
        db_session.commit()
        _gcal_event(db_session, app, "evt-5")

        get_events = {"evt-5": {
            "id": "evt-5",
            "organizer": {"email": "person@qorix.ai"},
        }}
        service = fake_google_calendar([], get_events=get_events)
        backfill_gcal_autor(db_session, user_id=1)

        service2 = fake_google_calendar([], get_events={})
        result = backfill_gcal_autor(db_session, user_id=1)

        assert result == {"updated": 0, "errors": []}
        assert service is not service2

    def test_negativ_dauerhafter_fehler_wird_nach_allen_versuchen_gemeldet(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session)
        db_session.commit()
        event = _gcal_event(db_session, app, "evt-6")

        fake_google_calendar([], get_events={}, batch_errors={"evt-6": Exception("429 rate limited")})

        result = backfill_gcal_autor(db_session, user_id=1)

        assert result["updated"] == 0
        assert len(result["errors"]) == 1
        assert "evt-6" in result["errors"][0]
        db_session.refresh(event)
        assert event.autor is None

    def test_positiv_mehr_als_eine_batch_wird_vollstaendig_verarbeitet(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session, firma="Qorix")
        db_session.commit()
        events = [_gcal_event(db_session, app, f"evt-bulk-{i}") for i in range(20)]

        get_events = {
            f"evt-bulk-{i}": {"id": f"evt-bulk-{i}", "organizer": {"email": f"person{i}@qorix.ai"}}
            for i in range(20)
        }
        fake_google_calendar([], get_events=get_events)

        result = backfill_gcal_autor(db_session, user_id=1)

        assert result == {"updated": 20, "errors": []}
        for i, event in enumerate(events):
            db_session.refresh(event)
            assert event.autor == f"person{i}@qorix.ai"

    def test_positiv_ohne_displayname_wird_nur_email_verwendet(
        self, db_session, google_sync, fake_google_calendar
    ):
        app = application_factory(db_session)
        db_session.commit()
        event = _gcal_event(db_session, app, "evt-7")

        fake_google_calendar([], get_events={"evt-7": {"id": "evt-7", "organizer": {"email": "bare@example.com"}}})

        backfill_gcal_autor(db_session, user_id=1)

        db_session.refresh(event)
        assert event.autor == "bare@example.com"
