"""L0 — service.py: the only logic is picking which OS-specific backend
(launchd/task_scheduler/systemd_service) to delegate to, based on
platform.system(). Verifies is_registered()/register()/unregister() forward
to the right module with the right arguments, and that an unsupported
platform raises rather than silently picking one."""
from unittest.mock import patch

import pytest

from agent import service


class TestGetImplDispatch:
    def test_positiv_darwin_delegiert_an_launchd(self):
        with patch("platform.system", return_value="Darwin"), \
             patch("agent.launchd.is_registered", return_value=True) as mock_is_reg:
            assert service.is_registered() is True
        mock_is_reg.assert_called_once()

    def test_positiv_windows_delegiert_an_task_scheduler(self):
        with patch("platform.system", return_value="Windows"), \
             patch("agent.task_scheduler.is_registered", return_value=False) as mock_is_reg:
            assert service.is_registered() is False
        mock_is_reg.assert_called_once()

    def test_positiv_linux_delegiert_an_systemd_service(self):
        with patch("platform.system", return_value="Linux"), \
             patch("agent.systemd_service.is_registered", return_value=True) as mock_is_reg:
            assert service.is_registered() is True
        mock_is_reg.assert_called_once()

    def test_negativ_unbekannte_plattform_wirft_not_implemented(self):
        with patch("platform.system", return_value="FreeBSD"):
            with pytest.raises(NotImplementedError):
                service.is_registered()


class TestRegisterDelegation:
    def test_positiv_uebergibt_command_und_args_unveraendert(self):
        with patch("platform.system", return_value="Darwin"), \
             patch("agent.launchd.register") as mock_register:
            service.register("/usr/bin/python3", ["-m", "agent.tray"])
        mock_register.assert_called_once_with("/usr/bin/python3", ["-m", "agent.tray"])

    def test_positiv_args_default_none(self):
        with patch("platform.system", return_value="Linux"), \
             patch("agent.systemd_service.register") as mock_register:
            service.register("/usr/bin/rapport-agent")
        mock_register.assert_called_once_with("/usr/bin/rapport-agent", None)


class TestUnregisterDelegation:
    def test_positiv_windows_delegiert_an_task_scheduler(self):
        with patch("platform.system", return_value="Windows"), \
             patch("agent.task_scheduler.unregister") as mock_unregister:
            service.unregister()
        mock_unregister.assert_called_once()
