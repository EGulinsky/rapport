"""L1 Component — cleanup.py Bewerbungs-Dublettenerkennung (_find_app_groups)."""
from datetime import date

import pytest

from app.routers.cleanup import _find_app_groups
from tests.factories import application_factory, contact_factory, event_factory

pytestmark = pytest.mark.component


class TestFindAppGroups:
    def test_positiv_gleiche_firma_und_rolle_werden_als_dublette_erkannt(self, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")

        groups = _find_app_groups(db_session)

        assert len(groups) == 1
        assert len(groups[0]["remove"]) == 1

    def test_negativ_unterschiedliche_rolle_keine_dublette(self, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        application_factory(db_session, firma="Contoso AG", rolle="Frontend Engineer")

        groups = _find_app_groups(db_session)

        assert groups == []

    def test_negativ_unterschiedliche_firma_keine_dublette(self, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        application_factory(db_session, firma="Andere Firma GmbH", rolle="Engineer")

        groups = _find_app_groups(db_session)

        assert groups == []

    def test_corner_case_firma_normalisierung_ignoriert_rechtsform_und_gross_klein(self, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        application_factory(db_session, firma="CONTOSO", rolle="Engineer")

        groups = _find_app_groups(db_session)

        assert len(groups) == 1

    def test_positiv_bevorzugt_bewerbung_mit_mehr_events_und_kontakten_als_keeper(self, db_session):
        sparse = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        rich = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        event_factory(db_session, rich, typ="notiz")
        contact = contact_factory(db_session)
        rich.contacts.append(contact)
        db_session.flush()

        groups = _find_app_groups(db_session)

        assert len(groups) == 1
        assert groups[0]["keep"]["id"] == rich.id
        assert groups[0]["remove"][0]["id"] == sparse.id

    def test_positiv_events_und_kontakte_der_entfernten_bewerbung_werden_gezaehlt(self, db_session):
        # keeper hat alle "filled"-Bonusfelder gesetzt und gewinnt dadurch den
        # Score-Vergleich trotz weniger Events/Kontakten als die Dublette.
        keeper = application_factory(
            db_session, firma="Contoso AG", rolle="Engineer",
            quelle="LinkedIn", kommentar="x", wurde_besetzt_von="y", zielfirma_bei_hh="z",
            datum_bewerbung=date.today(), gespraech_1="a", gespraech_2="b",
        )
        dup = application_factory(db_session, firma="Contoso AG", rolle="Engineer")
        event_factory(db_session, dup, typ="notiz")
        contact = contact_factory(db_session)
        dup.contacts.append(contact)
        db_session.flush()

        groups = _find_app_groups(db_session)

        assert len(groups) == 1
        assert groups[0]["keep"]["id"] == keeper.id
        assert groups[0]["events_merged"] == 1
        assert groups[0]["contacts_merged"] == 1

    def test_fehleingabe_leere_rolle_wird_wie_regulaerer_wert_behandelt(self, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="")
        application_factory(db_session, firma="Contoso AG", rolle="")

        groups = _find_app_groups(db_session)

        assert len(groups) == 1
