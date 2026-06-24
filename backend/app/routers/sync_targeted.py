"""
Targeted single-application sync.

For each source (Gmail, Google Calendar, iCloud Mail, iCloud Calendar,
iCloud Notes, Calls) it searches specifically for content related to
one application (by firm name + zielfirma variants) and classifies
items against that one application only — much more accurate than
the global sync which must choose among all active applications.
"""
from __future__ import annotations

import asyncio
import email as email_lib
import hashlib
import re as _re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models, schemas
from app.ai.provider import AINotConfigured, AIRateLimited, decrypt_api_key
from app.routers.sync_common import (
    is_synced, mark_synced, strip_html,
    term_variants, process_item_for_app, save_classified_event,
    init_progress, update_progress, finish_progress,
    upsert_contact_from_sender,
)
from app.ai.tasks import classify_batch_for_app, BATCH_SIZE

router = APIRouter(prefix="/api/sync/targeted", tags=["sync"])


def _search_terms(app: models.Application, db: Session) -> list[str]:
    """All unique search terms for this application (firm + zielfirma variants).

    Also includes alias_firma names from merged duplicates so that e-mails
    referencing the old company name are still found after a merge.
    """
    seen: set[str] = set()
    result: list[str] = []
    raws = [app.firma, app.zielfirma_bei_hh, app.wurde_besetzt_von]
    aliases = db.query(models.MergeAlias).filter(
        models.MergeAlias.entity_type == "application",
        models.MergeAlias.canonical_id == app.id,
        models.MergeAlias.alias_firma.isnot(None),
    ).all()
    raws += [a.alias_firma for a in aliases]
    for raw in raws:
        if raw and len(raw.strip()) >= 3:
            for v in term_variants(raw):
                vl = v.lower()
                if vl not in seen:
                    seen.add(vl)
                    result.append(v)
    return result


def _app_dict(app: models.Application) -> dict:
    d: dict = {"id": app.id, "firma": app.firma, "rolle": app.rolle, "is_headhunter": app.is_headhunter}
    if app.zielfirma_bei_hh:
        d["zielfirma"] = app.zielfirma_bei_hh
    return d


def _text_matches(text: str, terms: list[str]) -> bool:
    tl = text.lower()
    return any(t.lower() in tl for t in terms)


def _query_safe(term: str) -> str:
    """Return a search-safe version of a term: replace + and other operators with space,
    strip leading/trailing punctuation from each word."""
    clean = _re.sub(r'[+&|]', ' ', term)          # operators → space
    clean = _re.sub(r'[()[\]{}]', '', clean)        # brackets → remove
    clean = _re.sub(r'\s+', ' ', clean).strip()
    return clean


def _role_query_words(rolle: str) -> list[str]:
    """Extract clean search keywords from a role title (strip punctuation, skip short words)."""
    words = _re.split(r'[\s/()[\]{}]+', rolle)
    result = []
    for w in words:
        w = w.strip('.,;:!?-+&|"\'')
        if len(w) >= 5 and w not in result:
            result.append(w)
    return result


# ── Gmail ─────────────────────────────────────────────────────────────────────

async def _sync_gmail_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session) -> tuple[int, int, list[str]]:
    from app.routers.sync_google import _get_cfg as _get_google_cfg, _refresh_if_needed, _gmail_body
    cfg = _get_google_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        return 0, 0, []

    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    since = datetime.now(timezone.utc) - timedelta(days=365)
    after_ts = int(since.timestamp())

    # Build search terms: use clean versions (no +/operators) for the query,
    # but keep originals for in-Python text matching later.
    clean_terms = list(dict.fromkeys(_query_safe(t) for t in terms if _query_safe(t)))
    term_clause = " OR ".join(f'"{t}"' for t in clean_terms)

    role_words = _role_query_words(app.rolle or "")
    if role_words:
        role_clause = " OR ".join(f'"{w}"' for w in role_words[:3])
        query = f"after:{after_ts} ({term_clause}) ({role_clause})"
    else:
        query = f"after:{after_ts} ({term_clause})"

    messages: list[dict] = []
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
        return 0, 0, [f"Gmail API: {e}"]

    created = skipped = 0
    errors: list[str] = []
    total = len(messages)

    # Phase 1: fetch unsynced messages
    pending: list[dict] = []
    for i, msg_ref in enumerate(messages):
        update_progress("targeted_gmail", i, total, f"Gmail laden {i+1}/{total}")
        msg_id = msg_ref["id"]
        if is_synced(db, "gmail", msg_id):
            skipped += 1
            continue
        try:
            msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        except Exception as e:
            errors.append(f"gmail/{msg_id}: {e}")
            continue

        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("subject", "(kein Betreff)")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")
        body = _gmail_body(msg["payload"])[:1500]

        date_hint = None
        try:
            from email.utils import parsedate_to_datetime
            date_hint = parsedate_to_datetime(date_str).astimezone(timezone.utc)
        except Exception:
            pass

        # Skip reaction/like notifications — no informational content
        if "reacted to your message" in body.lower() or "liked your message" in body.lower():
            mark_synced(db, "gmail", msg_id)
            skipped += 1
            continue

        pending.append({"id": msg_id, "raw": f"Von: {sender}\nBetreff: {subject}\n\n{body}", "date_hint": date_hint})

    # Phase 2: batch classify
    n_pending = len(pending)
    for batch_start in range(0, n_pending, BATCH_SIZE):
        batch = pending[batch_start:batch_start + BATCH_SIZE]
        end = min(batch_start + len(batch), n_pending)
        update_progress("targeted_gmail", batch_start, n_pending, f"Gmail KI {batch_start+1}–{end}/{n_pending}")
        try:
            results = await classify_batch_for_app(db, "gmail", batch, app_dict)
        except (AINotConfigured, AIRateLimited):
            raise
        except Exception as e:
            errors.append(f"gmail batch: {e}")
            continue
        for item, result in zip(batch, results):
            try:
                ok = save_classified_event(db, "gmail", item["id"], result, item["raw"], item["date_hint"], app_dict)
                if ok:
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"gmail/{item['id']}: {e}")

    return created, total, errors


# ── Google Calendar ───────────────────────────────────────────────────────────

