"""
Google OAuth 2.0 + Gmail + Calendar sync.

Setup for users:
  1. Google Cloud Console → APIs & Services → Credentials
  2. Create OAuth 2.0 Client ID (type: Web application)
  3. Authorized redirect URI: http://localhost:8000/api/sync/google/callback
  4. Enter Client ID + Secret in rapport settings
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal, set_session_user
from app import models, schemas
from app.i18n_strings import resolve_ui_language, t
from app.ai.provider import encrypt_api_key, decrypt_api_key, AINotConfigured, AIRateLimited
from app.auth.dependencies import get_current_user
from app.routers.sync_common import (
    is_synced, mark_synced, load_synced_ids, purge_source,
    strip_html, decode_b64,
    build_firm_index, build_contact_domain_index, find_hint_apps,
    build_contact_email_index, find_apps_from_addresses, find_matching_apps,
    process_item, earliest_bewerbung_date, upsert_contact_from_sender,
    init_progress, update_progress, finish_progress, get_all_progress,
    set_batch_result, get_batch_results,
)

router = APIRouter(prefix="/api/sync/google", tags=["sync"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
REDIRECT_URI = "http://localhost:8000/api/sync/google/callback"

# Legacy aliases kept for any external imports
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
def google_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
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
def save_credentials(
    payload: schemas.GoogleCredentials,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg:
        cfg = models.GoogleSync(
            client_id=payload.client_id,
            client_secret_enc=encrypt_api_key(payload.client_secret),
            user_id=current_user.id,
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
def google_auth_url(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
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
    # Bewusst OHNE current_user-Dependency: dies ist ein Redirect direkt von
    # Googles OAuth-Server im Browser, kann also keinen Authorization-Header
    # mitschicken. Wie beim Hintergrund-Sync-Loop pragmatisch auf das
    # erste/einzige registrierte Konto gescoped.
    from app.database import get_first_user_id
    user_id = get_first_user_id(db)
    if user_id is not None:
        set_session_user(db, user_id)
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
def google_disconnect(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.access_token_enc  = None
        cfg.refresh_token_enc = None
        cfg.token_expiry      = None
        db.commit()


# ── Gmail Sync ────────────────────────────────────────────────────────────────

@router.get("/progress")
def sync_progress_all(current_user: models.User = Depends(get_current_user)):
    return get_all_progress()


@router.get("/batch/results")
def batch_results(current_user: models.User = Depends(get_current_user)):
    return get_batch_results()


# ── Gmail background task ─────────────────────────────────────────────────────

async def _do_gmail(user_id: int) -> dict:
    import time as _time
    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []

    # Timing buckets
    t_start = _time.perf_counter()
    t_index = t_list = t_phase1 = t_phase2 = t_ai = 0.0
    n_phase1 = n_phase2 = n_ai = 0          # API call counts

    try:
        cfg = db.query(models.GoogleSync).first()
        if not cfg or not cfg.refresh_token_enc:
            finish_progress("gmail", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("not_connected_google", lang)]}

        from googleapiclient.discovery import build
        creds = _refresh_if_needed(cfg, db)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        since = cfg.gmail_last_sync or (datetime.now(timezone.utc) - timedelta(days=90))
        after_ts = int(since.timestamp())

        _t0 = _time.perf_counter()
        contact_domain_index = build_contact_domain_index(db)
        contact_email_index  = build_contact_email_index(db)
        firm_clause, term_to_apps = build_firm_index(db)
        t_index = _time.perf_counter() - _t0

        # Query combines known contact domains (from:/to:, precise) with every
        # active application's company-name (+ variants) and role as quoted
        # phrase search — Gmail matches quoted phrases across subject+body.
        # Without the phrase clause, a mail from a sender with no saved
        # contact yet (but mentioning the company/role by name) was never
        # even fetched, let alone matched — this was Gmail's gap relative to
        # iCloud Mail's search, which always fetches broadly and only
        # filters client-side (see _do_icloud_mail below).
        domain_parts = [f"(from:{d} OR to:{d})" for d in contact_domain_index]
        clauses = domain_parts + ([firm_clause] if firm_clause else [])
        if not clauses:
            # No contact domains and no active applications to search for —
            # nothing to attribute mail to yet, and an unqualified `after:`
            # query would list the entire mailbox since the cutoff date.
            finish_progress("gmail", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": []}
        query = f"after:{after_ts} ({' OR '.join(clauses)})"

        # Global cutoff: skip mails older than the earliest application submission date
        global_cutoff = earliest_bewerbung_date(db)

        update_progress("gmail", 0, 0, t("loading_messages", lang))
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
            finish_progress("gmail", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("gmail_api_error", lang, error=e)]}
        t_list = _time.perf_counter() - _t0

        total = len(messages)
        update_progress("gmail", 0, total, t("messages_found", lang, count=total))
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
                            t("metadata_progress", lang, from_=batch_start + 1, to=batch_start + len(chunk), total=total))
            batch_req = service.new_batch_http_request(callback=_meta_cb)
            for msg_id in chunk:
                batch_req.add(
                    service.users().messages().get(
                        userId="me", id=msg_id, format="metadata",
                        metadataHeaders=["From", "To", "Cc", "Subject", "Date"],
                    ),
                    request_id=msg_id,
                )
            batch_req.execute()
            n_phase1 += len(chunk)
        t_phase1 = _time.perf_counter() - _t0

        # ── Filter: date cutoff + app matching on headers+subject (cheap) ──────
        # Same combined matcher iCloud Mail uses (find_matching_apps: address/
        # domain + company-name/role text) — subject text is available here,
        # the body isn't yet, so this pass can still miss a body-only company/
        # role mention. Re-checked with the full body once fetched (phase 2)
        # below, same as iCloud Mail already does.
        phase2_ids: list[str] = []
        phase2_meta: dict[str, tuple] = {}   # msg_id → (subject, sender, date_hint, hint_apps)

        for msg_id, msg_meta in meta_results.items():
            hdrs = {h["name"].lower(): h["value"] for h in msg_meta["payload"].get("headers", [])}
            subject  = hdrs.get("subject", "(kein Betreff)")
            sender   = hdrs.get("from", "")
            to_cc    = hdrs.get("to", "") + "," + hdrs.get("cc", "")
            date_str = hdrs.get("date", "")

            date_hint = None
            try:
                date_hint = _parse_date_hdr(date_str).astimezone(timezone.utc)
            except Exception:
                pass

            if global_cutoff and date_hint and date_hint.date() < global_cutoff:
                mark_synced(db, "gmail", msg_id, user_id)
                skipped += 1
                continue

            quick_text = f"Von: {sender}\nBetreff: {subject}"
            hint_apps = find_matching_apps(sender, to_cc, quick_text, contact_email_index, contact_domain_index, term_to_apps)
            if not hint_apps:
                mark_synced(db, "gmail", msg_id, user_id)
                skipped += 1
                continue

            phase2_ids.append(msg_id)
            phase2_meta[msg_id] = (subject, sender, to_cc, date_hint, hint_apps)

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
                            t("fulltext_progress", lang, from_=batch_start + 1, to=batch_start + len(chunk), total=len(phase2_ids)))
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

            subject, sender, to_cc, date_hint, _phase1_hint_apps = phase2_meta[msg_id]
            body = _gmail_body(msg_full["payload"])[:1500]
            # "An:" (To+Cc, cleaned of the stray comma the "to,cc" concatenation
            # above leaves when either side is empty) lets sync_common.py tell
            # sent mail from received mail and show the actual recipient
            # instead of the account owner's own name for sent mail.
            to_recipients = ", ".join(p.strip() for p in to_cc.split(",") if p.strip())
            raw = f"Von: {sender}\nAn: {to_recipients}\nBetreff: {subject}\n\n{body}"
            # Re-check with the full body — always a superset of the phase-1
            # (subject-only) result, since raw only adds text; can surface a
            # company/role mentioned only in the body, not the subject.
            hint_apps = find_matching_apps(sender, to_cc, raw, contact_email_index, contact_domain_index, term_to_apps)

            _t0 = _time.perf_counter()
            try:
                ok = await process_item(db, "gmail", msg_id, raw, date_hint, hint_apps=hint_apps, user_id=user_id)
            except AINotConfigured as e:
                finish_progress("gmail", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("gmail", lang=lang)
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
        finish_progress("gmail", lang=lang)

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
        finish_progress("gmail", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/gmail/reset", status_code=204)
def reset_gmail_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.gmail_last_sync = None
        purge_source(db, "gmail", current_user.id)
        db.commit()


def backfill_gmail_autor(db: Session, user_id: int) -> dict:
    """One-time repair for Gmail events created before v4.6.4 added
    Event.autor population. Event.autor is what the Mails tab (ContactModal.tsx,
    via GET /api/contacts/{id}/events in contacts.py) matches back to a
    contact by email address -- events from before that feature shipped have
    autor=NULL and so are invisible there, even though the contact and
    application match correctly otherwise. Re-fetches just the From header
    for each affected message via its stored external_id (the Gmail message
    ID), using the same cheap metadata-only batch call _do_gmail() already
    uses for its own Phase 1 — no need to re-fetch the full message body.
    Never touches an event that already has autor set, from a normal sync or
    a manual edit."""
    cfg = db.query(models.GoogleSync).first()
    if not cfg or not cfg.refresh_token_enc:
        return {"updated": 0, "errors": ["Nicht mit Google verbunden."]}

    events = db.query(models.Event).filter(
        models.Event.source == "gmail",
        models.Event.autor.is_(None),
        models.Event.external_id.isnot(None),
        models.Event.user_id == user_id,
    ).all()
    if not events:
        return {"updated": 0, "errors": []}

    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    by_id: dict[str, models.Event] = {e.external_id: e for e in events}
    meta_results: dict[str, dict] = {}
    errors: dict[str, Exception] = {}

    def _cb(request_id: str, response: dict | None, exception: Exception | None) -> None:
        if exception is None and response is not None:
            meta_results[request_id] = response
            errors.pop(request_id, None)
        else:
            errors[request_id] = exception

    # A personal Gmail account's concurrent-request limit is much lower than
    # the 100-per-batch chunk size _do_gmail() uses for its own Phase 1 (fine
    # there since it's spaced out by the full-body Phase 2 in between) --
    # blasting 100 sub-requests back-to-back here reliably triggered
    # "Too many concurrent requests for user" (429) past the first chunk or
    # so. Smaller chunks + a short pause + a few retries on 429 specifically
    # clears it without needing to fall back to one request at a time.
    BATCH = 15
    MAX_ATTEMPTS = 4
    ids = list(by_id.keys())

    for attempt in range(MAX_ATTEMPTS):
        pending = ids if attempt == 0 else list(errors.keys())
        if not pending:
            break
        for start in range(0, len(pending), BATCH):
            chunk = pending[start:start + BATCH]
            batch_req = service.new_batch_http_request(callback=_cb)
            for msg_id in chunk:
                batch_req.add(
                    service.users().messages().get(
                        userId="me", id=msg_id, format="metadata", metadataHeaders=["From"],
                    ),
                    request_id=msg_id,
                )
            batch_req.execute()
            time.sleep(1)
        if errors:
            time.sleep(2 ** attempt)

    errors_out = [f"{msg_id}: {exc}" for msg_id, exc in errors.items()]

    updated = 0
    for msg_id, meta in meta_results.items():
        hdrs = {h["name"].lower(): h["value"] for h in meta.get("payload", {}).get("headers", [])}
        sender = hdrs.get("from")
        if not sender:
            continue
        event = by_id[msg_id]
        event.autor = sender
        updated += 1
        app = db.query(models.Application).get(event.application_id)
        if app:
            upsert_contact_from_sender(
                db, sender, app_id=event.application_id, firma=app.firma,
                is_headhunter=app.is_headhunter, event_date=event.datum, user_id=user_id,
            )

    db.commit()
    return {"updated": updated, "errors": errors_out}


@router.post("/gmail/backfill-autor")
def gmail_backfill_autor(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return backfill_gmail_autor(db, current_user.id)


@router.post("/gmail", response_model=schemas.SyncResult)
async def sync_gmail(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        raise HTTPException(400, "Nicht mit Google verbunden.")

    set_batch_result("gmail", {"done": False})
    init_progress("gmail", "Gmail", lang=current_user.ui_language)

    async def _bg():
        result = await _do_gmail(current_user.id)
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

async def _do_gcal(user_id: int) -> dict:
    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.GoogleSync).first()
        if not cfg or not cfg.refresh_token_enc:
            finish_progress("gcal", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("not_connected_google", lang)]}

        from googleapiclient.discovery import build
        creds = _refresh_if_needed(cfg, db)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=180)).isoformat()
        time_max = (now + timedelta(days=90)).isoformat()

        update_progress("gcal", 0, 0, t("loading_appointments", lang))
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
            finish_progress("gcal", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("calendar_api_error", lang, error=e)]}

        cal_events = events_result.get("items", [])
        contact_domain_index = build_contact_domain_index(db)
        contact_email_index  = build_contact_email_index(db)
        _, term_to_apps = build_firm_index(db)

        total = len(cal_events)
        update_progress("gcal", 0, total, t("appointments_found", lang, count=total))
        synced_ids = load_synced_ids(db, "gcal")

        uid_set: set[str] = set()
        for i, ev in enumerate(cal_events):
            if i % 10 == 0:
                update_progress("gcal", i, total, t("appointment_progress", lang, current=i + 1, total=total))
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
            html_link = ev.get("htmlLink")

            if ev_id in synced_ids:
                # Check if the event changed (date or title), or is still
                # missing its deep link from before v4.6.18 added external_url
                new_datum = date_hint.date() if date_hint else None
                existing = db.query(models.Event).filter_by(source="gcal", external_id=ev_id).first()
                if existing:
                    if new_datum and (existing.datum != new_datum or existing.titel != summary):
                        existing.datum = new_datum
                        existing.titel = summary
                    if html_link and not existing.external_url:
                        existing.external_url = html_link
                skipped += 1
                continue

            organizer = ev.get("organizer") or {}
            attendees = ev.get("attendees") or []
            org_email = organizer.get("email", "")
            att_emails = ",".join(a.get("email", "") for a in attendees[:20])
            # Combined address + company-name/role-text matcher (same
            # find_matching_apps() Gmail/iCloud Mail sync already use) --
            # address-only matching (the previous behavior here) misses
            # self-organized events with no attendees at all, e.g. Gmail's
            # own "detected event" feature auto-adding an interview
            # invitation straight from an email to the calendar: organizer
            # is the account's own address, attendees is empty, so only the
            # summary/description text (which does name the company) can
            # ever match it to an application.
            hint_apps = find_matching_apps(
                org_email, att_emails, f"{summary} {desc}",
                contact_email_index, contact_domain_index, term_to_apps,
            )
            if not hint_apps:
                skipped += 1
                continue

            location = ev.get("location", "")
            participants = []
            if org_email:
                label = organizer.get("displayName", "")
                participants.append(f"{label} <{org_email}>" if label else org_email)
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

            try:
                ok = await process_item(db, "gcal", ev_id, raw, date_hint, hint_apps=hint_apps, user_id=user_id, external_url=html_link)
            except AINotConfigured as e:
                finish_progress("gcal", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("gcal", lang=lang)
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
                    db.query(models.SyncedItem).filter_by(
                        source="gcal", external_id=orphan.external_id, user_id=user_id
                    ).delete()
                    db.delete(orphan)
                    deleted_count += 1
            if deleted_count:
                db.commit()

        cfg.gcal_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("gcal", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("gcal", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/calendar/reset", status_code=204)
def reset_calendar_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.gcal_last_sync = None
        purge_source(db, "gcal", current_user.id)
        db.commit()


def backfill_gcal_autor(db: Session, user_id: int) -> dict:
    """One-time repair for Google Calendar events created before v4.6.14
    added Event.autor population for gcal. Analogous to
    backfill_gmail_autor() in the same file: re-fetches just the organizer/
    attendees for each affected event via its stored external_id (the
    Google Calendar event/instance ID), using the same batched-with-retry
    approach to stay under the API's per-user concurrent-request limit.

    Unlike mail's autor, this never triggers contact auto-creation (see the
    autor comment in sync_common.py's _save_deterministic_event()) -- it
    only lets an ALREADY-existing contact's Calendar tab match this event
    by email, exactly matching what a normal gcal sync does for new events."""
    cfg = db.query(models.GoogleSync).first()
    if not cfg or not cfg.refresh_token_enc:
        return {"updated": 0, "errors": ["Nicht mit Google verbunden."]}

    events = db.query(models.Event).filter(
        models.Event.source == "gcal",
        models.Event.autor.is_(None),
        models.Event.external_id.isnot(None),
        models.Event.user_id == user_id,
    ).all()
    if not events:
        return {"updated": 0, "errors": []}

    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    by_id: dict[str, models.Event] = {e.external_id: e for e in events}
    results: dict[str, dict] = {}
    errors: dict[str, Exception] = {}

    def _cb(request_id: str, response: dict | None, exception: Exception | None) -> None:
        if exception is None and response is not None:
            results[request_id] = response
            errors.pop(request_id, None)
        else:
            errors[request_id] = exception

    BATCH = 15
    MAX_ATTEMPTS = 4
    ids = list(by_id.keys())

    for attempt in range(MAX_ATTEMPTS):
        pending = ids if attempt == 0 else list(errors.keys())
        if not pending:
            break
        for start in range(0, len(pending), BATCH):
            chunk = pending[start:start + BATCH]
            batch_req = service.new_batch_http_request(callback=_cb)
            for ev_id in chunk:
                batch_req.add(
                    service.events().get(calendarId="primary", eventId=ev_id),
                    request_id=ev_id,
                )
            batch_req.execute()
            time.sleep(1)
        if errors:
            time.sleep(2 ** attempt)

    errors_out = [f"{ev_id}: {exc}" for ev_id, exc in errors.items()]

    updated = 0
    for ev_id, ev_data in results.items():
        organizer = ev_data.get("organizer") or {}
        attendees = ev_data.get("attendees") or []
        participants: list[str] = []
        org_email = organizer.get("email", "")
        if org_email:
            label = organizer.get("displayName", "")
            participants.append(f"{label} <{org_email}>" if label else org_email)
        for a in attendees[:8]:
            if a.get("email"):
                label = a.get("displayName", "")
                participants.append(f"{label} <{a['email']}>" if label else a["email"])
        if not participants:
            continue
        by_id[ev_id].autor = ", ".join(participants)
        updated += 1

    db.commit()
    return {"updated": updated, "errors": errors_out}


@router.post("/calendar/backfill-autor")
def gcal_backfill_autor(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return backfill_gcal_autor(db, current_user.id)


def backfill_gcal_external_url(db: Session, user_id: int) -> dict:
    """One-time repair for Google Calendar events created before v4.6.18
    added Event.external_url -- their timeline "open in app" link was
    reconstructed client-side from external_id alone (base64 of just the
    event ID), which Google Calendar's "eventedit" deep link format doesn't
    actually accept (it also needs the calendar ID baked into the same
    base64 blob) -- so every such link was broken. Re-fetches each affected
    event's own htmlLink (Google's ready-made, correctly-encoded link) via
    its stored external_id, using the same batched-with-retry approach as
    backfill_gcal_autor() in this file."""
    cfg = db.query(models.GoogleSync).first()
    if not cfg or not cfg.refresh_token_enc:
        return {"updated": 0, "errors": ["Nicht mit Google verbunden."]}

    events = db.query(models.Event).filter(
        models.Event.source == "gcal",
        models.Event.external_url.is_(None),
        models.Event.external_id.isnot(None),
        models.Event.user_id == user_id,
    ).all()
    if not events:
        return {"updated": 0, "errors": []}

    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    by_id: dict[str, models.Event] = {e.external_id: e for e in events}
    results: dict[str, dict] = {}
    errors: dict[str, Exception] = {}

    def _cb(request_id: str, response: dict | None, exception: Exception | None) -> None:
        if exception is None and response is not None:
            results[request_id] = response
            errors.pop(request_id, None)
        else:
            errors[request_id] = exception

    BATCH = 15
    MAX_ATTEMPTS = 4
    ids = list(by_id.keys())

    for attempt in range(MAX_ATTEMPTS):
        pending = ids if attempt == 0 else list(errors.keys())
        if not pending:
            break
        for start in range(0, len(pending), BATCH):
            chunk = pending[start:start + BATCH]
            batch_req = service.new_batch_http_request(callback=_cb)
            for ev_id in chunk:
                batch_req.add(
                    service.events().get(calendarId="primary", eventId=ev_id),
                    request_id=ev_id,
                )
            batch_req.execute()
            time.sleep(1)
        if errors:
            time.sleep(2 ** attempt)

    errors_out = [f"{ev_id}: {exc}" for ev_id, exc in errors.items()]

    updated = 0
    for ev_id, ev_data in results.items():
        html_link = ev_data.get("htmlLink")
        if not html_link:
            continue
        by_id[ev_id].external_url = html_link
        updated += 1

    db.commit()
    return {"updated": updated, "errors": errors_out}


@router.post("/calendar/backfill-external-url")
def gcal_backfill_external_url(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return backfill_gcal_external_url(db, current_user.id)


@router.get("/calendar/debug")
def debug_gcal_events(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
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
    contact_domain_index = build_contact_domain_index(db)
    contact_email_index  = build_contact_email_index(db)
    results = []
    for ev in events_result.get("items", []):
        summary = ev.get("summary", "") or ""
        start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", "")
        org_email  = ((ev.get("organizer") or {}).get("email") or "")
        att_emails = ",".join((a.get("email") or "") for a in (ev.get("attendees") or []))
        matched = find_apps_from_addresses(org_email, att_emails, contact_email_index, contact_domain_index)
        matched_firms = list({a["firma"] for a in matched})
        results.append({"summary": summary, "start": start[:10], "matched_firms": matched_firms, "synced": is_synced(db, "gcal", ev.get("id",""))})
    return sorted(results, key=lambda x: x["start"])


@router.post("/calendar", response_model=schemas.SyncResult)
async def sync_calendar(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        raise HTTPException(400, "Nicht mit Google verbunden.")

    set_batch_result("gcal", {"done": False})
    init_progress("gcal", "Google Calendar", lang=current_user.ui_language)

    async def _bg():
        result = await _do_gcal(current_user.id)
        set_batch_result("gcal", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])
