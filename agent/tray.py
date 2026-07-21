"""The single cross-platform entry point (`python -m agent.main` / the
packaged binary on every OS runs `main()` below).

macOS: rumps for the actual menu (menubar.py — pure UI, no bootstrap logic
       of its own anymore)
Windows/Linux: pystray + Pillow (clipboard/file-manager actions use stdlib
       `ctypes.windll`/`xclip`/`xsel` directly, not a separate win32 package)

Owns service self-registration, the HTTP server thread, and dispatch to the
right tray/menu-bar UI — menubar.py only builds the rumps menu.
"""
from __future__ import annotations

import subprocess
import sys
import threading

from agent.about import show_about_dialog
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
    """Run system tray app. Tries pystray first, falls back to headless.

    Catches more than ImportError: hardware-verified on real Linux (a
    container/server with no X11 display) that pystray's backend selection
    connects to the display *at import time* (`pystray/__init__.py`'s
    `backend` picks and imports `_xorg`/`_gtk`/`_appindicator` eagerly), and
    a missing display raises `Xlib.error.DisplayNameError` — a module
    successfully found and imported, just unable to do its job. Any such
    failure should fall back headless rather than crash the whole agent,
    since the FastAPI server doesn't need a tray icon to function."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
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

    def on_about(icon, item):
        show_about_dialog(config)

    def on_quit(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(t("running_on_port", lang, port=config.port), None, enabled=False),
        pystray.MenuItem(t("copy_token", lang), on_copy_token),
        pystray.MenuItem(t("open_logs", lang), on_open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("about", lang), on_about),
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


def _redirect_stdio_if_headless() -> None:
    """PyInstaller's windowed (console=False) Windows build has no console,
    so sys.stdout/sys.stderr don't behave like real streams — any library
    that logs through them (uvicorn's default logging setup, in particular)
    raises, which silently kills the server thread since a daemon thread's
    unhandled exception has no console to print to. Hardware-verified: the
    packaged .exe's server never started until this redirect was added
    (isolated by comparing against a console=True debug build, which worked
    fine using the same code). Dev runs (a real sys.stdout) are unaffected."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "agent.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = log_file
    sys.stderr = log_file


def bootstrap_or_run() -> bool:
    """True: continue and run the tray app. False: this process just
    self-registered as a service and should exit."""
    if service.is_registered():
        return True
    command, args = executable_command()
    service.register(command, args)
    return False


def executable_command() -> tuple[str, list[str]]:
    """Command + args the service manager should re-invoke — the frozen
    binary when packaged (no args needed), or this module (`-m agent.tray`,
    *not* `agent.main` — that's a separate bare-uvicorn dev entry point with
    no tray/menu or self-registration at all) via the current interpreter
    otherwise. Kept as a (command, args) pair rather than one embedded
    string so each service backend (launchd plist array / Task Scheduler
    <Command>+<Arguments> / systemd ExecStart) gets a correctly split argv
    instead of a single mangled string."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    return sys.executable, ["-m", "agent.tray"]


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

    _redirect_stdio_if_headless()
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