async def _sync_gcal_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session) -> tuple[int, int, list[str]]:
    from app.routers.sync_google import _get_cfg as _get_google_cfg, _refresh_if_needed
    cfg = _get_google_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        return 0, 0, []

    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.now(timezone.utc)
    try:
        events_result = service.events().list(
            calendarId="primary",
            timeMin=(now - timedelta(days=365)).isoformat(),
            timeMax=(now + timedelta(days=90)).isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=500,
        ).execute()
    except Exception as e:
        return 0, 0, [f"Google Calendar: {e}"]

    cal_events = [
        ev for ev in events_result.get("items", [])
        if _text_matches((ev.get("summary") or "") + " " + (ev.get("description") or ""), terms)
    ]
    created = skipped = 0
    errors: list[str] = []

    for ev in cal_events:
        ev_id = ev.get("id", "")
        if is_synced(db, "gcal", ev_id):
            skipped += 1
            continue

        summary = ev.get("summary", "") or ""
        desc = ev.get("description", "") or ""
        location = ev.get("location", "")
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

        date_hint = None
        time_info = ""
        try:
            start_raw = ev.get("start", {})
            end_raw = ev.get("end", {})
            dt_str = start_raw.get("dateTime") or start_raw.get("date")
            if dt_str:
                date_hint = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            start_dt_str = start_raw.get("dateTime")
            end_dt_str = end_raw.get("dateTime")
            if start_dt_str:
                s = datetime.fromisoformat(start_dt_str.replace("Z", "+00:00")).astimezone()
                time_info = s.strftime("%H:%M")
                if end_dt_str:
                    e2 = datetime.fromisoformat(end_dt_str.replace("Z", "+00:00")).astimezone()
                    mins = int((e2 - s).total_seconds() / 60)
                    h, m = divmod(mins, 60)
                    dur = f"{h}h {m:02d}min" if h else f"{m}min"
                    time_info += f"–{e2.strftime('%H:%M')} Uhr ({dur})"
                else:
                    time_info += " Uhr"
        except Exception:
            pass

        # Calendar events that match the company name are directly relevant — no AI needed.
        notiz_parts = []
        if time_info:
            notiz_parts.append(time_info)
        if location:
            notiz_parts.append(f"Ort: {location}")
        body = strip_html(desc)[:400].strip()
        if body:
            notiz_parts.append(body)
        notiz = "\n".join(notiz_parts) or None

        try:
            db.add(models.Event(
                application_id=app_dict["id"],
                typ="gespräch",
                datum=date_hint.date() if date_hint else None,
                titel=summary or "Kalendertermin",
                notiz=notiz,
                source="gcal",
            ))
            mark_synced(db, "gcal", ev_id)
            created += 1
            # Auto-create contacts from organizer + attendees
            event_date = date_hint.date() if date_hint else None
            for raw in participants:
                upsert_contact_from_sender(
                    db, raw,
                    app_id=app_dict["id"],
                    firma=app_dict.get("firma", ""),
                    is_headhunter=app_dict.get("is_headhunter", False),
                    event_date=event_date,
                )
        except Exception as e:
            errors.append(f"gcal/{summary}: {e}")

    return created, len(cal_events), errors


# ── iCloud Mail ───────────────────────────────────────────────────────────────

async def _sync_icloud_mail_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session) -> tuple[int, int, list[str]]:
    from app.routers.sync_icloud import _get_cfg as _get_icloud_cfg, _imap_connect, _imap_body
    cfg = _get_icloud_cfg(db)
    if not cfg:
        return 0, 0, []

    created = skipped = 0
    errors: list[str] = []
    # Use a clean version of the primary term for IMAP TEXT search (+ and operators break it)
    raw_primary = terms[0] if terms else (app.firma or "")
    primary_term = _query_safe(raw_primary)

    try:
        imap = _imap_connect(cfg)
        imap.select("INBOX")
        _, msg_ids = imap.search(None, f'TEXT "{primary_term}"')
        ids = msg_ids[0].split() if msg_ids[0] else []
    except Exception as e:
        return 0, 0, [f"iCloud Mail IMAP: {e}"]

    total = len(ids)

    # Phase 1: fetch unsynced messages
    pending: list[dict] = []
    for i, msg_id_bytes in enumerate(ids):
        update_progress("targeted_icloud_mail", i, total, f"iCloud Mail laden {i+1}/{total}")
        msg_id = msg_id_bytes.decode()
        if is_synced(db, "icloud_mail", msg_id):
            skipped += 1
            continue
        try:
            _, data = imap.fetch(msg_id_bytes, "(RFC822)")
            raw_email = data[0][1]
            msg = email_lib.message_from_bytes(raw_email)
        except Exception as e:
            errors.append(f"icloud_mail/{msg_id}: {e}")
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
        if not _text_matches(raw, terms):
            skipped += 1
            continue

        pending.append({"id": msg_id, "raw": raw, "date_hint": date_hint})

    try:
        imap.logout()
    except Exception:
        pass

    # Phase 2: batch classify
    n_pending = len(pending)
    for batch_start in range(0, n_pending, BATCH_SIZE):
        batch = pending[batch_start:batch_start + BATCH_SIZE]
        end = min(batch_start + len(batch), n_pending)
        update_progress("targeted_icloud_mail", batch_start, n_pending, f"iCloud Mail KI {batch_start+1}–{end}/{n_pending}")
        try:
            results = await classify_batch_for_app(db, "icloud_mail", batch, app_dict)
        except (AINotConfigured, AIRateLimited):
            raise
        except Exception as e:
            errors.append(f"icloud_mail batch: {e}")
            continue
        for item, result in zip(batch, results):
            try:
                ok = save_classified_event(db, "icloud_mail", item["id"], result, item["raw"], item["date_hint"], app_dict)
                if ok:
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"icloud_mail/{item['id']}: {e}")

    return created, total, errors


def _vobj_str(vevent, attr: str) -> str:
    """Extract plain string value from a vObject attribute (avoids '<ATTR{}>...' repr)."""
    obj = getattr(vevent, attr, None)
    if obj is None:
        return ""
    return str(getattr(obj, "value", None) or obj or "")


# ── iCloud Calendar ───────────────────────────────────────────────────────────

