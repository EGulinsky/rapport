"""Cross-platform system tray entry point.

macOS: rumps (existing, menubar.py)
Windows: pystray + win32gui
Linux: pystray + Gtk

This module provides a unified interface that works on all platforms.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from typing import Callable

from agent.config import AgentConfig, app_data_dir
from agent import service
from agent.strings import t


def _copy_to_clipboard(text: str) -> None:
    """Cross-platform clipboard copy."""
    system = sys.platform
    if system == "darwin":
        subprocess.run(["pbcopy"], input=text.encode(), timeout=5)
    elif system == "win32":
        try:
            import ctypes
            ctypes.windll.user32.OpenClipboard(0)
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.SetClipboardData(1, text.encode("utf-16-le"))
            ctypes.windll.user32.CloseClipboard()
        except Exception:
            pass
    else:
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), timeout=5)
        except FileNotFoundError:
            try:
                subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), timeout=5)
            except FileNotFoundError:
                pass


def _open_logs() -> None:
    """Open log directory in file manager."""
    log_path = app_data_dir() / "logs"
    system = sys.platform
    if system == "darwin":
        subprocess.Popen(["open", str(log_path)])
    elif system == "win32":
        subprocess.Popen(["explorer", str(log_path)])
    else:
        subprocess.Popen(["xdg-open", str(log_path)])


def run_tray_app(config: AgentConfig) -> None:
    """Run system tray app. Tries pystray first, falls back to headless."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        _run_headless(config)
        return

    lang = config.ui_language

    def create_image():
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse([8, 8, 56, 56], fill=(0, 200, 0, 255))
        return image

    def on_copy_token(icon, item):
        _copy_to_clipboard(config.token)

    def on_open_logs(icon, item):
        _open_logs()

    def on_quit(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(t("running_on_port", lang, port=config.port), None, enabled=False),
        pystray.MenuItem(t("copy_token", lang), on_copy_token),
        pystray.MenuItem(t("open_logs", lang), on_open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("quit", lang), on_quit),
    )

    icon = pystray.Icon(
        "Rapport Agent",
        create_image(),
        "Rapport Agent",
        menu,
    )

    icon.run()


def _run_headless(config: AgentConfig) -> None:
    """Fallback: run without system tray (for headless servers)."""
    lang = config.ui_language
    print(f"Rapport Agent {t('running_on_port', lang, port=config.port)}")
    print("No system tray available (pystray not installed).")
    print("Press Ctrl+C to stop.")

    import signal
    def handler(sig, frame):
        print("\nShutting down...")
        sys.exit(0)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    while True:
        import time
        time.sleep(3600)


def bootstrap_or_run() -> bool:
    """True: continue and run the tray app. False: this process just
    self-registered as a service and should exit."""
    if service.is_registered():
        return True
    service.register(executable_path())
    return False


def executable_path() -> str:
    """Path the service manager should re-invoke — the frozen binary when
    packaged, or this script via the current interpreter otherwise."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return f"{sys.executable} -m agent.main"


def _start_server_thread(config: AgentConfig) -> None:
    import uvicorn

    from agent.config import restart_process
    from agent.main import create_app
    from agent.providers import factory

    app = create_app(
        config,
        files_provider=factory.make_files_provider(),
        notes_provider=factory.make_notes_provider(),
        calls_provider=factory.make_calls_provider(),
        restart_agent=restart_process,
    )
    thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="0.0.0.0", port=config.port, log_level="info"),
        daemon=True,
    )
    thread.start()


def main() -> None:
    """Cross-platform entry point: register service + start tray."""
    if not bootstrap_or_run():
        return

    config = AgentConfig.load_or_create()
    _start_server_thread(config)

    system = sys.platform
    if system == "darwin":
        from agent.menubar import run_menubar_app
        run_menubar_app(config)
    else:
        run_tray_app(config)


if __name__ == "__main__":
    main()
