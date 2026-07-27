"""L2 API — HTTP-Endpunkte in settings.py.

Deckt AI-/Maps-/Agent-/Logo-/Sync-/Files-Einstellungen ab. `/agent/health`
und die AI-Test-Endpunkte mocken an der jeweiligen Netzwerkgrenze
(agent_client.agent_health, litellm.acompletion).
"""
import litellm
import pytest
from unittest.mock import patch

from app import models

pytestmark = pytest.mark.api


class TestAiSettings:
    def test_positiv_ohne_konfiguration_liefert_defaults(self, client):
        resp = client.get("/api/settings/ai")

        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "groq"
        assert body["has_key"] is False
        assert body["enabled"] is False

    def test_positiv_speichert_neue_konfiguration(self, client, db_session):
        resp = client.post("/api/settings/ai", json={
            "provider": "groq", "model": "groq/llama-3.3-70b-versatile",
            "api_key": "sk-test", "enabled": True,
        })

        assert resp.status_code == 200
        assert resp.json()["has_key"] is True
        cfg = db_session.query(models.AiSettings).one()
        assert cfg.api_key_enc is not None

    def test_positiv_leerer_key_behaelt_bestehenden_key(self, client, db_session):
        client.post("/api/settings/ai", json={"provider": "groq", "model": "m", "api_key": "sk-test", "enabled": True})

        resp = client.post("/api/settings/ai", json={"provider": "groq", "model": "m2", "enabled": True})

        assert resp.status_code == 200
        assert resp.json()["has_key"] is True
        assert resp.json()["model"] == "m2"

    def test_positiv_loescht_api_key(self, client, db_session):
        client.post("/api/settings/ai", json={"provider": "groq", "model": "m", "api_key": "sk-test", "enabled": True})

        resp = client.delete("/api/settings/ai/key")

        assert resp.status_code == 200
        assert resp.json()["has_key"] is False

    def test_negativ_key_loeschen_ohne_konfiguration_liefert_404(self, client):
        resp = client.delete("/api/settings/ai/key")
        assert resp.status_code == 404


class TestMapsSettings:
    def test_positiv_ohne_konfiguration_liefert_has_key_false(self, client):
        resp = client.get("/api/settings/maps")
        assert resp.json()["has_key"] is False

    def test_positiv_speichert_key(self, client):
        resp = client.post("/api/settings/maps", json={"api_key": "maps-key"})
        assert resp.json()["has_key"] is True

    def test_positiv_leerer_key_loescht_bestehenden(self, client):
        client.post("/api/settings/maps", json={"api_key": "maps-key"})

        resp = client.post("/api/settings/maps", json={"api_key": ""})

        assert resp.json()["has_key"] is False

    def test_positiv_key_loeschen_endpoint(self, client):
        client.post("/api/settings/maps", json={"api_key": "maps-key"})

        resp = client.delete("/api/settings/maps/key")

        assert resp.json()["has_key"] is False


class TestAgentSettings:
    def test_positiv_ohne_konfiguration_liefert_defaults(self, client):
        resp = client.get("/api/settings/agent")
        assert resp.json() == {"url": None, "has_token": False}

    def test_positiv_speichert_url_und_token(self, client):
        resp = client.post("/api/settings/agent", json={"url": "http://localhost:9000", "token": "tok"})

        assert resp.json()["url"] == "http://localhost:9000"
        assert resp.json()["has_token"] is True

    def test_positiv_leere_url_wird_zu_null(self, client):
        resp = client.post("/api/settings/agent", json={"url": "   ", "token": None})
        assert resp.json()["url"] is None
        assert resp.json()["has_token"] is False

    def test_positiv_token_loeschen(self, client):
        client.post("/api/settings/agent", json={"url": "http://x", "token": "tok"})

        resp = client.delete("/api/settings/agent/token")

        assert resp.json()["has_token"] is False

    def test_negativ_token_loeschen_ohne_konfiguration(self, client):
        resp = client.delete("/api/settings/agent/token")
        assert resp.json() == {"url": None, "has_token": False}

    def test_positiv_health_liefert_agent_status(self, client):
        async def _fake_health(db):
            return {"reachable": True, "version": "1.0", "platform": "darwin", "modules": {}, "error": None}

        with patch("app.agent_client.agent_health", new=_fake_health):
            resp = client.get("/api/settings/agent/health")

        assert resp.status_code == 200
        assert resp.json()["reachable"] is True


