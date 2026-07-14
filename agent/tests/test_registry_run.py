"""L0 — registry_run.py: HKCU Run-key registration, winreg gemockt via
sys.modules (this Mac has no winreg module at all). Regression context: the
Task-Scheduler-based predecessor (task_scheduler.py) was replaced after real
Windows hardware testing showed `schtasks /create` returns Access Denied
under a normal (UAC-filtered) user token, even for a task that only runs at
the current user's own logon — confirmed with a bare-minimum task, not just
the app's own XML. The HKCU Run key needs no elevation."""
import sys
from unittest.mock import MagicMock, patch

from agent import registry_run


def _fake_winreg():
    fake = MagicMock()
    fake.HKEY_CURRENT_USER = "HKCU"
    fake.REG_SZ = 1
    return fake


class TestCommandLine:
    def test_positiv_pfad_mit_leerzeichen_wird_gequotet(self):
        result = registry_run._command_line(r"C:\Program Files\Rapport Agent\Rapport Agent.exe", [])
        assert result == r'"C:\Program Files\Rapport Agent\Rapport Agent.exe"'

    def test_positiv_pfad_ohne_leerzeichen_bleibt_ungequotet(self):
        result = registry_run._command_line(r"C:\python.exe", ["-m", "agent.tray"])
        assert result == r"C:\python.exe -m agent.tray"

    def test_positiv_args_werden_angehaengt(self):
        result = registry_run._command_line(r"C:\Program Files\python.exe", ["-m", "agent.tray"])
        assert result == r'"C:\Program Files\python.exe" -m agent.tray'


class TestIsRegistered:
    def test_positiv_queryvalueex_erfolgreich(self):
        fake = _fake_winreg()
        with patch.dict(sys.modules, {"winreg": fake}):
            assert registry_run.is_registered() is True

    def test_negativ_openkey_wirft_filenotfound(self):
        fake = _fake_winreg()
        fake.OpenKey.side_effect = FileNotFoundError()
        with patch.dict(sys.modules, {"winreg": fake}):
            assert registry_run.is_registered() is False

    def test_negativ_queryvalueex_wirft_oserror(self):
        fake = _fake_winreg()
        fake.QueryValueEx.side_effect = OSError()
        with patch.dict(sys.modules, {"winreg": fake}):
            assert registry_run.is_registered() is False


class TestRegister:
    def test_positiv_schreibt_run_value(self):
        fake = _fake_winreg()
        with patch.dict(sys.modules, {"winreg": fake}):
            registry_run.register(r"C:\Program Files\Rapport Agent\Rapport Agent.exe", [])

        fake.CreateKey.assert_called_once_with("HKCU", registry_run.RUN_KEY)
        key = fake.CreateKey.return_value.__enter__.return_value
        fake.SetValueEx.assert_called_once_with(
            key, registry_run.VALUE_NAME, 0, 1, r'"C:\Program Files\Rapport Agent\Rapport Agent.exe"'
        )

    def test_positiv_args_default_none_wird_zu_leerer_liste(self):
        fake = _fake_winreg()
        with patch.dict(sys.modules, {"winreg": fake}):
            registry_run.register(r"C:\python.exe")

        key = fake.CreateKey.return_value.__enter__.return_value
        fake.SetValueEx.assert_called_once_with(key, registry_run.VALUE_NAME, 0, 1, r"C:\python.exe")


class TestUnregister:
    def test_positiv_ruft_deletevalue(self):
        fake = _fake_winreg()
        with patch.dict(sys.modules, {"winreg": fake}):
            registry_run.unregister()

        key = fake.OpenKey.return_value.__enter__.return_value
        fake.DeleteValue.assert_called_once_with(key, registry_run.VALUE_NAME)

    def test_negativ_value_fehlt_wird_stillschweigend_ignoriert(self):
        fake = _fake_winreg()
        fake.OpenKey.side_effect = FileNotFoundError()
        with patch.dict(sys.modules, {"winreg": fake}):
            registry_run.unregister()  # must not raise
