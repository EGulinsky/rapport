"""L0 — launchd.py: Plist-Erzeugung/Registrierung, subprocess gemockt."""
from unittest.mock import MagicMock, patch

from agent import launchd


class TestPlistPath:
    def test_positiv_liegt_unter_launchagents(self):
        path = launchd.plist_path()
        assert str(path).endswith("Library/LaunchAgents/com.jobtracker.agent.plist")


class TestIsRegistered:
    def test_negativ_keine_plist_datei(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launchd, "plist_path", lambda: tmp_path / "nicht_da.plist")
        assert launchd.is_registered() is False

    def test_positiv_plist_datei_vorhanden(self, tmp_path, monkeypatch):
        p = tmp_path / "com.jobtracker.agent.plist"
        p.write_text("<plist></plist>")
        monkeypatch.setattr(launchd, "plist_path", lambda: p)
        assert launchd.is_registered() is True


class TestRegister:
    def test_positiv_schreibt_plist_und_ruft_launchctl_load(self, tmp_path, monkeypatch):
        plist = tmp_path / "com.jobtracker.agent.plist"
        monkeypatch.setattr(launchd, "plist_path", lambda: plist)
        monkeypatch.setattr(launchd, "app_data_dir", lambda: tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            launchd.register("/Applications/JobTracker Agent.app/Contents/MacOS/JobTracker Agent")

        assert plist.exists()
        content = plist.read_text()
        assert "com.jobtracker.agent" in content
        assert "JobTracker Agent.app" in content
        assert "<key>RunAtLoad</key>" in content
        assert "<true/>" in content
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][:2] == ["launchctl", "load"]

    def test_corner_case_register_ist_idempotent(self, tmp_path, monkeypatch):
        plist = tmp_path / "com.jobtracker.agent.plist"
        monkeypatch.setattr(launchd, "plist_path", lambda: plist)
        monkeypatch.setattr(launchd, "app_data_dir", lambda: tmp_path)

        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            launchd.register("/path/to/agent")
            launchd.register("/path/to/agent")

        assert plist.exists()


class TestUnregister:
    def test_positiv_entfernt_plist_und_ruft_launchctl_unload(self, tmp_path, monkeypatch):
        plist = tmp_path / "com.jobtracker.agent.plist"
        plist.write_text("<plist></plist>")
        monkeypatch.setattr(launchd, "plist_path", lambda: plist)

        with patch("subprocess.run") as mock_run:
            launchd.unregister()

        assert not plist.exists()
        assert mock_run.call_args[0][0][:2] == ["launchctl", "unload"]

    def test_negativ_unregister_ohne_bestehende_plist_ist_no_op(self, tmp_path, monkeypatch):
        monkeypatch.setattr(launchd, "plist_path", lambda: tmp_path / "fehlt.plist")

        with patch("subprocess.run") as mock_run:
            launchd.unregister()

        mock_run.assert_not_called()
