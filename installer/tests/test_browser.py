"""L0 — browser.py: opens the running app's URL in the default browser."""
from unittest.mock import patch

from installer import browser


class TestOpenApp:
    def test_positiv_oeffnet_richtige_url(self):
        with patch("webbrowser.open", return_value=True) as mock_open:
            assert browser.open_app() is True
        mock_open.assert_called_once_with(browser.APP_URL)
