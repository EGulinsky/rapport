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
    is_synced, mark_synced, load_synced_ids, purge_source,
    strip_html, decode_b64,
    build_firm_index, build_contact_domain_index, find_hint_apps,
    process_item, earliest_bewerbung_date,
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
        try:
            creds.refresh(Request())
        except Exception as e:
            err_str = str(e).lower()
            if "invalid_grant" in err_str or "token has been expired" in err_str or "revoked" in err_str:
                # Refresh token is invalid — wipe stored tokens so user is prompted to reconnect
                cfg.access_token_enc  = None
                cfg.refresh_token_enc = None
                cfg.token_expiry      = None
                db.commit()
                raise RuntimeError(
                    "Gmail-Verbindung abgelaufen. Bitte unter Einstellungen → Google neu verbinden."
                ) from e
            raise
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

    # Fetch the authenticated user's email from Google Userinfo and store it
    try:
        import requests as _req
        ui = _req.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=5,
        ).json()
        if ui.get("email"):
            cfg.gmail_email = ui["email"].lower().strip()
    except Exception:
        pass

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
    import time as _time
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []

    # Timing buckets
    t_start = _time.perf_counter()
    t_index = t_list = t_phase1 = t_phase2 = t_ai = 0.0
    n_phase1 = n_phase2 = n_ai = 0          # API call counts

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

        _t0 = _time.perf_counter()
        firm_clause, term_to_apps = build_firm_index(db)
        contact_domain_index = build_contact_domain_index(db)
        t_index = _time.perf_counter() - _t0

        # When firm names are known, use only those — broad keywords fetch too many irrelevant mails
        fallback = (
            "Bewerbung OR Interview OR Gespräch OR Absage OR Einladung OR Angebot "
            "OR recruiting OR Headhunter OR Kandidat "
            "OR application OR position OR candidate OR hiring OR shortlisted "
            "OR \"not moving forward\" OR \"next steps\""
        )
        search_clause = firm_clause if firm_clause else f"({fallback})"
        query = f"after:{after_ts} {search_clause}"

        # Global cutoff: skip mails older than the earliest application submission date
        global_cutoff = earliest_bewerbung_date(db)

        update_progress("gmail", 0, 0, "Nachrichten werden geladen…")
        messages = []
        page_token = None
        _t0 = _time.perf_counter()
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
        t_list = _time.perf_counter() - _t0

        total = len(messages)
        update_progress("gmail", 0, total, f"{total} Nachrichten gefunden")
        synced_ids = load_synced_ids(db, "gmail")
        n_already_synced = sum(1 for m in messages if m["id"] in synced_ids)
        unsynced = [m["id"] for m in messages if m["id"] not in synced_ids]
        skipped += n_already_synced

        from email.utils import parsedate_to_datetime as _parse_date_hdr

        # ── Phase 1: batch-fetch metadata for all unsynced messages ───────────
        # Google API allows up to 100 requests per batch → 133 serial calls → 2 batch calls
        BATCH_META = 100
        meta_results: dict[str, dict] = {}

        def _meta_cb(req_id: str, response: dict | None, exception: Exception | None) -> None:
            if exception is None and response is not None:
                meta_results[req_id] = response
            else:
                errors.append(f"Metadata {req_id}: {exception}")

        _t0 = _time.perf_counter()
        for batch_start in range(0, len(unsynced), BATCH_META):
            chunk = unsynced[batch_start:batch_start + BATCH_META]
            update_progress("gmail", batch_start, total,
                            f"Metadaten {batch_start + 1}–{batch_start + len(chunk)}/{total}")
            batch_req = service.new_batch_http_request(callback=_meta_cb)
            for msg_id in chunk:
                batch_req.add(
                    service.users().messages().get(
                        userId="me", id=msg_id, format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    ),
                    request_id=msg_id,
                )
            batch_req.execute()
            n_phase1 += len(chunk)
        t_phase1 = _time.perf_counter() - _t0

        # ── Filter: date cutoff + quick firm check ─────────────────────────────
        phase2_ids: list[str] = []
        phase2_meta: dict[str, tuple] = {}   # msg_id → (subject, sender, date_hint)

        for msg_id, msg_meta in meta_results.items():
            hdrs = {h["name"].lower(): h["value"] for h in msg_meta["payload"].get("headers", [])}
            subject  = hdrs.get("subject", "(kein Betreff)")
            sender   = hdrs.get("from", "")
            date_str = hdrs.get("date", "")

            date_hint = None
            try:
                date_hint = _parse_date_hdr(date_str).astimezone(timezone.utc)
            except Exception:
                pass

            if global_cutoff and date_hint and date_hint.date() < global_cutoff:
                mark_synced(db, "gmail", msg_id)
                skipped += 1
                continue

            if not find_hint_apps(f"Von: {sender}\nBetreff: {subject}", term_to_apps, contact_domain_index):
                mark_synced(db, "gmail", msg_id)
                skipped += 1
                continue

            phase2_ids.append(msg_id)
            phase2_meta[msg_id] = (subject, sender, date_hint)

        # ── Phase 2: batch-fetch full body for promising messages ──────────────
        # Use smaller batches (50) as full bodies can be large
        BATCH_FULL = 50
        full_results: dict[str, dict] = {}

        def _full_cb(req_id: str, response: dict | None, exception: Exception | None) -> None:
            if exception is None and response is not None:
                full_results[req_id] = response
            else:
                errors.append(f"Volltext {req_id}: {exception}")

        _t0 = _time.perf_counter()
        for batch_start in range(0, len(phase2_ids), BATCH_FULL):
            chunk = phase2_ids[batch_start:batch_start + BATCH_FULL]
            update_progress("gmail", len(unsynced), total,
                            f"Volltext {batch_start + 1}–{batch_start + len(chunk)}/{len(phase2_ids)} Treffer")
            batch_req = service.new_batch_http_request(callback=_full_cb)
            for msg_id in chunk:
                batch_req.add(
                    service.users().messages().get(userId="me", id=msg_id, format="full"),
                    request_id=msg_id,
                )
            batch_req.execute()
            n_phase2 += len(chunk)
        t_phase2 = _time.perf_counter() - _t0

        # ── AI / deterministic processing ──────────────────────────────────────
        for msg_id in phase2_ids:
            msg_full = full_results.get(msg_id)
            if not msg_full:
                continue

            subject, sender, date_hint = phase2_meta[msg_id]
            body = _gmail_body(msg_full["payload"])[:1500]
            raw = f"Von: {sender}\nBetreff: {subject}\n\n{body}"
            hint_apps = find_hint_apps(raw, term_to_apps, contact_domain_index)

            _t0 = _time.perf_counter()
            try:
                ok = await process_item(db, "gmail", msg_id, raw, date_hint, hint_apps=hint_apps)
            except AINotConfigured as e:
                finish_progress("gmail")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("gmail")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [f"AI-Tageslimit: {e}"]}
            except Exception as e:
                errors.append(f"{subject}: {e}")
                continue
            finally:
                t_ai += _time.perf_counter() - _t0
                n_ai += 1

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.gmail_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("gmail")

        t_total = _time.perf_counter() - t_start
        perf = {
            "total_s":         round(t_total, 1),
            "index_s":         round(t_index, 2),
            "list_s":          round(t_list, 2),
            "phase1_s":        round(t_phase1, 1),
            "phase2_s":        round(t_phase2, 1),
            "ai_s":            round(t_ai, 1),
            "n_listed":        total,
            "n_already_synced": n_already_synced,
            "n_phase1_calls":  n_phase1,
            "n_phase2_calls":  n_phase2,
            "n_ai_calls":      n_ai,
            "phase1_avg_ms":   round(t_phase1 / n_phase1 * 1000, 0) if n_phase1 else 0,
            "phase2_avg_ms":   round(t_phase2 / n_phase2 * 1000, 0) if n_phase2 else 0,
            "ai_avg_ms":       round(t_ai / n_ai * 1000, 0) if n_ai else 0,
        }
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors, "perf": perf}
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
        if p := result.get("perf"):
            print(
                f"\n[Gmail Sync] total={p['total_s']}s  "
                f"list={p['list_s']}s  "
                f"phase1={p['phase1_s']}s ({p['n_phase1_calls']} calls, ~{p['phase1_avg_ms']}ms/call)  "
                f"phase2={p['phase2_s']}s ({p['n_phase2_calls']} calls, ~{p['phase2_avg_ms']}ms/call)  "
                f"ai={p['ai_s']}s ({p['n_ai_calls']} calls, ~{p['ai_avg_ms']}ms/call)  "
                f"| listed={p['n_listed']} already_synced={p['n_already_synced']} "
                f"phase1_fetched={p['n_phase1_calls']} phase2_fetched={p['n_phase2_calls']}",
                flush=True,
            )

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
        synced_ids = load_synced_ids(db, "gcal")

        uid_set: set[str] = set()
        for i, ev in enumerate(cal_events):
            if i % 10 == 0:
                update_progress("gcal", i, total, f"Termin {i + 1}/{total}")
            ev_id   = ev.get("id", "")
            if not ev_id:
                continue

            summary = ev.get("summary", "") or ""
            desc    = ev.get("description", "") or ""

            start_raw = ev.get("start", {})
            date_hint = None
            try:
                dt_str = start_raw.get("dateTime") or start_raw.get("date")
                if dt_str:
                    date_hint = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except Exception:
                pass

            uid_set.add(ev_id)

            if ev_id in synced_ids:
                # Check if the event changed (date or title)
                new_datum = date_hint.date() if date_hint else None
                if new_datum:
                    existing = db.query(models.Event).filter_by(source="gcal", external_id=ev_id).first()
                    if existing and (existing.datum != new_datum or existing.titel != summary):
                        existing.datum = new_datum
                        existing.titel = summary
                skipped += 1
                continue

            combined_lower = (summary + " " + desc).lower()
            has_keyword = any(kw in combined_lower for kw in JOB_KEYWORDS)
            has_firm    = any(ft in combined_lower for ft in firm_terms_lower)
            if not has_keyword and not has_firm:
                skipped += 1
                continue

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
                ok = await process_item(db, "gcal", ev_id, raw, date_hint, hint_apps=hint_apps)
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

        # Remove timeline events whose Google Calendar entries no longer exist within the sync window
        if uid_set:
            window_start = (now - timedelta(days=180)).date()
            window_end   = (now + timedelta(days=90)).date()
            orphaned = (
                db.query(models.Event)
                .filter(
                    models.Event.source == "gcal",
                    models.Event.external_id.isnot(None),
                    models.Event.datum >= window_start,
                    models.Event.datum <= window_end,
                )
                .all()
            )
            deleted_count = 0
            for orphan in orphaned:
                if orphan.external_id not in uid_set:
                    db.query(models.SyncedItem).filter_by(source="gcal", external_id=orphan.external_id).delete()
                    db.delete(orphan)
                    deleted_count += 1
            if deleted_count:
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
