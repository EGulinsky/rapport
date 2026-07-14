"""L0 — Linux provider adapters. FilesProvider's real logic is the
zenity -> kdialog -> tkinter cascade in _has_command()-gated branches;
subprocess and tkinter are mocked throughout. Notes/Calls are pure stubs
(Apple Notes / iPhone Continuity are macOS-only concepts) — just assert the
stub shape."""
import sys
from unittest.mock import MagicMock, patch

from agent.providers.linux.calls import LinuxCallsProvider
from agent.providers.linux.files import LinuxFilesProvider
from agent.providers.linux.notes import LinuxNotesProvider


class TestLinuxFilesProviderPickFolderCascade:
    def test_positiv_zenity_verfuegbar_wird_verwendet(self):
        def _run(cmd, **kwargs):
            if cmd[:2] == ["which", "zenity"]:
                return MagicMock(returncode=0)
            if cmd[0] == "zenity":
                return MagicMock(stdout="/home/test/Ordner\n")
            raise AssertionError(f"unerwarteter Aufruf: {cmd}")

        with patch("subprocess.run", side_effect=_run):
            result = LinuxFilesProvider().pick_folder("Wähle")

        assert result == "/home/test/Ordner"

    def test_positiv_kein_zenity_kdialog_verfuegbar_wird_verwendet(self):
        def _run(cmd, **kwargs):
            if cmd[:2] == ["which", "zenity"]:
                raise FileNotFoundError()
            if cmd[:2] == ["which", "kdialog"]:
                return MagicMock(returncode=0)
            if cmd[0] == "kdialog":
                return MagicMock(stdout="/home/test/Ordner2\n")
            raise AssertionError(f"unerwarteter Aufruf: {cmd}")

        with patch("subprocess.run", side_effect=_run):
            result = LinuxFilesProvider().pick_folder("Wähle")

        assert result == "/home/test/Ordner2"

    def test_negativ_weder_zenity_noch_kdialog_faellt_auf_tkinter_zurueck(self):
        def _run(cmd, **kwargs):
            if cmd[0] == "which":
                raise FileNotFoundError()
            raise AssertionError(f"unerwarteter Aufruf: {cmd}")

        mock_tkinter = MagicMock()
        mock_filedialog = MagicMock()
        mock_tkinter.filedialog = mock_filedialog
        mock_filedialog.askdirectory.return_value = "/home/test/Ordner3"

        with patch("subprocess.run", side_effect=_run), \
             patch.dict(sys.modules, {"tkinter": mock_tkinter, "tkinter.filedialog": mock_filedialog}):
            result = LinuxFilesProvider().pick_folder("Wähle")

        assert result == "/home/test/Ordner3"

    def test_negativ_nichts_verfuegbar_liefert_none(self):
        def _run(cmd, **kwargs):
            if cmd[0] == "which":
                raise FileNotFoundError()
            raise AssertionError(f"unerwarteter Aufruf: {cmd}")

        with patch("subprocess.run", side_effect=_run), \
             patch.dict(sys.modules, {"tkinter": None}):
            result = LinuxFilesProvider().pick_folder("Wähle")

        assert result is None


class TestLinuxFilesProviderPickFile:
    def test_positiv_zenity_mit_dateifilter(self):
        def _run(cmd, **kwargs):
            if cmd[:2] == ["which", "zenity"]:
                return MagicMock(returncode=0)
            if cmd[0] == "zenity":
                assert "--file-filter=ZIP files|*zip" in cmd
                return MagicMock(stdout="/home/test/backup.zip\n")
            raise AssertionError(f"unerwarteter Aufruf: {cmd}")

        with patch("subprocess.run", side_effect=_run):
            result = LinuxFilesProvider().pick_file("Backup wählen", ["zip"])

        assert result == "/home/test/backup.zip"


class TestLinuxFilesProviderOpenPath:
    def test_positiv_ruft_xdg_open(self):
        with patch("subprocess.Popen") as mock_popen:
            LinuxFilesProvider().open_path("/home/test/datei.pdf")
        mock_popen.assert_called_once_with(["xdg-open", "/home/test/datei.pdf"])


class TestLinuxNotesProvider:
    def test_positiv_ist_platform_limited(self):
        assert LinuxNotesProvider().platform_limited is True

    def test_positiv_list_notes_leer(self):
        assert LinuxNotesProvider().list_notes() == []

    def test_positiv_health_meldet_nicht_verfuegbar(self):
        health = LinuxNotesProvider().health()
        assert health["ok"] is False
        assert health["platform_limited"] is True


class TestLinuxCallsProvider:
    def test_positiv_ist_platform_limited(self):
        assert LinuxCallsProvider().platform_limited is True

    def test_positiv_list_calls_leer(self):
        assert LinuxCallsProvider().list_calls(90) == []

    def test_positiv_health_meldet_nicht_verfuegbar(self):
        health = LinuxCallsProvider().health()
        assert health["ok"] is False
        assert health["platform_limited"] is True
