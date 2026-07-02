"""L1 Component — cleanup.py Kontakt-Dublettenerkennung (_find_contact_groups)."""
import pytest

from app.routers.cleanup import _find_contact_groups
from tests.factories import application_factory, company_profile_factory, contact_factory

pytestmark = pytest.mark.component


class TestFindContactGroups:
    def test_positiv_gleicher_name_gleiche_company_profile_id_ist_dublette(self, db_session):
        cp = company_profile_factory(db_session)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)

        groups = _find_contact_groups(db_session)

        assert len(groups) == 1
        assert len(groups[0]["remove"]) == 1

    def test_negativ_gleicher_name_unterschiedliche_firma_keine_dublette(self, db_session):
        # Kern-Regressionsfall laut Docstring: zwei verschiedene Personen mit
        # demselben Namen bei unterschiedlichen Firmen dürfen nicht vermengt werden.
        cp_a = company_profile_factory(db_session, name_display="Contoso AG")
        cp_b = company_profile_factory(db_session, name_display="Andere Firma GmbH")
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp_a.id)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp_b.id)

        groups = _find_contact_groups(db_session)

        assert groups == []

    def test_negativ_unterschiedlicher_name_keine_dublette(self, db_session):
        cp = company_profile_factory(db_session)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        contact_factory(db_session, name="Erika Musterfrau", company_profile_id=cp.id)

        groups = _find_contact_groups(db_session)

        assert groups == []

    def test_positiv_fallback_auf_normalisierten_firmentext_ohne_company_profile(self, db_session):
        # Kein company_profile_id gepflegt — Gruppierung fällt auf den
        # normalisierten Freitext des "firma"-Felds zurück.
        contact_factory(db_session, name="Max Mustermann", company_profile_id=None, firma="Contoso AG")
        contact_factory(db_session, name="Max Mustermann", company_profile_id=None, firma="CONTOSO")

        groups = _find_contact_groups(db_session)

        assert len(groups) == 1

    def test_negativ_kein_company_profile_und_unterschiedliche_firma_keine_dublette(self, db_session):
        contact_factory(db_session, name="Max Mustermann", company_profile_id=None, firma="Contoso AG")
        contact_factory(db_session, name="Max Mustermann", company_profile_id=None, firma="Andere Firma GmbH")

        groups = _find_contact_groups(db_session)

        assert groups == []

    def test_positiv_bevorzugt_kontakt_mit_mehr_bewerbungen_und_feldern_als_keeper(self, db_session):
        cp = company_profile_factory(db_session)
        sparse = contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id, email=None, telefon=None)
        rich = contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id, email="max@contoso.de", telefon="+49123")
        app = application_factory(db_session)
        rich.applications.append(app)
        db_session.flush()

        groups = _find_contact_groups(db_session)

        assert len(groups) == 1
        assert groups[0]["keep"]["id"] == rich.id
        assert groups[0]["remove"][0]["id"] == sparse.id

    def test_corner_case_drei_dubletten_gleicher_gruppe(self, db_session):
        cp = company_profile_factory(db_session)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)
        contact_factory(db_session, name="Max Mustermann", company_profile_id=cp.id)

        groups = _find_contact_groups(db_session)

        assert len(groups) == 1
        assert len(groups[0]["remove"]) == 2
