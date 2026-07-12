"""L1 — config router: backend pushes ui_language, persisted to config.json."""
import json

from fastapi.testclient import TestClient

from agent.main import create_app


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


class TestPatchConfigRestartsAgent:
    """rumps builds its menu only once at process startup — a config push
    with no actual restart would silently never become visible. The endpoint
    must trigger the injected restart_agent callback, but only on a real
    language change (not on every push, e.g. re-saving the same value)."""

    def _client_with_restart_spy(self, test_config, fake_files_provider, fake_notes_provider, fake_calls_provider):
        calls = []
        app = create_app(
            test_config, fake_files_provider, fake_notes_provider, fake_calls_provider,
            restart_agent=lambda: calls.append(True),
        )
        return TestClient(app), calls

    def test_positiv_sprachaenderung_loest_neustart_aus(
        self, test_config, fake_files_provider, fake_notes_provider, fake_calls_provider, auth_headers, tmp_path, monkeypatch,
    ):
        import agent.config as config_module
        monkeypatch.setattr(config_module, "app_data_dir", lambda: tmp_path)
        client, calls = self._client_with_restart_spy(test_config, fake_files_provider, fake_notes_provider, fake_calls_provider)

        resp = client.patch("/config", json={"ui_language": "en"}, headers=auth_headers)

        assert resp.status_code == 200
        assert calls == [True]

    def test_negativ_unveraenderte_sprache_loest_keinen_neustart_aus(
        self, test_config, fake_files_provider, fake_notes_provider, fake_calls_provider, auth_headers, tmp_path, monkeypatch,
    ):
        import agent.config as config_module
        monkeypatch.setattr(config_module, "app_data_dir", lambda: tmp_path)
        test_config.ui_language = "en"
        client, calls = self._client_with_restart_spy(test_config, fake_files_provider, fake_notes_provider, fake_calls_provider)

        resp = client.patch("/config", json={"ui_language": "en"}, headers=auth_headers)

        assert resp.status_code == 200
        assert calls == []
