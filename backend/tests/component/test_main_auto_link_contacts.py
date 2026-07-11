"""L1 Component — _auto_link_contacts() in main.py: verknüpft beim Start
Kontakte ohne company_profile_id anhand ihres Firmennamens mit einem
bestehenden CompanyProfile."""
import pytest

from app.main import _auto_link_contacts
from tests.factories import company_profile_factory, contact_factory

pytestmark = pytest.mark.component


class TestAutoLinkContacts:
    def test_positiv_verknuepft_kontakt_mit_passendem_profil(self, db_session):
        profile = company_profile_factory(db_session, name_display="Contoso AG", name_norm="contoso")
        contact = contact_factory(db_session, firma="Contoso AG", company_profile_id=None)
        db_session.commit()

        _auto_link_contacts()

        db_session.refresh(contact)
        assert contact.company_profile_id == profile.id

    def test_negativ_kein_passendes_profil_bleibt_unveraendert(self, db_session):
        contact = contact_factory(db_session, firma="Unbekannte Firma GmbH", company_profile_id=None)
        db_session.commit()

        _auto_link_contacts()

        db_session.refresh(contact)
        assert contact.company_profile_id is None

    def test_negativ_kontakt_ohne_firma_wird_uebersprungen(self, db_session):
        contact = contact_factory(db_session, firma=None, company_profile_id=None)
        db_session.commit()

        _auto_link_contacts()  # darf nicht crashen

        db_session.refresh(contact)
        assert contact.company_profile_id is None

    def test_positiv_bereits_verknuepfter_kontakt_wird_nicht_angefasst(self, db_session):
        profile_a = company_profile_factory(db_session, name_display="A", name_norm="a")
        profile_b = company_profile_factory(db_session, name_display="Contoso AG", name_norm="contoso")
        contact = contact_factory(db_session, firma="Contoso AG", company_profile_id=profile_a.id)
        db_session.commit()

        _auto_link_contacts()

        db_session.refresh(contact)
        assert contact.company_profile_id == profile_a.id != profile_b.id

    def test_negativ_datenbankfehler_wird_geschluckt(self, db_session, monkeypatch):
        import app.database as db_module

        def _raise(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(db_module, "SessionLocal", _raise)

        _auto_link_contacts()  # darf nicht crashen, nur geloggt werden
