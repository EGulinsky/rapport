"""L0 — menubar.py: pure macOS menu-bar UI helpers. Bootstrap/registration
logic and the cross-platform entry point live in agent/tray.py now (see
test_tray.py) — menubar.py only builds the rumps menu and copies to the
clipboard, both of which need an actual GUI/pasteboard session to exercise
beyond this."""
from unittest.mock import patch

from agent import menubar


class TestCopyToClipboard:
    def test_positiv_ruft_pbcopy_mit_text_auf(self):
        with patch("subprocess.run") as mock_run:
            menubar._copy_to_clipboard("mein-token")

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["pbcopy"]
        assert kwargs["input"] == b"mein-token"
