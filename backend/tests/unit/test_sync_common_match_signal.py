"""L0 — matching-signal detail attached by find_apps_from_addresses()/
find_hint_apps()/find_matching_apps() and embedded into _classify_deterministic()'s
reason string.

Before this, an application match already decided everything (the app_id)
but discarded *why* it matched — the mail-address, contact-domain, or
company/role term that actually triggered the hit. That made it impossible
to tell from the audit log alone why a mail or contact ended up attached to
the wrong application. Each app_dict returned by the find_* helpers below now
carries a "matched_via" key with an already-translated, human-readable
description of the concrete signal, and _classify_deterministic() folds it
into the persisted reason string."""
import pytest

from app.routers.sync_common import (
    _classify_deterministic,
    _is_automated_sender,
    find_apps_from_addresses,
    find_hint_apps,
    find_matching_apps,
)

pytestmark = pytest.mark.unit


def _app(id_=1, firma="Contoso AG", rolle="Backend Engineer"):
    return {"id": id_, "firma": firma, "rolle": rolle}


class TestFindAppsFromAddresses:
    def test_positiv_email_match_signal_de(self):
        app = _app()
        result = find_apps_from_addresses(
            "Jane Doe <jane@contoso.example>", "",
            contact_email_index={"jane@contoso.example": [app]},
            contact_domain_index={},
            lang="de",
        )
        assert len(result) == 1
        assert result[0]["matched_via"] == 'Kontakt-E-Mail: jane@contoso.example'

    def test_positiv_domain_match_signal_en(self):
        app = _app()
        result = find_apps_from_addresses(
            "someone@contoso.example", "",
            contact_email_index={},
            contact_domain_index={"contoso.example": [app]},
            lang="en",
        )
        assert len(result) == 1
        assert result[0]["matched_via"] == "contact domain: contoso.example"

    def test_negativ_no_match_no_matched_via_key(self):
        result = find_apps_from_addresses(
            "nobody@example.com", "",
            contact_email_index={}, contact_domain_index={},
        )
        assert result == []

    def test_positiv_does_not_mutate_shared_index_dict(self):
        """The index dicts are built once per batch sync and reused across
        many raw_text items — the returned app_dict must be a copy, not the
        same object stored in the index, or a later call's matched_via would
        leak into an earlier already-returned result."""
        app = _app()
        index = {"jane@contoso.example": [app]}
        find_apps_from_addresses("jane@contoso.example", "", index, {}, lang="de")
        assert "matched_via" not in app


class TestFindHintApps:
    def test_positiv_term_match_signal(self):
        app = _app()
        result = find_hint_apps(
            "Wir freuen uns, Ihre Bewerbung bei Contoso AG erhalten zu haben.",
            term_to_apps={"Contoso AG": [app]},
        )
        assert len(result) == 1
        assert result[0]["matched_via"] == 'Firmen-/Rollenname: "Contoso AG"'

    def test_positiv_domain_match_signal_via_contact_domain_index(self):
        app = _app()
        result = find_hint_apps(
            "Von: recruiter@contoso.example",
            term_to_apps={},
            contact_domain_index={"contoso.example": [app]},
        )
        assert len(result) == 1
        assert result[0]["matched_via"] == "Kontakt-Domain: contoso.example"

    def test_positiv_domain_term_match_signal(self):
        # The domain is a truncated form of the company term ("conto.io" vs.
        # "Contoso") — the plain substring loop above can't catch this (the
        # full term never appears literally in the text), only the
        # domain-core-vs-term substring check that produces matched_via_domain_term.
        app = _app(firma="Contoso")
        result = find_hint_apps(
            "Von: recruiter@conto.io",
            term_to_apps={"Contoso": [app]},
        )
        assert len(result) == 1
        assert "Contoso" in result[0]["matched_via"]
        assert "conto.io" in result[0]["matched_via"]

    def test_negativ_no_match_returns_empty(self):
        assert find_hint_apps("irrelevant text", term_to_apps={"Contoso AG": [_app()]}) == []


