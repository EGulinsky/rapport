"""L1 Component — _match_contacts_by_name() in sync_icloud.py.

Fallback-Matching für den Anrufliste-Sync, wenn ein Anruf keine (oder keine
passende) Telefonnummer mitbringt: mindestens 2 gemeinsame Namens-Tokens
(Vor-/Nachname), oder 1 Token, wenn es lang/eindeutig genug ist (>= 6 Zeichen).
"""
import pytest

from app.routers.sync_icloud import _match_contacts_by_name
from tests.factories import contact_factory

pytestmark = pytest.mark.component


class TestMatchContactsByName:
    def test_positiv_vor_und_nachname_matchen(self, db_session):
        contact = contact_factory(db_session, name="Musterfrau", vorname="Erika")
        contact.name = "Erika Musterfrau"
        db_session.commit()

        matched = _match_contacts_by_name("Erika Musterfrau", db_session)

        assert contact in matched

    def test_positiv_vertauschte_reihenfolge_matcht_trotzdem(self, db_session):
        contact = contact_factory(db_session, name="Musterfrau Erika")
        db_session.commit()

        matched = _match_contacts_by_name("Erika Musterfrau", db_session)

        assert contact in matched

    def test_negativ_nur_ein_kurzes_gemeinsames_token_matcht_nicht(self, db_session):
        contact_factory(db_session, name="Karl Kurz")
        db_session.commit()

        matched = _match_contacts_by_name("Karl Neumann", db_session)

        assert matched == []

    def test_positiv_ein_langes_eindeutiges_token_reicht(self, db_session):
        contact = contact_factory(db_session, name="Musterfrau")
        db_session.commit()

        matched = _match_contacts_by_name("Musterfrau", db_session)

        assert contact in matched

    def test_negativ_leerer_name_liefert_keine_treffer(self, db_session):
        contact_factory(db_session, name="Erika Musterfrau")
        db_session.commit()

        matched = _match_contacts_by_name("", db_session)

        assert matched == []

    def test_negativ_kontakt_mit_leerem_namen_wird_uebersprungen(self, db_session):
        from app import models
        c = models.Contact(name="", user_id=1)
        db_session.add(c)
        db_session.commit()

        matched = _match_contacts_by_name("Erika Musterfrau", db_session)

        assert matched == []
