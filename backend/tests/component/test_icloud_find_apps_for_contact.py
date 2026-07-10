"""L1 Component — _find_apps_for_contact()/_find_apps_where_contact_mentioned()
in sync_icloud.py: Firmen-/Erwähnungs-Matching für den CardDAV-Kontakte-Sync,
direkt getestet statt nur indirekt über _sync_contacts_http().
"""
import pytest

from app.routers.sync_icloud import _find_apps_for_contact, _find_apps_where_contact_mentioned
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component


class TestFindAppsForContact:
    def test_negativ_leere_organisation_liefert_leere_liste(self, db_session):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        assert _find_apps_for_contact("", db_session) == []

    def test_positiv_exakter_match_nach_entfernung_der_rechtsform(self, db_session):
        app = application_factory(db_session, firma="Contoso GmbH")
        db_session.commit()

        matched = _find_apps_for_contact("Contoso GmbH", db_session)

        assert matched == [app.id]

    def test_positiv_substring_match_wenn_kein_exakter_treffer(self, db_session):
        # "Contoso Deutschland AG" enthält "Contoso" nicht exakt als eigene
        # Firma, matcht aber über die Substring-Prüfung.
        app = application_factory(db_session, firma="Contoso Deutschland AG")
        db_session.commit()

        matched = _find_apps_for_contact("Contoso", db_session)

        assert matched == [app.id]

    def test_negativ_kein_treffer_liefert_leere_liste(self, db_session):
        application_factory(db_session, firma="Ganz andere Firma GmbH")
        db_session.commit()

        assert _find_apps_for_contact("Contoso AG", db_session) == []


class TestFindAppsWhereContactMentioned:
    def test_negativ_ohne_namen_und_email_liefert_leere_liste(self, db_session):
        application_factory(db_session)
        db_session.commit()

        assert _find_apps_where_contact_mentioned("", None, db_session) == []

    def test_negativ_zu_kurzer_name_ohne_email_liefert_leere_liste(self, db_session):
        # "Ana X" ist < 5 Zeichen und liefert daher keinen brauchbaren Suchbegriff.
        application_factory(db_session)
        db_session.commit()

        assert _find_apps_where_contact_mentioned("Ana X", None, db_session) == []

    def test_positiv_erwaehnung_im_event_wird_gefunden(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="notiz", notiz="Telefonat mit Erika Musterfrau vereinbart")
        db_session.commit()

        matched = _find_apps_where_contact_mentioned("Erika Musterfrau", None, db_session)

        assert app.id in matched

    def test_positiv_email_match_ist_hoch_spezifisch(self, db_session):
        app = application_factory(db_session, kommentar="Kontakt: erika@contoso.com")
        db_session.commit()

        matched = _find_apps_where_contact_mentioned("Zu Kurz", "erika@contoso.com", db_session)

        assert app.id in matched
