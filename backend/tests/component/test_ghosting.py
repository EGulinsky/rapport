"""L1 — apply_ghosting_overrides() (applications.py): the ghosting flag now
measures gaps between real timeline activity and either today (active
applications) or the moment an application was switched to "rejected"
(via the "status" Event that's unconditionally created on every
main_status/sub_status change), instead of the manually-editable
letztes_update field. "status" events themselves are excluded from "last
activity" — otherwise the switch-to-rejected gap would always be zero."""
from datetime import date, timedelta

import pytest

from app.routers.applications import apply_ghosting_overrides
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component


class TestExcludedStatuses:
    def test_negativ_prospecting_nie_ghosting(self, db_session):
        app = application_factory(db_session, main_status="prospecting")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=100))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is False

    def test_negativ_signed_nie_ghosting(self, db_session):
        app = application_factory(db_session, main_status="signed")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=100))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is False


class TestNegotiatingNowIncluded:
    def test_positiv_negotiating_mit_alter_aktivitaet_ist_jetzt_ghosting(self, db_session):
        app = application_factory(db_session, main_status="negotiating")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=20))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is True

    def test_negativ_negotiating_mit_frischer_aktivitaet_kein_ghosting(self, db_session):
        app = application_factory(db_session, main_status="negotiating")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=5))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is False


class TestActiveBranchLastEventVsToday:
    def test_positiv_ueber_14_tage_seit_letztem_event_ist_ghosting(self, db_session):
        app = application_factory(db_session, main_status="applied")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=20))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is True

    def test_negativ_innerhalb_14_tage_kein_ghosting(self, db_session):
        app = application_factory(db_session, main_status="applied")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=10))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is False

    def test_negativ_status_event_zaehlt_nicht_als_aktivitaet(self, db_session):
        # Real activity is 20 days old, but a "status" bookkeeping event was
        # just created today (e.g. a sub-status tweak) — must not mask ghosting.
        app = application_factory(db_session, main_status="hr")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=20))
        event_factory(db_session, app, typ="status", datum=date.today())
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is True

    def test_positiv_fallback_auf_datum_bewerbung_ohne_events(self, db_session):
        app = application_factory(db_session, main_status="applied",
                                   datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is True


class TestRejectedBranchLastEventVsSwitchToRejected:
    def test_positiv_grosse_luecke_vor_absage_ist_ghosting(self, db_session):
        app = application_factory(db_session, main_status="rejected")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=40))
        event_factory(db_session, app, typ="status", datum=date.today() - timedelta(days=20))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is True

    def test_negativ_kleine_luecke_vor_absage_kein_ghosting(self, db_session):
        app = application_factory(db_session, main_status="rejected")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=25))
        event_factory(db_session, app, typ="status", datum=date.today() - timedelta(days=20))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is False

    def test_negativ_ohne_status_event_kein_ghosting(self, db_session):
        # No "status" event at all (e.g. imported data with main_status set
        # directly) — can't determine the switch-to-rejected moment.
        app = application_factory(db_session, main_status="rejected")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=40))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is False

    def test_negativ_aktivitaet_nach_absage_wird_nicht_fuer_negative_luecke_verwendet(self, db_session):
        # A follow-up note logged *after* the rejection must be excluded from
        # "last activity before rejection" — otherwise the gap goes negative
        # and always reads as "not ghosting" regardless of the real pre-rejection gap.
        app = application_factory(db_session, main_status="rejected")
        event_factory(db_session, app, typ="mail", datum=date.today() - timedelta(days=40))
        event_factory(db_session, app, typ="status", datum=date.today() - timedelta(days=20))
        event_factory(db_session, app, typ="notiz", datum=date.today() - timedelta(days=2))
        db_session.commit()

        apply_ghosting_overrides(db_session, [app])

        assert app.ghosting is True


class TestBulkMultipleApps:
    def test_positiv_mehrere_apps_werden_unabhaengig_berechnet(self, db_session):
        ghosted = application_factory(db_session, main_status="applied")
        event_factory(db_session, ghosted, typ="mail", datum=date.today() - timedelta(days=30))
        fresh = application_factory(db_session, main_status="applied")
        event_factory(db_session, fresh, typ="mail", datum=date.today() - timedelta(days=1))
        db_session.commit()

        apply_ghosting_overrides(db_session, [ghosted, fresh])

        assert ghosted.ghosting is True
        assert fresh.ghosting is False

    def test_negativ_leere_liste_wird_ohne_fehler_uebersprungen(self, db_session):
        apply_ghosting_overrides(db_session, [])
