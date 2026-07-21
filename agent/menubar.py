"""macOS menu-bar UI (`rumps`) — pure presentation module.

Service self-registration, the HTTP server thread, and the cross-platform
entry point all live in `agent/tray.py` now (single unified entry point for
all three OSes; on macOS it delegates the actual UI to `run_menubar_app()`
below via `agent.main:run()`/`tray.main()`). This module only builds the
rumps menu — it has no `__main__` of its own.
"""
from __future__ import annotations

import subprocess

from agent import launchd
from agent.about import about_message
from agent.config import AgentConfig, app_data_dir
from agent.strings import t


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
                rumps.MenuItem(t("about", lang), callback=self.show_about),
                rumps.MenuItem(t("uninstall", lang), callback=self.uninstall),
                rumps.MenuItem(t("quit", lang), callback=self.quit),
            ]

        def copy_token(self, _):
            _copy_to_clipboard(config.token)
            rumps.notification(t("notification_title", lang), "", t("token_copied", lang))

        def open_logs(self, _):
            subprocess.Popen(["open", str(log_path)])

        def show_about(self, _):
            rumps.alert(title=t("about", lang), message=about_message(config))

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
