"""L0/L1 — docker_install/windows.py: arch-appropriate installer URL,
the --quiet silent-install invocation, the reboot-required exit code
being surfaced distinctly rather than treated as a generic failure, and
launching Docker Desktop afterward — all with subprocess/requests mocked."""
from unittest.mock import MagicMock, patch

from installer.docker_install import windows


class TestInstallerUrl:
    def test_positiv_arm64_waehlt_arm_installer(self):
        with patch("platform.machine", return_value="ARM64"):
            assert windows._installer_url() == windows._INSTALLER_URLS["ARM64"]

    def test_positiv_amd64_waehlt_amd_installer(self):
        with patch("platform.machine", return_value="AMD64"):
            assert windows._installer_url() == windows._INSTALLER_URLS["AMD64"]

    def test_corner_case_unbekannte_architektur_faellt_auf_amd64_zurueck(self):
        with patch("platform.machine", return_value="ia64"):
            assert windows._installer_url() == windows._INSTALLER_URLS["AMD64"]


class TestInstallDocker:
    def test_positiv_erfolgreicher_lauf(self):
        with patch("installer.docker_install.windows.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run, \
             patch("subprocess.Popen"), \
             patch("installer.docker_install.windows._DOCKER_DESKTOP_EXE") as mock_exe, \
             patch("installer.docker_install.windows.docker_daemon_running", return_value=True):
            mock_get.return_value = MagicMock(iter_content=lambda chunk_size: [b"data"], raise_for_status=lambda: None)
            mock_exe.exists.return_value = True
            assert windows.install_docker() is True

        install_call = mock_run.call_args_list[0]
        assert install_call.args[0][1:] == ["install", "--quiet", "--accept-license"]

    def test_negativ_download_fehler_liefert_false(self):
        import requests
        with patch("installer.docker_install.windows.requests.get", side_effect=requests.RequestException("boom")), \
             patch("subprocess.run") as mock_run:
            assert windows.install_docker() is False
        mock_run.assert_not_called()

    def test_negativ_reboot_erforderlich_wird_erkannt(self):
        with patch("installer.docker_install.windows.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=windows._REBOOT_REQUIRED_EXIT_CODE)):
            mock_get.return_value = MagicMock(iter_content=lambda chunk_size: [b"data"], raise_for_status=lambda: None)
            assert windows.install_docker() is False

    def test_negativ_installer_fehlschlag(self):
        with patch("installer.docker_install.windows.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=1)):
            mock_get.return_value = MagicMock(iter_content=lambda chunk_size: [b"data"], raise_for_status=lambda: None)
            assert windows.install_docker() is False

    def test_negativ_daemon_startet_nicht_nach_install(self):
        with patch("installer.docker_install.windows.requests.get") as mock_get, \
             patch("subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("subprocess.Popen"), \
             patch("installer.docker_install.windows._DOCKER_DESKTOP_EXE") as mock_exe, \
             patch("installer.docker_install.windows.docker_daemon_running", return_value=False), \
             patch("time.sleep"):
            mock_get.return_value = MagicMock(iter_content=lambda chunk_size: [b"data"], raise_for_status=lambda: None)
            mock_exe.exists.return_value = True
            assert windows.install_docker() is False
