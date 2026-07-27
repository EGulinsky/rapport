"""L1 Unit — rapportGPT's tool executors in app/ai/chat.py, called directly
against a seeded DB (no litellm involved — see test_ai_chat_agent_loop.py
for the agent-loop integration tests that go through complete_with_tools())."""
import pytest

from app import models
from app.ai import chat
from app.database import set_session_user
from tests.factories import application_factory, company_profile_factory, contact_factory, event_factory

pytestmark = pytest.mark.unit


class TestListApplications:
    def test_positiv_liefert_kompakte_liste(self, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="applied")
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_list_applications(db_session, {})

        assert len(result) == 1
        assert result[0]["firma"] == "Contoso AG"
        assert result[0]["rolle"] == "Backend Engineer"
        assert "ai_color" not in result[0]

    def test_positiv_filtert_nach_status(self, db_session):
        application_factory(db_session, firma="Contoso AG", main_status="applied")
        application_factory(db_session, firma="Fabrikam GmbH", main_status="rejected")
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_list_applications(db_session, {"status": "rejected"})

        assert [a["firma"] for a in result] == ["Fabrikam GmbH"]

    def test_positiv_filtert_nach_firmenname(self, db_session):
        application_factory(db_session, firma="Contoso AG")
        application_factory(db_session, firma="Fabrikam GmbH")
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_list_applications(db_session, {"company_name_contains": "contoso"})

        assert [a["firma"] for a in result] == ["Contoso AG"]

    def test_negativ_andere_user_id_nicht_sichtbar(self, db_session):
        application_factory(db_session, firma="Firma A", user_id=1)
        application_factory(db_session, firma="Firma B", user_id=2)
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_list_applications(db_session, {})

        assert [a["firma"] for a in result] == ["Firma A"]


class TestGetApplicationDetail:
    def test_positiv_liefert_volle_details_mit_timeline_und_kontakten(self, db_session):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        event_factory(db_session, app, typ="mail", titel="Zwischenstand", notiz="Kurzes Update.")
        contact = contact_factory(db_session, name="Bernsee", vorname="Dennis")
        app.contacts.append(contact)
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_get_application_detail(db_session, {"application_id": app.id})

        assert result["firma"] == "Contoso AG"
        assert "Zwischenstand" in result["timeline"]
        assert result["contacts"][0]["name"] == "Dennis Bernsee"

    def test_negativ_unbekannte_id_liefert_error_payload(self, db_session):
        set_session_user(db_session, 1)

        result = chat._tool_get_application_detail(db_session, {"application_id": 99999})

        assert result["error"] == "not_found"

    def test_negativ_andere_user_id_liefert_not_found(self, db_session):
        app = application_factory(db_session, firma="Firma A", user_id=2)
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_get_application_detail(db_session, {"application_id": app.id})

        assert result["error"] == "not_found"


class TestGetCompanyDetail:
    def test_positiv_nach_id(self, db_session):
        cp = company_profile_factory(db_session, name_display="Contoso AG", industry="Software")
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_get_company_detail(db_session, {"company_id": cp.id})

        assert result["name_display"] == "Contoso AG"
        assert result["industry"] == "Software"

    def test_positiv_nach_name_eindeutiger_treffer(self, db_session):
        company_profile_factory(db_session, name_display="Contoso AG")
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_get_company_detail(db_session, {"company_name": "contoso"})

        assert result["name_display"] == "Contoso AG"

    def test_negativ_name_kein_treffer(self, db_session):
        set_session_user(db_session, 1)

        result = chat._tool_get_company_detail(db_session, {"company_name": "Nonexistent"})

        assert result["error"] == "not_found"

    def test_negativ_name_mehrdeutig_liefert_matches(self, db_session):
        company_profile_factory(db_session, name_display="Contoso AG")
        company_profile_factory(db_session, name_display="Contoso GmbH")
        db_session.commit()
        set_session_user(db_session, 1)

        result = chat._tool_get_company_detail(db_session, {"company_name": "contoso"})

        assert result["error"] == "ambiguous"
        assert len(result["matches"]) == 2

    def test_negativ_keine_argumente(self, db_session):
        set_session_user(db_session, 1)

        result = chat._tool_get_company_detail(db_session, {})

        assert result["error"] == "missing_argument"


class TestGetUserProfile:
    def test_positiv_liefert_cv_und_linkedin_text(self):
        user = models.User(
            id=1, email="x@example.com", password_hash="x",
            vorname="Eugen", nachname="Gulinsky",
            cv_extracted_text="Erfahrener Backend-Entwickler.",
            linkedin_profile_text="Headline: Senior Engineer.",
        )

        result = chat._tool_get_user_profile(user)

        assert result["cv_text"] == "Erfahrener Backend-Entwickler."
        assert result["linkedin_text"] == "Headline: Senior Engineer."
        assert "note" not in result

    def test_positiv_ohne_cv_und_linkedin_hat_hinweis(self):
        user = models.User(id=1, email="x@example.com", password_hash="x")

        result = chat._tool_get_user_profile(user)

        assert result["cv_text"] is None
        assert result["linkedin_text"] is None
        assert "note" in result
