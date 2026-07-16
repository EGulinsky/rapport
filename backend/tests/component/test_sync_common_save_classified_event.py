"""L1 Component — save_classified_event() in sync_common.py.

Persists an AI-pre-classified sync result (mail/note) as an Event. Previously
entirely uncovered (0% — never called in the test suite before), despite
being the core persistence path for every AI-classified sync source.

2026-07-16: _predates_bewerbung() now treats "no date available at all" —
either the item's own date, or the application's floor (earliest dated
event in its timeline) — as "do not sync". Most tests here seed an earlier
anchor event via event_factory() so the item under test has a floor to be
compared against; dateless items are expected to be skipped, not created
with datum=None as before.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_common import save_classified_event, is_synced
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component


def _target_app(app, firma="Contoso AG", is_headhunter=False):
    return {"id": app.id, "firma": firma, "is_headhunter": is_headhunter}


def _seed_floor(db_session, app, days_ago=60):
    """Anchor event establishing a floor, well before any date used in the test."""
    event_factory(db_session, app, datum=date.today() - timedelta(days=days_ago), source="icloud_mail")


class TestSaveClassifiedEvent:
    def test_negativ_niedrige_konfidenz_wird_uebersprungen(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        created = save_classified_event(
            db_session, "gmail", "ext_low", {"confidence": 0.2, "relevant": True},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )
        db_session.flush()

        assert created is False
        assert db_session.query(models.Event).filter_by(external_id="ext_low").count() == 0
        assert is_synced(db_session, "gmail", "ext_low")

    def test_negativ_nicht_relevant_wird_uebersprungen(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        created = save_classified_event(
            db_session, "gmail", "ext_irrelevant", {"confidence": 0.9, "relevant": False},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )

        assert created is False
        assert db_session.query(models.Event).filter_by(external_id="ext_irrelevant").count() == 0

    def test_positiv_event_wird_mit_date_hint_erstellt(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()
        hint = datetime(2026, 8, 1, 14, 30, tzinfo=timezone.utc)

        created = save_classified_event(
            db_session, "gmail", "ext_1",
            {"confidence": 0.9, "relevant": True, "extract": "Interview vereinbart", "titel": "Interview"},
            "Von: recruiter@contoso.com\nBetreff: Interview\n\nInhalt", hint, _target_app(app),
        )

        assert created is True
        ev = db_session.query(models.Event).filter_by(external_id="ext_1").one()
        assert ev.datum == hint.date()
        assert ev.autor == "recruiter@contoso.com"
        assert "Interview vereinbart" in (ev.notiz or "")

    def test_positiv_datum_aus_result_wenn_kein_date_hint(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_2",
            {"confidence": 0.9, "relevant": True, "datum": "2026-08-05", "extract": "Info"},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )

        ev = db_session.query(models.Event).filter_by(external_id="ext_2").one()
        assert ev.datum == date(2026, 8, 5)

    def test_negativ_ungueltiges_datum_in_result_wird_uebersprungen(self, db_session):
        # An unparseable date is treated the same as no date at all — see
        # _predates_bewerbung(): "if there is absolutely no date available,
        # do not sync timed events at all" (2026-07-16).
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        created = save_classified_event(
            db_session, "gmail", "ext_3",
            {"confidence": 0.9, "relevant": True, "datum": "nicht-valide", "extract": "Info"},
            "Betreff: Test\n\nInhalt", None, _target_app(app),
        )

        assert created is False
        assert db_session.query(models.Event).filter_by(external_id="ext_3").count() == 0

    def test_positiv_extract_fallback_auf_betreffzeile(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_4",
            {"confidence": 0.9, "relevant": True, "datum": "2026-06-01"},
            "Betreff: Einladung zum Gespräch\n\nInhalt ohne Extract", None, _target_app(app),
        )

        ev = db_session.query(models.Event).filter_by(external_id="ext_4").one()
        assert "Einladung zum Gespräch" in (ev.notiz or "")

    def test_negativ_event_vor_floor_wird_uebersprungen(self, db_session):
        # The floor is the earliest dated event already in the timeline —
        # an item from well before it must be skipped.
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date.today() - timedelta(days=10), source="icloud_mail")
        db_session.commit()
        old_datum = (date.today() - timedelta(days=400)).isoformat()

        created = save_classified_event(
            db_session, "gmail", "ext_5",
            {"confidence": 0.9, "relevant": True, "datum": old_datum, "extract": "Alt"},
            "Betreff: Alt\n\nInhalt", None, _target_app(app),
        )

        assert created is False
        assert db_session.query(models.Event).filter_by(external_id="ext_5").count() == 0

    def test_negativ_ohne_jegliches_datum_wird_uebersprungen(self, db_session):
        # No date_hint and no result["datum"] at all — nothing to anchor
        # relevance to, so this must be skipped even with a floor present.
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        created = save_classified_event(
            db_session, "gmail", "ext_dateless", {"confidence": 0.9, "relevant": True, "extract": "Hallo"},
            "Betreff: Hallo\n\nInhalt", None, _target_app(app),
        )

        assert created is False
        assert db_session.query(models.Event).filter_by(external_id="ext_dateless").count() == 0

    def test_positiv_kontakt_wird_aus_absender_angelegt(self, db_session):
        app = application_factory(db_session)
        _seed_floor(db_session, app)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_6",
            {"confidence": 0.9, "relevant": True, "datum": "2026-06-01", "extract": "Hallo"},
            "Von: Jane Doe <jane@contoso.com>\nBetreff: Hallo\n\nInhalt", None, _target_app(app),
        )

        contact = db_session.query(models.Contact).filter(models.Contact.email == "jane@contoso.com").first()
        assert contact is not None

    def test_positiv_statuswechsel_wird_als_pendingmatch_vorgeschlagen(self, db_session):
        app = application_factory(db_session, main_status="applied")
        _seed_floor(db_session, app)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_7",
            {"confidence": 0.8, "relevant": True, "datum": "2026-06-01", "extract": "Einladung", "suggested_main_status": "hr"},
            "Betreff: Einladung\n\nInhalt", None, _target_app(app),
        )
        db_session.flush()

        pm = db_session.query(models.PendingMatch).filter_by(external_id="ext_7__status").first()
        assert pm is not None
        assert pm.suggested_main_status == "hr"
        assert pm.event_type == "status_change"

    def test_negativ_kein_pendingmatch_wenn_status_gleich_bleibt(self, db_session):
        app = application_factory(db_session, main_status="hr")
        _seed_floor(db_session, app)
        db_session.commit()

        save_classified_event(
            db_session, "gmail", "ext_8",
            {"confidence": 0.8, "relevant": True, "datum": "2026-06-01", "extract": "Info", "suggested_main_status": "hr"},
            "Betreff: Info\n\nInhalt", None, _target_app(app),
        )

        assert db_session.query(models.PendingMatch).filter_by(external_id="ext_8__status").first() is None

    def test_negativ_kein_doppeltes_pendingmatch_bei_gleichem_external_id_suffix(self, db_session):
        # Zwei verschiedene Events (unterschiedliche external_ids), die beide auf
        # denselben Statuswechsel-Vorschlag "__status" abzielen würden — der zweite
        # Aufruf darf keinen zweiten PendingMatch mit demselben external_id erzeugen,
        # da PendingMatch.external_id in der Praxis pro Konversation stabil ist.
        app = application_factory(db_session, main_status="applied")
        _seed_floor(db_session, app)
        db_session.commit()
        result = {"confidence": 0.8, "relevant": True, "datum": "2026-06-01", "extract": "Einladung", "suggested_main_status": "hr"}

        save_classified_event(db_session, "gmail", "ext_9", result, "Betreff: A\n\nX", None, _target_app(app))
        # Zweiter Aufruf mit identischer external_id (z.B. erneuter Sync-Lauf) —
        # already-Guard muss ein Duplikat verhindern.
        save_classified_event(db_session, "gmail", "ext_9", result, "Betreff: A\n\nX", None, _target_app(app))

        assert db_session.query(models.PendingMatch).filter_by(external_id="ext_9__status").count() == 1
