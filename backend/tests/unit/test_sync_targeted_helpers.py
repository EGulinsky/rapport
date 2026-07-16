"""L0/L1 — reine Logik-Helfer in sync_targeted.py (Suchbegriffe, Domain-Matching,
Text-Matching, Live-Kandidaten-Deduplizierung). Keine Netzwerk-Mocks nötig.
"""
from datetime import date

import pytest

from app import models
from app.routers.sync_targeted import (
    _app_dict,
    _company_domains_for_app,
    _contact_mentioned_in_app,
    _domain_from_website,
    _make_live_candidate,
    _query_safe,
    _search_terms,
    _text_matches,
    _vobj_str,
)
from tests.factories import application_factory, company_profile_factory, contact_factory, event_factory

pytestmark = pytest.mark.unit


class TestSearchTerms:
    def test_positiv_firma_liefert_basisvariante_und_kurzform(self, db_session):
        app = application_factory(db_session, firma="Contoso AG", zielfirma_bei_hh=None, wurde_besetzt_von=None)
        terms = _search_terms(app, db_session)
        assert "Contoso AG" in terms
        assert "Contoso" in terms

    def test_positiv_zielfirma_und_wurde_besetzt_von_werden_einbezogen(self, db_session):
        app = application_factory(
            db_session, firma="Headhunter GmbH", zielfirma_bei_hh="Contoso AG", wurde_besetzt_von="Andere Firma AG",
        )
        terms = _search_terms(app, db_session)
        assert "Contoso AG" in terms
        assert "Andere Firma AG" in terms

    def test_positiv_alias_firma_aus_merge_wird_einbezogen(self, db_session):
        app = application_factory(db_session, firma="Contoso Deutschland GmbH")
        db_session.add(models.MergeAlias(entity_type="application", canonical_id=app.id, alias_firma="Alte Schreibweise AG"))
        db_session.commit()
        terms = _search_terms(app, db_session)
        assert "Alte Schreibweise AG" in terms

    def test_negativ_zu_kurze_firma_wird_ausgeschlossen(self, db_session):
        # rolle="" (not the factory's random fake.job() default) — the role
        # is included in _search_terms() too now, see the tests below, and
        # would otherwise randomly pollute this "nothing at all" assertion.
        app = application_factory(db_session, firma="AB", zielfirma_bei_hh=None, wurde_besetzt_von=None, rolle="")
        assert _search_terms(app, db_session) == []

    def test_corner_case_keine_doppelten_varianten(self, db_session):
        app = application_factory(db_session, firma="Contoso AG", zielfirma_bei_hh="Contoso AG", wurde_besetzt_von=None)
        terms = _search_terms(app, db_session)
        assert terms.count("Contoso AG") == 1

    def test_positiv_rolle_wird_als_ganze_phrase_einbezogen(self, db_session):
        app = application_factory(
            db_session, firma="Qorix", zielfirma_bei_hh=None, wurde_besetzt_von=None,
            rolle="Senior SW Projektleiter BMW",
        )
        terms = _search_terms(app, db_session)
        assert "Senior SW Projektleiter BMW" in terms
        # Not split into words — see the #230 false-positive incident this
        # whole-phrase design fixes (documented in this function's docstring).
        assert "Senior" not in terms
        assert "Projektleiter" not in terms

    def test_negativ_generisches_einzelwort_als_rolle_wird_ausgeschlossen(self, db_session):
        app = application_factory(db_session, firma="AB", zielfirma_bei_hh=None, wurde_besetzt_von=None, rolle="Manager")
        assert _search_terms(app, db_session) == []

    def test_negativ_generisches_einzelwort_gross_klein_wird_auch_ausgeschlossen(self, db_session):
        app = application_factory(db_session, firma="AB", zielfirma_bei_hh=None, wurde_besetzt_von=None, rolle="SENIOR")
        assert _search_terms(app, db_session) == []


class TestAppDict:
    def test_positiv_enthaelt_zielfirma_wenn_gesetzt(self, db_session):
        app = application_factory(db_session, is_headhunter=True, zielfirma_bei_hh="Contoso AG")
        d = _app_dict(app)
        assert d["zielfirma"] == "Contoso AG"

    def test_negativ_ohne_zielfirma_fehlt_der_schluessel(self, db_session):
        app = application_factory(db_session, zielfirma_bei_hh=None)
        assert "zielfirma" not in _app_dict(app)


class TestDomainFromWebsite:
    def test_positiv_extrahiert_domain_ohne_www(self):
        assert _domain_from_website("https://www.here.com/") == "here.com"

    def test_positiv_funktioniert_ohne_schema(self):
        # urlparse ohne Schema liefert kein hostname -> None ist hier das erwartete,
        # dokumentierte Verhalten (kein Fallback-Parsing).
        assert _domain_from_website("here.com") is None

    def test_negativ_none_liefert_none(self):
        assert _domain_from_website(None) is None

    def test_negativ_leerstring_liefert_none(self):
        assert _domain_from_website("") is None

    def test_corner_case_host_ohne_punkt_liefert_none(self):
        assert _domain_from_website("https://localhost/") is None