class TestLogoSettings:
    def test_positiv_ohne_konfiguration_liefert_none(self, client):
        resp = client.get("/api/settings/logo")
        assert resp.json() == {"api_key": None}

    def test_positiv_speichert_und_liest_key(self, client):
        resp = client.post("/api/settings/logo", json={"api_key": "logo-key"})
        assert resp.json() == {"api_key": "logo-key"}
        assert client.get("/api/settings/logo").json() == {"api_key": "logo-key"}


class TestSyncSettings:
    def test_positiv_erstanfrage_legt_defaults_an(self, client, db_session):
        resp = client.get("/api/settings/sync")

        assert resp.status_code == 200
        assert resp.json()["audit_log_level"] == "normal"
        assert db_session.query(models.SyncSettings).count() == 1

    def test_positiv_speichert_bool_felder(self, client):
        resp = client.post("/api/settings/sync", json={"gmail_enabled": False, "linkedin_enabled": True})

        assert resp.status_code == 200
        assert resp.json()["gmail_enabled"] is False
        assert resp.json()["linkedin_enabled"] is True

    def test_positiv_speichert_audit_log_level(self, client):
        resp = client.post("/api/settings/sync", json={"audit_log_level": "verbose"})
        assert resp.json()["audit_log_level"] == "verbose"

    def test_negativ_ungueltiges_audit_log_level_wird_ignoriert(self, client):
        resp = client.post("/api/settings/sync", json={"audit_log_level": "invalid"})
        assert resp.json()["audit_log_level"] == "normal"

    def test_negativ_nicht_bool_werte_werden_ignoriert(self, client):
        resp = client.post("/api/settings/sync", json={"gmail_enabled": "yes"})
        assert resp.status_code == 200  # kein Crash, Feld einfach unverändert


class TestFilesConfig:
    def test_positiv_erstanfrage_legt_enabled_default_an(self, client, db_session):
        resp = client.get("/api/settings/files")

        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        assert db_session.query(models.FilesConfig).count() == 1

    def test_positiv_speichert_ordnerpfad(self, client):
        resp = client.post("/api/settings/files", json={"folder_path": "/Users/x/Documents", "enabled": True})

        assert resp.json()["folder_path"] == "/Users/x/Documents"

    def test_corner_case_pfad_wird_von_anfuehrungszeichen_bereinigt(self, client):
        resp = client.post("/api/settings/files", json={"folder_path": "'/Users/x/Documents'"})
        assert resp.json()["folder_path"] == "/Users/x/Documents"

    def test_positiv_leerer_pfad_wird_zu_null(self, client):
        client.post("/api/settings/files", json={"folder_path": "/some/path"})

        resp = client.post("/api/settings/files", json={"folder_path": ""})

        assert resp.json()["folder_path"] is None


