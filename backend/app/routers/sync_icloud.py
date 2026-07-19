"""
iCloud sync via standard protocols.

Requires an App-Specific Password:
  Apple ID → Security → App-Specific Passwords → Generate

Protocols:
  Mail      – IMAP  imap.mail.me.com:993
  Calendar  – CalDAV https://caldav.icloud.com
  Reminders – CalDAV VTODO (same server)
  Contacts  – CardDAV https://contacts.icloud.com
  Notes     – IMAP folder "Notes" on imap.mail.me.com
"""
from __future__ import annotations

import asyncio
import email as email_lib
import hashlib
import imaplib
import os
import re
import html
import tempfile
from datetime import datetime, timedelta, timezone, date
from typing import Any, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import add_audit
from app.i18n_strings import resolve_ui_language, t
from app.database import get_db, SessionLocal, set_session_user
from app import models, schemas
from app.ai.provider import encrypt_api_key, decrypt_api_key, AINotConfigured, AIRateLimited
from app.auth.dependencies import get_current_user
from app.routers.sync_common import (
    is_synced, load_synced_ids, purge_source,
    build_firm_index, build_contact_domain_index, build_contact_email_index,
    find_hint_apps, find_matching_apps,
    process_item, strip_html, earliest_bewerbung_date, _predates_bewerbung,
    init_progress, update_progress, finish_progress,
    set_batch_result, vobj_str, vobj_participants, _to_naive_utc,
)

# In-memory session cache: apple_id -> {'api': ICloudPyService, 'sms_device': dict|None}
_ICLOUD_SESSIONS: dict[str, Any] = {}

router = APIRouter(prefix="/api/sync/icloud", tags=["icloud"])

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993
CALDAV_URL = "https://caldav.icloud.com"
CARDDAV_URL = "https://contacts.icloud.com"


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_cfg(db: Session) -> Optional[models.ICloudSync]:
    return db.query(models.ICloudSync).first()


def _imap_user(cfg: models.ICloudSync) -> str:
    """IMAP requires the @icloud.com/@me.com address, not the generic Apple ID."""
    return cfg.icloud_email or cfg.apple_id


def _caldav_calendars(cfg: models.ICloudSync) -> list:
    """Synchronous CalDAV connect + calendar list, run via asyncio.to_thread()
    by callers — caldav has no async variant, and calling it directly from an
    `async def` would freeze the whole app's single event loop until Apple's
    CalDAV server responds (hardware-verified: a slow/hanging response here
    took the entire app down for ~20 minutes in production, not just this
    sync). Shared by the periodic sync (_do_icloud_cal/_do_icloud_reminders
    below) and the targeted per-application sync (sync_targeted.py)."""
    import caldav
    client = caldav.DAVClient(
        url=CALDAV_URL,
        username=cfg.apple_id,
        password=decrypt_api_key(cfg.app_password_enc),
    )
    return client.principal().calendars()


def _caldav_collect_events(calendars: list, start: datetime, end: datetime) -> tuple[list, list[str]]:
    """Synchronous per-calendar date_search + materialization, run via
    asyncio.to_thread() by callers — same reasoning as _caldav_calendars()
    above. Returns (events, per-calendar error messages) rather than raising,
    matching the existing "skip broken calendars, keep the rest" behavior."""
    all_events: list = []
    errors: list[str] = []
    for cal in calendars:
        try:
            for ev in cal.date_search(start=start, end=end, expand=True):
                all_events.append(ev)
        except Exception as e:
            errors.append(f"Kalender {cal.name}: {e}")
    return all_events, errors


def _caldav_collect_todos(calendars: list) -> list:
    """Synchronous per-calendar todos() fetch, run via asyncio.to_thread() by
    callers — same reasoning as _caldav_calendars() above. Silently skips a
    calendar that errors, matching the existing behavior."""
    all_todos: list = []
    for cal in calendars:
        try:
            all_todos.extend(cal.todos())
        except Exception:
            pass
    return all_todos


def _imap_connect(cfg: models.ICloudSync) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(_imap_user(cfg), decrypt_api_key(cfg.app_password_enc))
    return imap


def _imap_connect_select(cfg: models.ICloudSync) -> imaplib.IMAP4_SSL:
    """Synchronous connect+select, run via asyncio.to_thread() by callers —
    imaplib is a blocking library with no async variant, and calling it
    directly from an `async def` would freeze the whole app's single event
    loop for every request until Apple's IMAP server responds (hardware-
    verified: a slow/hanging response here took the entire app down for
    ~20 minutes in production, not just this sync). Shared by the periodic
    sync (_do_icloud_mail below) and the targeted per-application sync
    (sync_targeted.py), which each need a different SEARCH query."""
    imap = _imap_connect(cfg)
    imap.select("INBOX")
    return imap


def _imap_connect_select_search(cfg: models.ICloudSync, since: str):
    """As _imap_connect_select(), plus a SINCE search — the query
    _do_icloud_mail() below always uses."""
    imap = _imap_connect_select(cfg)
    _, msg_ids = imap.search(None, f'SINCE "{since}"')
    return imap, msg_ids


def _imap_body(msg) -> str:
    """Extract plain text from an email.Message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
            if ct == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    raw_html = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                    return strip_html(raw_html)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
    return ""


def _since_date(dt: Optional[datetime]) -> str:
    """Return IMAP SINCE date string for the given datetime (or 90 days ago)."""
    if not dt:
        dt = datetime.now(timezone.utc) - timedelta(days=90)
    return dt.strftime("%d-%b-%Y")


# ── status / credentials ──────────────────────────────────────────────────────

@router.get("/status", response_model=schemas.ICloudSyncStatus)
def icloud_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if not cfg:
        return schemas.ICloudSyncStatus(connected=False)
    return schemas.ICloudSyncStatus(
        connected=True,
        apple_id=cfg.apple_id,
        icloud_email=cfg.icloud_email,
        mail_last_sync=cfg.mail_last_sync,
        calendar_last_sync=cfg.calendar_last_sync,
        reminders_last_sync=cfg.reminders_last_sync,
        contacts_last_sync=cfg.contacts_last_sync,
        notes_last_sync=cfg.notes_last_sync,
    )


@router.post("/credentials", response_model=schemas.ICloudSyncStatus)
def save_credentials(
    payload: schemas.ICloudCredentials,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    enc = encrypt_api_key(payload.app_password)
    web_enc = encrypt_api_key(payload.web_password) if payload.web_password else None
    if not cfg:
        cfg = models.ICloudSync(
            apple_id=payload.apple_id,
            icloud_email=payload.icloud_email or None,
            app_password_enc=enc,
            web_password_enc=web_enc,
            user_id=current_user.id,
        )
        db.add(cfg)
    else:
        cfg.apple_id = payload.apple_id
        cfg.icloud_email = payload.icloud_email or None
        cfg.app_password_enc = enc
        if web_enc:
            cfg.web_password_enc = web_enc
        # clear cached session when credentials change
        _ICLOUD_SESSIONS.pop(payload.apple_id, None)
    db.commit()
    db.refresh(cfg)
    return schemas.ICloudSyncStatus(connected=True, apple_id=cfg.apple_id, icloud_email=cfg.icloud_email)


@router.post("/web-password", status_code=204)
def save_web_password(
    payload: schemas.ICloud2FAVerify,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Update only the Apple ID web password (used for pyicloud/Notes sync)."""
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")
    cfg.web_password_enc = encrypt_api_key(payload.code)
    _ICLOUD_SESSIONS.pop(cfg.apple_id, None)
    db.commit()


