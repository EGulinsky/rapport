"""Cross-platform "About" dialog content + display — shared by menubar.py
(macOS, which has rumps.alert built in) and tray.py (Windows/Linux via
pystray, which has no alert dialog of its own, hence show_about_dialog()
below)."""
from __future__ import annotations

import subprocess
import sys

from agent.config import AgentConfig, platform_name
from agent.strings import t
from agent.version import __version__


def about_message(config: AgentConfig) -> str:
    return t("about_message", config.ui_language, version=__version__, platform=platform_name(), port=config.port)


def show_about_dialog(config: AgentConfig) -> None:
    """Windows/Linux only — macOS builds its About item straight from
    rumps.alert in menubar.py, since rumps already has a native dialog."""
    title = t("about", config.ui_language)
    message = about_message(config)

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0)
        return

    for cmd in (
        ["zenity", "--info", "--title", title, "--text", message],
        ["kdialog", "--msgbox", message, "--title", title],
    ):
        try:
            subprocess.run(cmd, timeout=30)
            return
        except FileNotFoundError:
            continue
        except subprocess.SubprocessError:
            return
    print(f"{title}\n{message}")