async def _sync_icloud_cal_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session) -> tuple[int, int, list[str]]:
    from app.routers.sync_icloud import _get_cfg as _get_icloud_cfg, CALDAV_URL
    cfg = _get_icloud_cfg(db)
    if not cfg:
        return 0, 0, []

    try:
        import caldav
    except ImportError:
        return 0, 0, ["caldav nicht installiert"]

    created = skipped = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc)

    try:
        client = caldav.DAVClient(url=CALDAV_URL, username=cfg.apple_id, password=decrypt_api_key(cfg.app_password_enc))
        calendars = client.principal().calendars()
    except Exception as e:
        return 0, 0, [f"iCloud CalDAV: {e}"]

    matched_events: list = []
    for cal in calendars:
        try:
            for ev in cal.date_search(start=now - timedelta(days=365), end=now + timedelta(days=90), expand=True):
                try:
                    vevent = ev.vobject_instance.vevent
                    summary = _vobj_str(vevent, "summary")
                    desc = _vobj_str(vevent, "description")
                    if _text_matches(summary + " " + desc, terms):
                        matched_events.append(ev)
                except Exception:
                    continue
        except Exception as e:
            errors.append(f"Kalender {cal.name}: {e}")

    for ev in matched_events:
        try:
            vevent = ev.vobject_instance.vevent
            summary = _vobj_str(vevent, "summary")
            desc = _vobj_str(vevent, "description")
            uid = _vobj_str(vevent, "uid") or str(ev.url)
        except Exception:
            continue

        if is_synced(db, "icloud_cal", uid):
            skipped += 1
            continue

        date_hint = None
        time_info = ""
        try:
            dtstart = vevent.dtstart.value
            if isinstance(dtstart, datetime):
                date_hint = dtstart.astimezone(timezone.utc) if dtstart.tzinfo else dtstart.replace(tzinfo=timezone.utc)
                s = dtstart.astimezone() if dtstart.tzinfo else dtstart
                time_info = s.strftime("%H:%M")
                dtend_obj = getattr(vevent, "dtend", None)
                if dtend_obj:
                    dtend = dtend_obj.value
                    if isinstance(dtend, datetime):
                        e2 = dtend.astimezone() if dtend.tzinfo else dtend
                        mins = int((e2 - s).total_seconds() / 60)
                        h, m = divmod(mins, 60)
                        dur = f"{h}h {m:02d}min" if h else f"{m}min"
                        time_info += f"–{e2.strftime('%H:%M')} Uhr ({dur})"
                    else:
                        time_info += " Uhr"
                else:
                    time_info += " Uhr"
            elif isinstance(dtstart, date):
                date_hint = datetime(dtstart.year, dtstart.month, dtstart.day, tzinfo=timezone.utc)
        except Exception:
            pass

        location = _vobj_str(vevent, "location")

        # Extract participants from vObject organizer + attendees
        ical_participants: list[str] = []
        for prop_name in ("organizer", "attendee"):
            for comp in vevent.contents.get(prop_name, []):
                try:
                    mailto = comp.value or ""
                    addr = mailto.replace("mailto:", "").replace("MAILTO:", "").strip()
                    cn = (comp.params.get("CN") or [""])[0]
                    ical_participants.append(f"{cn} <{addr}>" if cn else addr)
                except Exception:
                    pass

        # Calendar events that explicitly mention the company are directly relevant —
        # skip AI classification and create the event immediately.
        notiz_parts = []
        if time_info:
            notiz_parts.append(time_info)
        if location:
            notiz_parts.append(f"Ort: {location}")
        if desc.strip():
            notiz_parts.append(desc[:400])
        notiz = "\n".join(notiz_parts) or None

        try:
            db.add(models.Event(
                application_id=app_dict["id"],
                typ="gespräch",
                datum=date_hint.date() if date_hint else None,
                titel=summary or "Kalendertermin",
                notiz=notiz,
                source="icloud_cal",
            ))
            mark_synced(db, "icloud_cal", uid)
            created += 1
            # Auto-create contacts from calendar participants
            event_date = date_hint.date() if date_hint else None
            for raw in ical_participants:
                upsert_contact_from_sender(
                    db, raw,
                    app_id=app_dict["id"],
                    firma=app_dict.get("firma", ""),
                    is_headhunter=app_dict.get("is_headhunter", False),
                    event_date=event_date,
                )
            continue
        except Exception as e:
            errors.append(f"icloud_cal/{summary}: {e}")
            continue
    return created, len(matched_events), errors


# ── iCloud Notes ──────────────────────────────────────────────────────────────

async def _sync_icloud_notes_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session) -> tuple[int, int, list[str]]:
    NOTES_BRIDGE_URL = "http://host.docker.internal:9999/notes"
    created = skipped = 0
    errors: list[str] = []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(NOTES_BRIDGE_URL)
        if resp.status_code != 200:
            return 0, 0, [f"Notes Bridge: {resp.text[:200]}"]
        notes = resp.json()
    except Exception as e:
        return 0, 0, [f"Notes Bridge nicht erreichbar: {e}"]

    # Smart filter: always include text-matching notes (company/role in title/body) +
    # the 30 most recent notes (relevant notes often don't mention the company by name).
    # This avoids sending hundreds of old unrelated notes through AI on every targeted sync.
    notes_sorted = sorted(notes, key=lambda n: n.get("date") or n.get("creationDate") or "", reverse=True)
    matching = [n for n in notes_sorted if _text_matches((n.get("name") or "") + " " + (n.get("body") or ""), terms)]
    matching_ids = {n.get("id") for n in matching}
    recent = [n for n in notes_sorted if n.get("id") not in matching_ids][:30]
    candidates = (matching + recent)[:50]

    for note in candidates:
        title = (note.get("name") or "").strip()
        body = (note.get("body") or "").strip()
        uid = note.get("id") or title
        note_key = hashlib.md5(uid.encode()).hexdigest()[:16]

        if is_synced(db, "icloud_notes", note_key):
            skipped += 1
            continue

        date_hint = None
        for date_field in ("creationDate", "date"):
            raw_date = note.get(date_field) or ""
            if raw_date:
                try:
                    date_hint = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).astimezone(timezone.utc)
                    break
                except Exception:
                    pass

        raw = f"Titel: {title}\n\n{body[:2000]}"
        try:
            ok = await process_item_for_app(db, "icloud_notes", note_key, raw, date_hint, app_dict)
        except (AINotConfigured, AIRateLimited):
            raise
        except Exception as e:
            errors.append(f"note/{title}: {e}")
            continue
        if ok:
            created += 1
        else:
            skipped += 1

    return created, len(candidates), errors


# ── iCloud Contacts ───────────────────────────────────────────────────────────

