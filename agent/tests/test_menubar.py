"""L0 — menubar.py bootstrap logic: decides whether this process should
self-register-and-exit or continue running as the persistent menu bar app.
Only the pure logic is tested here — rumps/uvicorn (GUI/server loop) aren't
touched (they're deferred imports, only reached from main()/run_menubar_app()
which need an actual GUI session)."""
from unittest.mock import patch

from agent import menubar


class TestBootstrapOrRun:
    def test_negativ_nicht_registriert_registriert_und_gibt_false_zurueck(self):
        with patch("agent.launchd.is_registered", return_value=False), \
             patch("agent.launchd.register") as mock_register:
            result = menubar.bootstrap_or_run()

        assert result is False
        mock_register.assert_called_once()

    def test_positiv_bereits_registriert_gibt_true_zurueck_ohne_erneute_registrierung(self):
        with patch("agent.launchd.is_registered", return_value=True), \
             patch("agent.launchd.register") as mock_register:
            result = menubar.bootstrap_or_run()

        assert result is True
        mock_register.assert_not_called()


class TestExecutablePath:
    def test_positiv_frozen_liefert_sys_executable(self, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", "/Applications/JobTracker Agent.app/Contents/MacOS/JobTracker Agent")

        assert menubar.executable_path() == "/Applications/JobTracker Agent.app/Contents/MacOS/JobTracker Agent"

    def test_negativ_nicht_frozen_liefert_python_modul_aufruf(self, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "frozen", False, raising=False)

        path = menubar.executable_path()

        assert "agent.menubar" in path
