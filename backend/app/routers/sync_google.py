"""
Google OAuth 2.0 + Gmail + Calendar sync.

Setup for users:
  1. Google Cloud Console → APIs & Services → Credentials
  2. Create OAuth 2.0 Client ID (type: Web application)
  3. Authorized redirect URI: http://localhost:8000/api/sync/google/callback
  4. Enter Client ID + Secret in JobTracker settings
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models, schemas
from app.ai.provider import encrypt_api_key, decrypt_api_key, AINotConfigured, AIRateLimited
from app.routers.sync_common import (
    is_synced, mark_synced, purge_source,
    strip_html, decode_b64,
    build_firm_index, build_contact_domain_index, find_hint_apps,
    process_item,
    init_progress, update_progress, finish_progress, get_all_progress,
    set_batch_result, get_batch_results,
)

router = APIRouter(prefix="/api/sync/google", tags=["sync"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
REDIRECT_URI = "http://localhost:8000/api/sync/google/callback"

# Legacy aliases so sync_icloud.py imports keep working during any transition
_is_synced = is_synced
_mark_synced = mark_synced
_purge_source = purge_source
_build_firm_index = build_firm_index
_build_contact_domain_index = build_contact_domain_index
_find_hint_apps = find_hint_apps
_process_item = process_item
_strip_html = strip_html


# ── Google credential helpers ─────────────────────────────────────────────────

def _get_cfg(db: Session) -> Optional[models.GoogleSync]:
    return db.query(models.GoogleSync).first()


def _build_credentials(cfg: models.GoogleSync):
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=decrypt_api_key(cfg.access_token_enc) if cfg.access_token_enc else None,
        refresh_token=decrypt_api_key(cfg.refresh_token_enc) if cfg.refresh_token_enc else None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg.client_id,
        client_secret=decrypt_api_key(cfg.client_secret_enc),
        scopes=SCOPES,
    )
    if cfg.token_expiry:
        creds.expiry = cfg.token_expiry.replace(tzinfo=None)
    return creds


def _refresh_if_needed(cfg: models.GoogleSync, db: Session):
    from google.auth.transport.requests import Request

    creds = _build_credentials(cfg)
    if creds.expired or not creds.token:
        creds.refresh(Request())
        cfg.access_token_enc = encrypt_api_key(creds.token)
        if creds.expiry:
            cfg.token_expiry = creds.expiry.replace(tzinfo=timezone.utc)
        db.commit()
    return creds


def _gmail_body(payload: dict) -> str:
    """Recursively extract plain text from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return decode_b64(data) if data else ""
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        return strip_html(decode_b64(data)) if data else ""
    for part in payload.get("parts", []):
        text = _gmail_body(part)
        if text:
            return text
    return ""


# ── OAuth endpoints ───────────────────────────────────────────────────────────

