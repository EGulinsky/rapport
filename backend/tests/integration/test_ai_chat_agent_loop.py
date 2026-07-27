"""L3 Integration — app/ai/chat.py::run_chat_turn() end-to-end via
app/ai/provider.py::complete_with_tools(). Mocks at the litellm boundary
(fake_ai_provider), same convention as test_ai_provider_flow.py."""
import litellm
import pytest

from app.ai.chat import MAX_TOOL_ITERATIONS, run_chat_turn
from app.ai.provider import AIToolsUnsupported
from tests.factories import application_factory

pytestmark = pytest.mark.integration


class TestRunChatTurn:
    async def test_positiv_direkte_antwort_ohne_tool_call(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content("Du hast aktuell keine Bewerbungen.")
        user = type("U", (), {"id": 1, "vorname": None, "nachname": None, "cv_extracted_text": None, "linkedin_profile_text": None})()

        answer, tools_used = await run_chat_turn(db_session, user, "Wie viele Bewerbungen habe ich?")

        assert answer == "Du hast aktuell keine Bewerbungen."
        assert tools_used == []

    async def test_positiv_ein_tool_call_dann_finale_antwort(self, db_session, ai_settings, fake_ai_provider):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", main_status="applied")
        db_session.commit()
        fake_ai_provider.queue_tool_call("list_applications", {})
        fake_ai_provider.queue_content("Du hast eine Bewerbung bei Contoso AG als Backend Engineer.")
        user = type("U", (), {"id": 1, "vorname": None, "nachname": None, "cv_extracted_text": None, "linkedin_profile_text": None})()

        answer, tools_used = await run_chat_turn(db_session, user, "Wo habe ich mich beworben?")

        assert "Contoso AG" in answer
        assert tools_used == ["list_applications"]
        # second litellm call must include the tool result as context
        second_call_messages = fake_ai_provider.calls[1]["messages"]
        assert any(m.get("role") == "tool" for m in second_call_messages)

    async def test_positiv_mehrere_sequentielle_tool_calls(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        db_session.commit()
        fake_ai_provider.queue_tool_call("list_applications", {})
        fake_ai_provider.queue_tool_call("get_application_detail", {"application_id": app.id})
        fake_ai_provider.queue_content("Deine Bewerbung bei Contoso AG läuft seit Kurzem.")
        user = type("U", (), {"id": 1, "vorname": None, "nachname": None, "cv_extracted_text": None, "linkedin_profile_text": None})()

        answer, tools_used = await run_chat_turn(db_session, user, "Wie steht's um meine Bewerbung bei Contoso?")

        assert tools_used == ["list_applications", "get_application_detail"]
        assert "Contoso AG" in answer

    async def test_negativ_tool_fehler_bricht_loop_nicht_ab(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_tool_call("get_application_detail", {"application_id": 99999})
        fake_ai_provider.queue_content("Diese Bewerbung konnte ich nicht finden.")
        user = type("U", (), {"id": 1, "vorname": None, "nachname": None, "cv_extracted_text": None, "linkedin_profile_text": None})()

        answer, tools_used = await run_chat_turn(db_session, user, "Wie steht's um Bewerbung 99999?")

        assert "nicht finden" in answer
        assert tools_used == ["get_application_detail"]

    async def test_negativ_iterationslimit_erzwingt_finale_antwort(self, db_session, ai_settings, fake_ai_provider):
        for _ in range(MAX_TOOL_ITERATIONS):
            fake_ai_provider.queue_tool_call("list_applications", {})
        fake_ai_provider.queue_content("Basierend auf dem, was ich bereits weiß: keine offenen Bewerbungen.")
        user = type("U", (), {"id": 1, "vorname": None, "nachname": None, "cv_extracted_text": None, "linkedin_profile_text": None})()

        answer, tools_used = await run_chat_turn(db_session, user, "Fasse alles zusammen.")

        assert len(tools_used) == MAX_TOOL_ITERATIONS
        assert "keine offenen Bewerbungen" in answer
        # the forced final call must have been made with no tools at all
        assert "tools" not in fake_ai_provider.calls[-1]

    async def test_negativ_tools_nicht_unterstuetzt_wirft_aitoolsunsupported(self, db_session, ai_settings, fake_ai_provider, monkeypatch):
        monkeypatch.setattr(litellm, "supports_function_calling", lambda model: False)
        user = type("U", (), {"id": 1, "vorname": None, "nachname": None, "cv_extracted_text": None, "linkedin_profile_text": None})()

        with pytest.raises(AIToolsUnsupported):
            await run_chat_turn(db_session, user, "Hallo")
