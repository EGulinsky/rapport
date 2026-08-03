"""L1 Component -- _upsert_contact() in sync_common.py: name-based dedup
fallback and new-contact name storage.

Regression for a live incident (2026-08-03, application "AKKODIS"): an
existing contact "Timo Divivier" (name="Divivier", vorname="Timo", no email
-- e.g. from a LinkedIn import) wasn't matched against a mail from
"Timo.DIVIVIER@akkodis.com" (From header "DIVIVIER Timo"), creating a
duplicate contact instead of linking to the existing one. Two compounding
causes, both fixed here: (1) the dedup fallback compared the raw sender name
against the candidate's raw "name" column, which can hold only the surname
depending on which path created it -- not a like-for-like comparison; (2) a
new contact from this path stored the full raw sender name in "name" instead
of just the surname, unlike every other contact-creation path."""
from datetime import date

import pytest

from app import models
from app.routers.sync_common import _upsert_contact
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.component


class TestUpsertContactNameDedup:
    def test_positiv_matcht_bestehenden_kontakt_trotz_asymmetrischer_namensspeicherung(self, db_session):
        # Existing contact stores only the surname in "name" (the "most
        # paths" convention) -- no email, so the email-based lookup can't
        # find it; only the name+company fallback can.
        app = application_factory(db_session, firma="Akkodis")
        contact_factory(db_session, name="Divivier", vorname="Timo", email=None, firma="Akkodis")
        db_session.commit()

        _upsert_contact(
            db_session, "DIVIVIER Timo", "timo.divivier@akkodis.com", app.id, "Akkodis",
            is_headhunter=False, event_date=date.today(),
        )
        db_session.commit()

        contacts = db_session.query(models.Contact).filter_by(firma="Akkodis").all()
        assert len(contacts) == 1  # no duplicate created
        assert contacts[0].email == "timo.divivier@akkodis.com"  # backfilled onto the existing row

    def test_positiv_neuer_kontakt_speichert_nachname_nicht_vollen_rohnamen(self, db_session):
        app = application_factory(db_session, firma="Contoso")

        _upsert_contact(
            db_session, "GOEZ Jana", "jana.goez@contoso.example", app.id, "Contoso",
            is_headhunter=False, event_date=date.today(),
        )
        db_session.commit()

        contact = db_session.query(models.Contact).filter_by(email="jana.goez@contoso.example").first()
        assert contact is not None
        assert contact.name == "GOEZ"
        assert contact.vorname == "Jana"
        assert contact.display_name == "Jana GOEZ"  # no doubled name
