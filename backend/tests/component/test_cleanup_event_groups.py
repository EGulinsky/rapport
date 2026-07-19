"""L1 Component — cleanup.py Timeline-Dublettenerkennung.

Regressionstest für einen Bug, der live an Produktivdaten gefunden wurde:
33 echte Duplikate im Kalender/Timeline wurden von der Bereinigen-Funktion
nicht gefunden, weil derselbe synchronisierte Termin/Anruf/Mail bei
mehreren Sync-/Klassifikationsdurchläufen mit unterschiedlichem `typ`
gespeichert wurde (z.B. "status", "notiz", "gespräch" für denselben
gcal-Termin, teils sogar mit identischem external_id). Die alte
Gruppierung nach (application_id, typ, datum, titel) verlangte exakte
typ-Gleichheit und übersah dadurch jede dieser Dubletten.
"""
from datetime import date

import pytest

from app import models
from app.routers import cleanup
from app.routers.cleanup import _find_event_groups
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component


class TestFindEventGroups:
    def test_positiv_synced_events_unterschiedlicher_typ_werden_erkannt(self, db_session):
        # Regressionsfall: derselbe gcal-Termin wurde einmal als "status" und
        # einmal als "gespräch" klassifiziert — beides Mal source="gcal",
        # gleiches Datum, gleicher Titel.
        app = application_factory(db_session)
        event_factory(db_session, app, typ="status", source="gcal", datum=date(2026, 3, 5), titel="Discussion with Eugen Gulinsky")
        event_factory(db_session, app, typ="gespräch", source="gcal", datum=date(2026, 3, 5), titel="Discussion with Eugen Gulinsky")

        groups = _find_event_groups(db_session)

        assert len(groups) == 1
        assert len(groups[0]["remove"]) == 1

    def test_positiv_spezifischer_typ_wird_als_keeper_bevorzugt(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="status", source="gcal", datum=date(2026, 3, 5), titel="Interview")
        event_factory(db_session, app, typ="gespräch", source="gcal", datum=date(2026, 3, 5), titel="Interview")

        groups = _find_event_groups(db_session)

        assert groups[0]["keep"]["typ"] == "gespräch"
        assert groups[0]["remove"][0]["typ"] == "status"

    def test_negativ_manuelle_eintraege_ohne_source_brauchen_exakten_typ(self, db_session):
        # Manuell angelegte Einträge (source=None): typ bleibt ein bewusst vom
        # User gesetztes Unterscheidungsmerkmal, kein Klassifikations-Artefakt —
        # unterschiedlicher typ darf hier NICHT als Duplikat gelten.
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", source=None, datum=date(2026, 1, 1), titel="Rückfrage")
        event_factory(db_session, app, typ="gespräch", source=None, datum=date(2026, 1, 1), titel="Rückfrage")

        groups = _find_event_groups(db_session)

        assert groups == []

    def test_negativ_unterschiedliche_apps_kein_match(self, db_session):
        app1 = application_factory(db_session)
        app2 = application_factory(db_session)
        event_factory(db_session, app1, typ="status", source="gcal", datum=date(2026, 3, 5), titel="Interview")
        event_factory(db_session, app2, typ="gespräch", source="gcal", datum=date(2026, 3, 5), titel="Interview")

        groups = _find_event_groups(db_session)

        assert groups == []

    def test_corner_case_unterschiedliche_source_kein_match(self, db_session):
        # Gleicher Titel/Datum, aber verschiedene Sync-Quelle — kein sicheres
        # Indiz für dasselbe reale Ereignis, daher bewusst kein Merge.
        app = application_factory(db_session)
        event_factory(db_session, app, typ="status", source="gcal", datum=date(2026, 3, 5), titel="Interview")
        event_factory(db_session, app, typ="gespräch", source="icloud_cal", datum=date(2026, 3, 5), titel="Interview")

        groups = _find_event_groups(db_session)

        assert groups == []

    def test_positiv_drei_klassifikationsvarianten_werden_zu_einer_gruppe(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="status", source="gcal", datum=date(2026, 2, 24), titel="Valiantys - Delivery Director itw")
        event_factory(db_session, app, typ="notiz", source="gcal", datum=date(2026, 2, 24), titel="Valiantys - Delivery Director itw")
        event_factory(db_session, app, typ="gespräch", source="gcal", datum=date(2026, 2, 24), titel="Valiantys - Delivery Director itw")

        groups = _find_event_groups(db_session)

        assert len(groups) == 1
        assert len(groups[0]["remove"]) == 2