@router.get("/status", response_model=schemas.GoogleSyncStatus)
def google_status(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        return schemas.GoogleSyncStatus(connected=False)
    return schemas.GoogleSyncStatus(
        connected=bool(cfg.refresh_token_enc),
        client_id=cfg.client_id,
        gmail_last_sync=cfg.gmail_last_sync,
        gcal_last_sync=cfg.gcal_last_sync,
    )


@router.post("/credentials", response_model=schemas.GoogleSyncStatus)
def save_credentials(payload: schemas.GoogleCredentials, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        cfg = models.GoogleSync(
            client_id=payload.client_id,
            client_secret_enc=encrypt_api_key(payload.client_secret),
        )
        db.add(cfg)
    else:
        cfg.client_id = payload.client_id
        cfg.client_secret_enc = encrypt_api_key(payload.client_secret)
    db.commit()
    db.refresh(cfg)
    return schemas.GoogleSyncStatus(
        connected=bool(cfg.refresh_token_enc),
        client_id=cfg.client_id,
    )


@router.get("/auth")
def google_auth_url(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Erst Google-Credentials speichern.")
    from google_auth_oauthlib.flow import Flow

    state = secrets.token_urlsafe(16)
    cfg.oauth_state = state
    db.commit()

    client_config = {
        "web": {
            "client_id": cfg.client_id,
            "client_secret": decrypt_api_key(cfg.client_secret_enc),
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return {"url": auth_url}


@router.get("/callback", response_class=HTMLResponse)
def google_callback(code: str, state: str = "", db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        return HTMLResponse("<p>Keine Konfiguration gefunden.</p>", status_code=400)

    if state and cfg.oauth_state and state != cfg.oauth_state:
        return HTMLResponse("<p>Ungültiger OAuth-State.</p>", status_code=400)

    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": cfg.client_id,
            "client_secret": decrypt_api_key(cfg.client_secret_enc),
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=code)
    creds = flow.credentials

    cfg.access_token_enc  = encrypt_api_key(creds.token)
    cfg.refresh_token_enc = encrypt_api_key(creds.refresh_token) if creds.refresh_token else None
    cfg.token_expiry      = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None
    cfg.oauth_state       = None
    db.commit()

    return HTMLResponse("""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f8fafc}
.box{text-align:center;padding:2rem;border-radius:1rem;background:white;box-shadow:0 4px 24px rgba(0,0,0,.08)}
.check{font-size:3rem;margin-bottom:1rem}</style></head>
<body><div class="box"><div class="check">✅</div>
<h2 style="margin:0 0 .5rem;color:#111827">Google verbunden!</h2>
<p style="color:#6b7280;margin:0">Dieses Fenster schließt sich automatisch…</p></div>
<script>
  if(window.opener){window.opener.postMessage({type:'google_connected'},'*')}
  setTimeout(()=>window.close(),1500)
</script></body></html>
""")


@router.delete("", status_code=204)
def google_disconnect(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.access_token_enc  = None
        cfg.refresh_token_enc = None
        cfg.token_expiry      = None
        db.commit()


# ── Gmail Sync ────────────────────────────────────────────────────────────────

@router.get("/progress")
def sync_progress_all():
    return get_all_progress()


@router.get("/batch/results")
def batch_results():
    return get_batch_results()


# ── Gmail background task ─────────────────────────────────────────────────────

async def _do_gmail() -> dict:
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.GoogleSync).first()
        if not cfg or not cfg.refresh_token_enc:
            finish_progress("gmail")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Nicht mit Google verbunden."]}

        from googleapiclient.discovery import build
        creds = _refresh_if_needed(cfg, db)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        since = cfg.gmail_last_sync or (datetime.now(timezone.utc) - timedelta(days=90))
        after_ts = int(since.timestamp())

        firm_clause, term_to_apps = build_firm_index(db)
        contact_domain_index = build_contact_domain_index(db)

        fallback = (
            "Bewerbung OR Interview OR Gespräch OR Absage OR Einladung OR Angebot "
            "OR recruiting OR Headhunter OR Kandidat "
            "OR application OR position OR candidate OR hiring OR shortlisted "
            "OR \"not moving forward\" OR \"next steps\""
        )
        search_clause = f"({firm_clause} OR {fallback})" if firm_clause else f"({fallback})"
        query = f"after:{after_ts} {search_clause}"

        update_progress("gmail", 0, 0, "Nachrichten werden geladen…")
        messages = []
        page_token = None
        try:
            while True:
                kwargs: dict = {"userId": "me", "q": query, "maxResults": 500}
                if page_token:
                    kwargs["pageToken"] = page_token
                resp = service.users().messages().list(**kwargs).execute()
                messages.extend(resp.get("messages", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception as e:
            finish_progress("gmail")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"Gmail API Fehler: {e}"]}

        total = len(messages)
        update_progress("gmail", 0, total, f"{total} Nachrichten gefunden")

        for i, msg_ref in enumerate(messages):
            update_progress("gmail", i, total, f"E-Mail {i + 1}/{total}")
            msg_id = msg_ref["id"]
            if is_synced(db, "gmail", msg_id):
                skipped += 1
                continue
            try:
                msg = service.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()
            except Exception as e:
                errors.append(f"Nachricht {msg_id}: {e}")
                continue

            headers  = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
            subject  = headers.get("subject", "(kein Betreff)")
            sender   = headers.get("from", "")
            date_str = headers.get("date", "")
            body     = _gmail_body(msg["payload"])[:1500]

            date_hint = None
            try:
                from email.utils import parsedate_to_datetime
                date_hint = parsedate_to_datetime(date_str).astimezone(timezone.utc)
            except Exception:
                pass

            raw = f"Von: {sender}\nBetreff: {subject}\n\n{body}"
            hint_apps = find_hint_apps(raw, term_to_apps, contact_domain_index)

            try:
                ok = await process_item(db, "gmail", msg_id, raw, date_hint, hint_apps=hint_apps or None)
            except AINotConfigured as e:
                finish_progress("gmail")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("gmail")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [f"AI-Tageslimit: {e}"]}
            except Exception as e:
                errors.append(f"{subject}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.gmail_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("gmail")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("gmail")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/gmail/reset", status_code=204)
def reset_gmail_sync(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.gmail_last_sync = None
        purge_source(db, "gmail")
        db.commit()


@router.post("/gmail", response_model=schemas.SyncResult)
async def sync_gmail(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        raise HTTPException(400, "Nicht mit Google verbunden.")

    set_batch_result("gmail", {"done": False})
    init_progress("gmail", "Gmail", "Starte…")

    async def _bg():
        result = await _do_gmail()
        set_batch_result("gmail", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


# ── Google Calendar background task ──────────────────────────────────────────

async def _do_gcal() -> dict:
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.GoogleSync).first()
        if not cfg or not cfg.refresh_token_enc:
            finish_progress("gcal")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Nicht mit Google verbunden."]}

        from googleapiclient.discovery import build
        creds = _refresh_if_needed(cfg, db)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=180)).isoformat()
        time_max = (now + timedelta(days=90)).isoformat()

        update_progress("gcal", 0, 0, "Termine werden geladen…")
        try:
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=200,
            ).execute()
        except Exception as e:
            finish_progress("gcal")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"Calendar API Fehler: {e}"]}

        cal_events = events_result.get("items", [])
        _, term_to_apps = build_firm_index(db)
        contact_domain_index = build_contact_domain_index(db)

        JOB_KEYWORDS = {
            "interview", "gespräch", "vorstellungsgespräch", "assessment",
            "vorstellung", "bewerbung", "hr", "recruiting", "kennenlernen",
            "onboarding", "probearbeitstag",
        }
        firm_terms_lower = {t.lower() for t in term_to_apps}

        total = len(cal_events)
        update_progress("gcal", 0, total, f"{total} Termine gefunden")

        for i, ev in enumerate(cal_events):
            update_progress("gcal", i, total, f"Termin {i + 1}/{total}")
            ev_id   = ev.get("id", "")
            summary = ev.get("summary", "") or ""
            desc    = ev.get("description", "") or ""
            combined_lower = (summary + " " + desc).lower()

            has_keyword = any(kw in combined_lower for kw in JOB_KEYWORDS)
            has_firm    = any(ft in combined_lower for ft in firm_terms_lower)
            if not has_keyword and not has_firm:
                skipped += 1
                continue

            if is_synced(db, "gcal", ev_id):
                skipped += 1
                continue

            start_raw = ev.get("start", {})
            date_hint = None
            try:
                dt_str = start_raw.get("dateTime") or start_raw.get("date")
                if dt_str:
                    date_hint = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except Exception:
                pass

            location  = ev.get("location", "")
            organizer = ev.get("organizer", {})
            attendees = ev.get("attendees", [])
            participants = []
            if organizer.get("email"):
                label = organizer.get("displayName", "")
                participants.append(f"{label} <{organizer['email']}>" if label else organizer["email"])
            for a in attendees[:8]:
                if a.get("email"):
                    label = a.get("displayName", "")
                    participants.append(f"{label} <{a['email']}>" if label else a["email"])

            raw = (
                f"Titel: {summary}\n"
                f"Ort: {location}\n"
                + (f"Teilnehmer: {', '.join(participants)}\n" if participants else "")
                + f"Beschreibung: {strip_html(desc)[:800]}"
            )

            hint_apps = find_hint_apps(raw, term_to_apps, contact_domain_index)

            try:
                ok = await process_item(db, "gcal", ev_id, raw, date_hint, hint_apps=hint_apps or None)
            except AINotConfigured as e:
                finish_progress("gcal")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("gcal")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [f"AI-Tageslimit: {e}"]}
            except Exception as e:
                errors.append(f"{summary or ev_id}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.gcal_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("gcal")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("gcal")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/calendar/reset", status_code=204)
