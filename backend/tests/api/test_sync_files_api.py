"""L2 API — HTTP-Endpunkte in sync_files.py (Status, Reset, Sync starten,
Browse, manuelles Anhängen, Öffnen). Mockt den Rapport Agent an der
httpx.AsyncClient-Netzwerkgrenze."""
from unittest.mock import MagicMock

import pytest

from app import models
from tests.factories import application_factory

pytestmark = pytest.mark.api


def _mock_response(json_data, status=200, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = text
    resp.headers = {"content-type": "application/json"}
    return resp


class TestFilesStatus:
    def test_positiv_legt_config_an_und_meldet_nicht_erreichbar(self, client, db_session, monkeypatch):
        async def fake_get(self, url, **kw):
            raise RuntimeError("connection refused")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.get("/api/sync/files/status")

        assert resp.status_code == 200
        assert resp.json()["bridge_reachable"] is False
        assert db_session.query(models.FilesConfig).count() == 1

    def test_positiv_agent_erreichbar(self, client, monkeypatch):
        async def fake_get(self, url, **kw):
            return _mock_response({}, status=200)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.get("/api/sync/files/status")

        assert resp.json()["bridge_reachable"] is True


class TestResetFilesSync:
    def test_positiv_setzt_last_sync_zurueck(self, client, db_session):
        cfg = models.FilesConfig(enabled=True, folder_path="/x", user_id=1)
        db_session.add(cfg)
        db_session.commit()

        resp = client.post("/api/sync/files/reset")

        assert resp.status_code == 204
        db_session.refresh(cfg)
        assert cfg.last_sync is None

    def test_negativ_ohne_konfiguration_ist_no_op(self, client):
        resp = client.post("/api/sync/files/reset")
        assert resp.status_code == 204


class TestSyncFilesEndpoint:
    def test_negativ_deaktiviert_liefert_leeres_ergebnis_ohne_hintergrundlauf(self, client, db_session):
        cfg = models.FilesConfig(enabled=False, folder_path="/x", user_id=1)
        db_session.add(cfg)
        db_session.commit()

        resp = client.post("/api/sync/files")

        assert resp.status_code == 200
        assert resp.json() == {"processed": 0, "created": 0, "skipped": 0, "errors": []}

    def test_positiv_startet_hintergrund_sync(self, client, db_session, monkeypatch):
        cfg = models.FilesConfig(enabled=True, folder_path="/x", user_id=1)
        db_session.add(cfg)
        db_session.commit()

        async def fake_get(self, url, **kw):
            return _mock_response([])

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.post("/api/sync/files")

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0


class TestBrowseFiles:
    def test_negativ_kein_pfad_und_keine_konfiguration_liefert_400(self, client):
        resp = client.get("/api/sync/files/browse")
        assert resp.status_code == 400

    def test_positiv_listet_verzeichnisinhalt(self, client, db_session, monkeypatch):
        cfg = models.FilesConfig(enabled=True, folder_path="/root", user_id=1)
        db_session.add(cfg)
        db_session.commit()

        async def fake_get(self, url, **kw):
            return _mock_response([{"name": "Contoso AG", "is_dir": True}])

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.get("/api/sync/files/browse")

        assert resp.status_code == 200
        body = resp.json()
        assert body["default_root"] == "/root"
        assert len(body["items"]) == 1

    def test_negativ_agent_fehlerstatus_liefert_502(self, client, monkeypatch):
        async def fake_get(self, url, **kw):
            return _mock_response({"error": "kaputt"}, status=500)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.get("/api/sync/files/browse", params={"path": "/root"})

        assert resp.status_code == 502

    def test_negativ_agent_nicht_erreichbar_liefert_502(self, client, monkeypatch):
        async def fake_get(self, url, **kw):
            raise RuntimeError("connection refused")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.get("/api/sync/files/browse", params={"path": "/root"})

        assert resp.status_code == 502


class TestAttachFile:
    def test_negativ_bewerbung_nicht_gefunden(self, client):
        resp = client.post("/api/sync/files/attach", json={"app_id": 999, "path": "/root/cv.pdf"})
        assert resp.status_code == 404

    def test_positiv_einzelne_datei_wird_angehaengt(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/sync/files/attach", json={"app_id": app.id, "path": "/root/cv.pdf"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 1
        assert db_session.query(models.Event).filter_by(application_id=app.id, source="local_files").count() == 1

    def test_positiv_ordner_wird_rekursiv_angehaengt(self, client, db_session, monkeypatch):
        app = application_factory(db_session)
        db_session.commit()

        async def fake_get(self, url, **kw):
            return _mock_response([
                {"path": "/root/Contoso/cv.pdf", "name": "cv.pdf"},
                {"path": "/root/Contoso/anschreiben.pdf", "name": "anschreiben.pdf"},
            ])

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.post("/api/sync/files/attach", json={"app_id": app.id, "path": "/root/Contoso", "is_folder": True})

        assert resp.status_code == 200
        assert resp.json()["created"] == 2

    def test_corner_case_ordner_agent_nicht_erreichbar_liefert_null_dateien(self, client, db_session, monkeypatch):
        app = application_factory(db_session)
        db_session.commit()

        async def fake_get(self, url, **kw):
            raise RuntimeError("connection refused")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        resp = client.post("/api/sync/files/attach", json={"app_id": app.id, "path": "/root/Contoso", "is_folder": True})

        assert resp.status_code == 200
        assert resp.json()["created"] == 0


class TestOpenFile:
    def test_negativ_ohne_pfad_liefert_400(self, client):
        resp = client.post("/api/sync/files/open", json={})
        assert resp.status_code == 400

    def test_positiv_oeffnet_datei(self, client, monkeypatch):
        async def fake_post(self, url, **kw):
            return _mock_response({}, status=200)

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

        resp = client.post("/api/sync/files/open", json={"path": "/root/cv.pdf"})

        assert resp.status_code == 200
        assert resp.json() == {"success": True}

    def test_negativ_agent_fehlerstatus_liefert_502(self, client, monkeypatch):
        async def fake_post(self, url, **kw):
            return _mock_response({}, status=500, text="Fehler")

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

        resp = client.post("/api/sync/files/open", json={"path": "/root/cv.pdf"})

        assert resp.status_code == 502

    def test_negativ_agent_nicht_erreichbar_liefert_502(self, client, monkeypatch):
        async def fake_post(self, url, **kw):
            raise RuntimeError("connection refused")

        monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

        resp = client.post("/api/sync/files/open", json={"path": "/root/cv.pdf"})

        assert resp.status_code == 502
