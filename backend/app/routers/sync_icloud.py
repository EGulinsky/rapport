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

import email as email_lib
import hashlib
import imaplib
import os
import re
import html
from datetime import datetime, timedelta, timezone, date
from typing import Any, Optional
from xml.etree import ElementTree as ET

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models, schemas
from app.ai.provider import encrypt_api_key, decrypt_api_key, AINotConfigured, AIRateLimited
from app.routers.sync_common import (
    is_synced, purge_source,
    build_firm_index, build_contact_domain_index, find_hint_apps,
    process_item, strip_html,
    init_progress, update_progress, finish_progress,
    set_batch_result,
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


def _imap_connect(cfg: models.ICloudSync) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(_imap_user(cfg), decrypt_api_key(cfg.app_password_enc))
    return imap


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
def icloud_status(db: Session = Depends(get_db)):
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
def save_credentials(payload: schemas.ICloudCredentials, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    enc = encrypt_api_key(payload.app_password)
    web_enc = encrypt_api_key(payload.web_password) if payload.web_password else None
    if not cfg:
        cfg = models.ICloudSync(
            apple_id=payload.apple_id,
            icloud_email=payload.icloud_email or None,
            app_password_enc=enc,
            web_password_enc=web_enc,
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
def save_web_password(payload: schemas.ICloud2FAVerify, db: Session = Depends(get_db)):
    """Update only the Apple ID web password (used for pyicloud/Notes sync)."""
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")
    cfg.web_password_enc = encrypt_api_key(payload.code)
    _ICLOUD_SESSIONS.pop(cfg.apple_id, None)
    db.commit()


@router.post("/test")
def test_connection(db: Session = Depends(get_db)):
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
def delete_credentials(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        db.delete(cfg)
        db.commit()


# ── Mail ──────────────────────────────────────────────────────────────────────

@router.post("/mail/reset", status_code=204)
def reset_mail_sync(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.mail_last_sync = None
        purge_source(db, "icloud_mail")
        db.commit()


async def _do_icloud_mail() -> dict:
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    imap = None
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_mail")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Keine iCloud-Credentials gespeichert."]}

        _, term_to_apps = build_firm_index(db)
        contact_domain_index = build_contact_domain_index(db)

        update_progress("icloud_mail", 0, 0, "IMAP wird verbunden…")
        try:
            imap = _imap_connect(cfg)
            imap.select("INBOX")
            since = _since_date(cfg.mail_last_sync)
            _, msg_ids = imap.search(None, f'SINCE "{since}"')
            ids = msg_ids[0].split() if msg_ids[0] else []
        except Exception as e:
            finish_progress("icloud_mail")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"IMAP-Fehler: {e}"]}

        batch = ids[-100:]
        total = len(batch)
        update_progress("icloud_mail", 0, total, f"{total} Nachrichten gefunden")

        for i, msg_id_bytes in enumerate(batch):
            update_progress("icloud_mail", i, total, f"E-Mail {i + 1}/{total}")
            msg_id = msg_id_bytes.decode()

            if is_synced(db, "icloud_mail", msg_id):
                skipped += 1
                continue

            try:
                _, data = imap.fetch(msg_id_bytes, "(RFC822)")
                raw_email = data[0][1]
                msg = email_lib.message_from_bytes(raw_email)
            except Exception as e:
                errors.append(f"Nachricht {msg_id}: {e}")
                continue

            subject = msg.get("Subject", "(kein Betreff)")
            sender = msg.get("From", "")
            body = _imap_body(msg)[:1500]

            date_hint = None
            try:
                from email.utils import parsedate_to_datetime
                date_hint = parsedate_to_datetime(msg.get("Date", "")).astimezone(timezone.utc)
            except Exception:
                pass

            raw = f"Von: {sender}\nBetreff: {subject}\n\n{body}"
            hint_apps = find_hint_apps(raw, term_to_apps, contact_domain_index)

            try:
                ok = await process_item(db, "icloud_mail", msg_id, raw, date_hint, hint_apps=hint_apps or None)
            except AINotConfigured as e:
                finish_progress("icloud_mail")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("icloud_mail")
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
        finish_progress("icloud_mail")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_mail")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass
        db.close()


@router.post("/mail", response_model=schemas.SyncResult)
async def sync_mail(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_mail", {"done": False})
    init_progress("icloud_mail", "iCloud Mail", "Starte…")

    async def _bg():
        result = await _do_icloud_mail()
        set_batch_result("icloud_mail", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


# ── Notes (via pyicloud) ───────────────────────────────────────────────────────

@router.post("/notes/reset", status_code=204)
def reset_notes_sync(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.notes_last_sync = None
        purge_source(db, "icloud_notes")
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
    session_dir = f"/tmp/pyicloud_{hashlib.md5(apple_id.encode()).hexdigest()[:12]}"
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


async def _sync_notes_with_api(api: Any, cfg: models.ICloudSync, db: Session) -> schemas.SyncResult:
    _, term_to_apps = build_firm_index(db)
    processed = created = skipped = 0
    errors: list[str] = []

    init_progress("icloud_notes", "iCloud Notizen", "Notizen werden geladen…")
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
        finish_progress("icloud_notes")
        return schemas.SyncResult(
            processed=0, created=0, skipped=0,
            errors=[f"Notizen-Zugriff fehlgeschlagen: {e}"]
        )

    # Normalise to list
    if isinstance(raw_notes, dict):
        raw_notes = list(raw_notes.values())

    total = len(raw_notes)
    update_progress("icloud_notes", 0, total, f"{total} Notizen gefunden")

    for i, note in enumerate(raw_notes):
        update_progress("icloud_notes", i, total, f"Notiz {i + 1}/{total}")
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
            ok = await process_item(db, "icloud_notes", note_key, raw, None, hint_apps=hint_apps or None)
        except AINotConfigured as e:
            finish_progress("icloud_notes")
            raise HTTPException(400, str(e))
        except AIRateLimited as e:
            finish_progress("icloud_notes")
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
    finish_progress("icloud_notes")
    return schemas.SyncResult(processed=processed, created=created, skipped=skipped, errors=errors)


@router.post("/notes/verify-2fa", response_model=schemas.SyncResult)
async def verify_notes_2fa(payload: schemas.ICloud2FAVerify, db: Session = Depends(get_db)):
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

    return await _sync_notes_with_api(api, cfg, db)


NOTES_BRIDGE_URL = "http://host.docker.internal:9999/notes"


async def _do_icloud_notes() -> dict:
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_notes")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Keine iCloud-Credentials gespeichert."]}

        _, term_to_apps = build_firm_index(db)

        update_progress("icloud_notes", 0, 0, "Notes Bridge wird abgefragt…")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(NOTES_BRIDGE_URL)
            if resp.status_code != 200:
                err = resp.json().get('error', resp.text)
                finish_progress("icloud_notes")
                return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"Notes Bridge Fehler: {err}"]}
            notes = resp.json()
        except Exception as e:
            finish_progress("icloud_notes")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [
                f"Notes Bridge nicht erreichbar ({e}). Starte notes_bridge.py auf deinem Mac."
            ]}

        total = len(notes)
        update_progress("icloud_notes", 0, total, f"{total} Notizen gefunden")

        for i, note in enumerate(notes):
            update_progress("icloud_notes", i, total, f"Notiz {i + 1}/{total}")
            title = (note.get('name') or '').strip()
            body = (note.get('body') or '').strip()
            uid = note.get('id') or title
            if not body:
                skipped += 1
                continue

            note_key = hashlib.md5(uid.encode()).hexdigest()[:16]
            if is_synced(db, "icloud_notes", note_key):
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

            raw = f"Titel: {title}\n\n{body[:2000]}"
            hint_apps = find_hint_apps(raw, term_to_apps)

            try:
                ok = await process_item(db, "icloud_notes", note_key, raw, date_hint, hint_apps=hint_apps or None)
            except AINotConfigured as e:
                finish_progress("icloud_notes")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("icloud_notes")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [f"AI-Tageslimit: {e}"]}
            except Exception as e:
                errors.append(f"{title or uid}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.notes_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_notes")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_notes")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/notes", response_model=schemas.SyncResult)
