"""macOS menu-bar UI (`rumps`) — pure presentation module.

Service self-registration, the HTTP server thread, and the cross-platform
entry point all live in `agent/tray.py` now (single unified entry point for
all three OSes; on macOS it delegates the actual UI to `run_menubar_app()`
below via `agent.main:run()`/`tray.main()`). This module only builds the
rumps menu — it has no `__main__` of its own.
"""
from __future__ import annotations

import subprocess
import threading

from agent import launchd
from agent.about import about_message
from agent.config import AgentConfig, app_data_dir
from agent.permission_monitor import PermissionMonitor
from agent.providers.base import CallsProvider, NotesProvider
from agent.strings import t

# How often the periodic permission re-check runs, in seconds. Permission
# grants don't change on their own on a sub-minute timescale -- this just
# needs to notice within a reasonable window of a revoke, not instantly.
_PERMISSION_CHECK_INTERVAL_SECONDS = 1800


def _copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), timeout=5)


def run_menubar_app(config: AgentConfig, notes_provider: NotesProvider, calls_provider: CallsProvider) -> None:
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
            self._permission_monitor = PermissionMonitor(calls_provider, notes_provider)
            # Check once immediately at startup (a permission already
            # missing when the agent launches should notify right away, not
            # only after the first timer interval elapses).
            self._check_permissions_async()

        def _check_permissions_async(self, _sender=None):
            # Always off the main thread: a permission that's actually
            # missing doesn't just fail fast (a JXA/AppleScript call denied
            # Automation access can sit blocked in the OS's consent-dialog
            # handshake well past its own internal subprocess timeout,
            # observed hardware-verified during v4.7.7's rollout) -- running
            # this on rumps' own run loop thread would freeze the whole menu
            # bar app (and, worse, appears to also stall unrelated /health
            # requests handled on a different thread of the same process)
            # for as long as that hang lasts, rather than just the intended
            # background check.
            threading.Thread(target=self._check_permissions, daemon=True).start()

        def _check_permissions(self):
            self._permission_monitor.check(
                lang, lambda title, message: rumps.notification(title, "", message),
            )

        @rumps.timer(_PERMISSION_CHECK_INTERVAL_SECONDS)
        def _periodic_permission_check(self, _sender):
            self._check_permissions_async()

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
