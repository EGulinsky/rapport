"""L0 — docker_check.py: CLI/daemon detection and the sudo-fallback command
prefix used for the rest of a run right after a fresh Linux install."""
from unittest.mock import MagicMock, patch

from installer import docker_check


class TestDockerCliAvailable:
    def test_positiv_docker_im_path_gefunden(self):
        with patch("shutil.which", return_value="/usr/bin/docker"):
            assert docker_check.docker_cli_available() is True

    def test_negativ_docker_nicht_im_path(self):
        with patch("shutil.which", return_value=None):
            assert docker_check.docker_cli_available() is False


class TestDockerDaemonRunning:
    def test_positiv_docker_info_erfolgreich(self):
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            assert docker_check.docker_daemon_running() is True
        mock_run.assert_called_once_with(["docker", "info"], capture_output=True, timeout=10)

    def test_negativ_docker_cli_fehlt_kein_subprocess_aufruf(self):
        with patch("shutil.which", return_value=None), \
             patch("subprocess.run") as mock_run:
            assert docker_check.docker_daemon_running() is False
        mock_run.assert_not_called()

    def test_negativ_daemon_nicht_erreichbar(self):
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=MagicMock(returncode=1)):
            assert docker_check.docker_daemon_running() is False

    def test_corner_case_subprocess_timeout_wird_als_nicht_erreichbar_gewertet(self):
        import subprocess as subprocess_module
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", side_effect=subprocess_module.TimeoutExpired(cmd="docker", timeout=10)):
            assert docker_check.docker_daemon_running() is False

    def test_positiv_use_sudo_stellt_sudo_voran(self):
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            assert docker_check.docker_daemon_running(use_sudo=True) is True
        mock_run.assert_called_once_with(["sudo", "docker", "info"], capture_output=True, timeout=10)


class TestDockerCmdPrefix:
    def test_positiv_ohne_sudo_erreichbar_liefert_plain_docker(self):
        with patch.object(docker_check, "docker_daemon_running", side_effect=lambda use_sudo=False: not use_sudo):
            assert docker_check.docker_cmd_prefix() == ["docker"]

    def test_positiv_nur_mit_sudo_erreichbar_liefert_sudo_docker(self):
        with patch.object(docker_check, "docker_daemon_running", side_effect=lambda use_sudo=False: use_sudo):
            assert docker_check.docker_cmd_prefix() == ["sudo", "docker"]

    def test_corner_case_gar_nicht_erreichbar_faellt_auf_plain_docker_zurueck(self):
        with patch.object(docker_check, "docker_daemon_running", return_value=False):
            assert docker_check.docker_cmd_prefix() == ["docker"]
