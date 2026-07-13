"""L0 — factory.py: the platform dispatch is the only logic in this module
(each branch just imports and instantiates a concrete provider), so these
tests mock config.platform_name() and assert the right provider class comes
back for Darwin/Windows/Linux, plus NotImplementedError for anything else."""
from unittest.mock import patch

import pytest

from agent.providers import factory


class TestMakeFilesProvider:
    def test_positiv_darwin_liefert_mac_provider(self):
        from agent.providers.mac.files import MacFilesProvider
        with patch("agent.providers.factory.platform_name", return_value="Darwin"):
            assert isinstance(factory.make_files_provider(), MacFilesProvider)

    def test_positiv_windows_liefert_windows_provider(self):
        from agent.providers.windows.files import WindowsFilesProvider
        with patch("agent.providers.factory.platform_name", return_value="Windows"):
            assert isinstance(factory.make_files_provider(), WindowsFilesProvider)

    def test_positiv_linux_liefert_linux_provider(self):
        from agent.providers.linux.files import LinuxFilesProvider
        with patch("agent.providers.factory.platform_name", return_value="Linux"):
            assert isinstance(factory.make_files_provider(), LinuxFilesProvider)

    def test_negativ_unbekannte_plattform_wirft_not_implemented(self):
        with patch("agent.providers.factory.platform_name", return_value="FreeBSD"):
            with pytest.raises(NotImplementedError):
                factory.make_files_provider()


class TestMakeNotesProvider:
    def test_positiv_darwin_liefert_mac_provider(self):
        from agent.providers.mac.notes import MacNotesProvider
        with patch("agent.providers.factory.platform_name", return_value="Darwin"):
            assert isinstance(factory.make_notes_provider(), MacNotesProvider)

    def test_positiv_windows_liefert_windows_provider(self):
        from agent.providers.windows.notes import WindowsNotesProvider
        with patch("agent.providers.factory.platform_name", return_value="Windows"):
            assert isinstance(factory.make_notes_provider(), WindowsNotesProvider)

    def test_positiv_linux_liefert_linux_provider(self):
        from agent.providers.linux.notes import LinuxNotesProvider
        with patch("agent.providers.factory.platform_name", return_value="Linux"):
            assert isinstance(factory.make_notes_provider(), LinuxNotesProvider)

    def test_negativ_unbekannte_plattform_wirft_not_implemented(self):
        with patch("agent.providers.factory.platform_name", return_value="FreeBSD"):
            with pytest.raises(NotImplementedError):
                factory.make_notes_provider()


class TestMakeCallsProvider:
    def test_positiv_darwin_liefert_mac_provider(self):
        from agent.providers.mac.calls import MacCallsProvider
        with patch("agent.providers.factory.platform_name", return_value="Darwin"):
            assert isinstance(factory.make_calls_provider(), MacCallsProvider)

    def test_positiv_windows_liefert_windows_provider(self):
        from agent.providers.windows.calls import WindowsCallsProvider
        with patch("agent.providers.factory.platform_name", return_value="Windows"):
            assert isinstance(factory.make_calls_provider(), WindowsCallsProvider)

    def test_positiv_linux_liefert_linux_provider(self):
        from agent.providers.linux.calls import LinuxCallsProvider
        with patch("agent.providers.factory.platform_name", return_value="Linux"):
            assert isinstance(factory.make_calls_provider(), LinuxCallsProvider)

    def test_negativ_unbekannte_plattform_wirft_not_implemented(self):
        with patch("agent.providers.factory.platform_name", return_value="FreeBSD"):
            with pytest.raises(NotImplementedError):
                factory.make_calls_provider()
