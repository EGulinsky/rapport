"""L0 — AgentConfig: Token-Generierung/-Persistenz."""
from agent.config import AgentConfig


class TestAgentConfig:
    def test_positiv_erster_aufruf_generiert_und_speichert_token(self, tmp_path, monkeypatch):
        import agent.config as config_module
        monkeypatch.setattr(config_module, "app_data_dir", lambda: tmp_path)

        cfg = AgentConfig.load_or_create()

        assert cfg.token
        assert (tmp_path / "config.json").exists()

    def test_positiv_zweiter_aufruf_liest_denselben_token(self, tmp_path, monkeypatch):
        import agent.config as config_module
        monkeypatch.setattr(config_module, "app_data_dir", lambda: tmp_path)

        first = AgentConfig.load_or_create()
        second = AgentConfig.load_or_create()

        assert first.token == second.token

    def test_corner_case_zwei_instanzen_haben_unterschiedliche_tokens(self):
        a = AgentConfig(token="a")
        b = AgentConfig(token="b")
        assert a.token != b.token
