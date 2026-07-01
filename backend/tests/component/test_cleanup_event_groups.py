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