@router.post("/test")
def test_connection(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")
    imap_user = _imap_user(cfg)
    is_icloud_addr = any(imap_user.endswith(s) for s in ("@icloud.com", "@me.com", "@mac.com"))
    if not is_icloud_addr:
        raise HTTPException(400,
            f"Mail-Sync benötigt eine @icloud.com- oder @me.com-Adresse als Benutzernamen, "
            f"nicht '{imap_user}'. Trage sie im Feld 'iCloud-Mail-Adresse' ein."
        )
    try:
        imap = _imap_connect(cfg)
        imap.logout()
        return {"status": "ok", "message": f"IMAP-Verbindung als {imap_user} erfolgreich."}
    except imaplib.IMAP4.error as e:
        raise HTTPException(400, f"IMAP-Fehler: {e}")
    except Exception as e:
        raise HTTPException(502, f"Verbindungsfehler: {e}")


@router.delete("", status_code=204)
def delete_credentials(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        db.delete(cfg)
        db.commit()


# ── Mail ──────────────────────────────────────────────────────────────────────

@router.post("/mail/reset", status_code=204)
def reset_mail_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.mail_last_sync = None
        purge_source(db, "icloud_mail", current_user.id)
        db.commit()


async def _do_icloud_mail(user_id: int) -> dict:
    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []
    imap = None
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_mail", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("no_icloud_credentials", lang)]}

        _, term_to_apps = build_firm_index(db)
        contact_domain_index = build_contact_domain_index(db)
        contact_email_index = build_contact_email_index(db)
        global_cutoff = earliest_bewerbung_date(db)

        update_progress("icloud_mail", 0, 0, t("connecting_imap", lang))
        try:
            since = _since_date(cfg.mail_last_sync)
            imap, msg_ids = await asyncio.to_thread(_imap_connect_select_search, cfg, since)
            ids = msg_ids[0].split() if msg_ids[0] else []
        except Exception as e:
            finish_progress("icloud_mail", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("imap_error", lang, error=e)]}

        batch = ids[-100:]
        total = len(batch)
        update_progress("icloud_mail", 0, total, t("messages_found", lang, count=total))
        synced_ids = load_synced_ids(db, "icloud_mail")

        from email.utils import parsedate_to_datetime as _parse_date_hdr

        for i, msg_id_bytes in enumerate(batch):
            if i % 10 == 0:
                update_progress("icloud_mail", i, total, t("email_progress", lang, current=i + 1, total=total))
            msg_id = msg_id_bytes.decode()

            if msg_id in synced_ids:
                skipped += 1
                continue

            # ── Phase 1: headers only (FETCH RFC822.HEADER is much faster than full RFC822) ──
            try:
                _, hdr_data = await asyncio.to_thread(imap.fetch, msg_id_bytes, "(RFC822.HEADER)")
                hdr_msg = email_lib.message_from_bytes(hdr_data[0][1])
            except Exception as e:
                errors.append(f"Nachricht {msg_id}: {e}")
                continue

            subject = hdr_msg.get("Subject", "(kein Betreff)")
            sender  = hdr_msg.get("From", "")
            to_cc   = (hdr_msg.get("To", "") or "") + "," + (hdr_msg.get("Cc", "") or "")
            date_hint = None
            try:
                date_hint = _parse_date_hdr(hdr_msg.get("Date", "")).astimezone(timezone.utc)
            except Exception:
                pass

            # Skip mails before the earliest application date
            if global_cutoff and date_hint and date_hint.date() < global_cutoff:
                synced_ids.add(msg_id)
                skipped += 1
                continue

            # Quick check on subject + sender/to/cc — skip full fetch if no
            # match. Same combined matcher Gmail sync uses (find_matching_apps:
            # address/domain + company-name/role text) — previously this only
            # checked company-name/domain text, never a saved contact's exact
            # email address, unlike Gmail.
            quick_hints = find_matching_apps(
                sender, to_cc, f"Von: {sender}\nBetreff: {subject}",
                contact_email_index, contact_domain_index, term_to_apps,
            )
            if not quick_hints:
                synced_ids.add(msg_id)
                skipped += 1
                continue

            # ── Phase 2: full message (only for relevant mails) ────────────
            try:
                _, data = await asyncio.to_thread(imap.fetch, msg_id_bytes, "(RFC822)")
                raw_email = data[0][1]
                msg = email_lib.message_from_bytes(raw_email)
            except Exception as e:
                errors.append(f"Nachricht {msg_id}: {e}")
                continue

            body = _imap_body(msg)[:1500]
            raw = f"Von: {sender}\nBetreff: {subject}\n\n{body}"
            hint_apps = find_matching_apps(sender, to_cc, raw, contact_email_index, contact_domain_index, term_to_apps)

            try:
                ok = await process_item(db, "icloud_mail", msg_id, raw, date_hint, hint_apps=hint_apps, user_id=user_id)
            except AINotConfigured as e:
                finish_progress("icloud_mail", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("icloud_mail", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [f"AI-Tageslimit: {e}"]}
            except Exception as e:
                errors.append(f"{subject}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.mail_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_mail", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_mail", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        if imap:
            try:
                await asyncio.to_thread(imap.logout)
            except Exception:
                pass
        db.close()


@router.post("/mail", response_model=schemas.SyncResult)
async def sync_mail(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_mail", {"done": False})
    init_progress("icloud_mail", "iCloud Mail", lang=current_user.ui_language)

    async def _bg():
        result = await _do_icloud_mail(current_user.id)
        set_batch_result("icloud_mail", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


# ── Notes (via pyicloud) ───────────────────────────────────────────────────────

@router.post("/notes/reset", status_code=204)
def reset_notes_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.notes_last_sync = None
        purge_source(db, "icloud_notes", current_user.id)
        db.commit()
        _ICLOUD_SESSIONS.pop(cfg.apple_id, None)


def _get_pyicloud_api(cfg: models.ICloudSync, force_new: bool = False):
    """Return a cached (or fresh) ICloudPyService instance."""
    try:
        from icloudpy import ICloudPyService
    except ImportError:
        raise HTTPException(500, "icloudpy nicht installiert.")

    if not cfg.web_password_enc:
        raise HTTPException(400,
            "Apple-ID-Passwort für Notizen-Sync fehlt. "
            "Trage es im iCloud-Einstellungen-Feld 'Apple-ID-Passwort (für Notizen)' ein."
        )

    apple_id = cfg.apple_id
    web_pw = decrypt_api_key(cfg.web_password_enc)
    session_dir = os.path.join(tempfile.gettempdir(), f"pyicloud_{hashlib.md5(apple_id.encode()).hexdigest()[:12]}")
    os.makedirs(session_dir, exist_ok=True)

    if force_new or apple_id not in _ICLOUD_SESSIONS:
        _ICLOUD_SESSIONS.pop(apple_id, None)
        if force_new:
            # Wipe cached session cookies so Apple definitely triggers a new 2FA
            import shutil
            shutil.rmtree(session_dir, ignore_errors=True)
            os.makedirs(session_dir, exist_ok=True)
        try:
            api = ICloudPyService(apple_id, web_pw, cookie_directory=session_dir)
            _ICLOUD_SESSIONS[apple_id] = {'api': api, 'sms_device': None}
        except Exception as e:
            raise HTTPException(502, f"iCloud-Login fehlgeschlagen: {e}")

    return _ICLOUD_SESSIONS[apple_id]['api']


async def _sync_notes_with_api(
    api: Any, cfg: models.ICloudSync, db: Session, user_id: Optional[int] = None
) -> schemas.SyncResult:
    _, term_to_apps = build_firm_index(db)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []

    init_progress("icloud_notes", t("label_icloud_notes", lang), lang=lang)
    try:
        notes_service = api.notes
        # pyicloud Notes API: service may expose .notes dict, .get_all(), or be iterable
        if hasattr(notes_service, 'get_notes'):
            raw_notes = notes_service.get_notes()
        elif hasattr(notes_service, 'notes'):
            raw_notes = notes_service.notes
        else:
            raw_notes = list(notes_service)
    except Exception as e:
        finish_progress("icloud_notes", lang=lang)
        return schemas.SyncResult(
            processed=0, created=0, skipped=0,
            errors=[t("notes_access_failed", lang, error=e)]
        )

    # Normalise to list
    if isinstance(raw_notes, dict):
        raw_notes = list(raw_notes.values())

    total = len(raw_notes)
    update_progress("icloud_notes", 0, total, t("notes_found", lang, count=total))

    for i, note in enumerate(raw_notes):
        update_progress("icloud_notes", i, total, t("note_progress", lang, current=i + 1, total=total))
        try:
            if isinstance(note, dict):
                title = note.get("title") or note.get("subject") or ""
                content = note.get("content") or note.get("body") or note.get("text") or ""
                uid = str(note.get("id") or note.get("uid") or note.get("recordName") or title)
            else:
                title = str(getattr(note, "title", "") or getattr(note, "subject", "") or "")
                content = str(getattr(note, "content", "") or getattr(note, "body", "") or "")
                uid = str(getattr(note, "id", "") or getattr(note, "uid", "") or title)
        except Exception:
            continue

        # Strip HTML tags
        content_text = re.sub(r"<[^>]+>", " ", content)
        content_text = re.sub(r"\s+", " ", html.unescape(content_text)).strip()

        if not content_text:
            skipped += 1
            continue

        note_key = hashlib.md5(uid.encode()).hexdigest()[:16]
        if is_synced(db, "icloud_notes", note_key):
            skipped += 1
            continue

        raw = f"Titel: {title}\n\n{content_text[:2000]}"
        hint_apps = find_hint_apps(raw, term_to_apps)

        try:
            ok = await process_item(db, "icloud_notes", note_key, raw, None, hint_apps=hint_apps, user_id=user_id)
        except AINotConfigured as e:
            finish_progress("icloud_notes", lang=lang)
            raise HTTPException(400, str(e))
        except AIRateLimited as e:
            finish_progress("icloud_notes", lang=lang)
            raise HTTPException(429, f"AI-Tageslimit erreicht: {e}")
        except Exception as e:
            errors.append(f"{title or uid}: {e}")
            continue

        processed += 1
        if ok:
            created += 1

    db.commit()
    cfg.notes_last_sync = datetime.now(timezone.utc)
    db.commit()
    finish_progress("icloud_notes", lang=lang)
    return schemas.SyncResult(processed=processed, created=created, skipped=skipped, errors=errors)


@router.post("/notes/verify-2fa", response_model=schemas.SyncResult)
async def verify_notes_2fa(
    payload: schemas.ICloud2FAVerify,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    session = _ICLOUD_SESSIONS.get(cfg.apple_id)
    if not session:
        raise HTTPException(400, "Keine aktive Session. Bitte erneut auf 'Notizen Sync' klicken.")

    api = session['api']
    sms_device = session.get('sms_device')

    try:
        if sms_device:
            # Code was sent via send_verification_code → must validate with validate_verification_code
            result = api.validate_verification_code(sms_device, payload.code)
        elif api.requires_2fa:
            result = api.validate_2fa_code(payload.code)
        else:
            result = True
        if not result:
            raise HTTPException(400, "Ungültiger 2FA-Code. Bitte erneut versuchen.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"2FA-Fehler: {e}")

    return await _sync_notes_with_api(api, cfg, db, current_user.id)


async def _do_icloud_notes(user_id: int) -> dict:
    from app.agent_client import agent_get

    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_notes", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("no_icloud_credentials", lang)]}

        _, term_to_apps = build_firm_index(db)

        update_progress("icloud_notes", 0, 0, t("querying_agent", lang))
        try:
            resp = await agent_get(db, "/notes", timeout=30)
            if resp.status_code != 200:
                err = resp.json().get('error', resp.text)
                finish_progress("icloud_notes", lang=lang)
                return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("agent_error_notes", lang, error=err)]}
            notes = resp.json()
        except Exception as e:
            finish_progress("icloud_notes", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [
                t("agent_unreachable", lang, error=e)
            ]}

        total = len(notes)
        update_progress("icloud_notes", 0, total, t("notes_found", lang, count=total))
        synced_ids = load_synced_ids(db, "icloud_notes")

        # ── Phase 1: pre-filter (no AI) ────────────────────────────────────
        pending = []   # (note_key, raw, date_hint, hint_apps)
        for note in notes:
            title = (note.get('name') or '').strip()
            body  = (note.get('body') or '').strip()
            uid   = note.get('id') or title
            if not body:
                skipped += 1
                continue

            note_key = hashlib.md5(uid.encode()).hexdigest()[:16]
            if note_key in synced_ids:
                skipped += 1
                continue

            raw = f"Titel: {title}\n\n{body[:2000]}"
            hint_apps = find_hint_apps(raw, term_to_apps)
            if not hint_apps:
                # No known firm mentioned → can never match an application; skip AI
                skipped += 1
                continue

            date_hint = None
            for date_field in ('creationDate', 'date'):
                raw_date = note.get(date_field) or ''
                if raw_date:
                    try:
                        date_hint = datetime.fromisoformat(raw_date.replace('Z', '+00:00')).astimezone(timezone.utc)
                        break
                    except Exception:
                        pass

            pending.append((note_key, raw, date_hint, hint_apps))

        # ── Phase 2: parallel AI calls in batches of 5 ────────────────────
        import asyncio as _asyncio

        BATCH = 5
        n_pending = len(pending)
        update_progress("icloud_notes", 0, n_pending, t("notes_classifying", lang, count=n_pending))

        async def _process_one(idx: int, note_key: str, raw: str, date_hint, hint_apps):
            update_progress("icloud_notes", idx, n_pending, t("note_progress", lang, current=idx + 1, total=n_pending))
            return await process_item(db, "icloud_notes", note_key, raw, date_hint, hint_apps=hint_apps, user_id=user_id)

        for batch_start in range(0, n_pending, BATCH):
            batch = pending[batch_start:batch_start + BATCH]
            try:
                results = await _asyncio.gather(
                    *[_process_one(batch_start + j, nk, raw, dh, ha) for j, (nk, raw, dh, ha) in enumerate(batch)],
                    return_exceptions=True,
                )
            except AINotConfigured as e:
                finish_progress("icloud_notes", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}

            for (note_key, raw, _, _), result in zip(batch, results):
                if isinstance(result, AINotConfigured):
                    finish_progress("icloud_notes", lang=lang)
                    return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(result)]}
                if isinstance(result, AIRateLimited):
                    finish_progress("icloud_notes", lang=lang)
                    return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [t("ai_daily_limit", lang, error=result)]}
                if isinstance(result, Exception):
                    errors.append(str(result))
                    continue
                processed += 1
                if result:
                    created += 1

        db.commit()
        cfg.notes_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_notes", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_notes", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/notes", response_model=schemas.SyncResult)
async def sync_notes(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_notes", {"done": False})
    init_progress("icloud_notes", t("label_icloud_notes", current_user.ui_language), lang=current_user.ui_language)

    async def _bg():
        result = await _do_icloud_notes(current_user.id)
        set_batch_result("icloud_notes", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


@router.post("/notes/_legacy", response_model=schemas.SyncResult)
async def sync_notes_legacy(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    api = _get_pyicloud_api(cfg, force_new=True)

    r2fa = api.requires_2fa
    r2sa = getattr(api, 'requires_2sa', False)

    if r2fa:
        devices = []
        try:
            devices = list(getattr(api, 'trusted_devices', []) or [])
        except Exception:
            pass

        sms_devices = [d for d in devices if isinstance(d, dict) and d.get('deviceType') == 'SMS']
        push_devices = [d for d in devices if isinstance(d, dict) and d.get('deviceType') != 'SMS']

        sent_msgs = []

        # Explicitly trigger push notification to Apple devices
        if push_devices:
            try:
                api.trigger_2fa_push_notification()
                sent_msgs.append("Push-Benachrichtigung an Apple-Gerät gesendet")
            except Exception as e:
                sent_msgs.append(f"Push fehlgeschlagen: {e}")

        # Explicitly send SMS code to phone devices
        for dev in sms_devices:
            try:
                api.send_verification_code(dev)
                # Remember which device for validation
                _ICLOUD_SESSIONS[cfg.apple_id]['sms_device'] = dev
                num = dev.get('phoneNumber', '')
                sent_msgs.append(f"SMS-Code gesendet an …{num[-4:] if len(num) >= 4 else num}")
            except Exception as e:
                sent_msgs.append(f"SMS fehlgeschlagen: {e}")

        if not push_devices and not sms_devices:
            # No specific devices — try generic push trigger anyway
            try:
                api.trigger_2fa_push_notification()
                sent_msgs.append("Push-Benachrichtigung gesendet")
            except Exception as e:
                sent_msgs.append(f"Push-Trigger fehlgeschlagen: {e}")

        msg = " | ".join(sent_msgs) if sent_msgs else "Bitte prüfe dein iPhone auf eine Apple-ID-Benachrichtigung."
        return schemas.SyncResult(
            processed=0, created=0, skipped=0, requires_2fa=True,
            errors=[msg]
        )

    if r2sa:
        sent_to = "unbekannt"
        try:
            devices = api.trusted_devices or []
            device = devices[0] if devices else None
            if device:
                api.send_verification_code(device)
                _ICLOUD_SESSIONS[cfg.apple_id]['sms_device'] = device
                sent_to = str(device.get('phoneNumber') or device.get('name') or device)
        except Exception as e:
            sent_to = f"Fehler: {e}"
        return schemas.SyncResult(
            processed=0, created=0, skipped=0, requires_2fa=True,
            errors=[f"Code per SMS/Anruf gesendet an: {sent_to}"]
        )

    return await _sync_notes_with_api(api, cfg, db, current_user.id)


# ── Calendar (CalDAV) ─────────────────────────────────────────────────────────

@router.get("/calendar/debug")
def debug_calendar_events(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """List raw CalDAV events (no AI processing) for debugging."""
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")
    try:
        import caldav
    except ImportError:
        raise HTTPException(500, "caldav nicht installiert.")
    _, term_to_apps = build_firm_index(db)
    firm_terms_lower = {t.lower() for t in term_to_apps}
    JOB_KEYWORDS = {"interview","gespräch","vorstellungsgespräch","bewerbung","hr","recruiting","kennenlernen","assessment","onboarding"}
    try:
        client = caldav.DAVClient(url=CALDAV_URL, username=cfg.apple_id, password=decrypt_api_key(cfg.app_password_enc))
        calendars = client.principal().calendars()
    except Exception as e:
        raise HTTPException(502, str(e))
    now = datetime.now(timezone.utc)
    results = []
    for cal in calendars:
        try:
            events = cal.date_search(start=now - timedelta(days=180), end=now + timedelta(days=90), expand=True)
        except Exception:
            continue
        for ev in events:
            try:
                vevent = ev.vobject_instance.vevent
                summary = vobj_str(vevent, "summary")
                desc = vobj_str(vevent, "description")
                uid = vobj_str(vevent, "uid") or str(ev.url)
                dtstart = str(getattr(vevent, "dtstart", None) and vevent.dtstart.value or "")
            except Exception:
                continue
            combined_lower = (summary + " " + desc).lower()
            has_kw = any(kw in combined_lower for kw in JOB_KEYWORDS)
            matched_firms = [ft for ft in firm_terms_lower if ft in combined_lower]
            results.append({"cal": cal.name, "summary": summary, "dtstart": str(dtstart), "has_keyword": has_kw, "matched_firms": matched_firms, "uid": uid[:40]})
    return sorted(results, key=lambda x: x["dtstart"])


@router.post("/calendar/reset", status_code=204)
def reset_calendar_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.calendar_last_sync = None
        purge_source(db, "icloud_cal", current_user.id)
        db.commit()


async def _do_icloud_cal(user_id: int) -> dict:
    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_cal", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("no_icloud_credentials", lang)]}

        try:
            import caldav  # noqa: F401 -- import-only check for the friendlier "not installed" message below
        except ImportError:
            finish_progress("icloud_cal", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("caldav_lib_missing", lang)]}

        _, term_to_apps = build_firm_index(db)

        try:
            calendars = await asyncio.to_thread(_caldav_calendars, cfg)
        except Exception as e:
            finish_progress("icloud_cal", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("caldav_error", lang, error=e)]}

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=180)
        end = now + timedelta(days=90)

        JOB_KEYWORDS = {
            "interview", "gespräch", "vorstellungsgespräch", "bewerbung",
            "hr", "recruiting", "kennenlernen", "assessment", "onboarding",
        }
        firm_terms_lower = {t.lower() for t in term_to_apps}

        update_progress("icloud_cal", 0, 0, t("loading_appointments", lang))
        all_events, collect_errors = await asyncio.to_thread(_caldav_collect_events, calendars, start, end)
        errors.extend(collect_errors)

        total = len(all_events)
        update_progress("icloud_cal", 0, total, t("appointments_found", lang, count=total))
        synced_ids = load_synced_ids(db, "icloud_cal")

        uid_set: set[str] = set()
        for i, ev in enumerate(all_events):
            if i % 10 == 0:
                update_progress("icloud_cal", i, total, t("appointment_progress", lang, current=i + 1, total=total))
            try:
                vevent = ev.vobject_instance.vevent
                summary = vobj_str(vevent, "summary")
                desc = vobj_str(vevent, "description")
                uid = vobj_str(vevent, "uid") or str(ev.url)
            except Exception:
                continue

            uid_set.add(uid)

            date_hint = None
            try:
                dtstart = vevent.dtstart.value
                if isinstance(dtstart, datetime):
                    date_hint = dtstart.astimezone(timezone.utc) if dtstart.tzinfo else dtstart.replace(tzinfo=timezone.utc)
                elif isinstance(dtstart, date):
                    date_hint = datetime(dtstart.year, dtstart.month, dtstart.day, tzinfo=timezone.utc)
            except Exception:
                pass

            if uid in synced_ids:
                # Check if the event changed (date or title)
                new_datum = date_hint.date() if date_hint else None
                if new_datum:
                    existing = db.query(models.Event).filter_by(source="icloud_cal", external_id=uid).first()
                    if existing and (existing.datum != new_datum or existing.titel != summary):
                        existing.datum = new_datum
                        existing.titel = summary
                skipped += 1
                continue

            combined_lower = (summary + " " + desc).lower()
            has_keyword = any(kw in combined_lower for kw in JOB_KEYWORDS)
            has_firm = any(ft in combined_lower for ft in firm_terms_lower)
            if not has_keyword and not has_firm:
                skipped += 1
                continue

            location = vobj_str(vevent, "location")
            participants = vobj_participants(vevent)
            raw = (
                f"Titel: {summary}\nOrt: {location}\n"
                + (f"Teilnehmer: {', '.join(participants)}\n" if participants else "")
                + f"Beschreibung: {desc[:800]}"
            )
            hint_apps = find_hint_apps(raw, term_to_apps)

            try:
                ok = await process_item(db, "icloud_cal", uid, raw, date_hint, hint_apps=hint_apps, user_id=user_id)
            except AINotConfigured as e:
                finish_progress("icloud_cal", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("icloud_cal", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [t("ai_daily_limit", lang, error=e)]}
            except Exception as e:
                errors.append(f"{summary or uid}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()

        # Remove timeline events whose calendar entries no longer exist within the sync window
        if uid_set:
            window_start = start.date()
            window_end = end.date()
            deleted_count = 0
            orphaned = (
                db.query(models.Event)
                .filter(
                    models.Event.source == "icloud_cal",
                    models.Event.external_id.isnot(None),
                    models.Event.datum >= window_start,
                    models.Event.datum <= window_end,
                )
                .all()
            )
            for orphan in orphaned:
                if orphan.external_id not in uid_set:
                    db.query(models.SyncedItem).filter_by(
                        source="icloud_cal", external_id=orphan.external_id, user_id=user_id
                    ).delete()
                    db.delete(orphan)
                    deleted_count += 1
            if deleted_count:
                db.commit()

        cfg.calendar_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_cal", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_cal", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/calendar", response_model=schemas.SyncResult)
async def sync_calendar(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_cal", {"done": False})
    init_progress("icloud_cal", t("label_icloud_calendar", current_user.ui_language), lang=current_user.ui_language)

    async def _bg():
        result = await _do_icloud_cal(current_user.id)
        set_batch_result("icloud_cal", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


# ── Reminders (CalDAV VTODO) ──────────────────────────────────────────────────

@router.post("/reminders/reset", status_code=204)
def reset_reminders_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.reminders_last_sync = None
        purge_source(db, "icloud_todo", current_user.id)
        db.commit()


async def _do_icloud_reminders(user_id: int) -> dict:
    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_reminders", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("no_icloud_credentials", lang)]}

        try:
            import caldav  # noqa: F401 -- import-only check for the friendlier "not installed" message below
        except ImportError:
            finish_progress("icloud_reminders", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("caldav_lib_missing", lang)]}

        _, term_to_apps = build_firm_index(db)

        try:
            calendars = await asyncio.to_thread(_caldav_calendars, cfg)
        except Exception as e:
            finish_progress("icloud_reminders", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("caldav_error", lang, error=e)]}

        firm_terms_lower = {t.lower() for t in term_to_apps}

        update_progress("icloud_reminders", 0, 0, t("loading_reminders", lang))
        all_todos = await asyncio.to_thread(_caldav_collect_todos, calendars)

        total = len(all_todos)
        update_progress("icloud_reminders", 0, total, t("reminders_found", lang, count=total))
        synced_ids = load_synced_ids(db, "icloud_todo")

        for i, todo in enumerate(all_todos):
            if i % 10 == 0:
                update_progress("icloud_reminders", i, total, t("reminder_progress", lang, current=i + 1, total=total))
            try:
                vtodo = todo.vobject_instance.vtodo
                summary = vobj_str(vtodo, "summary")
                desc = vobj_str(vtodo, "description")
                uid = vobj_str(vtodo, "uid") or str(todo.url)
            except Exception:
                continue

            if uid in synced_ids:
                skipped += 1
                continue

            combined_lower = (summary + " " + desc).lower()
            if not any(ft in combined_lower for ft in firm_terms_lower):
                skipped += 1
                continue

            date_hint = None
            try:
                due = getattr(vtodo, "due", None)
                if due:
                    d = due.value
                    if isinstance(d, datetime):
                        date_hint = d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)
                    elif isinstance(d, date):
                        date_hint = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            except Exception:
                pass

            raw = f"Erinnerung: {summary}\n{desc[:800]}"
            hint_apps = find_hint_apps(raw, term_to_apps)

            try:
                ok = await process_item(db, "icloud_todo", uid, raw, date_hint, hint_apps=hint_apps, user_id=user_id)
            except AINotConfigured as e:
                finish_progress("icloud_reminders", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("icloud_reminders", lang=lang)
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [t("ai_daily_limit", lang, error=e)]}
            except Exception as e:
                errors.append(f"{summary or uid}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.reminders_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_reminders", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_reminders", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/reminders", response_model=schemas.SyncResult)
async def sync_reminders(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_reminders", {"done": False})
    init_progress("icloud_reminders", t("label_icloud_reminders", current_user.ui_language), lang=current_user.ui_language)

    async def _bg():
        result = await _do_icloud_reminders(current_user.id)
        set_batch_result("icloud_reminders", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


# ── Contacts (CardDAV) ────────────────────────────────────────────────────────

@router.post("/contacts/reset", status_code=204)
def reset_contacts_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.contacts_last_sync = None
        db.commit()


def _firm_variants(name: str) -> list[str]:
    """Return the name plus a version with common legal suffixes stripped."""
    suffixes = (" gmbh", " ag", " se", " kg", " ohg", " gbr", " inc", " ltd",
                " llc", " bv", " nv", " gmbh & co. kg", " gmbh & co kg")
    variants = [name]
    lower = name.lower()
    for s in suffixes:
        if lower.endswith(s):
            variants.append(name[: len(name) - len(s)].strip())
            break
    return variants


def _find_apps_for_contact(org: str, db) -> list[int]:
    """Return all application ids whose firma matches the contact's org field."""
    if not org:
        return []
    org_lower = org.strip().lower()
    apps = db.query(models.Application).all()
    matched: list[int] = []
    # Exact match pass
    for a in apps:
        for field in [a.firma, a.zielfirma_bei_hh, a.wurde_besetzt_von]:
            if not field:
                continue
            for variant in _firm_variants(field):
                if variant.lower() == org_lower and a.id not in matched:
                    matched.append(a.id)
    if matched:
        return matched
    # Substring containment pass
    for a in apps:
        for field in [a.firma, a.zielfirma_bei_hh, a.wurde_besetzt_von]:
            if not field:
                continue
            for variant in _firm_variants(field):
                v = variant.lower()
                if (v in org_lower or org_lower in v) and a.id not in matched:
                    matched.append(a.id)
    return matched


def _find_apps_where_contact_mentioned(name: str, email: str | None, db) -> list[int]:
    """Return app IDs where this contact is explicitly mentioned in events or application text fields.

    Only creates a match when the full name (or email) appears verbatim — avoids false
    positives from common first-name-only fragments.
    """
    from sqlalchemy import or_

    app_ids: set[int] = set()
    candidates: list[str] = []

    # Full name as-is
    if name and len(name) >= 5:
        candidates.append(name)

    # "Last First" inversion for contacts stored surname-first
    parts = name.split() if name else []
    if len(parts) >= 2:
        inverted = " ".join(reversed(parts))
        if inverted != name:
            candidates.append(inverted)

    # Email is highly specific
    if email:
        candidates.append(email.lower())

    if not candidates:
        return []

    # Search events
    for term in candidates:
        evs = (
            db.query(models.Event)
            .filter(or_(
                models.Event.titel.ilike(f"%{term}%"),
                models.Event.notiz.ilike(f"%{term}%"),
                models.Event.autor.ilike(f"%{term}%"),
            ))
            .all()
        )
        for ev in evs:
            app_ids.add(ev.application_id)

    # Search application text fields
    for term in candidates:
        apps = (
            db.query(models.Application)
            .filter(or_(
                models.Application.kommentar.ilike(f"%{term}%"),
                models.Application.gespraech_1.ilike(f"%{term}%"),
                models.Application.gespraech_2.ilike(f"%{term}%"),
                models.Application.gespraech_3.ilike(f"%{term}%"),
                models.Application.gespraech_4.ilike(f"%{term}%"),
                models.Application.gespraech_5.ilike(f"%{term}%"),
            ))
            .all()
        )
        for a in apps:
            app_ids.add(a.id)

    return list(app_ids)


@router.post("/contacts", response_model=schemas.SyncResult)
async def sync_contacts(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    init_progress("icloud_contacts", t("label_icloud_contacts", current_user.ui_language), t("loading_contacts", current_user.ui_language), lang=current_user.ui_language)
    created, errors = await _sync_contacts_http(cfg, db, current_user.id)

    # Backfill missing application links for already-imported contacts (mention-based)
    update_progress("icloud_contacts", 0, 1, t("updating_links", current_user.ui_language))
    all_contacts = db.query(models.Contact).all()
    backfilled = 0
    for c in all_contacts:
        mention_ids = _find_apps_where_contact_mentioned(c.name, c.email, db)
        linked_ids = {a.id for a in c.applications}
        for app_id in mention_ids:
            if app_id not in linked_ids:
                app = db.query(models.Application).get(app_id)
                if app:
                    c.applications.append(app)
                    backfilled += 1

    db.commit()
    cfg.contacts_last_sync = datetime.now(timezone.utc)
    db.commit()
    finish_progress("icloud_contacts", lang=current_user.ui_language)

    return schemas.SyncResult(
        processed=created,
        created=created,
        skipped=0,
        errors=errors + ([f"{backfilled} bestehende Kontakte verknüpft"] if backfilled else []),
    )


async def fetch_all_vcards(cfg: models.ICloudSync) -> list[str]:
    """CardDAV discovery + fetch: returns all raw vCard strings from iCloud."""
    import httpx
    import base64

    auth = base64.b64encode(
        f"{cfg.apple_id}:{decrypt_api_key(cfg.app_password_enc)}".encode()
    ).decode()

    def dav_headers(depth: str = "0", content_type: str = "text/xml; charset=utf-8") -> dict:
        return {"Authorization": f"Basic {auth}", "Content-Type": content_type, "Depth": depth}

    def xml_find(text: str, *paths: str) -> str | None:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None
        for path in paths:
            for el in root.iter():
                tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if tag == path.split(":")[-1]:
                    href = el.find("{DAV:}href")
                    val = (href.text if href is not None else el.text) or ""
                    if val.strip():
                        return val.strip()
        return None

    def xml_findall_address_data(text: str) -> list[str]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        return [el.text.strip() for el in root.iter() if el.tag.split("}")[-1] == "address-data" and el.text]

    from urllib.parse import urlparse
    base = f"{urlparse(CARDDAV_URL).scheme}://{urlparse(CARDDAV_URL).netloc}"

    all_vcards: list[str] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.request(
            "PROPFIND", f"{CARDDAV_URL}/",
            headers=dav_headers("0"),
            content='<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:current-user-principal/></D:prop></D:propfind>',
        )
        if r.status_code not in (200, 207):
            return []
        principal_path = xml_find(r.text, "current-user-principal")
        if not principal_path:
            return []
        principal_url = principal_path if principal_path.startswith("http") else base + principal_path

        r = await client.request(
            "PROPFIND", principal_url,
            headers=dav_headers("0"),
            content='<?xml version="1.0"?><D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><D:prop><C:addressbook-home-set/></D:prop></D:propfind>',
        )
        home_href = xml_find(r.text, "addressbook-home-set")
        if not home_href:
            return []
        home_url = home_href if home_href.startswith("http") else base + home_href

        r = await client.request(
            "PROPFIND", home_url,
            headers=dav_headers("1"),
            content='<?xml version="1.0"?><D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><D:prop><D:resourcetype/></D:prop></D:propfind>',
        )
        abook_urls: list[str] = []
        try:
            root_el = ET.fromstring(r.text)
            for resp_el in root_el.iter("{DAV:}response"):
                href_el = resp_el.find("{DAV:}href")
                if href_el is None or not href_el.text:
                    continue
                rt = resp_el.find(".//{DAV:}resourcetype")
                if rt is not None and rt.find("{urn:ietf:params:xml:ns:carddav}addressbook") is not None:
                    h = href_el.text.strip()
                    abook_urls.append(h if h.startswith("http") else base + h)
        except ET.ParseError:
            pass

        query_body = """<?xml version="1.0" encoding="UTF-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop><D:getetag/><C:address-data/></D:prop>
  <C:filter/>
</C:addressbook-query>"""

        for abook_url in abook_urls:
            r = await client.request(
                "REPORT", abook_url,
                headers=dav_headers("1", "application/xml; charset=utf-8"),
                content=query_body,
            )
            if r.status_code in (200, 207):
                all_vcards.extend(xml_findall_address_data(r.text))

    return all_vcards


def _parse_vcard(raw_vcard: str) -> Optional[dict]:
    """Parse one raw vCard string into a plain field dict, or None if unparsable/empty.

    Shared by the automatic CardDAV sync and the manual contact search — keeping this
    in one place avoids the parsing logic drifting apart between the two call sites.
    """
    import vobject

    try:
        card = vobject.readOne(raw_vcard)
    except Exception:
        return None

    fn = str(card.fn.value) if hasattr(card, "fn") else ""
    if not fn:
        return None

    # Vor-/Nachname aus dem strukturierten N:-Feld (Family;Given;;;) statt aus
    # FN (Anzeigename) zu raten: FN-Reihenfolge ist uneinheitlich ("Vorname
    # Nachname", "NACHNAME Vorname", "Nachname, Vorname" — je nach Quelle/
    # Adressbuch-Konvention), aber N: ist von Apple Contacts strukturiert und
    # damit zuverlässig — auch wenn FN z.B. "Bayer Sarah" zeigt, steht in N:
    # korrekt "Bayer;Sarah". Bei reinen Firmen-Einträgen ist N: leer (";;;;")
    # und FN bleibt als Ganzes stehen (kein Rate-Split für Firmennamen).
    name = fn
    vorname_val: Optional[str] = None
    if hasattr(card, "n"):
        family = str(getattr(card.n.value, "family", "") or "").strip()
        given = str(getattr(card.n.value, "given", "") or "").strip()
        if family:
            name = family
            vorname_val = given or None

    email_val = str(card.email.value) if hasattr(card, "email") else None

    def _vcard_phone_type(type_str: str) -> str:
        if any(t in type_str for t in ("CELL", "IPHONE", "MOBILE")):
            return "mobile"
        if "HOME" in type_str:
            return "home"
        if "WORK" in type_str:
            return "work"
        if "MAIN" in type_str or "PREF" in type_str:
            return "main"
        return "other"

    phones_val: list[dict] = []
    _seen_numbers: set[str] = set()
    for _tp in card.contents.get("tel", []):
        _number = str(_tp.value).strip()
        if not _number or _number in _seen_numbers:
            continue
        _seen_numbers.add(_number)
        _type_str = str(getattr(_tp, "params", {}).get("TYPE", "")).upper()
        phones_val.append({"number": _number, "type": _vcard_phone_type(_type_str)})
    org_val = None
    if hasattr(card, "org"):
        parts = card.org.value
        org_val = parts[0] if isinstance(parts, list) and parts else str(parts)
        org_val = org_val.strip() or None
    title_val = str(card.title.value) if hasattr(card, "title") else None

    linkedin_url = None
    for url_prop in card.contents.get("url", []) + card.contents.get("item1.url", []):
        val = str(url_prop.value)
        if "linkedin.com" in val:
            linkedin_url = val
            break

    return {
        "name": name, "vorname": vorname_val, "fn": fn, "email": email_val, "phones": phones_val,
        "firma": org_val, "rolle": title_val, "linkedin_url": linkedin_url,
    }


def _merge_parsed_contact(
    contact: "models.Contact", parsed: dict, db: Session, user_id: Optional[int], force: bool = False
) -> list[str]:
    """Apply a freshly parsed vCard onto an EXISTING contact — shared by every
    sync path that discovers new info for an already-known contact (automatic
    CardDAV address-book sync, mail/calendar-triggered contact discovery, and
    the explicit per-contact Sync/Re-Sync action).

    force=False ("Sync" / passive backfill): only fills fields that are
    currently empty, and only ADDS phone numbers not already present — never
    overwrites or removes existing data. This is the long-standing automatic-
    sync behavior.

    force=True ("Re-Sync"): overwrites name/vorname/rolle/linkedin_url/firma
    (+ company link) directly from iCloud, and replaces the phone list
    wholesale with the freshly parsed set — an explicit user request to make
    the contact match iCloud right now.

    Returns the list of changed field names (used for the Sync/Re-Sync result
    message and to decide whether icloud_last_synced_at should be bumped).
    """
    from app.dedup import norm_firma

    changed: list[str] = []

    def _set_scalar(field: str, new_value):
        if not new_value:
            return
        old_value = getattr(contact, field)
        if not force and old_value:
            return
        if str(old_value or "") == str(new_value):
            return
        add_audit(db, "update", "sync", contact_id=contact.id,
                  field=field, old_value=old_value, new_value=new_value,
                  reason_key="contact_from_icloud_addressbook", user_id=user_id)
        setattr(contact, field, new_value)
        changed.append(field)

    # vorname fill-if-empty is deliberately NOT handled by _set_scalar: a legacy
    # contact whose name still holds the pre-split full display name needs BOTH
    # vorname and name corrected together (see the dedicated block in each
    # non-force call site) — setting vorname alone there would leave name
    # stale/mismatched. force=True has no such ambiguity (name is left as-is,
    # only vorname is refreshed), so it's safe to handle generically here.
    if force:
        _set_scalar("vorname", parsed.get("vorname"))
    _set_scalar("linkedin_url", parsed.get("linkedin_url"))
    _set_scalar("rolle", parsed.get("rolle"))

    org_val = parsed.get("firma")
    if org_val and (force or not contact.firma):
        company_profile_id = None
        cp = db.query(models.CompanyProfile).filter_by(name_norm=norm_firma(org_val)).first()
        if cp:
            company_profile_id = cp.id
        if contact.firma != org_val or contact.company_profile_id != company_profile_id:
            add_audit(db, "update", "sync", contact_id=contact.id,
                      field="firma", old_value=contact.firma, new_value=org_val,
                      reason_key="contact_from_icloud_addressbook", user_id=user_id)
            contact.firma = org_val
            contact.company_profile_id = company_profile_id
            changed.append("firma")

    parsed_phones = parsed.get("phones") or []
    if force:
        if parsed_phones or contact.phones:
            contact.phones.clear()
            for p in parsed_phones:
                contact.phones.append(models.ContactPhone(number=p["number"], type=p["type"], user_id=user_id))
            changed.append("phones")
    else:
        existing_norm = {_normalize_phone(p.number) for p in contact.phones}
        added = False
        for p in parsed_phones:
            norm = _normalize_phone(p["number"])
            if norm and norm not in existing_norm:
                contact.phones.append(models.ContactPhone(number=p["number"], type=p["type"], user_id=user_id))
                existing_norm.add(norm)
                added = True
        if added:
            changed.append("phones")

    return changed


async def _sync_contacts_http(
    cfg: models.ICloudSync, db: Session, user_id: Optional[int] = None
) -> tuple[int, list[str]]:
    """CardDAV sync via HTTP using fetch_all_vcards helper."""
    processed = created = 0
    errors: list[str] = []

    try:
        vcards_raw = await fetch_all_vcards(cfg)
    except Exception as e:
        return 0, [f"CardDAV HTTP-Fehler: {e}"]

    if not vcards_raw:
        return 0, ["Keine vCards gefunden (CardDAV)"]

    lang = resolve_ui_language(db, user_id)
    total_vcards = len(vcards_raw)
    update_progress("icloud_contacts", 0, total_vcards, t("contacts_found", lang, count=total_vcards))

    for idx, raw_vcard in enumerate(vcards_raw):
        update_progress("icloud_contacts", idx, total_vcards, t("contact_progress", lang, current=idx + 1, total=total_vcards))
        parsed = _parse_vcard(raw_vcard)
        if not parsed:
            continue

        try:
            name = parsed["name"]
            vorname_val = parsed["vorname"]
            fn = parsed["fn"]
            email_val = parsed["email"]
            org_val = parsed["firma"]
            title_val = parsed["rolle"]
            linkedin_url = parsed["linkedin_url"]

            existing = None
            if email_val:
                existing = db.query(models.Contact).filter_by(email=email_val).first()
            if not existing:
                existing = db.query(models.Contact).filter_by(name=name).first()
            if not existing and name != fn:
                # Kontakte von vor dem Vorname/Nachname-Split (name enthielt den
                # vollen Anzeigenamen statt nur den Nachnamen) sonst hier nicht
                # finden und fälschlich als Duplikat neu anlegen.
                existing = db.query(models.Contact).filter_by(name=fn).first()
            if existing:
                _merge_parsed_contact(existing, parsed, db, user_id, force=False)
                if vorname_val and not existing.vorname:
                    # Nachträglicher Vorname/Nachname-Split für Alt-Kontakte —
                    # nutzt das strukturierte N:-Feld der vCard (echte Adress-
                    # buch-Daten), kein Rate-Heuristik-Backfill über den
                    # bisherigen (evtl. schon falsch zusammengesetzten) Namen.
                    existing.vorname = vorname_val
                    existing.name = name
                continue

            # Always import the contact so it appears in the company Kontakte tab.
            # Application links are created only for apps where the contact is
            # explicitly mentioned in events or application text (not just by firma match).
            # Volltext-Erwähnungssuche braucht den vollen Anzeigenamen (fn), nicht
            # nur den seit dem Vorname/Nachname-Split isolierten Nachnamen — sonst
            # würden z.B. Erwähnungen von "Max Mustermann" im Bewerbungstext nicht
            # mehr gefunden.
            mention_app_ids = _find_apps_where_contact_mentioned(fn, email_val, db)
            firma_app_ids = _find_apps_for_contact(org_val or "", db) if org_val else []

            # Check whether the org matches a known CompanyProfile. A text match on the
            # org field alone is NOT enough to justify import — the user's address book
            # can contain hundreds of colleagues from a former employer that happens to
            # share a name with a CompanyProfile (e.g. from an unrelated application),
            # which previously caused entire company address books to be imported wholesale
            # (592 contacts, 272 from a single "Contoso GmbH" match — live-verified bug).
            # Only accept the company match as a standalone reason if the contact's email
            # domain also matches the company's website — an org-name match by itself
            # still populates company_profile_id for display, but doesn't gate import.
            # Additionally, the CompanyProfile must actually be tied to a real application —
            # a CompanyProfile can exist standalone (e.g. leftover from an old/removed
            # application, LinkedIn import, etc.) without ever having been applied to. An
            # email-domain match against such a profile still isn't a real connection: it
            # imported 32 Contoso-domain contacts even though Contoso has zero applications
            # (live-verified follow-up to the bug above).
            company_profile_id = None
            company_domain_match = False
            if org_val:
                from app.dedup import norm_firma
                norm = norm_firma(org_val)
                cp = db.query(models.CompanyProfile).filter_by(name_norm=norm).first()
                if cp:
                    company_profile_id = cp.id
                    if email_val and cp.website and (cp.applications or cp.hh_applications):
                        host = (urlparse(cp.website if "//" in cp.website else f"//{cp.website}").hostname or "").removeprefix("www.")
                        email_domain = email_val.split("@", 1)[1].lower() if "@" in email_val else ""
                        if host and email_domain and (email_domain == host or email_domain.endswith(f".{host}")):
                            company_domain_match = True

            # Skip contacts with no real connection to job applications or known companies
            if not mention_app_ids and not firma_app_ids and not company_domain_match:
                continue

            contact = models.Contact(
                name=name, vorname=vorname_val, email=email_val,
                firma=org_val, rolle=title_val, linkedin_url=linkedin_url,
                company_profile_id=company_profile_id, user_id=user_id,
            )
            for p in parsed.get("phones") or []:
                contact.phones.append(models.ContactPhone(number=p["number"], type=p["type"], user_id=user_id))
            db.add(contact)
            db.flush()
            if mention_app_ids:
                match_reason = t("mentioned_in_app_text_or_email", lang)
            elif firma_app_ids:
                match_reason = t("company_matches_existing_application", lang, org=org_val)
            else:
                match_reason = t("email_domain_matches_company", lang, org=org_val)
            add_audit(db, "create", "sync", contact_id=contact.id,
                      new_value=contact.display_name,
                      reason_key="contact_imported_icloud_addressbook", reason_params={"match_reason": match_reason},
                      user_id=user_id)
            linked_ids = list({*mention_app_ids, *firma_app_ids})
            for aid in linked_ids:
                app_obj = db.query(models.Application).get(aid)
                if app_obj:
                    contact.applications.append(app_obj)
            if linked_ids:
                from app.routers.sync_linkedin import attach_linkedin_messages_for_contact
                attach_linkedin_messages_for_contact(db, contact, user_id)
            processed += 1
            created += 1
        except Exception as e:
            errors.append(f"Kontakt: {e}")

    return created, errors


@router.get("/contacts/search")
async def search_contacts(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Volltextsuche im kompletten iCloud-Adressbuch, unabhängig von der
    Relevanz-Prüfung des automatischen Syncs (_sync_contacts_http). Für den
    manuellen Import sucht der User gezielt nach einer Person und entscheidet
    selbst, ob sie importiert wird — die "hat eine echte Verbindung zu einer
    Bewerbung"-Gate gilt hier bewusst nicht.
    """
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(status_code=400, detail="iCloud nicht konfiguriert")

    try:
        vcards_raw = await fetch_all_vcards(cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"CardDAV HTTP-Fehler: {e}")

    q_lower = q.strip().lower()
    results: list[dict] = []
    seen_keys: set[str] = set()
    for raw in vcards_raw:
        parsed = _parse_vcard(raw)
        if not parsed:
            continue
        haystack = " ".join(filter(None, [parsed["fn"], parsed["email"], parsed["firma"]])).lower()
        if q_lower not in haystack:
            continue

        existing = None
        if parsed["email"]:
            existing = db.query(models.Contact).filter_by(email=parsed["email"]).first()
        if not existing:
            existing = db.query(models.Contact).filter_by(name=parsed["name"]).first()
        if not existing and parsed["name"] != parsed["fn"]:
            existing = db.query(models.Contact).filter_by(name=parsed["fn"]).first()
        # Bereits vorhandene Kontakte weiterhin mit anzeigen (nur als "schon
        # importiert" markiert), statt sie stillschweigend aus dem Ergebnis zu
        # werfen — sonst wirkt eine Suche, deren einzige Treffer bereits
        # importiert sind, wie ein kaputtes "0 Treffer". Live beobachtet: Suche
        # nach "qorix" fand 3 echte vCards, aber alle drei waren schon
        # importierte Kontakte → Ergebnis war fälschlich leer.
        parsed["already_imported"] = existing is not None

        key = f"{parsed['email'] or ''}|{parsed['name']}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        parsed.pop("fn", None)
        results.append(parsed)
        if len(results) >= 30:
            break

    return results


class ContactPhoneIn(BaseModel):
    number: str
    type: str = "other"


class ContactImportCandidate(BaseModel):
    name: str
    vorname: Optional[str] = None
    email: Optional[str] = None
    phones: list[ContactPhoneIn] = []
    firma: Optional[str] = None
    rolle: Optional[str] = None
    linkedin_url: Optional[str] = None


class ContactImportPayload(BaseModel):
    candidates: list[ContactImportCandidate]
    application_id: Optional[int] = None


@router.post("/contacts/import")
def import_contacts(
    body: ContactImportPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Importiert vom User ausgewählte Kandidaten (aus /contacts/search) als
    echte Contact-Zeilen. Explizite User-Aktion, deshalb ohne die
    Relevanz-Prüfung des automatischen Syncs — der User hat die Auswahl
    bereits selbst getroffen.
    """
    app_obj = None
    if body.application_id:
        app_obj = db.query(models.Application).filter(
            models.Application.id == body.application_id
        ).first()
        if not app_obj:
            raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")

    imported = 0
    skipped = 0
    for cand in body.candidates:
        existing = None
        if cand.email:
            existing = db.query(models.Contact).filter_by(email=cand.email).first()
        if not existing:
            existing = db.query(models.Contact).filter_by(name=cand.name).first()
        if existing:
            skipped += 1
            if app_obj and app_obj not in existing.applications:
                existing.applications.append(app_obj)
                from app.routers.sync_linkedin import attach_linkedin_messages_for_contact
                attach_linkedin_messages_for_contact(db, existing, current_user.id)
            continue
        contact = models.Contact(
            name=cand.name, vorname=cand.vorname, email=cand.email,
            firma=cand.firma, rolle=cand.rolle, linkedin_url=cand.linkedin_url,
            user_id=current_user.id,
        )
        for p in cand.phones:
            contact.phones.append(models.ContactPhone(number=p.number, type=p.type, user_id=current_user.id))
        db.add(contact)
        db.flush()
        if app_obj:
            contact.applications.append(app_obj)
        add_audit(db, "create", "user", contact_id=contact.id,
                  app_id=app_obj.id if app_obj else None,
                  new_value=contact.display_name, reason_key="import_from_icloud_contact_search",
                  user_id=current_user.id)
        if app_obj:
            from app.routers.sync_linkedin import attach_linkedin_messages_for_contact
            attach_linkedin_messages_for_contact(db, contact, current_user.id)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}


class ContactsSyncPayload(BaseModel):
    contact_ids: Optional[list[int]] = None
    force: bool = False


@router.post("/contacts/sync")
async def sync_contacts_icloud(
    body: ContactsSyncPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Per-contact "Sync"/"Re-Sync": re-matches the given (or, if contact_ids
    is omitted, all of the user's) contacts against the current iCloud address
    book. force=False only adds new phone numbers and fills currently-empty
    fields (the existing passive-sync behavior); force=True overwrites the
    contact wholesale from the matched vCard — an explicit "make this match
    iCloud now" action, unlike the automatic sync's conservative default.
    """
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(status_code=400, detail="iCloud nicht konfiguriert")

    if body.contact_ids:
        contacts = db.query(models.Contact).filter(models.Contact.id.in_(body.contact_ids)).all()
    else:
        contacts = db.query(models.Contact).all()
    if not contacts:
        return {"synced": [], "not_found": [], "errors": []}

    try:
        vcards_raw = await fetch_all_vcards(cfg)
    except Exception as e:
        return {"synced": [], "not_found": [], "errors": [f"CardDAV HTTP-Fehler: {e}"]}

    parsed_cards = [p for p in (_parse_vcard(v) for v in vcards_raw) if p]
    by_email = {p["email"].lower(): p for p in parsed_cards if p["email"]}
    by_name: dict[str, dict] = {}
    for p in parsed_cards:
        by_name.setdefault(p["name"], p)
        by_name.setdefault(p["fn"], p)

    synced: list[int] = []
    not_found: list[int] = []
    errors: list[str] = []

    for contact in contacts:
        try:
            match = None
            if contact.email:
                match = by_email.get(contact.email.lower())
            if not match:
                match = by_name.get(contact.name)
            if not match:
                not_found.append(contact.id)
                continue
            _merge_parsed_contact(contact, match, db, current_user.id, force=body.force)
            contact.icloud_last_synced_at = datetime.now(timezone.utc)
            synced.append(contact.id)
        except Exception as e:
            errors.append(f"{contact.display_name}: {e}")

    db.commit()
    return {"synced": synced, "not_found": not_found, "errors": errors}


# ── Anrufliste (via Rapport Agent) ─────────────────────────────────────────

def _get_calls_cfg(db: Session, user_id: Optional[int] = None) -> models.CallsConfig:
    cfg = db.query(models.CallsConfig).first()
    if not cfg:
        cfg = models.CallsConfig(enabled=True, user_id=user_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


async def _agent_reachable(db: Session) -> bool:
    from app.agent_client import agent_get
    try:
        resp = await agent_get(db, "/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


@router.get("/calls/status", response_model=schemas.CallsStatus)
async def calls_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = _get_calls_cfg(db, current_user.id)
    return schemas.CallsStatus(
        enabled=cfg.enabled,
        last_sync=cfg.last_sync,
        bridge_reachable=await _agent_reachable(db),
    )


@router.post("/calls/settings", response_model=schemas.CallsStatus)
async def calls_settings(
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = _get_calls_cfg(db, current_user.id)
    if "enabled" in body:
        cfg.enabled = bool(body["enabled"])
        db.commit()
    return schemas.CallsStatus(enabled=cfg.enabled, last_sync=cfg.last_sync, bridge_reachable=await _agent_reachable(db))


def _normalize_phone(phone: str) -> str:
    """Normalize phone to a canonical digit string for comparison."""
    if not phone:
        return ""
    phone = phone.strip()
    # Strip "+CC (0) ..." formatting artifact (e.g. "+49 (0) 172 …" → "+49 172 …")
    phone = re.sub(r'(\+\d+)\s*\(0\)\s*', r'\1 ', phone)
    has_plus = phone.startswith("+")
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    if has_plus:
        return f"+{digits}"
    if digits.startswith("00"):
        return f"+{digits[2:]}"
    if digits.startswith("0"):
        return f"+49{digits[1:]}"
    return digits


def _phones_match(a: str, b: str) -> bool:
    """Compare two phone numbers, tolerating suffix matches for short numbers."""
    na, nb = _normalize_phone(a), _normalize_phone(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # suffix match for numbers like "0151…" vs "+49151…"
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 7 and longer.endswith(shorter[-9:])


def _name_tokens(name: str) -> set[str]:
    """Return lower-case word tokens ≥4 chars, stripping honorifics."""
    stop = {"dr.", "dr", "prof.", "prof", "hr", "frau", "mr", "ms", "mrs"}
    return {w.lower() for w in re.split(r"[\s,.\-]+", name) if len(w) >= 4 and w.lower() not in stop}


def _match_contacts_by_name(call_name: str, db: Session) -> list[models.Contact]:
    """Find contacts whose name shares ≥2 significant tokens with call_name (handles First/Last inversion)."""
    call_tokens = _name_tokens(call_name)
    if len(call_tokens) < 1:
        return []
    all_contacts = db.query(models.Contact).all()
    matched: list[models.Contact] = []
    for c in all_contacts:
        if not c.name:
            continue
        c_tokens = _name_tokens(c.name)
        shared = call_tokens & c_tokens
        # Need at least 2 matching tokens (first + last name), or 1 if it's a long unique token
        if len(shared) >= 2 or (len(shared) == 1 and len(next(iter(shared))) >= 6):
            matched.append(c)
    return matched


@router.post("/calls/reset", status_code=204)
def reset_calls_sync(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    calls_cfg = _get_calls_cfg(db, current_user.id)
    calls_cfg.last_sync = None
    purge_source(db, "icloud_calls", current_user.id)
    deleted = db.query(models.Event).filter_by(source="icloud_calls", user_id=current_user.id).delete()
    if deleted:
        add_audit(db, "delete", "user", old_value=f"{deleted} synchronisierte Anrufe",
                  reason_key="call_sync_reset_manually", user_id=current_user.id)
    db.commit()


async def _do_icloud_calls(user_id: int) -> dict:
    from app.agent_client import agent_get

    db = SessionLocal()
    set_session_user(db, user_id)
    lang = resolve_ui_language(db, user_id)
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        calls_cfg = _get_calls_cfg(db, user_id)
        if not calls_cfg.enabled:
            finish_progress("icloud_calls", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("calls_sync_disabled", lang)]}

        update_progress("icloud_calls", 0, 0, t("loading_calls", lang))
        try:
            resp = await agent_get(db, "/calls", timeout=30)
            resp.raise_for_status()
            calls: list[dict] = resp.json()
        except Exception as e:
            finish_progress("icloud_calls", lang=lang)
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [t("agent_unreachable_short", lang, error=e)]}

        total = len(calls)
        update_progress("icloud_calls", 0, total, t("calls_found", lang, count=total))

        all_contacts = db.query(models.Contact).join(models.ContactPhone).distinct().all()

        for i, call in enumerate(calls):
            update_progress("icloud_calls", i, total, t("call_progress", lang, current=i + 1, total=total))

            call_id = str(call.get("id", ""))
            source_key = f"icloud_calls:{call_id}"
            if not call_id or is_synced(db, "icloud_calls", source_key):
                skipped += 1
                continue

            phone_raw = call.get("phone") or ""
            call_name = call.get("name") or ""
            call_date_str = call.get("date") or ""
            duration_s: int = call.get("duration_s") or 0
            direction = call.get("direction") or "incoming"
            answered: bool = call.get("answered", True)

            try:
                call_datetime = datetime.fromisoformat(call_date_str) if call_date_str else None
            except ValueError:
                call_datetime = None
            call_date = call_datetime.date() if call_datetime else None

            matched_contacts: list[models.Contact] = []
            if phone_raw:
                for c in all_contacts:
                    if any(_phones_match(phone_raw, p.number) for p in c.phones):
                        matched_contacts.append(c)

            if not matched_contacts and call_name:
                matched_contacts = _match_contacts_by_name(call_name, db)

            if not matched_contacts:
                skipped += 1
                continue

            # Prefer our own contact record's (enriched, vorname+name) display
            # name over the raw name the OS/agent supplied — the phone's own
            # call history can have an incomplete name (e.g. only a surname
            # saved locally) even when our contact record has the full name.
            call_name = matched_contacts[0].display_name

            apps_by_id: dict[int, models.Application] = {}
            for c in matched_contacts:
                for a in c.applications:
                    apps_by_id[a.id] = a

            if not apps_by_id:
                skipped += 1
                continue

            # Calls sync previously had NO date filtering at all here — any
            # call, ever, to/from a matched contact's phone number/name got
            # attributed to every application that contact is linked to. A
            # real incident (2026-07-16, application #230): a coincidental
            # phone match attributed an unrelated personal call. Filter per
            # application since each has its own effective date floor. A
            # call with no parseable date at all is excluded too — see
            # _predates_bewerbung(): with nothing to compare, there's no
            # way to judge whether it's a genuine reaction to this application.
            app_ids = {
                app_id for app_id, app_obj in apps_by_id.items()
                if not _predates_bewerbung(call_date, app_obj)
            }
            if not app_ids:
                skipped += 1
                continue

            display_name = call_name or phone_raw
            if direction == "outgoing":
                titel = f"Anruf an {display_name}"
            else:
                titel = f"Anruf von {display_name}"
            if not answered:
                titel = f"↗ Verpasst: {display_name}" if direction == "outgoing" else f"↙ Verpasst: {display_name}"

            mins, secs = divmod(duration_s, 60)
            duration_str = f"{mins}:{secs:02d} min" if mins else f"{secs}s"
            time_str = call_date_str[11:16] if len(call_date_str) >= 16 else ""
            notiz = f"Dauer: {duration_str}" + (f"  ·  {time_str} Uhr" if time_str else "")

            for app_id in app_ids:
                call_event = models.Event(
                    application_id=app_id,
                    typ="anruf",
                    datum=call_date,
                    datum_zeit=_to_naive_utc(call_datetime),
                    titel=titel,
                    notiz=notiz,
                    source="icloud_calls",
                    external_id=source_key,
                    user_id=user_id,
                )
                db.add(call_event)
                db.flush()
                add_audit(db, "create", "icloud_calls", app_id=app_id, event_id=call_event.id,
                          new_value=titel, user_id=user_id)
                created += 1

            _mark_synced(db, "icloud_calls", source_key, user_id)
            processed += 1

        db.commit()
        calls_cfg.last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_calls", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_calls", lang=lang)
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/calls", response_model=schemas.SyncResult)
async def sync_calls(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    calls_cfg = _get_calls_cfg(db, current_user.id)
    if not calls_cfg.enabled:
        return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[t("calls_sync_disabled", current_user.ui_language)])

    set_batch_result("icloud_calls", {"done": False})
    init_progress("icloud_calls", t("label_call_list", current_user.ui_language), lang=current_user.ui_language)

    async def _bg():
        result = await _do_icloud_calls(current_user.id)
        set_batch_result("icloud_calls", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


def _mark_synced(db: Session, source: str, external_id: str, user_id: Optional[int] = None) -> None:
    """Insert a SyncedItem record (idempotent)."""
    existing = db.query(models.SyncedItem).filter_by(source=source, external_id=external_id).first()
    if not existing:
        db.add(models.SyncedItem(source=source, external_id=external_id, user_id=user_id))
        db.flush()
