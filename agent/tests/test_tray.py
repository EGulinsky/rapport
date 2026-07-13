"""L0 — tray.py: the single cross-platform entry point's bootstrap logic
(decides whether this process should self-register-and-exit or continue
running as the persistent tray/menu-bar app) and executable_command()
(what the service manager should re-invoke). Only the pure logic is tested
here — pystray/rumps/uvicorn's actual GUI/server loops aren't touched
(deferred imports, only reached from main()/run_tray_app() which need a
real GUI/display session); run_tray_app()'s own try/except fallback logic
is testable and covered below via a patched builtins.__import__."""
import sys
from unittest.mock import MagicMock, patch

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
        the executable_command() refactor (see registry_run.py/
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


class TestRunTrayAppFallback:
    """Regression test for a second hardware-verified bug: pystray's backend
    selection can raise non-ImportError exceptions during `import pystray`
    itself — confirmed on real Linux (no X11 display available) via
    `Xlib.error.DisplayNameError`, not ImportError. The fallback must catch
    those too, or the whole agent crashes instead of degrading to headless."""

    def test_positiv_nicht_import_error_faellt_auch_auf_headless_zurueck(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pystray":
                raise RuntimeError('Bad display name ""')
            return real_import(name, *args, **kwargs)

        config = MagicMock(ui_language="en")
        with patch("builtins.__import__", side_effect=fake_import), \
             patch("agent.tray._run_headless") as mock_headless:
            tray.run_tray_app(config)

        mock_headless.assert_called_once_with(config)


class TestRedirectStdioIfHeadless:
    """Regression test for the hardware-verified bug: a PyInstaller
    windowed (console=False) Windows build has no real sys.stdout/stderr,
    which crashes uvicorn's logging setup and silently kills the server
    thread. _redirect_stdio_if_headless() must swap in a log file whenever
    either stream is missing, and leave real dev-run streams untouched."""

    def test_positiv_stdout_none_leitet_in_logdatei_um(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tray, "app_data_dir", lambda: tmp_path)
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)

        tray._redirect_stdio_if_headless()

        assert sys.stdout is not None
        assert sys.stdout is sys.stderr
        print("hello")
        sys.stdout.flush()
        assert (tmp_path / "logs" / "agent.log").read_text() == "hello\n"

    def test_negativ_echte_streams_bleiben_unveraendert(self, monkeypatch):
        real_stdout, real_stderr = sys.stdout, sys.stderr

        tray._redirect_stdio_if_headless()

        assert sys.stdout is real_stdout
        assert sys.stderr is real_stderr
