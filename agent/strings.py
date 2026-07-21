"""Tiny i18n helper for the menu bar UI — no dependency on the frontend's
react-i18next setup since this is a separate, PyInstaller-packaged process.
rumps builds the menu once at startup, so a language change only takes
effect after the agent is restarted; that's an accepted limitation (see
CLAUDE.md's i18n phase notes)."""
from __future__ import annotations

_STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "running_on_port": "Läuft auf Port {port}",
        "copy_token": "Token kopieren",
        "open_logs": "Logs öffnen",
        "uninstall": "Deinstallieren",
        "quit": "Beenden",
        "notification_title": "Rapport Agent",
        "token_copied": "Token in Zwischenablage kopiert",
        "uninstall_confirm_title": "Agent deinstallieren?",
        "uninstall_confirm_message": "Entfernt den Autostart-Eintrag und beendet den Agenten.",
        "uninstall_confirm_ok": "Deinstallieren",
        "uninstall_confirm_cancel": "Abbrechen",
        "about": "Über Rapport Agent",
        "about_message": "Version {version}\nPlattform: {platform}\nPort: {port}",
    },
    "en": {
        "running_on_port": "Running on port {port}",
        "copy_token": "Copy token",
        "open_logs": "Open logs",
        "uninstall": "Uninstall",
        "quit": "Quit",
        "notification_title": "Rapport Agent",
        "token_copied": "Token copied to clipboard",
        "uninstall_confirm_title": "Uninstall agent?",
        "uninstall_confirm_message": "Removes the autostart entry and stops the agent.",
        "uninstall_confirm_ok": "Uninstall",
        "uninstall_confirm_cancel": "Cancel",
        "about": "About Rapport Agent",
        "about_message": "Version {version}\nPlatform: {platform}\nPort: {port}",
    },
}


def t(key: str, ui_language: str, **kwargs: object) -> str:
    strings = _STRINGS.get(ui_language, _STRINGS["de"])
    template = strings.get(key, _STRINGS["de"].get(key, key))
    return template.format(**kwargs) if kwargs else template
