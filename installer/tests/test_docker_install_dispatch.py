"""L0 — docker_install/__init__.py: picks which OS-specific installer
(macos/linux) to delegate to, based on platform.system() — Windows isn't
dispatched here at all (its own WiX-based installer handles Docker
directly). Mirrors agent/tests/test_service.py's dispatch-testing pattern."""
from unittest.mock import patch

import pytest

from installer import docker_install


class TestGetImplDispatch:
    def test_positiv_darwin_delegiert_an_macos(self):
        with patch("platform.system", return_value="Darwin"), \
             patch("installer.docker_install.macos.install_docker", return_value=True) as mock_install:
            assert docker_install.install_docker() is True
        mock_install.assert_called_once()

    def test_negativ_windows_nicht_mehr_ueber_python_dispatcht(self):
        with patch("platform.system", return_value="Windows"):
            with pytest.raises(NotImplementedError):
                docker_install.install_docker()

    def test_positiv_linux_delegiert_an_linux_modul(self):
        with patch("platform.system", return_value="Linux"), \
             patch("installer.docker_install.linux.install_docker", return_value=True) as mock_install:
            assert docker_install.install_docker() is True
        mock_install.assert_called_once()

    def test_negativ_unbekannte_plattform_wirft_not_implemented(self):
        with patch("platform.system", return_value="FreeBSD"):
            with pytest.raises(NotImplementedError):
                docker_install.install_docker()