async def sync_notes(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_notes", {"done": False})
    init_progress("icloud_notes", "iCloud Notizen", "Starte…")

    async def _bg():
        result = await _do_icloud_notes()
        set_batch_result("icloud_notes", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


@router.post("/notes/_legacy", response_model=schemas.SyncResult)
async def sync_notes_legacy(db: Session = Depends(get_db)):
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

    return await _sync_notes_with_api(api, cfg, db)


# ── Calendar (CalDAV) ─────────────────────────────────────────────────────────

@router.get("/calendar/debug")
def debug_calendar_events(db: Session = Depends(get_db)):
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
                summary = str(getattr(vevent, "summary", None) or "")
                desc = str(getattr(vevent, "description", None) or "")
                uid = str(getattr(vevent, "uid", None) or ev.url)
                dtstart = str(getattr(vevent, "dtstart", None) and vevent.dtstart.value or "")
            except Exception:
                continue
            combined_lower = (summary + " " + desc).lower()
            has_kw = any(kw in combined_lower for kw in JOB_KEYWORDS)
            matched_firms = [ft for ft in firm_terms_lower if ft in combined_lower]
            results.append({"cal": cal.name, "summary": summary, "dtstart": str(dtstart), "has_keyword": has_kw, "matched_firms": matched_firms, "uid": uid[:40]})
    return sorted(results, key=lambda x: x["dtstart"])


@router.post("/calendar/reset", status_code=204)
def reset_calendar_sync(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.calendar_last_sync = None
        purge_source(db, "icloud_cal")
        db.commit()


async def _do_icloud_cal() -> dict:
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_cal")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Keine iCloud-Credentials gespeichert."]}

        try:
            import caldav
        except ImportError:
            finish_progress("icloud_cal")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["caldav-Bibliothek nicht installiert."]}

        _, term_to_apps = build_firm_index(db)

        try:
            client = caldav.DAVClient(
                url=CALDAV_URL,
                username=cfg.apple_id,
                password=decrypt_api_key(cfg.app_password_enc),
            )
            principal = client.principal()
            calendars = principal.calendars()
        except Exception as e:
            finish_progress("icloud_cal")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"CalDAV-Fehler: {e}"]}

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=180)
        end = now + timedelta(days=90)

        JOB_KEYWORDS = {
            "interview", "gespräch", "vorstellungsgespräch", "bewerbung",
            "hr", "recruiting", "kennenlernen", "assessment", "onboarding",
        }
        firm_terms_lower = {t.lower() for t in term_to_apps}

        update_progress("icloud_cal", 0, 0, "Termine werden geladen…")
        all_events: list[tuple] = []
        for cal in calendars:
            try:
                for ev in cal.date_search(start=start, end=end, expand=True):
                    all_events.append(ev)
            except Exception as e:
                errors.append(f"Kalender {cal.name}: {e}")

        total = len(all_events)
        update_progress("icloud_cal", 0, total, f"{total} Termine gefunden")

        for i, ev in enumerate(all_events):
            update_progress("icloud_cal", i, total, f"Termin {i + 1}/{total}")
            try:
                vevent = ev.vobject_instance.vevent
                summary = str(getattr(vevent, "summary", None) or "")
                desc = str(getattr(vevent, "description", None) or "")
                uid = str(getattr(vevent, "uid", None) or ev.url)
            except Exception:
                continue

            combined_lower = (summary + " " + desc).lower()
            has_keyword = any(kw in combined_lower for kw in JOB_KEYWORDS)
            has_firm = any(ft in combined_lower for ft in firm_terms_lower)
            if not has_keyword and not has_firm:
                skipped += 1
                continue

            if is_synced(db, "icloud_cal", uid):
                skipped += 1
                continue

            date_hint = None
            try:
                dtstart = vevent.dtstart.value
                if isinstance(dtstart, datetime):
                    date_hint = dtstart.astimezone(timezone.utc) if dtstart.tzinfo else dtstart.replace(tzinfo=timezone.utc)
                elif isinstance(dtstart, date):
                    date_hint = datetime(dtstart.year, dtstart.month, dtstart.day, tzinfo=timezone.utc)
            except Exception:
                pass

            location = str(getattr(vevent, "location", None) or "")
            raw = f"Titel: {summary}\nOrt: {location}\nBeschreibung: {desc[:800]}"
            hint_apps = find_hint_apps(raw, term_to_apps)

            try:
                ok = await process_item(db, "icloud_cal", uid, raw, date_hint, hint_apps=hint_apps or None)
            except AINotConfigured as e:
                finish_progress("icloud_cal")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("icloud_cal")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [f"AI-Tageslimit: {e}"]}
            except Exception as e:
                errors.append(f"{summary or uid}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.calendar_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_cal")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_cal")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/calendar", response_model=schemas.SyncResult)
