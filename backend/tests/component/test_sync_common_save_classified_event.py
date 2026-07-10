"""L1 Component — save_classified_event() in sync_common.py.

Persists an AI-pre-classified sync result (mail/note) as an Event. Previously
entirely uncovered (0% — never called in the test suite before), despite
being the core persistence path for every AI-classified sync source.
"""
from datetime import date, datetime, timezone

import pytest

from app import models
from app.routers.sync_common import save_classified_event, mark_synced, is_synced
from tests.factories import application_factory

pytestmark = pytest.mark.component


def _target_app(app, firma="Contoso AG", is_headhunter=False):
    return {"id": app.id, "firma": firma, "is_headhunter": is_headhunter}


class TestSaveClassifiedEvent:
    def test_negativ_niedrige_konfidenz_wird_uebersprungen(self, db_session):
        app = application_factory(db_session)
        db_session.commit()

        created = save_classified_event(
            db_session, "gmail", "ext_low", {"confidence": 0.2, "relevant": True},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )
        db_session.flush()

        assert created is False
        assert db_session.query(models.Event).count() == 0
        assert is_synced(db_session, "gmail", "ext_low")

    def test_negativ_nicht_relevant_wird_uebersprungen(self, db_session):
        app = application_factory(db_session)
        db_session.commit()

        created = save_classified_event(
            db_session, "gmail", "ext_irrelevant", {"confidence": 0.9, "relevant": False},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )

        assert created is False
        assert db_session.query(models.Event).count() == 0

    def test_positiv_event_wird_mit_date_hint_erstellt(self, db_session):
        app = application_factory(db_session)
        db_session.commit()
        hint = datetime(2026, 8, 1, 14, 30, tzinfo=timezone.utc)

        created = save_classified_event(
            db_session, "gmail", "ext_1",
            {"confidence": 0.9, "relevant": True, "extract": "Interview vereinbart", "titel": "Interview"},
            "Von: recruiter@contoso.com\nBetreff: Interview\n\nInhalt", hint, _target_app(app),
        )

        assert created is True
        ev = db_session.query(models.Event).one()
        assert ev.datum == hint.date()
        assert ev.autor == "recruiter@contoso.com"
        assert "Interview vereinbart" in (ev.notiz or "")

    def test_positiv_datum_aus_result_wenn_kein_date_hint(self, db_session):
        app = application_factory(db_session)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_2",
            {"confidence": 0.9, "relevant": True, "datum": "2026-08-05", "extract": "Info"},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )

        ev = db_session.query(models.Event).one()
        assert ev.datum == date(2026, 8, 5)

    def test_corner_case_ungueltiges_datum_in_result_wird_ignoriert(self, db_session):
        app = application_factory(db_session)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_3",
            {"confidence": 0.9, "relevant": True, "datum": "nicht-valide", "extract": "Info"},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )

        ev = db_session.query(models.Event).one()
        assert ev.datum is None

    def test_positiv_extract_fallback_auf_betreffzeile(self, db_session):
        app = application_factory(db_session)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_4",
            {"confidence": 0.9, "relevant": True},
            "Betreff: Einladung zum Gespräch\n\nInhalt ohne Extract", None, _target_app(app),
        )

        ev = db_session.query(models.Event).one()
        assert "Einladung zum Gespräch" in (ev.notiz or "")

    def test_negativ_event_vor_bewerbungsdatum_wird_uebersprungen(self, db_session):
        app = application_factory(db_session, datum_bewerbung=date(2026, 6, 1))
        db_session.commit()

        created = save_classified_event(
            db_session, "gmail", "ext_5",
            {"confidence": 0.9, "relevant": True, "datum": "2026-01-01", "extract": "Alt"},
            "Betreff: Alt\n\nInhalt", None, _target_app(app),
        )

        assert created is False
        assert db_session.query(models.Event).count() == 0

    def test_positiv_kontakt_wird_aus_absender_angelegt(self, db_session):
        app = application_factory(db_session)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_6",
            {"confidence": 0.9, "relevant": True, "extract": "Hallo"},
            "Von: Jane Doe <jane@contoso.com>\nBetreff: Hallo\n\nInhalt", None, _target_app(app),
        )

        contact = db_session.query(models.Contact).filter(models.Contact.email == "jane@contoso.com").first()
        assert contact is not None

    def test_positiv_statuswechsel_wird_als_pendingmatch_vorgeschlagen(self, db_session):
        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_7",
            {"confidence": 0.8, "relevant": True, "extract": "Einladung", "suggested_main_status": "hr"},
            "Betreff: Einladung\n\nInhalt", None, _target_app(app),
        )
        db_session.flush()

        pm = db_session.query(models.PendingMatch).filter_by(external_id="ext_7__status").first()
        assert pm is not None
        assert pm.suggested_main_status == "hr"
        assert pm.event_type == "status_change"

    def test_negativ_kein_pendingmatch_wenn_status_gleich_bleibt(self, db_session):
        app = application_factory(db_session, main_status="hr")
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_8",
            {"confidence": 0.8, "relevant": True, "extract": "Info", "suggested_main_status": "hr"},
            "Betreff: Info\n\nInhalt", None, _target_app(app),
        )

        assert db_session.query(models.PendingMatch).filter_by(external_id="ext_8__status").first() is None

    def test_negativ_kein_doppeltes_pendingmatch_bei_gleichem_external_id_suffix(self, db_session):
        # Zwei verschiedene Events (unterschiedliche external_ids), die beide auf
        # denselben Statuswechsel-Vorschlag "__status" abzielen würden — der zweite
        # Aufruf darf keinen zweiten PendingMatch mit demselben external_id erzeugen,
        # da PendingMatch.external_id in der Praxis pro Konversation stabil ist.
        app = application_factory(db_session, main_status="applied")
        db_session.commit()
        result = {"confidence": 0.8, "relevant": True, "extract": "Einladung", "suggested_main_status": "hr"}

        save_classified_event(db_session, "gmail", "ext_9", result, "Betreff: A\n\nX", None, _target_app(app))
        # Zweiter Aufruf mit identischer external_id (z.B. erneuter Sync-Lauf) —
        # already-Guard muss ein Duplikat verhindern.
        save_classified_event(db_session, "gmail", "ext_9", result, "Betreff: A\n\nX", None, _target_app(app))

        assert db_session.query(models.PendingMatch).filter_by(external_id="ext_9__status").count() == 1