class TestCalendarOnlyFilter:
    """Der 'Bereinigen'-Button der Kalenderansicht ruft scope='events' auf,
    was jetzt calendar_only=True setzt — nur echte Kalendereinträge
    (typ in gespräch/interview/termin ODER source in gcal/icloud_cal),
    keine Mail-/Anruf-Duplikate."""

    def test_positiv_kalender_dublette_wird_mit_calendar_only_gefunden(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="status", source="gcal", datum=date(2026, 3, 5), titel="Discussion")
        event_factory(db_session, app, typ="termin", source="gcal", datum=date(2026, 3, 5), titel="Discussion")

        groups = _find_event_groups(db_session, calendar_only=True)

        assert len(groups) == 1

    def test_negativ_mail_dublette_wird_mit_calendar_only_ausgeblendet(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="status", source="gmail", datum=date(2026, 4, 27), titel="Re: AW: Ihre Bewerbung")
        event_factory(db_session, app, typ="notiz", source="gmail", datum=date(2026, 4, 27), titel="Re: AW: Ihre Bewerbung")

        groups = _find_event_groups(db_session, calendar_only=True)

        assert groups == []

    def test_negativ_anruf_dublette_wird_mit_calendar_only_ausgeblendet(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", source="icloud_calls", datum=date(2026, 5, 7), titel="Anruf von Natalia Kühne")
        event_factory(db_session, app, typ="anruf", source="icloud_calls", datum=date(2026, 5, 7), titel="Anruf von Natalia Kühne")

        groups = _find_event_groups(db_session, calendar_only=True)

        assert groups == []

    def test_corner_case_manueller_gespraech_eintrag_zaehlt_als_kalender(self, db_session):
        # typ="gespräch" gilt auch ohne source (manuell) als Kalendereintrag —
        # exakt dieselbe Definition wie in routers/calendar.py.
        app = application_factory(db_session)
        event_factory(db_session, app, typ="gespräch", source=None, datum=date(2026, 1, 1), titel="Notiz-Duplikat")
        event_factory(db_session, app, typ="gespräch", source=None, datum=date(2026, 1, 1), titel="Notiz-Duplikat")

        groups = _find_event_groups(db_session, calendar_only=True)

        assert len(groups) == 1


class TestApplicationsScopeIncludesEvents:
    """Regression: live-reported that scope="applications" (the Applications
    view's own "Bereinigen" button) never checked for event duplicates at
    all -- cleanup_preview()/cleanup_run() only ran _find_event_groups() for
    scope in (None, "events"), so an icloud_notes duplicate on an application
    (same source+datum+titel, e.g. from a sync re-run after a synced_items
    marker reset) never surfaced there, only under the unscoped "clean up
    everything" run. scope="applications" now checks events too, unrestricted
    (calendar_only=False) -- notes/mail/call duplicates are as much a part of
    an application's own data as calendar entries."""

    def _user(self) -> models.User:
        return models.User(id=1, email="test@x.de", password_hash="x", email_verified=True)

    def test_positiv_preview_findet_notiz_dublette_unter_applications_scope(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        db_session.commit()

        result = cleanup.cleanup_preview(db=db_session, scope="applications", current_user=self._user())

        assert len(result["events"]) == 1
        assert len(result["events"][0]["remove"]) == 1

    async def test_positiv_run_loescht_notiz_dublette_unter_applications_scope(self, db_session):
        app = application_factory(db_session)
        keeper_ev = event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        dup_ev = event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        db_session.commit()

        await cleanup.cleanup_run(db=db_session, scope="applications", current_user=self._user())

        db_session.expire_all()
        assert db_session.get(models.Event, keeper_ev.id) is not None
        assert db_session.get(models.Event, dup_ev.id) is None

    def test_negativ_events_scope_bleibt_kalender_beschraenkt(self, db_session):
        # Regression guard: scope="events" (Kalenderansicht) darf durch diese
        # Änderung nicht auf einmal auch Notiz-Duplikate zeigen.
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        db_session.commit()

        result = cleanup.cleanup_preview(db=db_session, scope="events", current_user=self._user())

        assert result["events"] == []

    def test_negativ_contacts_scope_prueft_weiterhin_keine_events(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        event_factory(db_session, app, typ="notiz", source="icloud_notes", datum=date(2026, 7, 14), titel="Erstgespräch")
        db_session.commit()

        result = cleanup.cleanup_preview(db=db_session, scope="contacts", current_user=self._user())

        assert result["events"] == []

    def test_positiv_applications_scope_findet_auch_echte_kalenderdubletten(self, db_session):
        # Nicht nur Notizen -- ein echter Kalendertermin-Duplikat (source=gcal)
        # muss unter scope="applications" ebenfalls unbeschränkt gefunden werden.
        app = application_factory(db_session)
        event_factory(db_session, app, typ="gespräch", source="gcal", datum=date(2026, 7, 14), titel="Kennen lernen")
        event_factory(db_session, app, typ="gespräch", source="gcal", datum=date(2026, 7, 14), titel="Kennen lernen")
        db_session.commit()

        result = cleanup.cleanup_preview(db=db_session, scope="applications", current_user=self._user())

        assert len(result["events"]) == 1
