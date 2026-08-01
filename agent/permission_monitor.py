"""Tracks whether the Calls/Notes providers still have the macOS permissions
they need (Full Disk Access for Calls' phone/WhatsApp reads, Automation
access for driving Notes.app via AppleScript) and reports only state
*transitions* into failure.

Kept free of any `rumps`/UI dependency on purpose — menubar.py is otherwise
untestable without an actual GUI session (see test_menubar.py's docstring),
so the actual comparison/dedup logic lives here where it can be unit tested,
and menubar.py only wires PermissionMonitor.check()'s notify callback to
rumps.notification().
"""
from __future__ import annotations

from typing import Callable

from agent.providers.base import CallsProvider, NotesProvider
from agent.strings import t

_MESSAGE_KEYS: dict[str, str] = {
    "calls_phone": "perm_lost_calls_phone",
    "calls_whatsapp": "perm_lost_calls_whatsapp",
    "notes": "perm_lost_notes",
}


class PermissionMonitor:
    def __init__(self, calls_provider: CallsProvider, notes_provider: NotesProvider):
        self._calls_provider = calls_provider
        self._notes_provider = notes_provider
        # Which checks are currently in a "already notified, still broken"
        # state -- so a permission that's been missing for hours doesn't
        # re-fire a notification on every periodic check. Empty at
        # construction time, so a permission already broken at the very
        # first check (e.g. agent startup) still notifies once.
        self._broken: set[str] = set()

    def check(self, lang: str, notify: Callable[[str, str], None]) -> None:
        """Run one check pass. `notify(title, message)` is called once per
        check that just transitioned from ok (or never-checked) to broken;
        a check that recovers is cleared so a later re-break notifies again."""
        for key, ok in self._collect().items():
            if ok:
                self._broken.discard(key)
            elif key not in self._broken:
                self._broken.add(key)
                notify(t("notification_title", lang), t(_MESSAGE_KEYS[key], lang))

    def _collect(self) -> dict[str, bool]:
        # health() is documented to report expected failure modes as
        # {"ok": False, ...} rather than raising (see calls.py/notes.py) --
        # an exception here is an unexpected bug in the check itself, not a
        # permission problem, so it's treated as "unknown" (assume ok) rather
        # than triggering a false-positive notification.
        try:
            calls_health = self._calls_provider.health()
        except Exception:
            calls_health = {}
        try:
            notes_health = self._notes_provider.health()
        except Exception:
            notes_health = {}

        return {
            "calls_phone": bool(calls_health.get("phone_accessible", True)),
            "calls_whatsapp": bool(calls_health.get("whatsapp_accessible", True)),
            "notes": bool(notes_health.get("ok", True)),
        }
