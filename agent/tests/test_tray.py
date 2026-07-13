"""L0 — tray.py: the single cross-platform entry point's bootstrap logic
(decides whether this process should self-register-and-exit or continue
running as the persistent tray/menu-bar app) and executable_command()
(what the service manager should re-invoke). Only the pure logic is tested
here — pystray/rumps/uvicorn (GUI/server loop) aren't touched (deferred
imports, only reached from main()/run_tray_app() which need a real
GUI/display session)."""
from unittest.mock import patch

from agent import tray


class TestBootstrapOrRun:
    def test_negativ_nicht_registriert_registriert_und_gibt_false_zurueck(self):
        with patch("agent.service.is_registered", return_value=False), \
             patch("agent.service.register") as mock_register:
            result = tray.bootstrap_or_run()

        assert result is False
        mock_register.assert_called_once()

    def test_positiv_bereits_registriert_gibt_true_zurueck_ohne_erneute_registrierung(self):
        with patch("agent.service.is_registered", return_value=True), \
             patch("agent.service.register") as mock_register:
            result = tray.bootstrap_or_run()

        assert result is True
        mock_register.assert_not_called()

    def test_positiv_registriert_mit_command_und_args_getrennt(self):
        """service.register() must receive command/args as separate
        arguments, not one embedded string — that was the whole point of
        the executable_command() refactor (see task_scheduler.py/
        systemd_service.py, which previously ignored the passed path)."""
        with patch("agent.service.is_registered", return_value=False), \
             patch("agent.service.register") as mock_register, \
             patch("agent.tray.executable_command", return_value=("/usr/bin/python3", ["-m", "agent.tray"])):
            tray.bootstrap_or_run()

        mock_register.assert_called_once_with("/usr/bin/python3", ["-m", "agent.tray"])


class TestExecutableCommand:
    def test_positiv_frozen_liefert_nur_binary_ohne_args(self, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", "/Applications/Rapport Agent.app/Contents/MacOS/Rapport Agent")

        command, args = tray.executable_command()

        assert command == "/Applications/Rapport Agent.app/Contents/MacOS/Rapport Agent"
        assert args == []

    def test_negativ_nicht_frozen_liefert_python_modul_aufruf(self, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "frozen", False, raising=False)

        command, args = tray.executable_command()

        assert command == sys.executable
        # Re-invokes tray.py itself (the unified entry point) — not
        # agent.main, which is a bare headless dev server with no
        # self-registration or tray/menu at all.
        assert args == ["-m", "agent.tray"]
