"""L1 Component — _process_linkedin_job() in sync_linkedin.py.

Deckt die Status-Progressions- und PendingMatch-Dedup-Logik ab, die historisch
die meisten echten Bugs verursacht hat: wiederholte Duplikat-Statusvorschläge
bei jedem erneuten Sync (Issues #9, #14 — siehe GitHub-Issue-Historie). Die
Logik war ursprünglich eine verschachtelte Closure in _async_sync() und damit
nur über einen echten Playwright-Sync-Lauf erreichbar; für diese Tests wurde
sie in eine eigenständige, reine DB-Funktion extrahiert (kein Verhaltensunterschied).
"""
import pytest

from app import models
from app.routers.sync_linkedin import _process_linkedin_job
from tests.factories import application_factory

pytestmark = pytest.mark.component


def _job(**overrides) -> dict:
    base = dict(
        id="", title="Backend Engineer", company="Contoso AG", ort=None,
        applied_date=None, default_status="applied", status_hint=None, hinweis="",
        stellenanzeige_url=None,
    )
    base.update(overrides)
    return base


class TestNeueBewerbung:
    def test_positiv_neue_bewerbung_ohne_hinweis_wird_direkt_angelegt(self, db_session):
        outcome = _process_linkedin_job(db_session, _job(default_status="applied"))
        db_session.flush()

        assert outcome["result"] == "created"
        assert outcome["pending_status"] is None
        app = db_session.query(models.Application).get(outcome["app_id"])
        assert app.main_status == "applied"
        assert db_session.query(models.PendingMatch).count() == 0

    def test_positiv_neue_archivierte_bewerbung_landet_in_review_queue(self, db_session):
        # Neue Bewerbung aus der ARCHIVED-Kategorie: wird nie direkt als
        # "rejected" angelegt, sondern als "applied" + PendingMatch zur Bestätigung.
        outcome = _process_linkedin_job(db_session, _job(default_status="rejected"))
        db_session.flush()

        assert outcome["result"] == "created"
        assert outcome["pending_status"] == "rejected"
        assert outcome["pending_match_created"] is True
        app = db_session.query(models.Application).get(outcome["app_id"])
        assert app.main_status == "applied"  # nie direkt rejected
        pm = db_session.query(models.PendingMatch).one()
        assert pm.suggested_main_status == "rejected"
        assert pm.status_only is True


class TestStatusfortschrittBestehenderBewerbung:
    def test_positiv_vorwaertsschritt_erzeugt_pending_match(self, db_session):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="applied")
        db_session.commit()

        outcome = _process_linkedin_job(db_session, _job(default_status="hr"))
        db_session.flush()

        assert outcome["result"] == "updated"
        assert outcome["pending_match_created"] is True
        pm = db_session.query(models.PendingMatch).filter_by(suggested_app_id=app.id).one()
        assert pm.suggested_main_status == "hr"
        assert pm.review_status == "pending"

    def test_negativ_rueckschritt_wird_nicht_vorgeschlagen(self, db_session):
        # Ein bereits weiter fortgeschrittener Status darf durch einen älteren
        # LinkedIn-Snapshot nicht zurückgestuft werden.
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="hr")
        db_session.commit()

        outcome = _process_linkedin_job(db_session, _job(default_status="applied"))
        db_session.flush()

        assert outcome["result"] == "skipped"
        assert db_session.query(models.PendingMatch).count() == 0

    def test_positiv_rejected_ist_von_jedem_status_aus_vorschlagbar(self, db_session):
        # Absage ist die einzige Ausnahme von der reinen Vorwärts-Regel.
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="hr")
        db_session.commit()

        outcome = _process_linkedin_job(db_session, _job(default_status="rejected"))

        assert outcome["result"] == "updated"
        assert outcome["target_status"] == "rejected"

    def test_negativ_bereits_rejected_bleibt_ohne_erneuten_vorschlag(self, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="rejected")
        db_session.commit()

        outcome = _process_linkedin_job(db_session, _job(default_status="rejected"))

        assert outcome["result"] == "skipped"


class TestPendingMatchDedupRegression:
    """Regressionstests für Issue #9: 'LI-Sync stellt Bewerbung nach jeder
    Synchronisation erneut auf Abgesagt' — derselbe Statusvorschlag wurde bei
    jedem erneuten Sync als neuer PendingMatch angelegt, unabhängig davon, ob
    er schon aussteht oder bereits vom User entschieden wurde."""

    def test_negativ_bereits_ausstehender_vorschlag_wird_nicht_dupliziert(self, db_session):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="applied")
        db_session.add(models.PendingMatch(
            source="linkedin", external_id="linkedin___status__hr",
            confidence=90, event_type="status_change", suggested_app_id=app.id,
            suggested_main_status="hr", status_only=True, review_status="pending",
        ))
        db_session.commit()

        outcome = _process_linkedin_job(db_session, _job(default_status="hr"))

        assert outcome["result"] == "updated"
        assert outcome["pending_match_created"] is False
        assert db_session.query(models.PendingMatch).count() == 1  # kein Duplikat

    def test_negativ_bereits_entschiedener_vorschlag_wird_nicht_erneut_angelegt(self, db_session):
        # Exakter Issue-#9-Fall: User hat den Vorschlag bereits abgelehnt oder
        # genehmigt — ein späterer Sync darf ihn nicht erneut vorschlagen.
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="applied")
        db_session.add(models.PendingMatch(
            source="linkedin", external_id="linkedin___status__hr",
            confidence=90, event_type="status_change", suggested_app_id=app.id,
            suggested_main_status="hr", status_only=True, review_status="rejected",
        ))
        db_session.commit()

        outcome = _process_linkedin_job(db_session, _job(default_status="hr"))

        assert outcome["result"] == "updated"
        assert outcome["pending_match_created"] is False
        assert db_session.query(models.PendingMatch).count() == 1

    def test_positiv_unterschiedliche_zielstatus_erzeugen_getrennte_vorschlaege(self, db_session):
        # Ein bereits entschiedener Vorschlag für Status X darf einen neuen,
        # unabhängigen Vorschlag für Status Y nicht blockieren.
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="applied")
        db_session.add(models.PendingMatch(
            source="linkedin", external_id="linkedin___status__hr",
            confidence=90, event_type="status_change", suggested_app_id=app.id,
            suggested_main_status="hr", status_only=True, review_status="rejected",
        ))
        db_session.commit()

        outcome = _process_linkedin_job(db_session, _job(default_status="rejected"))
        db_session.flush()

        assert outcome["pending_match_created"] is True
        assert db_session.query(models.PendingMatch).count() == 2