async def sync_calendar(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_cal", {"done": False})
    init_progress("icloud_cal", "iCloud Kalender", "Starte…")

    async def _bg():
        result = await _do_icloud_cal()
        set_batch_result("icloud_cal", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


# ── Reminders (CalDAV VTODO) ──────────────────────────────────────────────────

@router.post("/reminders/reset", status_code=204)
def reset_reminders_sync(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if cfg:
        cfg.reminders_last_sync = None
        purge_source(db, "icloud_todo")
        db.commit()


async def _do_icloud_reminders() -> dict:
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        cfg = db.query(models.ICloudSync).first()
        if not cfg:
            finish_progress("icloud_reminders")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Keine iCloud-Credentials gespeichert."]}

        try:
            import caldav
        except ImportError:
            finish_progress("icloud_reminders")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["caldav-Bibliothek nicht installiert."]}

        _, term_to_apps = build_firm_index(db)

        try:
            client = caldav.DAVClient(
                url=CALDAV_URL,
                username=cfg.apple_id,
                password=decrypt_api_key(cfg.app_password_enc),
            )
            principal = client.principal()
            calendars = principal.calendars()
        except Exception as e:
            finish_progress("icloud_reminders")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"CalDAV-Fehler: {e}"]}

        firm_terms_lower = {t.lower() for t in term_to_apps}

        update_progress("icloud_reminders", 0, 0, "Erinnerungen werden geladen…")
        all_todos = []
        for cal in calendars:
            try:
                all_todos.extend(cal.todos())
            except Exception:
                pass

        total = len(all_todos)
        update_progress("icloud_reminders", 0, total, f"{total} Erinnerungen gefunden")

        for i, todo in enumerate(all_todos):
            update_progress("icloud_reminders", i, total, f"Erinnerung {i + 1}/{total}")
            try:
                vtodo = todo.vobject_instance.vtodo
                summary = str(getattr(vtodo, "summary", None) or "")
                desc = str(getattr(vtodo, "description", None) or "")
                uid = str(getattr(vtodo, "uid", None) or todo.url)
            except Exception:
                continue

            combined_lower = (summary + " " + desc).lower()
            if not any(ft in combined_lower for ft in firm_terms_lower):
                skipped += 1
                continue

            if is_synced(db, "icloud_todo", uid):
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
                ok = await process_item(db, "icloud_todo", uid, raw, date_hint, hint_apps=hint_apps or None)
            except AINotConfigured as e:
                finish_progress("icloud_reminders")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
            except AIRateLimited as e:
                finish_progress("icloud_reminders")
                return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [f"AI-Tageslimit: {e}"]}
            except Exception as e:
                errors.append(f"{summary or uid}: {e}")
                continue

            processed += 1
            if ok:
                created += 1

        db.commit()
        cfg.reminders_last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_reminders")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_reminders")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/reminders", response_model=schemas.SyncResult)
