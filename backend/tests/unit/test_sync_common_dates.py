"""L0/L1 — effective_bewerbung_floor()/_predates_bewerbung() in sync_common.py:
the shared per-application date floor used by mail, calendar, and call-log
sync to decide whether a timed item is old enough to ignore.

2026-07-16 revision: the floor is the earliest DATED EVENT already in an
application's timeline, not the user-entered application date
(datum_bewerbung) — a recruiter call or prep email can genuinely predate
the day the formal application was submitted, and keying the floor off
datum_bewerbung would wrongly exclude exactly that kind of legitimate
early activity. Falls back to a loose 365-day lookback from today when the
application has no dated events yet at all, so a brand-new application
still gets some bound rather than being searched with no filtering
whatsoever (the original #230 incident, 2026-07-16: datum_bewerbung was
left unset, so the then-current floor logic never filtered anything)."""
from datetime import date, timedelta

import pytest

from app.routers.sync_common import _predates_bewerbung, effective_bewerbung_floor
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.unit


class TestEffectiveBewerbungFloor:
    def test_positiv_nutzt_fruehestes_ereignis(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 3, 1))
        event_factory(db_session, app, datum=date(2026, 1, 15))
        event_factory(db_session, app, datum=date(2026, 2, 1))
        assert effective_bewerbung_floor(app) == date(2026, 1, 15)

    def test_positiv_ignoriert_datum_bewerbung(self, db_session):
        # The core 2026-07-16 revision: an event predating datum_bewerbung
        # (e.g. a prep call before the formal application) is not excluded.
        app = application_factory(db_session, datum_bewerbung=date(2026, 6, 1))
        event_factory(db_session, app, datum=date(2026, 1, 1))
        assert effective_bewerbung_floor(app) == date(2026, 1, 1)

    def test_positiv_ignoriert_events_ohne_datum(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, datum=None)
        event_factory(db_session, app, datum=date(2026, 4, 1))
        assert effective_bewerbung_floor(app) == date(2026, 4, 1)

    def test_negativ_faellt_ohne_ereignisse_auf_lockeres_fenster_zurueck(self, db_session):
        app = application_factory(db_session)
        expected = date.today() - timedelta(days=365)
        assert effective_bewerbung_floor(app) == expected


class TestPredatesBewerbung:
    def test_positiv_datum_vor_floor_wird_erkannt(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 6, 1))
        assert _predates_bewerbung(date(2026, 5, 31), app) is True

    def test_negativ_gleicher_tag_gilt_nicht_als_zu_frueh(self, db_session):
        # "same day or later" is kept — only strictly earlier is excluded.
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 6, 1))
        assert _predates_bewerbung(date(2026, 6, 1), app) is False

    def test_negativ_datum_danach_wird_nicht_ausgeschlossen(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 6, 1))
        assert _predates_bewerbung(date(2026, 6, 2), app) is False

    def test_negativ_innerhalb_lockeres_fensters_ohne_ereignisse_wird_nicht_ausgeschlossen(self, db_session):
        app = application_factory(db_session)
        assert _predates_bewerbung(date.today() - timedelta(days=30), app) is False

    def test_positiv_ausserhalb_lockeres_fensters_ohne_ereignisse_wird_ausgeschlossen(self, db_session):
        app = application_factory(db_session)
        assert _predates_bewerbung(date.today() - timedelta(days=400), app) is True

    def test_negativ_fehlendes_item_datum_wird_nicht_ausgeschlossen(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date(2026, 6, 1))
        assert _predates_bewerbung(None, app) is False
