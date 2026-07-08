"""L1 Component — _find_or_create_application()/_process_linkedin_job() protokollieren
still nachgezogene Felder (rolle, ort, stellenanzeige_url, datum_bewerbung) im Audit-Log,
statt die bestehende Bewerbung unbemerkt zu verändern.
"""
import pytest

from app.routers.sync_linkedin import _find_or_create_application, _process_linkedin_job
from tests.factories import application_factory
from app import models

pytestmark = pytest.mark.component


def _job(**overrides):
    base = dict(
        id="", title="Backend Engineer", company="Contoso AG", ort="München, Deutschland",
        applied_date=None, default_status="applied", status_hint=None, hinweis="",
        stellenanzeige_url=None,
    )
    base.update(overrides)
    return base


def _make_verbose(db):
    db.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
    db.commit()


class TestFindOrCreateApplicationAudit:
    def test_positiv_ort_backfill_wird_protokolliert(self, db_session):
        _make_verbose(db_session)
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", ort=None)
        db_session.commit()

        app, _created, _pending, _dbg = _find_or_create_application(db_session, _job(), user_id=1)
        db_session.commit()

        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="ort").first()
        assert audit is not None
        assert audit.source == "linkedin"
        assert audit.new_value == "München, Deutschland"

    def test_positiv_rolle_cleanup_wird_protokolliert(self, db_session):
        # Rolle-Cleanup läuft nur auf dem job_id-Match-Pfad (bereits bekannte
        # LinkedIn-ID) — ein firma+rolle-Fuzzy-Match würde eine verrauschte
        # Rolle wie "... · Applied · Add note" von vornherein nicht matchen.
        _make_verbose(db_session)
        existing = application_factory(
            db_session, firma="Contoso AG", rolle="Backend Engineer · Applied · Add note",
            ort="Remote", linkedin_job_id="123456",
        )
        db_session.commit()

        app, _created, _pending, _dbg = _find_or_create_application(
            db_session, _job(id="123456", title="Backend Engineer"), user_id=1,
        )
        db_session.commit()

        assert app.id == existing.id
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="rolle").first()
        assert audit is not None
        assert audit.new_value == "Backend Engineer"

    def test_negativ_unveraenderter_ort_erzeugt_keinen_eintrag(self, db_session):
        _make_verbose(db_session)
        existing = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", ort="Bereits gesetzt")
        db_session.commit()

        app, _created, _pending, _dbg = _find_or_create_application(db_session, _job(), user_id=1)
        db_session.commit()

        assert app.id == existing.id
        audit = db_session.query(models.AuditLog).filter_by(app_id=app.id, field="ort").first()
        assert audit is None


class TestProcessLinkedinJobAudit:
    def test_positiv_stellenanzeige_url_backfill_wird_protokolliert(self, db_session):
        _make_verbose(db_session)
        existing = application_factory(
            db_session, firma="Contoso AG", rolle="Backend Engineer", stellenanzeige_url=None,
        )
        db_session.commit()

        _process_linkedin_job(
            db_session,
            _job(stellenanzeige_url="https://linkedin.com/jobs/view/123"),
            user_id=1,
        )
        db_session.commit()

        audit = db_session.query(models.AuditLog).filter_by(
            app_id=existing.id, field="stellenanzeige_url",
        ).first()
        assert audit is not None
        assert audit.source == "linkedin"
        assert audit.new_value == "https://linkedin.com/jobs/view/123"
