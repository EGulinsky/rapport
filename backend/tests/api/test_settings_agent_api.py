"""L2 API — /api/settings/agent*: Token wird verschlüsselt gespeichert, nie
im Klartext zurückgegeben (nur has_token)."""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.api


class TestAgentSettings:
    def test_positiv_ohne_gespeicherten_token(self, client):
        resp = client.get("/api/settings/agent")

        assert resp.status_code == 200
        assert resp.json() == {"url": None, "has_token": False}

    def test_positiv_token_speichern_setzt_has_token(self, client):
        async def fake_patch(self, url, **kw):
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient.patch", new=fake_patch):
            resp = client.post("/api/settings/agent", json={"token": "AgentToken123"})

        assert resp.status_code == 200
        assert resp.json() == {"url": None, "has_token": True}

        get_resp = client.get("/api/settings/agent")
        assert "AgentToken123" not in get_resp.text

    def test_positiv_url_und_token_zusammen_speichern(self, client):
        async def fake_patch(self, url, **kw):
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient.patch", new=fake_patch):
            resp = client.post("/api/settings/agent", json={"url": "http://192.168.1.5:9996", "token": "xyz"})

        assert resp.status_code == 200
        assert resp.json() == {"url": "http://192.168.1.5:9996", "has_token": True}

    def test_positiv_token_loeschen(self, client):
        client.post("/api/settings/agent", json={"token": "xyz"})

        resp = client.delete("/api/settings/agent/token")

        assert resp.status_code == 200
        assert resp.json()["has_token"] is False

    def test_negativ_leerer_token_wird_wie_kein_token_behandelt(self, client):
        resp = client.post("/api/settings/agent", json={"token": "  "})

        assert resp.status_code == 200
        assert resp.json()["has_token"] is False


class TestAgentUiLanguagePush:
    """Saving a token pushes the current user's ui_language to the agent's
    /config endpoint so its menu bar renders in the right language on next
    restart — see agent/routers/config.py."""

    def test_positiv_speichern_pusht_ui_language_an_agent(self, client, db_session):
        # fake_user in the `client` fixture is a bare in-memory models.User(), never
        # persisted — its ui_language is None regardless of the column's server_default,
        # so we swap in our own current_user override with ui_language explicitly set.
        from app import models
        from app.auth.dependencies import get_current_user
        from app.database import set_session_user
        from app.main import app

        custom_user = models.User(id=1, email="test-client@example.com", password_hash="x", email_verified=True, ui_language="en")

        def _override():
            set_session_user(db_session, custom_user.id)
            return custom_user

        app.dependency_overrides[get_current_user] = _override

        calls = []

        async def fake_patch(self, url, **kw):
            calls.append((url, kw.get("json")))
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient.patch", new=fake_patch):
            resp = client.post("/api/settings/agent", json={"token": "AgentToken123"})

        assert resp.status_code == 200
        assert len(calls) == 1
        url, payload = calls[0]
        assert url.endswith("/config")
        assert payload == {"ui_language": "en"}

    def test_negativ_ohne_token_wird_nicht_gepusht(self, client):
        calls = []

        async def fake_patch(self, url, **kw):
            calls.append(url)
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient.patch", new=fake_patch):
            resp = client.post("/api/settings/agent", json={"token": "  "})

        assert resp.status_code == 200
        assert calls == []

    def test_corner_case_nicht_erreichbarer_agent_blockiert_speichern_nicht(self, client):
        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        with patch("httpx.AsyncClient.patch", new=raise_conn_error):
            resp = client.post("/api/settings/agent", json={"token": "AgentToken123"})

        assert resp.status_code == 200
        assert resp.json()["has_token"] is True


class TestAgentHealthEndpoint:
    def test_positiv_erreichbarer_agent(self, client):
        resp_mock = MagicMock(status_code=200)
        resp_mock.json.return_value = {
            "status": "ok", "version": "0.1.0", "platform": "Darwin",
            "modules": {"files": {"ok": True}, "notes": {"ok": True}, "calls": {"ok": True}},
        }

        async def fake_get(self, url, **kw):
            return resp_mock

        with patch("httpx.AsyncClient.get", new=fake_get):
            resp = client.get("/api/settings/agent/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is True
        assert body["modules"]["files"]["ok"] is True

    def test_negativ_nicht_erreichbarer_agent(self, client):
        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        with patch("httpx.AsyncClient.get", new=raise_conn_error):
            resp = client.get("/api/settings/agent/health")

        assert resp.status_code == 200
        assert resp.json()["reachable"] is False
