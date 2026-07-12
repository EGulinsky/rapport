"""Menu bar entry point (macOS only — `rumps`). Structured so the
registration decision is a pure, testable function; the actual GUI event
loop only runs under `if __name__ == "__main__"`.

A Windows entry point would be a sibling module (`agent/tray.py`, `pystray`)
behind the same `bootstrap_or_run()` + server-thread pattern.
"""
from __future__ import annotations

import subprocess
import sys
import threading

from agent import launchd
from agent.config import AgentConfig, app_data_dir
from agent.strings import t


def executable_path() -> str:
    """Path launchd should re-invoke — the frozen .app binary when packaged
    with PyInstaller, or this script via the current interpreter otherwise
    (useful for local dev testing of the registration flow)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return f"{sys.executable} -m agent.menubar"


def bootstrap_or_run() -> bool:
    """True: continue and run the menu bar app in this process. False: this
    process just self-registered as a LaunchAgent and should exit — the
    launchd-spawned instance (which will find itself already registered)
    becomes the persistent one. Avoids two servers fighting over the port."""
    if launchd.is_registered():
        return True
    launchd.register(executable_path())
    return False


def _start_server_thread(config: AgentConfig) -> None:
    import uvicorn

    from agent.main import create_app
    from agent.providers import factory

    app = create_app(
        config,
        files_provider=factory.make_files_provider(),
        notes_provider=factory.make_notes_provider(),
        calls_provider=factory.make_calls_provider(),
    )
    thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="0.0.0.0", port=config.port, log_level="info"),
        daemon=True,
    )
    thread.start()


def _copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), timeout=5)


def run_menubar_app(config: AgentConfig) -> None:
    import rumps

    log_path = app_data_dir() / "logs" / "agent.log"

    lang = config.ui_language

    class AgentMenuBarApp(rumps.App):
        def __init__(self):
            super().__init__("Rapport Agent", title="🟢", quit_button=None)
            self.menu = [
                rumps.MenuItem(t("running_on_port", lang, port=config.port)),
                None,
                rumps.MenuItem(t("copy_token", lang), callback=self.copy_token),
                rumps.MenuItem(t("open_logs", lang), callback=self.open_logs),
                None,
                rumps.MenuItem(t("uninstall", lang), callback=self.uninstall),
                rumps.MenuItem(t("quit", lang), callback=self.quit),
            ]

        def copy_token(self, _):
            _copy_to_clipboard(config.token)
            rumps.notification(t("notification_title", lang), "", t("token_copied", lang))

        def open_logs(self, _):
            subprocess.Popen(["open", str(log_path)])

        def uninstall(self, _):
            if rumps.alert(
                title=t("uninstall_confirm_title", lang),
                message=t("uninstall_confirm_message", lang),
                ok=t("uninstall_confirm_ok", lang), cancel=t("uninstall_confirm_cancel", lang),
            ) == 1:
                launchd.unregister()
                rumps.quit_application()

        def quit(self, _):
            rumps.quit_application()

    AgentMenuBarApp().run()


def main() -> None:
    if not bootstrap_or_run():
        return

    config = AgentConfig.load_or_create()
    _start_server_thread(config)
    run_menubar_app(config)


if __name__ == "__main__":
    main()