async def _sync_contacts_for_app(app: models.Application, terms: list[str], db: Session) -> tuple[int, int, list[str]]:
    from app.routers.sync_icloud import _get_cfg as _get_icloud_cfg, fetch_all_vcards
    cfg = _get_icloud_cfg(db)
    if not cfg:
        return 0, 0, []

    try:
        import vobject
        vcards_raw = await fetch_all_vcards(cfg)
    except Exception as e:
        return 0, 0, [f"CardDAV: {e}"]

    if not vcards_raw:
        return 0, 0, []

    created = skipped = 0
    errors: list[str] = []

    for raw_vcard in vcards_raw:
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
                    if any(t in str(getattr(_tp, "params", {}).get("TYPE", "")).upper() for t in ("CELL", "IPHONE", "MOBILE")):
                        _cell = str(_tp.value)
                        break
                tel_val = _cell or _first
            org_val = None
            if hasattr(card, "org"):
                parts = card.org.value
                org_val = (parts[0] if isinstance(parts, list) and parts else str(parts)).strip() or None
            title_val = str(card.title.value) if hasattr(card, "title") else None
            linkedin_url = None
            for url_prop in card.contents.get("url", []) + card.contents.get("item1.url", []):
                if "linkedin.com" in str(url_prop.value):
                    linkedin_url = str(url_prop.value)
                    break

            # Gate: contact must match by company name OR be mentioned in this app's events/text
            org_matches = org_val and _text_matches(org_val, terms)
            name_in_app_text = _contact_mentioned_in_app(name, email_val, app, db)
            if not org_matches and not name_in_app_text:
                skipped += 1
                continue

            # Upsert
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
                db.execute(text(
                    "INSERT OR IGNORE INTO contact_application (contact_id, application_id) VALUES (:c, :a)"
                ), {"c": existing.id, "a": app.id})
            else:
                contact = models.Contact(
                    name=name, email=email_val, telefon=tel_val,
                    firma=org_val, rolle=title_val, linkedin_url=linkedin_url,
                )
                db.add(contact)
                db.flush()
                db.execute(text(
                    "INSERT OR IGNORE INTO contact_application (contact_id, application_id) VALUES (:c, :a)"
                ), {"c": contact.id, "a": app.id})
                created += 1
        except Exception as e:
            errors.append(f"Kontakt {name if 'name' in dir() else '?'}: {e}")

    return created, len(vcards_raw), errors


def _contact_mentioned_in_app(name: str, email: Optional[str], app: models.Application, db: Session) -> bool:
    """Check if this contact is named in any event or text field of the given application."""
    name_lower = name.lower()
    search_fields = [
        app.kommentar, app.gespraech_1, app.gespraech_2,
        app.gespraech_3, app.gespraech_4, app.gespraech_5,
    ]
    for f in search_fields:
        if f and name_lower in f.lower():
            return True
    events = db.query(models.Event).filter_by(application_id=app.id).all()
    for ev in events:
        for field in [ev.titel, ev.notiz, ev.autor]:
            if field and name_lower in field.lower():
                return True
        if email:
            for field in [ev.titel, ev.notiz, ev.autor]:
                if field and email.lower() in field.lower():
                    return True
    return False


# ── iCloud Reminders ─────────────────────────────────────────────────────────

async def _sync_icloud_reminders_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session) -> tuple[int, int, list[str]]:
    from app.routers.sync_icloud import _get_cfg as _get_icloud_cfg, CALDAV_URL
    cfg = _get_icloud_cfg(db)
    if not cfg:
        return 0, 0, []

    try:
        import caldav
    except ImportError:
        return 0, 0, ["caldav nicht installiert"]

    created = skipped = 0
    errors: list[str] = []

    try:
        client = caldav.DAVClient(url=CALDAV_URL, username=cfg.apple_id, password=decrypt_api_key(cfg.app_password_enc))
        calendars = client.principal().calendars()
    except Exception as e:
        return 0, 0, [f"iCloud Reminders CalDAV: {e}"]

    matched_todos: list = []
    for cal in calendars:
        try:
            for todo in cal.todos():
                try:
                    vtodo = todo.vobject_instance.vtodo
                    summary = str(getattr(vtodo, "summary", None) or "")
                    desc = str(getattr(vtodo, "description", None) or "")
                    if _text_matches(summary + " " + desc, terms):
                        matched_todos.append(todo)
                except Exception:
                    continue
        except Exception:
            pass

    for todo in matched_todos:
        try:
            vtodo = todo.vobject_instance.vtodo
            summary = str(getattr(vtodo, "summary", None) or "")
            desc = str(getattr(vtodo, "description", None) or "")
            uid = str(getattr(vtodo, "uid", None) or todo.url)
        except Exception:
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
        try:
            ok = await process_item_for_app(db, "icloud_todo", uid, raw, date_hint, app_dict)
        except (AINotConfigured, AIRateLimited):
            raise
        except Exception as e:
            errors.append(f"reminder/{summary}: {e}")
            continue
        if ok:
            created += 1
        else:
            skipped += 1

    return created, len(matched_todos), errors


# ── Calls ─────────────────────────────────────────────────────────────────────

async def _sync_calls_for_app(app: models.Application, app_dict: dict, db: Session) -> tuple[int, int, list[str]]:
    CALLS_BRIDGE_URL = "http://host.docker.internal:9997/calls"
    created = skipped = 0
    errors: list[str] = []

    # Phone numbers of contacts linked to this application
    contacts = app.contacts or []
    if not contacts:
        return 0, 0, []

    from app.routers.sync_icloud import _normalize_phone, _phones_match

    contact_phones: list[tuple[str, str]] = []  # (normalized, contact_name)
    for c in contacts:
        if c.telefon:
            n = _normalize_phone(c.telefon)
            if n:
                contact_phones.append((n, c.name))

    if not contact_phones:
        return 0, 0, []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(CALLS_BRIDGE_URL)
        if resp.status_code != 200:
            return 0, 0, [f"Calls Bridge: {resp.text[:200]}"]
        calls = resp.json()
    except Exception as e:
        return 0, 0, [f"Calls Bridge nicht erreichbar: {e}"]

    for call in calls:
        phone_raw = str(call.get("phone") or "")
        call_key = str(call.get("id") or phone_raw)

        if is_synced(db, "icloud_calls", call_key):
            skipped += 1
            continue

        matched_contact: Optional[str] = None
        for norm_phone, cname in contact_phones:
            if _phones_match(phone_raw, norm_phone):
                matched_contact = cname
                break

        if not matched_contact:
            continue

        call_name = call.get("name") or matched_contact
        direction = call.get("direction", "")
        answered = call.get("answered", True)
        duration = call.get("duration_s") or call.get("duration") or 0

        duration_str = ""
        if duration:
            m, s = divmod(int(duration), 60)
            duration_str = f"{m}:{s:02d} min"

        ts = call.get("date") or call.get("timestamp") or ""
        date_hint = None
        time_str = ""
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
                date_hint = dt
                time_str = dt.astimezone().strftime("%H:%M")
            except Exception:
                pass

        if not answered:
            titel = f"↗ Verpasst: {call_name}" if direction == "outgoing" else f"↙ Verpasst: {call_name}"
        elif direction == "outgoing":
            titel = f"Anruf an {call_name}"
        else:
            titel = f"Anruf von {call_name}"

        notiz = f"Dauer: {duration_str}" if duration_str else ""
        if time_str:
            notiz += f"  ·  {time_str} Uhr" if notiz else f"{time_str} Uhr"

        db.add(models.Event(
            application_id=app.id,
            typ="notiz",
            datum=date_hint.date() if date_hint else None,
            titel=titel,
            notiz=notiz or None,
            source="icloud_calls",
        ))
        mark_synced(db, "icloud_calls", call_key)
        created += 1

    return created, len(calls), errors


