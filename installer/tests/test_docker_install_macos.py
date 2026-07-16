"""L0/L1 — docker_install/macos.py: arch-appropriate .dmg URL selection,
hdiutil mount-point parsing, and the install orchestration (download ->
mount -> silent install -> unmount -> launch -> wait), all with
subprocess/requests mocked — no real network/disk/install calls."""
from unittest.mock import MagicMock, patch

from installer.docker_install import macos


class TestDmgUrl:
    def test_positiv_arm64_waehlt_apple_silicon_url(self):
        with patch("platform.machine", return_value="arm64"):
            assert macos._dmg_url() == macos._DMG_URLS["arm64"]

    def test_positiv_x86_64_waehlt_intel_url(self):
        with patch("platform.machine", return_value="x86_64"):
            assert macos._dmg_url() == macos._DMG_URLS["x86_64"]

    def test_corner_case_unbekannte_architektur_faellt_auf_intel_zurueck(self):
        with patch("platform.machine", return_value="ppc"):
            assert macos._dmg_url() == macos._DMG_URLS["x86_64"]


class TestMountPoint:
    def test_positiv_extrahiert_volumes_pfad_aus_hdiutil_ausgabe(self):
        output = (
            "/dev/disk4          \tGUID_partition_scheme          \n"
            "/dev/disk4s1        \tApple_HFS                      \t/Volumes/Docker\n"
        )
        assert macos._mount_point(output) == "/Volumes/Docker"

    def test_negativ_kein_volumes_pfad_wirft_runtime_error(self):
        import pytest
        with pytest.raises(RuntimeError):
            macos._mount_point("nothing useful here")


class TestInstallDocker:
    def test_positiv_erfolgreicher_lauf(self, tmp_path):
        attach_result = MagicMock(returncode=0, stdout="/dev/disk4\t\t/Volumes/Docker\n", stderr="")
        install_result = MagicMock(returncode=0)

        with patch("installer.docker_install.macos._download"), \
             patch("subprocess.run", side_effect=[attach_result, install_result, MagicMock(returncode=0), MagicMock(returncode=0)]) as mock_run, \
             patch("installer.docker_install.macos.docker_daemon_running", return_value=True):
            assert macos.install_docker() is True

        # attach, sudo install, hdiutil detach, `open -a Docker`
        assert mock_run.call_count == 4
        assert mock_run.call_args_list[1].args[0][0] == "sudo"

    def test_negativ_download_fehler_liefert_false_ohne_weitere_schritte(self):
        import requests
        with patch("installer.docker_install.macos._download", side_effect=requests.RequestException("boom")), \
             patch("subprocess.run") as mock_run:
            assert macos.install_docker() is False
        mock_run.assert_not_called()

    def test_negativ_mount_fehlschlag_liefert_false(self):
        attach_result = MagicMock(returncode=1, stdout="", stderr="mount failed")
        with patch("installer.docker_install.macos._download"), \
             patch("subprocess.run", return_value=attach_result):
            assert macos.install_docker() is False

    def test_negativ_install_fehlschlag_hdiutil_detach_wird_trotzdem_aufgerufen(self):
        attach_result = MagicMock(returncode=0, stdout="/dev/disk4\t\t/Volumes/Docker\n", stderr="")
        install_result = MagicMock(returncode=1)
        detach_result = MagicMock(returncode=0)

        with patch("installer.docker_install.macos._download"), \
             patch("subprocess.run", side_effect=[attach_result, install_result, detach_result]) as mock_run:
            assert macos.install_docker() is False

        assert mock_run.call_count == 3
        assert mock_run.call_args_list[2].args[0] == ["hdiutil", "detach", "/Volumes/Docker", "-quiet"]

    def test_negativ_daemon_startet_nicht_nach_install(self):
        attach_result = MagicMock(returncode=0, stdout="/dev/disk4\t\t/Volumes/Docker\n", stderr="")
        install_result = MagicMock(returncode=0)

        with patch("installer.docker_install.macos._download"), \
             patch("subprocess.run", side_effect=[attach_result, install_result, MagicMock(returncode=0), MagicMock(returncode=0)]), \
             patch("installer.docker_install.macos.docker_daemon_running", return_value=False), \
             patch("time.sleep"):
            assert macos.install_docker() is False
