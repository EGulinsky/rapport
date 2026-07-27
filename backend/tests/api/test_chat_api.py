"""L2 API — /api/chat/history, /api/chat/messages, /api/chat. Patches
app.ai.chat.run_chat_turn directly (same convention as the ai-assess
endpoint tests in test_applications_events_contacts_api.py) rather than
mocking litellm — the agent loop itself is covered by
test_ai_chat_agent_loop.py."""
from unittest.mock import patch

import pytest

from app import models

pytestmark = pytest.mark.api


class TestChatHistory:
    def test_positiv_leer_ohne_nachrichten(self, client):
        resp = client.get("/api/chat/history")

        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    def test_positiv_liefert_gespeicherte_nachrichten_aufsteigend(self, client, db_session):
        db_session.add(models.ChatMessage(user_id=1, role="user", content="Hallo"))
        db_session.add(models.ChatMessage(user_id=1, role="assistant", content="Hi, wie kann ich helfen?"))
        db_session.commit()

        resp = client.get("/api/chat/history")

        body = resp.json()["messages"]
        assert [m["content"] for m in body] == ["Hallo", "Hi, wie kann ich helfen?"]

    def test_negativ_andere_user_id_nicht_sichtbar(self, client, db_session):
        db_session.add(models.ChatMessage(user_id=2, role="user", content="Fremde Nachricht"))
        db_session.commit()

        resp = client.get("/api/chat/history")

        assert resp.json()["messages"] == []


class TestSendMessage:
    def test_positiv_persistiert_beide_nachrichten(self, client, db_session):
        async def _fake_run_chat_turn(db, current_user, user_text):
            return "Du hast aktuell keine Bewerbungen.", []

        with patch("app.routers.chat.run_chat_turn", new=_fake_run_chat_turn):
            resp = client.post("/api/chat/messages", json={"content": "Wie viele Bewerbungen habe ich?"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_message"]["content"] == "Wie viele Bewerbungen habe ich?"
        assert body["assistant_message"]["content"] == "Du hast aktuell keine Bewerbungen."
        rows = db_session.query(models.ChatMessage).order_by(models.ChatMessage.id).all()
        assert [r.role for r in rows] == ["user", "assistant"]

    def test_negativ_leerer_inhalt_liefert_422(self, client):
        resp = client.post("/api/chat/messages", json={"content": ""})
        assert resp.status_code == 422

    def test_negativ_ai_not_configured_liefert_400_behaelt_user_nachricht(self, client, db_session):
        from app.ai.provider import AINotConfigured

        async def _fake_run_chat_turn(db, current_user, user_text):
            raise AINotConfigured("nicht konfiguriert")

        with patch("app.routers.chat.run_chat_turn", new=_fake_run_chat_turn):
            resp = client.post("/api/chat/messages", json={"content": "Hallo"})

        assert resp.status_code == 400
        rows = db_session.query(models.ChatMessage).all()
        assert len(rows) == 1
        assert rows[0].role == "user"

    def test_negativ_rate_limit_liefert_429_mit_error_key(self, client):
        from app.ai.provider import AIRateLimited

        async def _fake_run_chat_turn(db, current_user, user_text):
            raise AIRateLimited("zu viele Anfragen")

        with patch("app.routers.chat.run_chat_turn", new=_fake_run_chat_turn):
            resp = client.post("/api/chat/messages", json={"content": "Hallo"})

        assert resp.status_code == 429
        assert resp.json()["detail"]["error_key"] == "ai.rate_limit"

    def test_negativ_tools_unsupported_liefert_400_mit_error_key(self, client):
        from app.ai.provider import AIToolsUnsupported

        async def _fake_run_chat_turn(db, current_user, user_text):
            raise AIToolsUnsupported("kein Tool-Calling")

        with patch("app.routers.chat.run_chat_turn", new=_fake_run_chat_turn):
            resp = client.post("/api/chat/messages", json={"content": "Hallo"})

        assert resp.status_code == 400
        assert resp.json()["detail"]["error_key"] == "ai.tools_unsupported"


class TestClearConversation:
    def test_positiv_loescht_alle_nachrichten(self, client, db_session):
        db_session.add(models.ChatMessage(user_id=1, role="user", content="Hallo"))
        db_session.commit()

        resp = client.delete("/api/chat")

        assert resp.status_code == 204
        assert db_session.query(models.ChatMessage).count() == 0

    def test_negativ_loescht_nur_eigene_nachrichten(self, client, db_session):
        from sqlalchemy import text

        db_session.add(models.ChatMessage(user_id=1, role="user", content="Meine"))
        db_session.add(models.ChatMessage(user_id=2, role="user", content="Fremde"))
        db_session.commit()

        client.delete("/api/chat")

        # Raw SQL bypasses the ORM-level tenant filter (which the `client`
        # fixture's set_session_user() call left active on this very
        # session) — needed here to see across both users' rows at once.
        remaining = db_session.execute(text("SELECT content FROM chat_messages")).fetchall()
        assert [r[0] for r in remaining] == ["Fremde"]