# ── Task result store ────────────────────────────────────────────────────────

_task_results: dict[str, dict] = {}  # str(app_id) -> result dict


# ── Reset endpoint ────────────────────────────────────────────────────────────

@router.post("/{app_id}/reset", status_code=200)
def reset_targeted_sync(app_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).get(app_id)
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden.")

    deleted_events = db.query(models.Event).filter(
        models.Event.application_id == app_id,
        models.Event.source.isnot(None),
    ).delete()

    # Clear ALL source synced_items so everything gets re-evaluated from scratch
    deleted_items = db.query(models.SyncedItem).filter(
        models.SyncedItem.source.in_(
            ["gmail", "gcal", "icloud_mail", "icloud_cal", "icloud_notes", "icloud_todo", "icloud_calls"]
        )
    ).delete()

    db.commit()
    return {"deleted_events": deleted_events, "deleted_items": deleted_items}


# ── Main endpoint ─────────────────────────────────────────────────────────────

async def _do_sync(app_id: int) -> dict:
    """Run full targeted sync in a fresh DB session (for background task use)."""
    db = SessionLocal()
    try:
        app = db.query(models.Application).get(app_id)
        if not app:
            return {"created": 0, "processed": 0, "errors": [f"App {app_id} nicht gefunden"]}

        terms = _search_terms(app, db)
        app_dict = _app_dict(app)
        total_created = 0
        total_processed = 0
        all_errors: list[str] = []

        # 1. Contacts (sequential — calls need phone numbers)
        init_progress("targeted_contacts", "iCloud Kontakte", "Starte…")
        try:
            c, p, errs = await _sync_contacts_for_app(app, terms, db)
            total_created += c
            total_processed += p
            all_errors.extend(errs)
        except Exception as e:
            all_errors.append(f"Kontakte: {e}")
        finish_progress("targeted_contacts")
        db.commit()

        # 2. All AI sources in parallel
        sources = [
            ("Gmail",               "targeted_gmail",             _sync_gmail_for_app),
            ("Google Calendar",     "targeted_gcal",              _sync_gcal_for_app),
            ("iCloud Mail",         "targeted_icloud_mail",       _sync_icloud_mail_for_app),
            ("iCloud Kalender",     "targeted_icloud_cal",        _sync_icloud_cal_for_app),
            ("iCloud Notizen",      "targeted_icloud_notes",      _sync_icloud_notes_for_app),
            ("iCloud Erinnerungen", "targeted_icloud_reminders",  _sync_icloud_reminders_for_app),
        ]
        for _, pk, _ in sources:
            init_progress(pk, pk.replace("targeted_", "").replace("_", " ").title(), "Starte…")

        async def _run_source(label: str, prog_key: str, fn) -> tuple[int, int, list[str]]:
            try:
                c, p, errs = await fn(app, app_dict, terms, db)
                finish_progress(prog_key)
                return c, p, errs
            except Exception as e:
                finish_progress(prog_key)
                return 0, 0, [f"{label}: {e}"]

        ai_results = await asyncio.gather(
            *[_run_source(lbl, pk, fn) for lbl, pk, fn in sources],
            return_exceptions=True,
        )
        for r in ai_results:
            if isinstance(r, Exception):
                all_errors.append(str(r))
            else:
                c, p, errs = r
                total_created += c
                total_processed += p
                all_errors.extend(errs)

        # 3. Calls (no AI)
        init_progress("targeted_calls", "Anrufliste", "Starte…")
        try:
            c, p, errs = await _sync_calls_for_app(app, app_dict, db)
            total_created += c
            total_processed += p
            all_errors.extend(errs)
        except Exception as e:
            all_errors.append(f"Anrufliste: {e}")
        finish_progress("targeted_calls")

        db.commit()
        return {"created": total_created, "processed": total_processed, "errors": all_errors}
    finally:
        db.close()