class TestAiTest:
    def test_positiv_mit_payload_testet_direkt_ohne_speichern(self, client, db_session):
        async def _fake_acompletion(**kwargs):
            from types import SimpleNamespace
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

        with patch.object(litellm, "acompletion", new=_fake_acompletion):
            resp = client.post("/api/settings/ai/test", json={
                "provider": "groq", "model": "groq/llama-3.3-70b-versatile", "api_key": "sk-test", "enabled": True,
            })

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_positiv_mit_base_url_wird_als_api_base_durchgereicht(self, client):
        captured = {}

        async def _fake_acompletion(**kwargs):
            from types import SimpleNamespace
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

        with patch.object(litellm, "acompletion", new=_fake_acompletion):
            resp = client.post("/api/settings/ai/test", json={
                "provider": "custom", "model": "some-model", "base_url": "http://localhost:11434", "enabled": True,
            })

        assert resp.status_code == 200
        assert captured["api_base"] == "http://localhost:11434"

    def test_negativ_rate_limit_liefert_429(self, client):
        async def _raise(**kwargs):
            raise litellm.RateLimitError(message="rate limited", llm_provider="groq", model="m")

        with patch.object(litellm, "acompletion", new=_raise):
            resp = client.post("/api/settings/ai/test", json={
                "provider": "groq", "model": "m", "api_key": "sk-test", "enabled": True,
            })

        assert resp.status_code == 429

    def test_negativ_authentication_error_liefert_401(self, client):
        async def _raise(**kwargs):
            raise litellm.AuthenticationError(message="bad key", llm_provider="groq", model="m")

        with patch.object(litellm, "acompletion", new=_raise):
            resp = client.post("/api/settings/ai/test", json={
                "provider": "groq", "model": "m", "api_key": "sk-test", "enabled": True,
            })

        assert resp.status_code == 401

    def test_negativ_sonstiger_fehler_liefert_502_gekuerzt(self, client):
        async def _raise(**kwargs):
            raise RuntimeError("x" * 400)

        with patch.object(litellm, "acompletion", new=_raise):
            resp = client.post("/api/settings/ai/test", json={
                "provider": "groq", "model": "m", "api_key": "sk-test", "enabled": True,
            })

        assert resp.status_code == 502
        assert resp.json()["detail"].endswith("…")

    def test_positiv_fallback_auf_gespeicherten_key_bei_gleichem_provider(self, client, db_session):
        client.post("/api/settings/ai", json={"provider": "groq", "model": "m", "api_key": "sk-stored", "enabled": True})

        captured = {}

        async def _fake_acompletion(**kwargs):
            from types import SimpleNamespace
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

        with patch.object(litellm, "acompletion", new=_fake_acompletion):
            resp = client.post("/api/settings/ai/test", json={"provider": "groq", "model": "m2", "enabled": True})

        assert resp.status_code == 200
        assert captured["api_key"] == "sk-stored"

    def test_positiv_ohne_payload_nutzt_test_connection(self, db_session, client, monkeypatch):
        import app.routers.settings as settings_module

        async def _fake_test_connection(db):
            return "ok"

        monkeypatch.setattr(settings_module, "test_connection", _fake_test_connection)

        resp = client.post("/api/settings/ai/test")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "ok"}

    def test_negativ_ohne_payload_ainotconfigured_liefert_400(self, db_session, client, monkeypatch):
        import app.routers.settings as settings_module
        from app.ai.provider import AINotConfigured

        async def _fake_test_connection(db):
            raise AINotConfigured("Kein Provider konfiguriert")

        monkeypatch.setattr(settings_module, "test_connection", _fake_test_connection)

        resp = client.post("/api/settings/ai/test")

        assert resp.status_code == 400

    def test_negativ_ohne_payload_rate_limit_liefert_429(self, db_session, client, monkeypatch):
        import app.routers.settings as settings_module

        async def _fake_test_connection(db):
            raise litellm.RateLimitError(message="rate limited", llm_provider="groq", model="m")

        monkeypatch.setattr(settings_module, "test_connection", _fake_test_connection)

        resp = client.post("/api/settings/ai/test")

        assert resp.status_code == 429

    def test_negativ_ohne_payload_sonstiger_fehler_liefert_502(self, db_session, client, monkeypatch):
        import app.routers.settings as settings_module

        async def _fake_test_connection(db):
            raise RuntimeError("boom")

        monkeypatch.setattr(settings_module, "test_connection", _fake_test_connection)

        resp = client.post("/api/settings/ai/test")

        assert resp.status_code == 502

    def test_negativ_ohne_payload_lange_fehlermeldung_wird_gekuerzt(self, db_session, client, monkeypatch):
        import app.routers.settings as settings_module

        async def _fake_test_connection(db):
            raise RuntimeError("x" * 400)

        monkeypatch.setattr(settings_module, "test_connection", _fake_test_connection)

        resp = client.post("/api/settings/ai/test")

        assert resp.status_code == 502
        assert resp.json()["detail"].endswith("…")


