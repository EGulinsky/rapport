"""macOS CallsProvider — ported 1:1 from calls_bridge.py.

Reads iPhone call history (Continuity, needs Full Disk Access) and WhatsApp
call history (Mac app's local SQLite store). Both are macOS-only concepts —
there is no Windows equivalent, so this module will likely stay macOS-only
even after a Windows port (documented as a known platform limitation, not a
gap to eventually close).
"""
from __future__ import annotations

import datetime
import hashlib
import os
import sqlite3
from typing import Any

from agent.providers.base import CallsProvider

PHONE_DB = os.path.expanduser(
    "~/Library/Application Support/CallHistoryDB/CallHistory.storedata"
)
WA_BASE = os.path.expanduser(
    "~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/"
)
WA_CALLS = os.path.join(WA_BASE, "CallHistory.sqlite")
WA_CONTACTS = os.path.join(WA_BASE, "ContactsV2.sqlite")
WA_CHAT = os.path.join(WA_BASE, "ChatStorage.sqlite")

_EPOCH = datetime.datetime(2001, 1, 1)
_EPOCH_UTC = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)


def _ts(coredata_secs) -> str | None:
    if not coredata_secs:
        return None
    try:
        dt_utc = _EPOCH_UTC + datetime.timedelta(seconds=float(coredata_secs))
        return dt_utc.astimezone().strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _uid(source: str, raw: str) -> str:
    return hashlib.md5(f"{source}:{raw}".encode()).hexdigest()


def _can_read_db(path: str) -> bool:
    """Whether path exists AND is actually queryable — os.path.exists() alone
    stays true even when Full Disk Access has been revoked, which previously
    made the health check report phone call history as accessible while every
    read silently failed and returned no calls."""
    if not os.path.exists(path):
        return False
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        # "SELECT 1" doesn't touch the file at all (SQLite connections are
        # lazy) and passed even against unreadable/corrupt files on some
        # platforms — querying sqlite_master forces an actual page read.
        db.execute("SELECT count(*) FROM sqlite_master").fetchone()
        db.close()
        return True
    except Exception:
        return False


class MacCallsProvider(CallsProvider):
    def list_calls(self, since_days: int = 90, source: str = "all") -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        if source in ("all", "phone"):
            calls += self._read_phone_calls(since_days)
        if source in ("all", "whatsapp"):
            calls += self._read_whatsapp_calls(since_days)
        return calls

    def health(self) -> dict[str, Any]:
        phone_ok = _can_read_db(PHONE_DB)
        whatsapp_ok = _can_read_db(WA_CALLS)
        return {
            "ok": phone_ok or whatsapp_ok,
            "phone_accessible": phone_ok,
            "whatsapp_accessible": whatsapp_ok,
        }

    def _read_phone_calls(self, since_days: int) -> list[dict[str, Any]]:
        if not os.path.exists(PHONE_DB):
            return []
        try:
            db = sqlite3.connect(f"file:{PHONE_DB}?mode=ro", uri=True)
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=since_days) - _EPOCH).total_seconds()
            rows = db.execute("""
                SELECT ZDATE, ZDURATION, ZADDRESS, ZNAME,
                       ZORIGINATED, ZANSWERED,
                       ZSERVICE_PROVIDER, ZCALLTYPE
                FROM ZCALLRECORD
                WHERE ZDATE > ?
                ORDER BY ZDATE DESC
            """, (cutoff,)).fetchall()
            db.close()
            result = []
            for r in rows:
                phone = (r[2] or "").strip()
                result.append({
                    "id":         _uid("phone", f"{r[0]}:{phone}"),
                    "source":     "phone",
                    "date":       _ts(r[0]),
                    "duration_s": int(r[1] or 0),
                    "phone":      phone,
                    "name":       (r[3] or "").strip() or None,
                    "direction":  "outgoing" if r[4] else "incoming",
                    "answered":   bool(r[5]),
                    "service":    r[6] or "Phone",
                })
            return result
        except Exception:
            return []

    def _read_whatsapp_calls(self, since_days: int) -> list[dict[str, Any]]:
        if not os.path.exists(WA_CALLS):
            return []
        try:
            db = sqlite3.connect(WA_CALLS)
            db.execute(f"ATTACH DATABASE '{WA_CONTACTS}' AS contacts")
            db.execute(f"ATTACH DATABASE '{WA_CHAT}' AS chat")
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=since_days) - _EPOCH).total_seconds()
            rows = db.execute("""
                SELECT e.ZDATE, e.ZDURATION, e.ZOUTCOME,
                       a.ZINCOMING, a.ZMISSED, a.ZVIDEO,
                       p.ZJIDSTRING,
                       c.ZFULLNAME, c.ZPHONENUMBER,
                       cs.ZPARTNERNAME,
                       e.Z1CALLEVENTS
                FROM ZWACDCALLEVENT e
                LEFT JOIN ZWAAGGREGATECALLEVENT a ON a.ZFIRSTDATE = e.ZDATE
                LEFT JOIN ZWACDCALLEVENTPARTICIPANT p ON p.Z1PARTICIPANTS = e.Z1CALLEVENTS
                LEFT JOIN contacts.ZWAADDRESSBOOKCONTACT c ON c.ZLID = p.ZJIDSTRING
                LEFT JOIN chat.ZWACHATSESSION cs ON cs.ZCONTACTJID = p.ZJIDSTRING
                WHERE e.ZDATE > ?
                ORDER BY e.ZDATE DESC
            """, (cutoff,)).fetchall()
            db.close()
            result = []
            for r in rows:
                name = (r[7] or r[9] or "").strip() or None
                phone = (r[8] or "").strip() or None
                result.append({
                    "id":         _uid("whatsapp", f"{r[0]}:{r[10]}"),
                    "source":     "whatsapp",
                    "date":       _ts(r[0]),
                    "duration_s": int(r[1] or 0),
                    "phone":      phone,
                    "name":       name,
                    "direction":  "incoming" if r[3] else "outgoing",
                    "answered":   r[2] == 0,
                    "service":    "WhatsApp",
                })
            return result
        except Exception:
            return []
