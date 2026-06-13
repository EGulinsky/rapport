#!/usr/bin/env python3
"""
calls_bridge.py – lokaler HTTP-Server für Anrufliste.
Liest iPhone-Anrufe (CallHistoryDB, braucht Full Disk Access)
und WhatsApp-Anrufe (CallHistory.sqlite).

Start: python3 calls_bridge.py
Port:  9997
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# ── Paths ──────────────────────────────────────────────────────────────────────
PHONE_DB  = os.path.expanduser(
    "~/Library/Application Support/CallHistoryDB/CallHistory.storedata"
)
WA_BASE   = os.path.expanduser(
    "~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/"
)
WA_CALLS  = os.path.join(WA_BASE, "CallHistory.sqlite")
WA_CONTACTS = os.path.join(WA_BASE, "ContactsV2.sqlite")
WA_CHAT   = os.path.join(WA_BASE, "ChatStorage.sqlite")

PORT = 9997
EPOCH = datetime.datetime(2001, 1, 1)  # naive, for cutoff math only
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


# ── iPhone calls ───────────────────────────────────────────────────────────────

def read_phone_calls_raw(since_days: int = 10) -> list[dict]:
    """All calls without duration filter — for debugging."""
    if not os.path.exists(PHONE_DB):
        return []
    try:
        db = sqlite3.connect(f"file:{PHONE_DB}?mode=ro", uri=True)
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=since_days)
                  - EPOCH).total_seconds()
        rows = db.execute("""
            SELECT ZDATE, ZDURATION, ZADDRESS, ZNAME, ZORIGINATED, ZANSWERED, ZSERVICE_PROVIDER
            FROM ZCALLRECORD
            WHERE ZDATE > ?
            ORDER BY ZDATE DESC
        """, (cutoff,)).fetchall()
        db.close()
        result = []
        for r in rows:
            ts = _ts(r[0])
            phone = (r[2] or "").strip()
            result.append({
                "date": ts,
                "duration_s": int(r[1] or 0),
                "phone": phone,
                "name": (r[3] or "").strip() or None,
                "direction": "outgoing" if r[4] else "incoming",
                "answered": bool(r[5]),
                "service": r[6] or "Phone",
            })
        return result
    except Exception as e:
        print(f"[phone/raw] Fehler: {e}")
        return []


def read_phone_calls(since_days: int = 90) -> list[dict]:
    if not os.path.exists(PHONE_DB):
        return []
    try:
        db = sqlite3.connect(f"file:{PHONE_DB}?mode=ro", uri=True)
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=since_days)
                  - EPOCH).total_seconds()
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
            ts = _ts(r[0])
            phone = (r[2] or "").strip()
            result.append({
                "id":         _uid("phone", f"{r[0]}:{phone}"),
                "source":     "phone",
                "date":       ts,
                "duration_s": int(r[1] or 0),
                "phone":      phone,
                "name":       (r[3] or "").strip() or None,
                "direction":  "outgoing" if r[4] else "incoming",
                "answered":   bool(r[5]),
                "service":    r[6] or "Phone",
            })
        return result
    except Exception as e:
        print(f"[phone] Fehler: {e}")
        return []


# ── WhatsApp calls ─────────────────────────────────────────────────────────────

def read_whatsapp_calls(since_days: int = 90) -> list[dict]:
    if not os.path.exists(WA_CALLS):
        return []
    try:
        db = sqlite3.connect(WA_CALLS)
        db.execute(f"ATTACH DATABASE '{WA_CONTACTS}' AS contacts")
        db.execute(f"ATTACH DATABASE '{WA_CHAT}' AS chat")
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=since_days)
                  - EPOCH).total_seconds()
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
            ts     = _ts(r[0])
            name   = (r[7] or r[9] or "").strip() or None
            phone  = (r[8] or "").strip() or None
            result.append({
                "id":         _uid("whatsapp", f"{r[0]}:{r[10]}"),
                "source":     "whatsapp",
                "date":       ts,
                "duration_s": int(r[1] or 0),
                "phone":      phone,
                "name":       name,
                "direction":  "incoming" if r[3] else "outgoing",
                "answered":   r[2] == 0,  # outcome 0 = connected
                "service":    "WhatsApp",
            })
        return result
    except Exception as e:
        print(f"[whatsapp] Fehler: {e}")
        return []


# ── HTTP Server ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        since_days = int(params.get("since_days", ["90"])[0])

        if parsed.path == "/calls/raw":
            data = read_phone_calls_raw(since_days)
        elif parsed.path == "/calls/phone":
            data = read_phone_calls(since_days)
        elif parsed.path == "/calls/whatsapp":
            data = read_whatsapp_calls(since_days)
        elif parsed.path == "/calls":
            data = read_phone_calls(since_days) + read_whatsapp_calls(since_days)
        elif parsed.path == "/health":
            data = {"status": "ok",
                    "phone_accessible": os.path.exists(PHONE_DB),
                    "whatsapp_accessible": os.path.exists(WA_CALLS)}
        else:
            self.send_response(404)
            self.end_headers()
            return

        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    phone_ok = os.path.exists(PHONE_DB)
    wa_ok    = os.path.exists(WA_CALLS)
    print(f"Calls Bridge startet auf Port {PORT}")
    print(f"  iPhone-Anrufe:   {'✅' if phone_ok else '❌ Full Disk Access fehlt'}")
    print(f"  WhatsApp-Anrufe: {'✅' if wa_ok else '❌ Datei nicht gefunden'}")
    print()
    print(f"  Endpunkte:")
    print(f"    GET http://localhost:{PORT}/calls          (beide Quellen)")
    print(f"    GET http://localhost:{PORT}/calls/phone    (nur iPhone)")
    print(f"    GET http://localhost:{PORT}/calls/whatsapp (nur WhatsApp)")
    print(f"    GET http://localhost:{PORT}/health")
    print()
    server = HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBridge gestoppt.")
