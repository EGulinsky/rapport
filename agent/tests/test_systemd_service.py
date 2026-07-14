"""L0 — systemd_service.py: .service-Unit-Erzeugung/Registrierung, subprocess
gemockt. Schwerpunkt: _service_content() muss command/args in ExecStart
zusammensetzen (Regression für den Phase-1-Fix, der zuvor sys.executable +
"-m agent.main" hartkodiert hat, unabhängig vom übergebenen Pfad)."""
from unittest.mock import MagicMock, patch

from agent import systemd_service


class TestServiceContent:
    def test_positiv_execstart_mit_command_und_args(self, tmp_path, monkeypatch):
        monkeypatch.setattr(systemd_service, "app_data_dir", lambda: tmp_path)

        content = systemd_service._service_content("/usr/bin/python3", ["-m", "agent.tray"])

        assert "ExecStart=/usr/bin/python3 -m agent.tray" in content

    def test_positiv_ohne_args_nur_command(self, tmp_path, monkeypatch):
        monkeypatch.setattr(systemd_service, "app_data_dir", lambda: tmp_path)

        content = systemd_service._service_content("/usr/bin/rapport-agent", [])

        assert "ExecStart=/usr/bin/rapport-agent\n" in content
        assert "ExecStart=/usr/bin/rapport-agent " not in content


class TestIsRegistered:
    def test_negativ_keine_unit_datei(self, tmp_path, monkeypatch):
        monkeypatch.setattr(systemd_service, "_service_file", lambda: tmp_path / "nicht_da.service")
        assert systemd_service.is_registered() is False

    def test_positiv_unit_datei_vorhanden(self, tmp_path, monkeypatch):
        p = tmp_path / "rapport-agent.service"
        p.write_text("[Unit]")
        monkeypatch.setattr(systemd_service, "_service_file", lambda: p)
        assert systemd_service.is_registered() is True


class TestRegister:
    def test_positiv_schreibt_unit_und_ruft_systemctl(self, tmp_path, monkeypatch):
        service_file = tmp_path / "rapport-agent.service"
        monkeypatch.setattr(systemd_service, "_service_file", lambda: service_file)
        monkeypatch.setattr(systemd_service, "app_data_dir", lambda: tmp_path)

        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            systemd_service.register("/usr/bin/python3", ["-m", "agent.tray"])

        assert service_file.exists()
        assert "ExecStart=/usr/bin/python3 -m agent.tray" in service_file.read_text()
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["systemctl", "--user", "daemon-reload"] in calls
        assert ["systemctl", "--user", "enable", "rapport-agent"] in calls
        assert ["systemctl", "--user", "start", "rapport-agent"] in calls


class TestUnregister:
    def test_positiv_stoppt_deaktiviert_und_entfernt_unit(self, tmp_path, monkeypatch):
        service_file = tmp_path / "rapport-agent.service"
        service_file.write_text("[Unit]")
        monkeypatch.setattr(systemd_service, "_service_file", lambda: service_file)

        with patch("subprocess.run") as mock_run:
            systemd_service.unregister()

        assert not service_file.exists()
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["systemctl", "--user", "stop", "rapport-agent"] in calls
        assert ["systemctl", "--user", "disable", "rapport-agent"] in calls
