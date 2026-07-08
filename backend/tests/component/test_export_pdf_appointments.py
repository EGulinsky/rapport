"""L1 Component — _fetch_recent_appointments() im PDF-Export soll nur echte
Kalendereinträge liefern (gleiche Definition wie routers/calendar.py und
cleanup.py's _calendar_filter), keine Anrufe oder sonstigen Timeline-Einträge.
"""
from datetime import date, timedelta

import pytest

from app.routers.export_pdf import _fetch_recent_appointments
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component


class TestFetchRecentAppointments:
    def test_positiv_gespraech_wird_uebernommen(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="gespräch", source=None)
        db_session.commit()

        result = _fetch_recent_appointments(db_session, date.today() - timedelta(weeks=4))

        assert ev.id in [e.id for e in result]

    def test_positiv_gcal_termin_wird_uebernommen_unabhaengig_vom_typ(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="status", source="gcal")
        db_session.commit()

        result = _fetch_recent_appointments(db_session, date.today() - timedelta(weeks=4))

        assert ev.id in [e.id for e in result]

    def test_negativ_anruf_wird_nicht_uebernommen(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="anruf", source="icloud_calls")
        db_session.commit()

        result = _fetch_recent_appointments(db_session, date.today() - timedelta(weeks=4))

        assert ev.id not in [e.id for e in result]

    def test_negativ_notiz_wird_nicht_uebernommen(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="notiz", source="gmail")
        db_session.commit()

        result = _fetch_recent_appointments(db_session, date.today() - timedelta(weeks=4))

        assert ev.id not in [e.id for e in result]

    def test_negativ_zu_alter_termin_wird_nicht_uebernommen(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="gespräch", source=None,
                            datum=date.today() - timedelta(weeks=5))
        db_session.commit()

        result = _fetch_recent_appointments(db_session, date.today() - timedelta(weeks=4))

        assert ev.id not in [e.id for e in result]
