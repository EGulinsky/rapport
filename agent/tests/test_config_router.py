"""L1 — config router: backend pushes ui_language, persisted to config.json."""
import json


class TestPatchConfig:
    def test_positiv_setzt_ui_language_und_speichert(self, client, auth_headers, test_config, tmp_path, monkeypatch):
        import agent.config as config_module
        monkeypatch.setattr(config_module, "app_data_dir", lambda: tmp_path)

        resp = client.patch("/config", json={"ui_language": "en"}, headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["ui_language"] == "en"
        assert test_config.ui_language == "en"
        saved = json.loads((tmp_path / "config.json").read_text())
        assert saved["ui_language"] == "en"

    def test_negativ_ohne_token_liefert_401(self, client, tmp_path, monkeypatch):
        import agent.config as config_module
        monkeypatch.setattr(config_module, "app_data_dir", lambda: tmp_path)

        resp = client.patch("/config", json={"ui_language": "en"})

        assert resp.status_code == 401

    def test_fehleingabe_ohne_ui_language_liefert_422(self, client, auth_headers, tmp_path, monkeypatch):
        import agent.config as config_module
        monkeypatch.setattr(config_module, "app_data_dir", lambda: tmp_path)

        resp = client.patch("/config", json={}, headers=auth_headers)

        assert resp.status_code == 422
