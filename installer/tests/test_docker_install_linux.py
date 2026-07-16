"""L0/L1 — docker_install/linux.py: running the official get.docker.com
convenience script, the best-effort group-membership + systemd-enable
follow-up steps, and waiting for the daemon via the sudo fallback (fresh
installs need it until the next login) — all with subprocess/requests
mocked."""
from unittest.mock import MagicMock, patch

from installer.docker_install import linux


class TestInstallDocker:
    def test_positiv_erfolgreicher_lauf(self):
        with patch("installer.docker_install.linux.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run, \
             patch("installer.docker_install.linux.docker_daemon_running", return_value=True):
            mock_get.return_value = MagicMock(text="#!/bin/sh\necho hi", raise_for_status=lambda: None)
            assert linux.install_docker() is True

        # sudo sh get-docker.sh, usermod -aG docker, systemctl enable --now docker
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[0].args[0][:2] == ["sudo", "sh"]
        assert mock_run.call_args_list[1].args[0][:3] == ["sudo", "usermod", "-aG"]
        assert mock_run.call_args_list[2].args[0] == ["sudo", "systemctl", "enable", "--now", "docker"]

    def test_negativ_download_fehler_liefert_false(self):
        import requests
        with patch("installer.docker_install.linux.requests.get", side_effect=requests.RequestException("boom")), \
             patch("subprocess.run") as mock_run:
            assert linux.install_docker() is False
        mock_run.assert_not_called()

    def test_negativ_install_skript_fehlschlag_stoppt_ohne_folgeschritte(self):
        with patch("installer.docker_install.linux.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=1)) as mock_run:
            mock_get.return_value = MagicMock(text="boom", raise_for_status=lambda: None)
            assert linux.install_docker() is False
        mock_run.assert_called_once()

    def test_negativ_daemon_auch_mit_sudo_nicht_erreichbar(self):
        with patch("installer.docker_install.linux.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("installer.docker_install.linux.docker_daemon_running", return_value=False), \
             patch("time.sleep"):
            mock_get.return_value = MagicMock(text="ok", raise_for_status=lambda: None)
            assert linux.install_docker() is False

    def test_positiv_wartet_mit_use_sudo_true_auf_daemon(self):
        with patch("installer.docker_install.linux.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("installer.docker_install.linux.docker_daemon_running", return_value=True) as mock_daemon:
            mock_get.return_value = MagicMock(text="ok", raise_for_status=lambda: None)
            linux.install_docker()
        mock_daemon.assert_called_with(use_sudo=True)
