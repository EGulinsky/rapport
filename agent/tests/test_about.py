"""L0 — agent/about.py: About-dialog message formatting + cross-platform
dispatch (menubar.py uses rumps.alert directly with about_message(); tray.py
has no built-in alert, so show_about_dialog() covers Windows/Linux)."""
import subprocess
import sys

from agent import about
from agent.config import AgentConfig


def _config():
    return AgentConfig(token="tok", port=9996, ui_language="en")


class TestAboutMessage:
    def test_positiv_enthaelt_version_platform_port(self, monkeypatch):
        monkeypatch.setattr(about, "__version__", "4.6.29")

        message = about.about_message(_config())

        assert "4.6.29" in message
        assert "9996" in message

    def test_positiv_deutsch_liefert_deutsche_vorlage(self, monkeypatch):
        monkeypatch.setattr(about, "__version__", "4.6.29")
        config = _config()
        config.ui_language = "de"

        message = about.about_message(config)

        assert "Plattform" in message


class TestShowAboutDialog:
    def test_positiv_windows_ruft_messagebox_auf(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        calls = []

        class FakeUser32:
            def MessageBoxW(self, *args):
                calls.append(args)

        class FakeWindll:
            user32 = FakeUser32()

        monkeypatch.setitem(sys.modules, "ctypes", type(sys)("ctypes"))
        sys.modules["ctypes"].windll = FakeWindll()

        about.show_about_dialog(_config())

        assert len(calls) == 1

    def test_positiv_linux_zenity_vorhanden_wird_verwendet(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "zenity":
                return None
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", fake_run)

        about.show_about_dialog(_config())

        assert calls[0][0] == "zenity"

    def test_negativ_linux_ohne_zenity_kdialog_faellt_auf_print_zurueck(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "platform", "linux")

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", fake_run)

        about.show_about_dialog(_config())

        assert "9996" in capsys.readouterr().out