class TestFindMatchingApps:
    def test_positiv_prefers_address_signal_over_text_hint(self):
        """When both an exact contact-email match and a company-name text hint
        would explain the same app, the stronger address-based signal wins —
        it's checked first and find_matching_apps() dedupes by id, keeping
        whichever matched_via was recorded first."""
        app = _app()
        result = find_matching_apps(
            "jane@contoso.example", "",
            "Bewerbung bei Contoso AG",
            contact_email_index={"jane@contoso.example": [app]},
            contact_domain_index={},
            term_to_apps={"Contoso AG": [app]},
        )
        assert len(result) == 1
        assert result[0]["matched_via"].startswith("Kontakt-E-Mail")

    def test_negativ_google_alerts_wird_nicht_ueber_firmenname_gematcht(self):
        # Regression (live incident, 2026-08-03): a Google Alerts news digest
        # mentioning the company name isn't evidence the applicant's own
        # application is involved -- it was being matched and saved as a
        # timeline event on every sync before this fix.
        app = _app(firma="Akkodis")
        result = find_matching_apps(
            "Google Alerts <googlealerts-noreply@google.com>", "",
            "Neuigkeiten zu Akkodis: ...",
            contact_email_index={},
            contact_domain_index={},
            term_to_apps={"Akkodis": [app]},
        )
        assert result == []

    def test_positiv_adress_match_feuert_trotzdem_fuer_automatisierten_absender(self):
        # An exact contact-email/domain match is the stronger signal and is
        # never suppressed, even for a from-address that also looks
        # automated -- only the weaker text-hint pass is skipped.
        app = _app()
        result = find_matching_apps(
            "Google Alerts <googlealerts-noreply@google.com>", "",
            "irrelevant",
            contact_email_index={"googlealerts-noreply@google.com": [app]},
            contact_domain_index={},
            term_to_apps={},
        )
        assert len(result) == 1


class TestIsAutomatedSender:
    def test_positiv_google_alerts(self):
        assert _is_automated_sender("Google Alerts <googlealerts-noreply@google.com>") is True

    def test_positiv_noreply_variante(self):
        assert _is_automated_sender("no-reply@example.com") is True

    def test_negativ_echte_person(self):
        assert _is_automated_sender("Jane Doe <jane@contoso.example>") is False

    def test_negativ_leerer_from_header(self):
        assert _is_automated_sender("") is False

    def test_negativ_recruiting_mailbox_ist_nicht_automatisiert(self):
        # Regression: a generic-but-real HR/recruiting mailbox ("talent@...")
        # is correctly excluded from contact creation (_SKIP_CONTACT_LOCALS),
        # but it still sends genuine, on-topic correspondence about an
        # application and must keep matching by company/role mention —
        # conflating the two lists broke exactly that (caught by existing
        # gmail/icloud sync integration tests).
        assert _is_automated_sender("Recruiting Team <talent@some-ats-vendor.example>") is False


class TestClassifyDeterministicMatchSignal:
    def test_positiv_calendar_reason_includes_match_signal(self):
        hint_apps = [{**_app(), "matched_via": 'Firmen-/Rollenname: "Contoso AG"'}]
        det = _classify_deterministic("gcal", "Betreff: Interview", None, hint_apps, lang="de")
        assert det["match_signal"] == 'Firmen-/Rollenname: "Contoso AG"'
        assert "Kalendertermin" in det["reason"]
        assert "Contoso AG" in det["reason"]

    def test_positiv_local_files_reason_includes_match_signal(self):
        hint_apps = [{**_app(), "matched_via": "Kontakt-Domain: contoso.example"}]
        det = _classify_deterministic("local_files", "Contoso_Vertrag.pdf", None, hint_apps, lang="de")
        assert det["match_signal"] == "Kontakt-Domain: contoso.example"
        assert "contoso.example" in det["reason"]

    def test_positiv_single_hint_reason_includes_match_signal(self):
        hint_apps = [{**_app(), "matched_via": "Kontakt-E-Mail: jane@contoso.example"}]
        det = _classify_deterministic(
            "gmail", "Betreff: Absage\n\nLeider koennen wir Ihnen keine Zusage machen.",
            None, hint_apps, lang="de",
        )
        assert det["match_signal"] == "Kontakt-E-Mail: jane@contoso.example"
        assert "jane@contoso.example" in det["reason"]

    def test_positiv_multi_hint_reason_includes_match_signal_and_count(self):
        hint_apps = [
            {**_app(id_=1), "matched_via": 'Firmen-/Rollenname: "Contoso AG"'},
            {**_app(id_=2), "matched_via": 'Firmen-/Rollenname: "Contoso Consulting"'},
        ]
        det = _classify_deterministic(
            "gmail", "Betreff: Frage\n\nHallo, kurze Frage zum Stand.",
            None, hint_apps, lang="de",
        )
        assert det["app_id"] == 1
        assert det["match_signal"] == 'Firmen-/Rollenname: "Contoso AG"'
        assert "2 Matches" in det["reason"]
        assert "Contoso AG" in det["reason"]

    def test_negativ_no_matched_via_falls_back_to_plain_reason(self):
        """hint_apps built without matched_via (e.g. an older/manual caller
        that pre-dates this feature) should still work — reason just has no
        appended match-signal segment."""
        hint_apps = [_app()]
        det = _classify_deterministic("gcal", "Betreff: Interview", None, hint_apps, lang="de")
        assert det["match_signal"] is None
        assert det["reason"] == "Kalendertermin → immer Gespräch"