async def sync_reminders(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    set_batch_result("icloud_reminders", {"done": False})
    init_progress("icloud_reminders", "iCloud Erinnerungen", "Starte…")

    async def _bg():
        result = await _do_icloud_reminders()
        set_batch_result("icloud_reminders", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


# ── Contacts (CardDAV) ────────────────────────────────────────────────────────

@router.post("/contacts/reset", status_code=204)
def reset_contacts_sync(db: Session = Depends(get_db)):
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
async def sync_contacts(db: Session = Depends(get_db)):
    cfg = _get_cfg(db)
    if not cfg:
        raise HTTPException(400, "Keine iCloud-Credentials gespeichert.")

    init_progress("icloud_contacts", "iCloud Kontakte", "Kontakte werden geladen…")
    created, errors = await _sync_contacts_http(cfg, db)

    # Backfill missing application links for already-imported contacts (mention-based)
    update_progress("icloud_contacts", 0, 1, "Verlinkungen werden aktualisiert…")
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
    finish_progress("icloud_contacts")

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


async def _sync_contacts_http(cfg: models.ICloudSync, db: Session) -> tuple[int, list[str]]:
    """CardDAV sync via HTTP using fetch_all_vcards helper."""
    import vobject

    processed = created = 0
    errors: list[str] = []

    try:
        vcards_raw = await fetch_all_vcards(cfg)
    except Exception as e:
        return 0, [f"CardDAV HTTP-Fehler: {e}"]

    if not vcards_raw:
        return 0, ["Keine vCards gefunden (CardDAV)"]

    total_vcards = len(vcards_raw)
    update_progress("icloud_contacts", 0, total_vcards, f"{total_vcards} Kontakte gefunden")

    for idx, raw_vcard in enumerate(vcards_raw):
        update_progress("icloud_contacts", idx, total_vcards, f"Kontakt {idx + 1}/{total_vcards}")
        try:
            card = vobject.readOne(raw_vcard)
        except Exception:
            continue

        try:
            name = str(card.fn.value) if hasattr(card, "fn") else ""
            if not name:
                continue

            email_val = str(card.email.value) if hasattr(card, "email") else None
            tel_val = None
            _tel_props = card.contents.get("tel", [])
            if _tel_props:
                _cell = None
                _first = str(_tel_props[0].value)
                for _tp in _tel_props:
                    _type_str = str(getattr(_tp, "params", {}).get("TYPE", "")).upper()
                    if any(t in _type_str for t in ("CELL", "IPHONE", "MOBILE")):
                        _cell = str(_tp.value)
                        break
                tel_val = _cell or _first
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

            existing = None
            if email_val:
                existing = db.query(models.Contact).filter_by(email=email_val).first()
            if not existing:
                existing = db.query(models.Contact).filter_by(name=name).first()
            if existing:
                if linkedin_url and not existing.linkedin_url:
                    existing.linkedin_url = linkedin_url
                if tel_val and not existing.telefon:
                    existing.telefon = tel_val
                if org_val and not existing.firma:
                    existing.firma = org_val
                if title_val and not existing.rolle:
                    existing.rolle = title_val
                continue

            mention_app_ids = _find_apps_where_contact_mentioned(name, email_val, db)
            if not mention_app_ids:
                continue

            company_app_ids = _find_apps_for_contact(org_val, db)
            all_app_ids = list(set(mention_app_ids) | set(company_app_ids))

            contact = models.Contact(
                name=name, email=email_val, telefon=tel_val,
                firma=org_val, rolle=title_val, linkedin_url=linkedin_url,
            )
            db.add(contact)
            db.flush()
            for aid in all_app_ids:
                app_obj = db.query(models.Application).get(aid)
                if app_obj:
                    contact.applications.append(app_obj)
            processed += 1
            created += 1
        except Exception as e:
            errors.append(f"Kontakt: {e}")

    return created, errors


# ── Anrufliste (Calls Bridge) ────────────────────────────────────────────────

CALLS_BRIDGE_URL = os.getenv("CALLS_BRIDGE_URL", "http://host.docker.internal:9997/calls")


def _get_calls_cfg(db: Session) -> models.CallsConfig:
    cfg = db.query(models.CallsConfig).first()
    if not cfg:
        cfg = models.CallsConfig(enabled=True)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/calls/status", response_model=schemas.CallsStatus)
async def calls_status(db: Session = Depends(get_db)):
    import httpx
    cfg = _get_calls_cfg(db)
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(CALLS_BRIDGE_URL.replace("/calls", "/health"))
            reachable = resp.status_code == 200
    except Exception:
        pass
    return schemas.CallsStatus(
        enabled=cfg.enabled,
        last_sync=cfg.last_sync,
        bridge_reachable=reachable,
    )


@router.post("/calls/settings", response_model=schemas.CallsStatus)
async def calls_settings(body: dict, db: Session = Depends(get_db)):
    import httpx
    cfg = _get_calls_cfg(db)
    if "enabled" in body:
        cfg.enabled = bool(body["enabled"])
        db.commit()
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(CALLS_BRIDGE_URL.replace("/calls", "/health"))
            reachable = resp.status_code == 200
    except Exception:
        pass
    return schemas.CallsStatus(enabled=cfg.enabled, last_sync=cfg.last_sync, bridge_reachable=reachable)


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
def reset_calls_sync(db: Session = Depends(get_db)):
    calls_cfg = _get_calls_cfg(db)
    calls_cfg.last_sync = None
    purge_source(db, "icloud_calls")
    db.query(models.Event).filter_by(source="icloud_calls").delete()
    db.commit()


async def _do_icloud_calls() -> dict:
    import httpx
    db = SessionLocal()
    processed = created = skipped = 0
    errors: list[str] = []
    try:
        calls_cfg = _get_calls_cfg(db)
        if not calls_cfg.enabled:
            finish_progress("icloud_calls")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": ["Anrufliste-Sync deaktiviert"]}

        update_progress("icloud_calls", 0, 0, "Anrufe werden geladen…")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(CALLS_BRIDGE_URL)
                resp.raise_for_status()
                calls: list[dict] = resp.json()
        except Exception as e:
            finish_progress("icloud_calls")
            return {"processed": 0, "created": 0, "skipped": 0, "errors": [f"Calls bridge nicht erreichbar: {e}"]}

        total = len(calls)
        update_progress("icloud_calls", 0, total, f"{total} Anrufe gefunden")

        all_contacts = db.query(models.Contact).filter(models.Contact.telefon != None).all()  # noqa

        for i, call in enumerate(calls):
            update_progress("icloud_calls", i, total, f"Anruf {i + 1}/{total}")

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
                call_date = datetime.fromisoformat(call_date_str).date() if call_date_str else None
            except ValueError:
                call_date = None

            matched_contacts: list[models.Contact] = []
            if phone_raw:
                for c in all_contacts:
                    if c.telefon and _phones_match(phone_raw, c.telefon):
                        matched_contacts.append(c)

            if not matched_contacts and call_name:
                matched_contacts = _match_contacts_by_name(call_name, db)

            if not matched_contacts:
                skipped += 1
                continue

            if not call_name and matched_contacts:
                call_name = matched_contacts[0].name

            app_ids: set[int] = set()
            for c in matched_contacts:
                for a in c.applications:
                    app_ids.add(a.id)

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
                db.add(models.Event(
                    application_id=app_id,
                    typ="anruf",
                    datum=call_date,
                    titel=titel,
                    notiz=notiz,
                    source="icloud_calls",
                ))
                created += 1

            _mark_synced(db, "icloud_calls", source_key)
            processed += 1

        db.commit()
        calls_cfg.last_sync = datetime.now(timezone.utc)
        db.commit()
        finish_progress("icloud_calls")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors}
    except Exception as e:
        finish_progress("icloud_calls")
        return {"processed": processed, "created": created, "skipped": skipped, "errors": errors + [str(e)]}
    finally:
        db.close()


@router.post("/calls", response_model=schemas.SyncResult)
async def sync_calls(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    calls_cfg = _get_calls_cfg(db)
    if not calls_cfg.enabled:
        return schemas.SyncResult(processed=0, created=0, skipped=0, errors=["Anrufliste-Sync deaktiviert"])

    set_batch_result("icloud_calls", {"done": False})
    init_progress("icloud_calls", "Anrufliste", "Starte…")

    async def _bg():
        result = await _do_icloud_calls()
        set_batch_result("icloud_calls", {**result, "done": True})

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


def _mark_synced(db: Session, source: str, external_id: str) -> None:
    """Insert a SyncedItem record (idempotent)."""
    existing = db.query(models.SyncedItem).filter_by(source=source, external_id=external_id).first()
    if not existing:
        db.add(models.SyncedItem(source=source, external_id=external_id))
        db.flush()
