"""L2 API — GET /api/calendar/events: liefert Termine für die Kalenderansicht,
gefiltert auf Events mit Kalender-Quelle (gcal/icloud_cal) oder Kalender-Typ
(gespräch/interview/termin), innerhalb eines optionalen Datumsbereichs.
"""
from datetime import date

import pytest

from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.api


class TestGetCalendarEvents:
    def test_positiv_termin_mit_kalender_typ_wird_geliefert(self, client, db_session):
        app = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        event_factory(db_session, app, typ="gespräch", datum=date(2026, 8, 1), titel="Interview")
        db_session.commit()

        resp = client.get("/api/calendar/events")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["firma"] == "Contoso AG"
        assert body[0]["rolle"] == "Engineer"
        assert body[0]["titel"] == "Interview"

    def test_positiv_event_mit_kalender_quelle_wird_geliefert(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", datum=date(2026, 8, 1), source="gcal")
        db_session.commit()

        resp = client.get("/api/calendar/events")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_negativ_event_ohne_kalender_bezug_wird_nicht_geliefert(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", datum=date(2026, 8, 1), source="gmail")
        db_session.commit()

        resp = client.get("/api/calendar/events")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_negativ_event_ohne_datum_wird_nicht_geliefert(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="gespräch", datum=None)
        db_session.commit()

        resp = client.get("/api/calendar/events")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_positiv_from_date_filtert_fruehere_termine_aus(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="termin", datum=date(2026, 1, 1))
        event_factory(db_session, app, typ="termin", datum=date(2026, 12, 1))
        db_session.commit()

        resp = client.get("/api/calendar/events", params={"from_date": "2026-06-01"})

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["datum"] == "2026-12-01"

    def test_positiv_to_date_filtert_spaetere_termine_aus(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="termin", datum=date(2026, 1, 1))
        event_factory(db_session, app, typ="termin", datum=date(2026, 12, 1))
        db_session.commit()

        resp = client.get("/api/calendar/events", params={"to_date": "2026-06-01"})

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["datum"] == "2026-01-01"

    def test_positiv_ergebnisse_sind_nach_datum_sortiert(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="termin", datum=date(2026, 12, 1))
        event_factory(db_session, app, typ="termin", datum=date(2026, 1, 1))
        db_session.commit()

        resp = client.get("/api/calendar/events")

        body = resp.json()
        assert [b["datum"] for b in body] == ["2026-01-01", "2026-12-01"]
