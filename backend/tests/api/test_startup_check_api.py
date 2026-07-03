"""L2 API — /api/startup-check: nie ungetestet, deshalb unbemerkt live
gebrochen (FilesConfig.folder statt .folder_path, AttributeError → 500
sobald der lokale Dateien-Sync aktiviert war)."""
from unittest.mock import MagicMock, patch

import pytest

from app import models

pytestmark = pytest.mark.api


def _agent_health_response(reachable=True, modules=None):
    resp = MagicMock(status_code=200 if reachable else 500)
    resp.json.return_value = {
        "status": "ok", "version": "0.1.0", "platform": "Darwin",
        "modules": modules or {"files": {"ok": True}, "notes": {"ok": True}, "calls": {"ok": True}},
    }
    return resp


def _fake_get(reachable=True, modules=None):
    # Muss eine echte Coroutine-Funktion sein: httpx.AsyncClient.get wird mit
    # `await` aufgerufen — eine Lambda liefert kein awaitable Objekt zurück
    # und würde die Exception im try/except von agent_health() verschlucken,
    # wodurch der Test fälschlich den "nicht erreichbar"-Pfad testet (live an
    # dieser Datei selbst passiert, bevor es aufgefallen ist).
    async def fake(self, url, **kw):
        return _agent_health_response(reachable=reachable, modules=modules)
    return fake


class TestStartupCheck:
    def test_positiv_grundzustand_ohne_config_liefert_200(self, client):
        with patch("httpx.AsyncClient.get", new=_fake_get()):
            resp = client.get("/api/startup-check")

        assert resp.status_code == 200
        body = resp.json()
        assert "checks" in body and "all_ok" in body and "errors" in body

    def test_negativ_regressionsfall_files_config_aktiviert_mit_ordner_stuerzt_nicht_mehr_ab(self, client, db_session):
        # Live-verifizierter Bug: FilesConfig.folder_path (nicht .folder) —
        # der Endpoint gab bei enabled=True + gesetztem Ordner einen 500er
        # zurück, weil das falsche Attribut gelesen wurde.
        db_session.add(models.FilesConfig(enabled=True, folder_path="/Users/test/Dokumente"))
        db_session.commit()

        with patch("httpx.AsyncClient.get", new=_fake_get()):
            resp = client.get("/api/startup-check")

        assert resp.status_code == 200
        files_check = next(c for c in resp.json()["checks"] if c["name"] == "Lokale Dateien")
        assert files_check["ok"] is True

    def test_negativ_files_config_deaktiviert_meldet_nicht_ok(self, client, db_session):
        db_session.add(models.FilesConfig(enabled=False, folder_path="/Users/test/Dokumente"))
        db_session.commit()

        with patch("httpx.AsyncClient.get", new=_fake_get()):
            resp = client.get("/api/startup-check")

        files_check = next(c for c in resp.json()["checks"] if c["name"] == "Lokale Dateien")
        assert files_check["ok"] is False

    def test_positiv_agent_erreichbar_liefert_drei_einzelne_modul_checks(self, client):
        with patch("httpx.AsyncClient.get", new=_fake_get()):
            resp = client.get("/api/startup-check")

        names = {c["name"] for c in resp.json()["checks"]}
        assert {"Agent: Dateien", "Agent: Notizen", "Agent: Anrufe"} <= names

    def test_negativ_agent_nicht_erreichbar_alle_drei_module_ok_false(self, client):
        async def raise_conn_error(self, url, **kw):
            raise ConnectionError("kein Agent")

        with patch("httpx.AsyncClient.get", new=raise_conn_error):
            resp = client.get("/api/startup-check")

        bridge_checks = [c for c in resp.json()["checks"] if c["group"] == "bridges"]
        assert len(bridge_checks) == 3
        assert all(c["ok"] is False for c in bridge_checks)

    def test_negativ_einzelnes_agent_modul_kaputt_meldet_nur_dieses(self, client):
        modules = {"files": {"ok": True}, "notes": {"ok": False, "error": "Notes app nicht erreichbar"}, "calls": {"ok": True}}
        with patch("httpx.AsyncClient.get", new=_fake_get(modules=modules)):
            resp = client.get("/api/startup-check")

        checks = {c["name"]: c for c in resp.json()["checks"]}
        assert checks["Agent: Dateien"]["ok"] is True
        assert checks["Agent: Notizen"]["ok"] is False
        assert checks["Agent: Anrufe"]["ok"] is True

    def test_positiv_all_ok_true_wenn_wirklich_alles_ok(self, client, db_session):
        db_session.add(models.GoogleSync(client_id="x", client_secret_enc="s", refresh_token_enc="y"))
        db_session.add(models.ICloudSync(apple_id="x@icloud.com", app_password_enc="y"))
        db_session.add(models.AiSettings(api_key_enc="y"))
        db_session.add(models.FilesConfig(enabled=True, folder_path="/x"))
        db_session.commit()

        with patch("httpx.AsyncClient.get", new=_fake_get()):
            resp = client.get("/api/startup-check")

        assert resp.json()["all_ok"] is True
        assert resp.json()["errors"] == []
