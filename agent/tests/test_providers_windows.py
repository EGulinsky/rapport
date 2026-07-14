"""L0 — Windows provider adapters. FilesProvider's tkinter usage is mocked
via sys.modules (this Mac has no Windows GUI to exercise); open_path's
os.startfile()/xdg-open branching is mocked via sys.platform. Notes/Calls
are pure stubs (Apple Notes / iPhone Continuity are macOS-only concepts) —
just assert the stub shape."""
import sys
from unittest.mock import MagicMock, patch

from agent.providers.windows.calls import WindowsCallsProvider
from agent.providers.windows.files import WindowsFilesProvider
from agent.providers.windows.notes import WindowsNotesProvider


class TestWindowsFilesProviderPickFolder:
    def test_positiv_liefert_gewaehlten_pfad(self):
        mock_tkinter = MagicMock()
        mock_filedialog = MagicMock()
        mock_tkinter.filedialog = mock_filedialog
        mock_filedialog.askdirectory.return_value = r"C:\Users\test\Ordner"

        with patch.dict(sys.modules, {"tkinter": mock_tkinter, "tkinter.filedialog": mock_filedialog}):
            result = WindowsFilesProvider().pick_folder("Wähle einen Ordner")

        assert result == r"C:\Users\test\Ordner"

    def test_negativ_abgebrochen_liefert_none(self):
        mock_tkinter = MagicMock()
        mock_filedialog = MagicMock()
        mock_tkinter.filedialog = mock_filedialog
        mock_filedialog.askdirectory.return_value = ""

        with patch.dict(sys.modules, {"tkinter": mock_tkinter, "tkinter.filedialog": mock_filedialog}):
            result = WindowsFilesProvider().pick_folder("x")

        assert result is None

    def test_negativ_ohne_tkinter_liefert_none(self):
        with patch.dict(sys.modules, {"tkinter": None}):
            result = WindowsFilesProvider().pick_folder("x")

        assert result is None


class TestWindowsFilesProviderPickFile:
    def test_positiv_liefert_gewaehlte_datei_mit_typfilter(self):
        mock_tkinter = MagicMock()
        mock_filedialog = MagicMock()
        mock_tkinter.filedialog = mock_filedialog
        mock_filedialog.askopenfilename.return_value = r"C:\Users\test\backup.zip"

        with patch.dict(sys.modules, {"tkinter": mock_tkinter, "tkinter.filedialog": mock_filedialog}):
            result = WindowsFilesProvider().pick_file("Backup wählen", ["zip", "db"])

        assert result == r"C:\Users\test\backup.zip"
        filetypes = mock_filedialog.askopenfilename.call_args.kwargs["filetypes"]
        assert ("ZIP files", "*zip") in filetypes
        assert ("DB files", "*db") in filetypes


class TestWindowsFilesProviderOpenPath:
    def test_positiv_win32_ruft_os_startfile(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("os.startfile", create=True) as mock_startfile:
            WindowsFilesProvider().open_path(r"C:\Users\test\datei.pdf")
        mock_startfile.assert_called_once_with(r"C:\Users\test\datei.pdf")

    def test_negativ_nicht_win32_faellt_auf_xdg_open_zurueck(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with patch("subprocess.Popen") as mock_popen:
            WindowsFilesProvider().open_path("/home/test/datei.pdf")
        mock_popen.assert_called_once_with(["xdg-open", "/home/test/datei.pdf"])


class TestWindowsNotesProvider:
    def test_positiv_ist_platform_limited(self):
        assert WindowsNotesProvider().platform_limited is True

    def test_positiv_list_notes_leer(self):
        assert WindowsNotesProvider().list_notes() == []

    def test_positiv_health_meldet_nicht_verfuegbar(self):
        health = WindowsNotesProvider().health()
        assert health["ok"] is False
        assert health["platform_limited"] is True


class TestWindowsCallsProvider:
    def test_positiv_ist_platform_limited(self):
        assert WindowsCallsProvider().platform_limited is True

    def test_positiv_list_calls_leer(self):
        assert WindowsCallsProvider().list_calls(90) == []

    def test_positiv_health_meldet_nicht_verfuegbar(self):
        health = WindowsCallsProvider().health()
        assert health["ok"] is False
        assert health["platform_limited"] is True