def reset_calendar_sync(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.gcal_last_sync = None
        purge_source(db, "gcal")
        db.commit()


@router.get("/calendar/debug")
def debug_gcal_events(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        raise HTTPException(400, "Nicht mit Google verbunden.")
    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    now = datetime.now(timezone.utc)
    events_result = service.events().list(
        calendarId="primary",
        timeMin=(now - timedelta(days=30)).isoformat(),
        timeMax=(now + timedelta(days=90)).isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=200,
    ).execute()
    _, term_to_apps = build_firm_index(db)
    firm_terms_lower = {t.lower() for t in term_to_apps}
    JOB_KEYWORDS = {"interview","gespräch","vorstellungsgespräch","assessment","vorstellung","bewerbung","hr","recruiting","kennenlernen","onboarding","probearbeitstag"}
    results = []
    for ev in events_result.get("items", []):
        summary = ev.get("summary", "") or ""
        desc = ev.get("description", "") or ""
        combined_lower = (summary + " " + desc).lower()
        has_kw = any(kw in combined_lower for kw in JOB_KEYWORDS)
        matched_firms = [ft for ft in firm_terms_lower if ft in combined_lower]
        start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
        results.append({"summary": summary, "start": start[:10], "has_keyword": has_kw, "matched_firms": matched_firms, "synced": is_synced(db, "gcal", ev.get("id",""))})
    return sorted(results, key=lambda x: x["start"])


@router.post("/calendar", response_model=schemas.SyncResult)
async def sync_calendar(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        raise HTTPException(400, "Nicht mit Google verbunden.")

    set_batch_result("gcal", {"done": False})
    init_progress("gcal", "Google Calendar", "Starte…")

    async def _bg():
        result = await _do_gcal()
        set_batch_result("gcal", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])