class TestAiModelsList:
    """POST /api/settings/ai/models — live model list per provider."""

    class _FakeResp:
        def __init__(self, json_body, status_code=200):
            self._json = json_body
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._json

    class _FakeClient:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return self._resp

    def test_negativ_ohne_api_key_liefert_reachable_false(self, client):
        resp = client.post("/api/settings/ai/models", json={"provider": "groq"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert body["models"] == []
        assert body["error"] == "No API key configured"

    def test_negativ_unbekannter_provider(self, client):
        resp = client.post("/api/settings/ai/models", json={"provider": "does-not-exist", "api_key": "x"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert "Unknown provider" in body["error"]

    def test_positiv_groq_filtert_whisper_modelle(self, client):
        fake = self._FakeClient(self._FakeResp({"data": [
            {"id": "llama-3.3-70b-versatile"},
            {"id": "distil-whisper-large-v3-en"},
        ]}))

        with patch("httpx.AsyncClient", return_value=fake):
            resp = client.post("/api/settings/ai/models", json={"provider": "groq", "api_key": "gsk-test"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is True
        assert [m["model"] for m in body["models"]] == ["groq/llama-3.3-70b-versatile"]

    def test_positiv_anthropic_nutzt_display_name(self, client):
        fake = self._FakeClient(self._FakeResp({"data": [
            {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5"},
            {"id": "claude-opus-4-1", "display_name": "Claude Opus 4.1"},
        ]}))

        with patch("httpx.AsyncClient", return_value=fake):
            resp = client.post("/api/settings/ai/models", json={"provider": "anthropic", "api_key": "sk-ant-test"})

        assert resp.status_code == 200
        body = resp.json()
        labels = {m["model"]: m["label"] for m in body["models"]}
        assert labels["anthropic/claude-haiku-4-5"] == "Claude Haiku 4.5"
        assert labels["anthropic/claude-opus-4-1"] == "Claude Opus 4.1"

    def test_positiv_openai_filtert_nicht_chat_modelle(self, client):
        fake = self._FakeClient(self._FakeResp({"data": [
            {"id": "gpt-4o"},
            {"id": "text-embedding-3-small"},
            {"id": "whisper-1"},
            {"id": "o1-mini"},
        ]}))

        with patch("httpx.AsyncClient", return_value=fake):
            resp = client.post("/api/settings/ai/models", json={"provider": "openai", "api_key": "sk-test"})

        assert resp.status_code == 200
        body = resp.json()
        assert sorted(m["model"] for m in body["models"]) == ["gpt-4o", "o1-mini"]

    def test_positiv_gemini_filtert_auf_generate_content(self, client):
        fake = self._FakeClient(self._FakeResp({"models": [
            {"name": "models/gemini-2.0-flash", "displayName": "Gemini 2.0 Flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/embedding-001", "displayName": "Embedding 001", "supportedGenerationMethods": ["embedContent"]},
        ]}))

        with patch("httpx.AsyncClient", return_value=fake):
            resp = client.post("/api/settings/ai/models", json={"provider": "gemini", "api_key": "AIza-test"})

        assert resp.status_code == 200
        body = resp.json()
        assert [m["model"] for m in body["models"]] == ["gemini/gemini-2.0-flash"]

    def test_positiv_nutzt_gespeicherten_key_bei_gleichem_provider(self, client, db_session):
        client.post("/api/settings/ai", json={"provider": "groq", "model": "m", "api_key": "sk-stored", "enabled": True})
        captured = {}

        class _CapturingClient(self._FakeClient):
            async def get(self, url, headers=None):
                captured.update(headers or {})
                return self._resp

        fake = _CapturingClient(self._FakeResp({"data": [{"id": "llama-3.3-70b-versatile"}]}))

        with patch("httpx.AsyncClient", return_value=fake):
            resp = client.post("/api/settings/ai/models", json={"provider": "groq"})

        assert resp.status_code == 200
        assert resp.json()["reachable"] is True
        assert captured["Authorization"] == "Bearer sk-stored"

    def test_negativ_gespeicherter_key_anderer_provider_wird_nicht_verwendet(self, client, db_session):
        client.post("/api/settings/ai", json={"provider": "groq", "model": "m", "api_key": "sk-stored", "enabled": True})

        resp = client.post("/api/settings/ai/models", json={"provider": "anthropic"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert body["error"] == "No API key configured"

    def test_negativ_provider_fehler_wird_als_reachable_false_gemeldet(self, client):
        fake = self._FakeClient(self._FakeResp({}, status_code=401))

        with patch("httpx.AsyncClient", return_value=fake):
            resp = client.post("/api/settings/ai/models", json={"provider": "groq", "api_key": "bad-key"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert body["models"] == []
        assert body["error"]