@router.post("/{app_id}", response_model=schemas.SyncResult)
async def sync_for_app(app_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    app = db.query(models.Application).get(app_id)
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    if not _search_terms(app, db):
        raise HTTPException(400, "Keine Suchbegriffe für diese Bewerbung ableitbar.")

    _task_results.pop(str(app_id), None)
    init_progress(f"targeted_{app_id}", f"Sync: {app.firma}", "Startet…")

    async def _bg():
        try:
            result = await _do_sync(app_id)
        except Exception as e:
            result = {"created": 0, "processed": 0, "errors": [str(e)]}
        result["done"] = True
        _task_results[str(app_id)] = result
        finish_progress(f"targeted_{app_id}")

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


@router.get("/{app_id}/result")
def get_result(app_id: int):
    return _task_results.get(str(app_id)) or {"done": False}


_SYNC_SOURCES = {"gmail", "gcal", "icloud_mail", "icloud_cal", "icloud_notes", "calls"}


@router.get("/{app_id}/candidates")
def list_candidates(app_id: int, q: str = "", db: Session = Depends(get_db)):
    """Return items that could be manually assigned to this application.

    Two pools:
    1. PendingMatch rows (not yet assigned anywhere)
    2. Events already assigned to OTHER applications but from a sync source
       (can be re-assigned here)
    Both pools are filtered by the query string (or app search terms if no query).
    """
    app = db.query(models.Application).get(app_id)
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden.")

    q_lower = q.strip().lower()
    terms = _search_terms(app, db)

    def _matches(haystack: str) -> bool:
        h = haystack.lower()
        if q_lower:
            return q_lower in h
        return any(t.lower() in h for t in terms)

    results = []
    seen_external: set[str] = set()

    # ── Pool 1: PendingMatch ──────────────────────────────────────────────
    pending = (
        db.query(models.PendingMatch)
        .filter(models.PendingMatch.review_status == "pending")
        .order_by(models.PendingMatch.datum.desc())
        .limit(200)
        .all()
    )
    for pm in pending:
        haystack = " ".join(filter(None, [pm.titel, pm.extract, pm.raw_content or ""]))
        if not _matches(haystack):
            continue
        key = f"{pm.source}:{pm.external_id}"
        seen_external.add(key)
        results.append({
            "id":                  pm.id,
            "source":              pm.source,
            "external_id":         pm.external_id,
            "event_type":          pm.event_type,
            "datum":               str(pm.datum) if pm.datum else None,
            "titel":               pm.titel,
            "extract":             pm.extract,
            "confidence":          pm.confidence,
            "suggested_app_id":    pm.suggested_app_id,
            "suggested_app_firma": pm.application.firma if pm.application else None,
            "_pool":               "pending",
        })

    # ── Pool 2: Events from OTHER applications (sync sources only) ────────
    other_events = (
        db.query(models.Event)
        .filter(
            models.Event.application_id != app_id,
            models.Event.source.in_(list(_SYNC_SOURCES)),
        )
        .order_by(models.Event.datum.desc())
        .limit(500)
        .all()
    )
    for ev in other_events:
        key = f"{ev.source}:{ev.external_id}" if ev.external_id else f"ev:{ev.id}"
        if key in seen_external:
            continue
        haystack = " ".join(filter(None, [ev.titel, ev.notiz or ""]))
        if not _matches(haystack):
            continue
        seen_external.add(key)
        other_app = db.query(models.Application).get(ev.application_id)
        results.append({
            "id":                  -(ev.id),   # negative = event pool, not PendingMatch
            "source":              ev.source,
            "external_id":         ev.external_id,
            "event_type":          ev.typ,
            "datum":               str(ev.datum) if ev.datum else None,
            "titel":               ev.titel,
            "extract":             ev.notiz,
            "confidence":          50,
            "suggested_app_id":    ev.application_id,
            "suggested_app_firma": other_app.firma if other_app else None,
            "_pool":               "event",
        })

    # ── Pool 3: Live search across all connected external sources ────────
    if q_lower:
        for _live_fn in (
            _gmail_live_candidates,
            _gcal_live_candidates,
            _icloud_mail_live_candidates,
            _icloud_cal_live_candidates,
            _icloud_notes_live_candidates,
        ):
            try:
                results += _live_fn(q_lower, app_id, seen_external, db)
            except Exception:
                pass  # source not connected or API error — silently skip

    # strip internal _pool field before returning
    for r in results:
        r.pop("_pool", None)

    results.sort(key=lambda r: r["datum"] or "", reverse=True)
    return results[:100]


def _make_live_candidate(source: str, external_id: str, datum, titel: str, extract: str, seen: set) -> dict | None:
    key = f"{source}:{external_id}"
    if key in seen:
        return None
    seen.add(key)
    return {
        "id":                  0,
        "source":              source,
        "external_id":         external_id,
        "event_type":          "termin" if "cal" in source else "email" if "mail" in source or source == "gmail" else "notiz",
        "datum":               str(datum) if datum else None,
        "titel":               titel,
        "extract":             extract,
        "confidence":          70,
        "suggested_app_id":    None,
        "suggested_app_firma": None,
    }


def _gmail_live_candidates(q: str, app_id: int, seen_external: set, db) -> list:
    """Search Gmail directly for q (Pool 3)."""
    from app import models as _m
    from app.routers.sync_google import _refresh_if_needed
    from googleapiclient.discovery import build

    cfg = db.query(_m.GoogleSync).first()
    if not cfg or not cfg.refresh_token_enc:
        return []

    creds = _refresh_if_needed(cfg, db)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    resp = service.users().messages().list(userId="me", q=q, maxResults=25).execute()
    out = []
    for msg_ref in resp.get("messages", []):
        msg_id = msg_ref["id"]
        existing = db.query(_m.Event).filter(
            _m.Event.external_id == msg_id, _m.Event.application_id == app_id
        ).first()
        if existing:
            continue
        try:
            meta = service.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
        except Exception:
            continue
        hdrs = {h["name"].lower(): h["value"] for h in meta["payload"].get("headers", [])}
        subject = hdrs.get("subject", "(kein Betreff)")
        sender = hdrs.get("from", "")
        date_str = hdrs.get("date", "")
        datum = None
        if date_str:
            try:
                from email.utils import parsedate_to_datetime as _pdt
                datum = _pdt(date_str).date()
            except Exception:
                pass
        c = _make_live_candidate("gmail", msg_id, datum, subject, f"Von: {sender}", seen_external)
        if c:
            out.append(c)
    return out


def _gcal_live_candidates(q: str, app_id: int, seen_external: set, db) -> list:
    """Search Google Calendar for q using the API full-text search (Pool 3)."""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from app import models as _m
    from app.routers.sync_google import _refresh_if_needed
    from googleapiclient.discovery import build

    cfg = db.query(_m.GoogleSync).first()
    if not cfg or not cfg.refresh_token_enc:
        return []

    creds = _refresh_if_needed(cfg, db)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = _dt.now(_tz.utc)
    time_min = (now - _td(days=730)).isoformat()
    time_max = (now + _td(days=90)).isoformat()

    out = []
    try:
        cal_list = service.calendarList().list().execute()
    except Exception:
        return []

    for cal in cal_list.get("items", []):
        cal_id = cal["id"]
        try:
            resp = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=100,
                singleEvents=True,
                q=q,
            ).execute()
        except Exception:
            continue

        for ev in resp.get("items", []):
            ev_id = ev.get("id", "")
            summary = ev.get("summary", "(kein Titel)")
            start = ev.get("start", {})
            date_str = start.get("dateTime", start.get("date", ""))
            datum = None
            if date_str:
                try:
                    datum = _dt.fromisoformat(date_str.replace("Z", "+00:00")).date()
                except Exception:
                    pass

            desc = (ev.get("description") or "")[:100]
            c = _make_live_candidate("gcal", ev_id, datum, summary, desc or cal.get("summary", ""), seen_external)
            if c:
                out.append(c)

    return out[:50]