class TestCompanyDomainsForApp:
    def test_positiv_direkte_bewerbung_nutzt_company_profile_domain(self, db_session):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, is_headhunter=False, company_profile_id=profile.id)
        assert _company_domains_for_app(app, [], db_session) == ["contoso.de"]

    def test_positiv_headhunter_nutzt_ziel_und_hh_domain(self, db_session):
        target = company_profile_factory(db_session, website="https://www.contoso.de/")
        hh = company_profile_factory(db_session, website="https://www.headhunter-gmbh.de/")
        app = application_factory(
            db_session, is_headhunter=True, company_profile_id=hh.id, target_company_profile_id=target.id,
        )
        domains = _company_domains_for_app(app, [], db_session)
        assert domains == sorted(["contoso.de", "headhunter-gmbh.de"])

    def test_positiv_kontakt_email_domain_wird_ergaenzt(self, db_session):
        app = application_factory(db_session, is_headhunter=False, company_profile_id=None)
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()
        assert _company_domains_for_app(app, [], db_session) == ["contoso.com"]

    def test_negativ_personal_domain_wird_ausgeschlossen(self, db_session):
        profile = company_profile_factory(db_session, website="https://www.gmail.com/")
        app = application_factory(db_session, is_headhunter=False, company_profile_id=profile.id)
        contact = contact_factory(db_session, email="jemand@gmail.com")
        app.contacts.append(contact)
        db_session.commit()
        assert _company_domains_for_app(app, [], db_session) == []

    def test_negativ_ohne_profile_und_kontakte_leere_liste(self, db_session):
        app = application_factory(db_session, is_headhunter=False, company_profile_id=None)
        assert _company_domains_for_app(app, [], db_session) == []

    def test_positiv_contacts_override_ignoriert_live_app_contacts(self, db_session):
        # Regression test for the #230 followup incident: a contact created
        # by one sync source mid-run (e.g. mail) becomes visible via the
        # live app.contacts relationship to a sibling source (e.g. GCal)
        # running in the same asyncio.gather() call moments later, even
        # before anything is committed. Passing a pre-sync `contacts`
        # snapshot must make the live, newly-added contact's domain
        # invisible — only the snapshot's contacts count.
        app = application_factory(db_session, is_headhunter=False, company_profile_id=None)
        live_only_contact = contact_factory(db_session, email="justcreated@newcompany.com")
        app.contacts.append(live_only_contact)
        db_session.commit()

        assert _company_domains_for_app(app, [], db_session, contacts=[]) == []
        assert _company_domains_for_app(app, [], db_session) == ["newcompany.com"]

    def test_positiv_contacts_override_nutzt_uebergebene_liste(self, db_session):
        app = application_factory(db_session, is_headhunter=False, company_profile_id=None)
        snapshot_contact = contact_factory(db_session, email="recruiterin@contoso.com")
        db_session.commit()

        assert _company_domains_for_app(app, [], db_session, contacts=[snapshot_contact]) == ["contoso.com"]


class TestTextMatches:
    def test_positiv_case_insensitiv(self):
        assert _text_matches("Wir bei CONTOSO suchen...", ["contoso"]) is True

    def test_negativ_kein_treffer(self):
        assert _text_matches("Newsletter dieser Woche", ["contoso"]) is False


class TestQuerySafe:
    def test_positiv_operatoren_werden_zu_leerzeichen(self):
        assert _query_safe("C++ & Java|Python") == "C Java Python"

    def test_positiv_klammern_werden_entfernt(self):
        assert _query_safe("Backend (Senior) [DE]") == "Backend Senior DE"


class TestVobjStr:
    def test_negativ_fehlendes_attribut_liefert_leerstring(self):
        class _Empty:
            pass
        assert _vobj_str(_Empty(), "summary") == ""

    def test_positiv_extrahiert_value_attribut(self):
        class _Val:
            value = "Interview Termin"
        class _VEvent:
            summary = _Val()
        assert _vobj_str(_VEvent(), "summary") == "Interview Termin"


class TestContactMentionedInApp:
    def test_positiv_name_im_kommentar_feld(self, db_session):
        app = application_factory(db_session, kommentar="Gespräch mit Erika Musterfrau war gut.")
        assert _contact_mentioned_in_app("Erika Musterfrau", None, app, db_session) is True

    def test_positiv_name_in_event_titel(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, titel="Interview mit Erika Musterfrau")
        assert _contact_mentioned_in_app("Erika Musterfrau", None, app, db_session) is True

    def test_positiv_email_in_event_notiz(self, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, titel="Interview", notiz="Kontakt: erika@contoso.de")
        assert _contact_mentioned_in_app("Unbekannter Name", "erika@contoso.de", app, db_session) is True

    def test_negativ_kein_treffer(self, db_session):
        app = application_factory(db_session, kommentar="Nichts Relevantes.")
        assert _contact_mentioned_in_app("Erika Musterfrau", "erika@contoso.de", app, db_session) is False


class TestMakeLiveCandidate:
    def test_positiv_erster_treffer_wird_zurueckgegeben(self):
        seen = set()
        cand = _make_live_candidate("gmail", "msg-1", date.today(), "Betreff", "Auszug", seen)
        assert cand is not None
        assert cand["event_type"] == "email"
        assert ("gmail:msg-1") in seen

    def test_negativ_duplikat_liefert_none(self):
        seen = {"gmail:msg-1"}
        assert _make_live_candidate("gmail", "msg-1", date.today(), "Betreff", "Auszug", seen) is None

    def test_positiv_event_type_fuer_kalenderquelle(self):
        seen = set()
        cand = _make_live_candidate("gcal", "evt-1", date.today(), "Termin", "", seen)
        assert cand["event_type"] == "termin"

    def test_positiv_event_type_fuer_notizquelle(self):
        seen = set()
        cand = _make_live_candidate("icloud_notes", "note-1", date.today(), "Notiz", "", seen)
        assert cand["event_type"] == "notiz"
