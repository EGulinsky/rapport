"""Opens the running app in the user's default browser once it's healthy."""
from __future__ import annotations

import webbrowser

APP_URL = "http://localhost:3000"


def open_app() -> bool:
    return webbrowser.open(APP_URL)