def _icloud_mail_live_candidates(q: str, app_id: int, seen_external: set, db) -> list:
    """Search iCloud Mail via IMAP for q (Pool 3)."""
    import email as _email_lib
    from app import models as _m
    from app.routers.sync_icloud import _imap_connect

    cfg = db.query(_m.ICloudSync).first()
    if not cfg or not cfg.app_password_enc:
        return []

    out = []
    imap = None
    try:
        imap = _imap_connect(cfg)
        imap.select("INBOX")
        # Search by subject OR from
        _, ids_sub = imap.search(None, f'SUBJECT "{q}"')
        _, ids_frm = imap.search(None, f'FROM "{q}"')
        ids_set: set[bytes] = set()
        for part in [ids_sub[0], ids_frm[0]]:
            if part:
                ids_set.update(part.split())
        for msg_id_bytes in list(ids_set)[:25]:
            msg_id = msg_id_bytes.decode()
            existing = db.query(_m.Event).filter(
                _m.Event.external_id == msg_id, _m.Event.application_id == app_id
            ).first()
            if existing:
                continue
            try:
                _, hdr_data = imap.fetch(msg_id_bytes, "(RFC822.HEADER)")
                hdr_msg = _email_lib.message_from_bytes(hdr_data[0][1])
            except Exception:
                continue
            subject = hdr_msg.get("Subject", "(kein Betreff)")
            sender = hdr_msg.get("From", "")
            date_str = hdr_msg.get("Date", "")
            datum = None
            if date_str:
                try:
                    from email.utils import parsedate_to_datetime as _pdt
                    datum = _pdt(date_str).date()
                except Exception:
                    pass
            c = _make_live_candidate("icloud_mail", msg_id, datum, subject, f"Von: {sender}", seen_external)
            if c:
                out.append(c)
    except Exception:
        pass
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass
    return out


def _icloud_cal_live_candidates(q: str, app_id: int, seen_external: set, db) -> list:
    """Search iCloud Calendar via CalDAV for q (Pool 3)."""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from app import models as _m
    from app.routers.sync_icloud import CALDAV_URL
    from app.ai.provider import decrypt_api_key

    cfg = db.query(_m.ICloudSync).first()
    if not cfg or not cfg.app_password_enc:
        return []

    try:
        import caldav
    except ImportError:
        return []

    q_lower = q.lower()
    out = []
    try:
        client = caldav.DAVClient(
            url=CALDAV_URL,
            username=cfg.apple_id,
            password=decrypt_api_key(cfg.app_password_enc),
        )
        principal = client.principal()
        now = _dt.now(_tz.utc)
        start = now - _td(days=365)
        end = now + _td(days=90)
        for cal in principal.calendars():
            try:
                for ev in cal.date_search(start=start, end=end, expand=True):
                    try:
                        comp = ev.icalendar_component
                    except Exception:
                        continue
                    summary = str(comp.get("SUMMARY", ""))
                    desc = str(comp.get("DESCRIPTION", ""))
                    if q_lower not in summary.lower() and q_lower not in desc.lower():
                        continue
                    uid = str(comp.get("UID", ""))
                    dtstart = comp.get("DTSTART")
                    datum = dtstart.dt.date() if dtstart and hasattr(dtstart.dt, "date") else (dtstart.dt if dtstart else None)
                    c = _make_live_candidate("icloud_cal", uid, datum, summary or "(kein Titel)", desc[:100] if desc else "", seen_external)
                    if c:
                        out.append(c)
            except Exception:
                continue
    except Exception:
        pass
    return out[:25]


def _icloud_notes_live_candidates(q: str, app_id: int, seen_external: set, db) -> list:
    """Search iCloud Notes via pyicloud for q (Pool 3)."""
    from app import models as _m
    from app.routers.sync_icloud import _get_pyicloud_api

    cfg = db.query(_m.ICloudSync).first()
    if not cfg or not cfg.web_password_enc:
        return []

    q_lower = q.lower()
    out = []
    try:
        api = _get_pyicloud_api(cfg)
        notes_service = api.notes
        if hasattr(notes_service, 'get_notes'):
            raw_notes = notes_service.get_notes()
        elif hasattr(notes_service, 'notes'):
            raw_notes = notes_service.notes
        else:
            raw_notes = list(notes_service)
        if isinstance(raw_notes, dict):
            raw_notes = list(raw_notes.values())

        for note in raw_notes:
            title = str(getattr(note, 'title', None) or note.get('title', '') if isinstance(note, dict) else '')
            body = str(getattr(note, 'body', None) or note.get('body', '') if isinstance(note, dict) else '')
            if q_lower not in title.lower() and q_lower not in body.lower():
                continue
            note_id = str(getattr(note, 'id', None) or note.get('id', '') if isinstance(note, dict) else id(note))
            c = _make_live_candidate("icloud_notes", note_id, None, title or "(ohne Titel)", body[:100], seen_external)
            if c:
                out.append(c)
    except Exception:
        pass
    return out[:25]


class ManualAssignPayload(BaseModel):
    match_id: int
    external_id: Optional[str] = None  # required when match_id==0 (live pool)
    source: Optional[str] = None       # required when match_id==0: "gmail"|"icloud_mail"|"icloud_cal"|"icloud_notes"
    event_type: Optional[str] = None
    datum: Optional[str] = None
    titel: Optional[str] = None
    remove_from_other: bool = False


