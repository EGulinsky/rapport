"""L0 — task_scheduler.py: Task-XML-Erzeugung/Registrierung, subprocess
gemockt. Schwerpunkt: _task_xml() muss command/args getrennt in <Command>/
<Arguments> setzen (Regression für den Phase-1-Fix, der zuvor sys.executable
+ "-m agent.main" hartkodiert hat, unabhängig vom übergebenen Pfad)."""
from unittest.mock import MagicMock, patch

from agent import task_scheduler


class TestTaskXml:
    def test_positiv_command_und_args_getrennt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(task_scheduler, "app_data_dir", lambda: tmp_path)

        xml = task_scheduler._task_xml("/usr/bin/python3", ["-m", "agent.tray"])

        assert "<Command>/usr/bin/python3</Command>" in xml
        assert "<Arguments>-m agent.tray</Arguments>" in xml

    def test_positiv_ohne_args_leeres_arguments_element(self, tmp_path, monkeypatch):
        monkeypatch.setattr(task_scheduler, "app_data_dir", lambda: tmp_path)

        xml = task_scheduler._task_xml(r"C:\Program Files\Rapport Agent\agent.exe", [])

        assert r"<Command>C:\Program Files\Rapport Agent\agent.exe</Command>" in xml
        assert "<Arguments></Arguments>" in xml


class TestIsRegistered:
    def test_positiv_schtasks_query_erfolgreich(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            assert task_scheduler.is_registered() is True

    def test_negativ_schtasks_query_fehlschlaegt(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            assert task_scheduler.is_registered() is False

    def test_negativ_schtasks_nicht_vorhanden(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert task_scheduler.is_registered() is False


class TestRegister:
    def test_positiv_schreibt_xml_und_ruft_schtasks_create(self, tmp_path, monkeypatch):
        monkeypatch.setattr(task_scheduler, "app_data_dir", lambda: tmp_path)

        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            task_scheduler.register("/usr/bin/python3", ["-m", "agent.tray"])

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any(c[:3] == ["schtasks", "/delete", "/tn"] for c in calls)
        assert any(c[:3] == ["schtasks", "/create", "/tn"] for c in calls)

    def test_positiv_args_default_none_wird_zu_leerer_liste(self, tmp_path, monkeypatch):
        monkeypatch.setattr(task_scheduler, "app_data_dir", lambda: tmp_path)

        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            task_scheduler.register("/path/to/agent.exe")


class TestUnregister:
    def test_positiv_ruft_schtasks_delete(self):
        with patch("subprocess.run") as mock_run:
            task_scheduler.unregister()
        assert mock_run.call_args[0][0][:3] == ["schtasks", "/delete", "/tn"]
