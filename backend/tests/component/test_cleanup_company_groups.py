"""L1 Component — cleanup.py Firmen-Dublettenerkennung gegen echte Test-DB.
Beweist gleichzeitig, dass die Factories funktionieren.
"""
import pytest

from app.routers.cleanup import _find_company_groups
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


class TestFindCompanyGroups:
    def test_positiv_gleiche_domain_wird_als_dublette_erkannt(self, db_session):
        company_profile_factory(db_session, name_display="Contoso AG", website="https://www.contoso.com/")
        company_profile_factory(db_session, name_display="Contoso Advanta", website="https://www.contoso.com/")

        groups = _find_company_groups(db_session)

        assert len(groups) == 1
        names = {groups[0]["keep"]["name"]} | {r["name"] for r in groups[0]["remove"]}
        assert names == {"Contoso AG", "Contoso Advanta"}

    def test_negativ_unterschiedliche_domains_keine_dublette(self, db_session):
        company_profile_factory(db_session, name_display="Contoso AG", website="https://www.contoso.com/")
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

    def test_negativ_bereits_verknuepfte_tochterfirma_wird_ignoriert(self, db_session):
        # Regressionsfall: Töchter teilen oft die Website-Domain der Mutter
        # (z.B. "Contoso Digital Industries Software" unter contoso.com) und
        # wurden fälschlich als Dublette der Mutter erkannt, obwohl die
        # Beziehung über parent_company_id bereits gepflegt war. Live an
        # Produktivdaten verifiziert: 3 bereits verknüpfte Contoso-Töchter
        # wurden korrekt ausgeschlossen.
        parent = company_profile_factory(db_session, name_display="Contoso AG", website="https://www.contoso.com/")
        company_profile_factory(db_session, name_display="Contoso Digital Industries Software", website="https://www.contoso.com/", parent_company_id=parent.id)

        groups = _find_company_groups(db_session)

        assert groups == []

    def test_positiv_teilweise_verknuepft_rest_bleibt_dublette(self, db_session):
        # Mutter + eine bereits zugeordnete Tochter + eine noch unverknüpfte
        # dritte Firma auf derselben Domain: die verknüpfte Tochter wird
        # ausgeblendet, die unverknüpfte bleibt als echte Dublette übrig.
        parent = company_profile_factory(db_session, name_display="Contoso AG", website="https://www.contoso.com/")
        company_profile_factory(db_session, name_display="Contoso Advanta", website="https://www.contoso.com/", parent_company_id=parent.id)
        unresolved = company_profile_factory(db_session, name_display="Contoso PV", website="https://www.contoso.com/")

        groups = _find_company_groups(db_session)

        assert len(groups) == 1
        names = {groups[0]["keep"]["name"]} | {r["name"] for r in groups[0]["remove"]}
        assert names == {"Contoso AG", "Contoso PV"}
        assert unresolved.name_display in names

    def test_corner_case_verknuepfung_ausserhalb_des_buckets_zaehlt_nicht(self, db_session):
        # parent_company_id zeigt auf eine Firma AUSSERHALB dieser Domain-
        # Gruppe (z.B. ein anderer Datenfehler) — darf die beiden Profile in
        # diesem Bucket nicht fälschlich als "bereits verknüpft" ausschließen.
        other_domain_parent = company_profile_factory(db_session, name_display="Andere Firma", website="https://www.andere-firma.de/")
        a = company_profile_factory(db_session, name_display="Contoso AG", website="https://www.contoso.com/", parent_company_id=other_domain_parent.id)
        b = company_profile_factory(db_session, name_display="Contoso Advanta", website="https://www.contoso.com/")

        groups = _find_company_groups(db_session)

        assert len(groups) == 1
        names = {a.name_display, b.name_display}
        found_names = {groups[0]["keep"]["name"]} | {r["name"] for r in groups[0]["remove"]}
        assert found_names == names