@router.post("/{app_id}/assign")
def manual_assign(app_id: int, body: ManualAssignPayload, db: Session = Depends(get_db)):
    """Manually assign a PendingMatch or existing Event to an application.

    Positive match_id → PendingMatch row.
    Negative match_id → abs(match_id) is an Event.id from another application
    (returned by list_candidates when the item is already in Pool 2).
    """
    app = db.query(models.Application).get(app_id)
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden.")

    from datetime import date as _date

    # ── Pool 3: Live item from any external source (match_id==0) ─────────────
    if body.match_id == 0:
        if not body.external_id or not body.source:
            raise HTTPException(400, "external_id und source erforderlich für Live-Zuweisung.")
        src = body.source
        ext_id = body.external_id

        existing = db.query(models.Event).filter(
            models.Event.external_id == ext_id,
            models.Event.application_id == app_id,
        ).first()
        if existing:
            return {"conflict": False, "event_id": existing.id}

        from app.routers.sync_common import strip_html, mark_synced

        subject = body.titel or "(kein Titel)"
        body_text: Optional[str] = None
        datum_val = None
        try:
            datum_val = _date.fromisoformat(body.datum) if body.datum else None
        except ValueError:
            pass

        if src == "gmail":
            try:
                from app.routers.sync_google import _refresh_if_needed
                from googleapiclient.discovery import build as _gbuild
                import base64 as _b64
                gcfg = db.query(models.GoogleSync).first()
                if not gcfg or not gcfg.refresh_token_enc:
                    raise HTTPException(400, "Google nicht verbunden.")
                creds = _refresh_if_needed(gcfg, db)
                service = _gbuild("gmail", "v1", credentials=creds, cache_discovery=False)
                msg_full = service.users().messages().get(userId="me", id=ext_id, format="full").execute()
                pl = msg_full.get("payload", {})
                hdrs = {h["name"].lower(): h["value"] for h in pl.get("headers", [])}
                subject = hdrs.get("subject", subject)
                date_str = hdrs.get("date", "")
                if date_str and not datum_val:
                    try:
                        from email.utils import parsedate_to_datetime as _pdt
                        datum_val = _pdt(date_str).date()
                    except Exception:
                        pass

                def _gbody(p):
                    mime = p.get("mimeType", "")
                    if mime == "text/plain":
                        d = p.get("body", {}).get("data", "")
                        return _b64.urlsafe_b64decode(d + "==").decode("utf-8", errors="replace") if d else ""
                    if mime == "text/html":
                        d = p.get("body", {}).get("data", "")
                        return strip_html(_b64.urlsafe_b64decode(d + "==").decode("utf-8", errors="replace")) if d else ""
                    for part in p.get("parts", []):
                        t = _gbody(part)
                        if t:
                            return t
                    return ""
                body_text = _gbody(pl)[:500] or None
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(502, f"Gmail API Fehler: {exc}")

        elif src == "icloud_mail":
            import email as _email_lib
            from app.routers.sync_icloud import _imap_connect
            icfg = db.query(models.ICloudSync).first()
            if not icfg or not icfg.app_password_enc:
                raise HTTPException(400, "iCloud nicht verbunden.")
            imap = None
            try:
                imap = _imap_connect(icfg)
                imap.select("INBOX")
                _, fetch_data = imap.fetch(ext_id.encode(), "(RFC822)")
                raw = fetch_data[0][1] if fetch_data and fetch_data[0] else b""
                msg = _email_lib.message_from_bytes(raw)
                subject = msg.get("Subject", subject)
                date_str = msg.get("Date", "")
                if date_str and not datum_val:
                    try:
                        from email.utils import parsedate_to_datetime as _pdt
                        datum_val = _pdt(date_str).date()
                    except Exception:
                        pass
                from app.routers.sync_icloud import _imap_body
                body_text = (_imap_body(msg) or "")[:500] or None
            except Exception as exc:
                raise HTTPException(502, f"iCloud-Mail Fehler: {exc}")
            finally:
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass

        elif src == "gcal":
            # Fetch full event details to get description
            try:
                from app.routers.sync_google import _refresh_if_needed
                from googleapiclient.discovery import build as _gbuild
                gcfg = db.query(models.GoogleSync).first()
                if gcfg and gcfg.refresh_token_enc:
                    creds = _refresh_if_needed(gcfg, db)
                    service = _gbuild("calendar", "v3", credentials=creds, cache_discovery=False)
                    # Try primary calendar first, then all calendars
                    ev_data = None
                    try:
                        ev_data = service.events().get(calendarId="primary", eventId=ext_id).execute()
                    except Exception:
                        cals = service.calendarList().list().execute()
                        for cal in cals.get("items", []):
                            try:
                                ev_data = service.events().get(calendarId=cal["id"], eventId=ext_id).execute()
                                break
                            except Exception:
                                continue
                    if ev_data:
                        subject = ev_data.get("summary", subject)
                        body_text = (ev_data.get("description") or "")[:500] or None
                        start = ev_data.get("start", {})
                        date_str = start.get("dateTime", start.get("date", ""))
                        if date_str and not datum_val:
                            try:
                                from datetime import datetime as _dtime
                                datum_val = _dtime.fromisoformat(date_str.replace("Z", "+00:00")).date()
                            except Exception:
                                pass
            except Exception:
                pass

        elif src == "icloud_cal":
            pass  # title/datum already sent from frontend via candidates metadata

        elif src == "icloud_notes":
            pass  # title already sent; no full-body fetch needed

        event_typ = body.event_type or ("termin" if "cal" in src else "email" if "mail" in src or src == "gmail" else "notiz")
        if event_typ in ("status_change", "duplicate_contact", "duplicate_event"):
            event_typ = "notiz"

        ev = models.Event(
            application_id=app_id,
            typ=event_typ,
            datum=datum_val,
            titel=subject,
            notiz=body_text,
            source=src,
            external_id=ext_id,
        )
        db.add(ev)
        mark_synced(db, src, ext_id)
        db.commit()
        db.refresh(ev)
        return {"conflict": False, "event_id": ev.id}

    # ── Pool 2: re-assign an existing Event ───────────────────────────────
    if body.match_id < 0:
        event_id = abs(body.match_id)
        src_event = db.query(models.Event).get(event_id)
        if not src_event:
            raise HTTPException(404, "Event nicht gefunden.")
        if src_event.application_id == app_id:
            return {"conflict": False, "event_id": src_event.id}

        if not body.remove_from_other:
            conflict_app = db.query(models.Application).get(src_event.application_id)
            return {
                "conflict": True,
                "conflict_app_id": src_event.application_id,
                "conflict_app_firma": conflict_app.firma if conflict_app else None,
                "conflict_event_id": src_event.id,
            }

        # Move event to this application
        src_event.application_id = app_id
        if body.event_type:
            src_event.typ = body.event_type
        if body.titel:
            src_event.titel = body.titel
        if body.datum:
            try:
                src_event.datum = _date.fromisoformat(body.datum)
            except ValueError:
                pass
        db.commit()
        db.refresh(src_event)
        return {"conflict": False, "event_id": src_event.id}

    # ── Pool 1: PendingMatch ───────────────────────────────────────────────
    pm = db.query(models.PendingMatch).get(body.match_id)
    if not pm:
        raise HTTPException(404, "PendingMatch nicht gefunden.")

    try:
        datum = _date.fromisoformat(body.datum) if body.datum else pm.datum
    except ValueError:
        datum = pm.datum

    ext_id = pm.external_id
    conflict_event = (
        db.query(models.Event)
        .filter(
            models.Event.external_id == ext_id,
            models.Event.application_id != app_id,
        )
        .first()
    ) if ext_id else None

    if conflict_event and not body.remove_from_other:
        conflict_app = db.query(models.Application).get(conflict_event.application_id)
        return {
            "conflict": True,
            "conflict_app_id": conflict_event.application_id,
            "conflict_app_firma": conflict_app.firma if conflict_app else None,
            "conflict_event_id": conflict_event.id,
        }

    if conflict_event and body.remove_from_other:
        db.delete(conflict_event)

    event_typ = body.event_type or pm.event_type or "notiz"
    if event_typ in ("status_change", "duplicate_contact", "duplicate_event"):
        event_typ = "notiz"

    ev = models.Event(
        application_id=app_id,
        typ=event_typ,
        datum=datum,
        titel=body.titel or pm.titel,
        notiz=pm.extract,
        source=pm.source,
        external_id=ext_id,
    )
    db.add(ev)
    pm.review_status = "approved"
    db.commit()
    db.refresh(ev)
    return {"conflict": False, "event_id": ev.id}
