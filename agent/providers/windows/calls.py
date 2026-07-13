"""Windows CallsProvider — not available (iPhone calls are macOS-only).

This is a stub that returns empty results. The macOS CallsProvider reads
iPhone call history (Continuity) and WhatsApp Mac app calls, both of which
are macOS-only concepts.
"""
from __future__ import annotations

from typing import Any

from agent.providers.base import CallsProvider


class WindowsCallsProvider(CallsProvider):
    def list_calls(self, since_days: int = 90, source: str = "all") -> list[dict[str, Any]]:
        return []

    def health(self) -> dict[str, Any]:
        return {"ok": False, "error": "Call history not available on Windows"}
