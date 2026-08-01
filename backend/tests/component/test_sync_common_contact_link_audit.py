"""L1 Component -- _upsert_contact() in sync_common.py: audit trail when an
*existing* contact gets linked to a new application.

Previously this path (an existing contact matched by email/name+company and
newly linked to app_id via `INSERT OR IGNORE`) logged nothing at all -- only
the incidental telefon/rolle field backfills next to it had a reason. That
made it impossible to tell from the audit log why a contact ended up on a
given application when the contact itself wasn't brand new. Now every first-
time link writes an "update"/"sync" audit row, carrying the concrete
match_signal (the mail-address/domain/company-term that caused this
particular app_id to be picked) when the caller has one."""
from datetime import date

import pytest
from sqlalchemy import text

from app import models
from app.routers.sync_common import _upsert_contact
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.component

_LINK_SQL = text("INSERT INTO contact_application (contact_id, application_id) VALUES (:cid, :aid)")


@pytest.fixture(autouse=True)
def _verbose_audit(db_session):
    # "update"-action audit rows (the new contact-link entry uses action=
    # "update", matching the telefon/rolle field-backfill entries right next
    # to it in the same function) are only persisted in verbose mode.
    db_session.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
    db_session.commit()


class TestUpsertContactLinkAudit:
    def test_positiv_neue_verknuepfung_mit_match_signal_wird_geloggt(self, db_session):
        app1 = application_factory(db_session)
        app2 = application_factory(db_session)
        contact = contact_factory(db_session, email="jane@contoso.example", firma=app1.firma)
        db_session.execute(_LINK_SQL, {"cid": contact.id, "aid": app1.id})
        db_session.commit()

        _upsert_contact(
            db_session, contact.name, "jane@contoso.example", app2.id, app2.firma,
            is_headhunter=False, event_date=date.today(),
            match_signal="Kontakt-E-Mail: jane@contoso.example",
        )
        db_session.commit()

        entries = db_session.query(models.AuditLog).filter_by(
            contact_id=contact.id, app_id=app2.id, action="update",
        ).all()
        assert len(entries) == 1
        assert "jane@contoso.example" in entries[0].reason

    def test_positiv_ohne_match_signal_generischer_grund(self, db_session):
        app1 = application_factory(db_session)
        app2 = application_factory(db_session)
        contact = contact_factory(db_session, email="ben@contoso.example", firma=app1.firma)
        db_session.execute(_LINK_SQL, {"cid": contact.id, "aid": app1.id})
        db_session.commit()

        _upsert_contact(
            db_session, contact.name, "ben@contoso.example", app2.id, app2.firma,
            is_headhunter=False, event_date=date.today(),
        )
        db_session.commit()

        entry = db_session.query(models.AuditLog).filter_by(
            contact_id=contact.id, app_id=app2.id, action="update",
        ).first()
        assert entry is not None
        assert entry.reason  # non-empty generic reason, not None/blank

    def test_negativ_bereits_verknuepft_kein_doppelter_audit_eintrag(self, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session, email="anna@contoso.example", firma=app.firma)
        db_session.execute(_LINK_SQL, {"cid": contact.id, "aid": app.id})
        db_session.commit()

        # Re-matched to the *same* application on a subsequent sync run --
        # must not spam a duplicate "linked" audit entry every time.
        _upsert_contact(
            db_session, contact.name, "anna@contoso.example", app.id, app.firma,
            is_headhunter=False, event_date=date.today(),
            match_signal="Kontakt-E-Mail: anna@contoso.example",
        )
        db_session.commit()

        entries = db_session.query(models.AuditLog).filter_by(
            contact_id=contact.id, app_id=app.id, action="update",
        ).all()
        assert entries == []

    def test_positiv_neuer_kontakt_weiterhin_unveraendert_geloggt(self, db_session):
        """Regression: the pre-existing new-contact-creation audit entry
        (reason_key=contact_from_email_sync) must be unaffected by this change."""
        app = application_factory(db_session)

        _upsert_contact(
            db_session, "Nina Neu", "nina@contoso.example", app.id, app.firma,
            is_headhunter=False, event_date=date.today(),
        )
        db_session.commit()

        contact = db_session.query(models.Contact).filter_by(email="nina@contoso.example").first()
        assert contact is not None
        entry = db_session.query(models.AuditLog).filter_by(
            contact_id=contact.id, action="create",
        ).first()
        assert entry is not None
        assert entry.reason == "automatisch aus E-Mail-Sync erstellt"
