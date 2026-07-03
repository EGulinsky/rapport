"""L0/L1 — agent_client.py: URL/Token-Auflösung und /health-Aggregation."""
from unittest.mock import MagicMock, patch

import pytest

from app.agent_client import agent_health, get_agent_token, get_agent_url
from app.ai.provider import encrypt_api_key
from app import models

pytestmark = pytest.mark.component


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    return resp


class TestGetAgentUrl:
    def test_negativ_ohne_config_liefert_default(self, db_session):
        assert get_agent_url(db_session) == "http://host.docker.internal:9996"

    def test_positiv_konfigurierte_url_ueberschreibt_default(self, db_session):
        db_session.add(models.AgentSettings(url="http://192.168.1.5:9996"))
        db_session.commit()
        assert get_agent_url(db_session) == "http://192.168.1.5:9996"

    def test_corner_case_trailing_slash_wird_entfernt(self, db_session):
        db_session.add(models.AgentSettings(url="http://example.com:9996/"))
        db_session.commit()
        assert get_agent_url(db_session) == "http://example.com:9996"


class TestGetAgentToken:
    def test_negativ_ohne_config_liefert_none(self, db_session):
        assert get_agent_token(db_session) is None

    def test_positiv_entschluesselt_gespeicherten_token(self, db_session):
        db_session.add(models.AgentSettings(token_enc=encrypt_api_key("geheim-123")))
        db_session.commit()
        assert get_agent_token(db_session) == "geheim-123"

    def test_negativ_kaputter_token_liefert_none_statt_exception(self, db_session):
        db_session.add(models.AgentSettings(token_enc="kein-gueltiges-fernet-token"))
        db_session.commit()
        assert get_agent_token(db_session) is None


class TestAgentHealth:
    async def test_positiv_erreichbar_liefert_module(self, db_session):
        data = {"status": "ok", "version": "0.1.0", "platform": "Darwin", "modules": {"files": {"ok": True}}}
        async def fake_get(self, url, **kw):
            return _mock_response(data)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await agent_health(db_session)
        assert result["reachable"] is True
        assert result["version"] == "0.1.0"
        assert result["modules"]["files"]["ok"] is True

    async def test_negativ_nicht_erreichbar_liefert_reachable_false(self, db_session):
        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        with patch("httpx.AsyncClient.get", new=raise_conn_error):
            result = await agent_health(db_session)
        assert result["reachable"] is False
        assert "error" in result

    async def test_negativ_http_fehler_liefert_reachable_false(self, db_session):
        async def fake_get(self, url, **kw):
            return _mock_response({}, status=401)

        with patch("httpx.AsyncClient.get", new=fake_get):
            result = await agent_health(db_session)
        assert result["reachable"] is False
