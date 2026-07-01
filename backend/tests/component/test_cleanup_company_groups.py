"""L1 Component — cleanup.py Firmen-Dublettenerkennung gegen echte Test-DB.
Beweist gleichzeitig, dass die Factories funktionieren.
"""
import pytest

from app.routers.cleanup import _find_company_groups
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


class TestFindCompanyGroups:
    def test_positiv_gleiche_domain_wird_als_dublette_erkannt(self, db_session):
        company_profile_factory(db_session, name_display="Siemens", website="https://www.siemens.com/")
        company_profile_factory(db_session, name_display="Siemens Advanta", website="https://www.siemens.com/")

        groups = _find_company_groups(db_session)

        assert len(groups) == 1
        names = {groups[0]["keep"]["name"]} | {r["name"] for r in groups[0]["remove"]}
        assert names == {"Siemens", "Siemens Advanta"}

    def test_negativ_unterschiedliche_domains_keine_dublette(self, db_session):
        company_profile_factory(db_session, name_display="Siemens", website="https://www.siemens.com/")
        company_profile_factory(db_session, name_display="Bosch", website="https://www.bosch.com/")

        groups = _find_company_groups(db_session)

        assert groups == []

    def test_corner_case_generische_domain_wird_ignoriert(self, db_session):
        # example.com ist ein Platzhalter — darf keine Dublette zwischen zwei
        # völlig unabhängigen Firmen erzeugen (Regressionstest für den Bug,
        # der in dieser Session live an Produktivdaten gefunden wurde).
        company_profile_factory(db_session, name_display="Firma A", website="https://www.example.com/")
        company_profile_factory(db_session, name_display="Firma B", website="https://www.example.com/")

        groups = _find_company_groups(db_session)

        assert groups == []

    def test_corner_case_kein_website_kein_match(self, db_session):
        company_profile_factory(db_session, name_display="Firma ohne Website", website=None)
        company_profile_factory(db_session, name_display="Noch eine Firma ohne Website", website=None)

        groups = _find_company_groups(db_session)

        assert groups == []

    def test_positiv_bestes_profil_wird_als_keeper_gewaehlt(self, db_session):
        from tests.factories import application_factory, contact_factory

        sparse = company_profile_factory(db_session, name_display="Sparse GmbH", website="https://www.acme.de/")
        rich = company_profile_factory(db_session, name_display="Acme GmbH", website="https://www.acme.de/", description="Ausführliche Firmenbeschreibung")
        app = application_factory(db_session, company_profile_id=rich.id)
        contact_factory(db_session, company_profile_id=rich.id)
        db_session.flush()

        groups = _find_company_groups(db_session)

        assert len(groups) == 1
        assert groups[0]["keep"]["id"] == rich.id
        assert groups[0]["remove"][0]["id"] == sparse.id
        assert app.company_profile_id == rich.id  # sanity: Fixture-Setup korrekt verknüpft
