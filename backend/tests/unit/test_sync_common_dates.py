"""L0/L1 — effective_bewerbung_floor()/_predates_bewerbung() in sync_common.py:
the shared per-application date floor used by mail, calendar, and call-log
sync to decide whether a timed item is old enough to ignore.

Regression coverage for a real incident (2026-07-16, application #230):
datum_bewerbung was never set on that application, so _predates_bewerbung()
returned False unconditionally — no date filtering happened at all, and
mail/calendar/call items spanning many months of unrelated history got
matched and saved. effective_bewerbung_floor() now falls back to
letztes_update (which defaults to the creation date even when
datum_bewerbung is left blank, see create_application()'s docstring in
applications.py) before giving up entirely.
"""
from datetime import date

import pytest

from app.routers.sync_common import _predates_bewerbung, effective_bewerbung_floor
from tests.factories import application_factory

pytestmark = pytest.mark.unit


class TestEffectiveBewerbungFloor:
    def test_positiv_nutzt_datum_bewerbung_wenn_gesetzt(self, db_session):
        app = application_factory(db_session, datum_bewerbung=date(2026, 1, 1), letztes_update=date(2026, 6, 1))
        assert effective_bewerbung_floor(app) == date(2026, 1, 1)

    def test_positiv_faellt_zurueck_auf_letztes_update(self, db_session):
        app = application_factory(db_session, datum_bewerbung=None, letztes_update=date(2026, 6, 30))
        assert effective_bewerbung_floor(app) == date(2026, 6, 30)

    def test_negativ_none_wenn_beide_fehlen(self, db_session):
        app = application_factory(db_session, datum_bewerbung=None, letztes_update=None)
        assert effective_bewerbung_floor(app) is None


class TestPredatesBewerbung:
    def test_positiv_datum_vor_bewerbungsdatum_wird_erkannt(self, db_session):
        app = application_factory(db_session, datum_bewerbung=date(2026, 6, 1), letztes_update=None)
        assert _predates_bewerbung(date(2026, 5, 31), app) is True

    def test_negativ_gleicher_tag_gilt_nicht_als_zu_frueh(self, db_session):
        # "same day or later" is kept — only strictly earlier is excluded.
        app = application_factory(db_session, datum_bewerbung=date(2026, 6, 1), letztes_update=None)
        assert _predates_bewerbung(date(2026, 6, 1), app) is False

    def test_negativ_datum_danach_wird_nicht_ausgeschlossen(self, db_session):
        app = application_factory(db_session, datum_bewerbung=date(2026, 6, 1), letztes_update=None)
        assert _predates_bewerbung(date(2026, 6, 2), app) is False

    def test_positiv_faellt_zurueck_auf_letztes_update_ohne_datum_bewerbung(self, db_session):
        # The core #230 regression: no datum_bewerbung, but letztes_update
        # is set (as it always is after create_application()) — an item
        # from well before that must now be excluded, whereas before this
        # fix _predates_bewerbung() would have returned False unconditionally.
        app = application_factory(db_session, datum_bewerbung=None, letztes_update=date(2026, 6, 30))
        assert _predates_bewerbung(date(2025, 11, 26), app) is True  # e.g. an old "Google Alert"
        assert _predates_bewerbung(date(2026, 7, 1), app) is False   # after creation — still counts

    def test_negativ_ohne_jegliches_datum_wird_nichts_ausgeschlossen(self, db_session):
        app = application_factory(db_session, datum_bewerbung=None, letztes_update=None)
        assert _predates_bewerbung(date(2020, 1, 1), app) is False

    def test_negativ_fehlendes_item_datum_wird_nicht_ausgeschlossen(self, db_session):
        app = application_factory(db_session, datum_bewerbung=date(2026, 6, 1), letztes_update=None)
        assert _predates_bewerbung(None, app) is False
