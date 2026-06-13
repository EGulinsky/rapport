"""
Provider-agnostic sync helpers shared by sync_google.py and sync_icloud.py.

Anything here must have zero knowledge of Google APIs, iCloud, IMAP, CalDAV, etc.
Provider-specific code stays in the respective router file.
"""
from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import models
from app.ai.provider import AINotConfigured, AIRateLimited
from app.ai.tasks import match_and_classify

_TZ_BERLIN = ZoneInfo("Europe/Berlin")


def _time_prefix(date_hint: Optional[datetime]) -> str:
    """Return 'HH:MM Uhr\n' in Berlin time if date_hint has a meaningful time, else ''."""
    if date_hint is None:
        return ""
    local = date_hint.astimezone(_TZ_BERLIN)
    if local.hour == 0 and local.minute == 0:
        return ""
    return f"{local.hour}:{local.minute:02d} Uhr\n"


# ── Contact auto-creation ─────────────────────────────────────────────────────

_SKIP_CONTACT_LOCALS = frozenset({
    "noreply", "no-reply", "donotreply", "notifications", "notification",
    "mailer-daemon", "postmaster", "support", "hello", "info", "contact",
    "newsletter", "automatisch", "automated", "reply", "bounce",
})

# Phone: matches "Tel.: +49 89 123", "Mobile: 0171 123456", "T +49..." etc.
_PHONE_RE = re.compile(
    r'(?:Tel\.?(?:efon)?|Phone|Fon|Mob(?:ile)?|Handy|M\.?|T\.?)\s*[:\-]?\s*'
    r'((?:\+\d{1,3}[\s\-\(\)\/\.]*)?\(?\d[\d\s\-\(\)\/\.]{5,20}\d)',
    re.IGNORECASE,
)

# Bare phone numbers (last resort): +49… or 0… with enough digits
_BARE_PHONE_RE = re.compile(
    r'(?<!\w)(\+49[\s\-]?[\d\s\-\(\)\/\.]{7,18}\d|0[\d]{2,4}[\s\/\-]?[\d]{3,}[\d\s\-\/\.]*\d)(?!\w)',
)

# Title/role explicitly labelled
_TITLE_LABEL_RE = re.compile(
    r'(?:Position|Titel|Title|Job\s*[Tt]itle|Funktion|Rolle|Role|Designation)\s*[:\-]\s*(.+)',
    re.IGNORECASE,
)

# Keywords that suggest a line is a job title
_TITLE_KW_RE = re.compile(
    r'\b(Manager|Director|Head\s+of|Leiter(?:in)?|Senior|Junior|Engineer|Ingenieur|'
    r'Berater(?:in)?|Consultant|Recruiter|HR|Talent|Partner|CEO|CTO|CFO|COO|VP|'
    r'Lead|Specialist|Koordinator(?:in)?|Referent(?:in)?|Beauftragter?|'
    r'Geschäftsführer(?:in)?|Projektleiter(?:in)?|Teamleiter(?:in)?|'
    r'Account\s+Executive|Business\s+\w+)\b',
    re.IGNORECASE,
)


def _extract_footer_info(body: str, sender_name: str) -> dict:
    """
    Parse phone number and job title from email body/footer.
    Returns dict with any of: telefon, rolle.
    """
    info: dict = {}

    # ── Phone ──────────────────────────────────────────────────────────────
    m = _PHONE_RE.search(body)
    if m:
        phone = re.sub(r'\s+', ' ', m.group(1)).strip().rstrip('.,;')
        if len(re.sub(r'\D', '', phone)) >= 7:
            info['telefon'] = phone
    elif not info.get('telefon'):
        m2 = _BARE_PHONE_RE.search(body)
        if m2:
            phone = re.sub(r'\s+', ' ', m2.group(1)).strip().rstrip('.,;')
            if len(re.sub(r'\D', '', phone)) >= 7:
                info['telefon'] = phone

    # ── Role ──────────────────────────────────────────────────────────────
    # 1. Explicitly labelled line
    m = _TITLE_LABEL_RE.search(body)
    if m:
        rolle = m.group(1).strip()[:120]
        if rolle:
            info['rolle'] = rolle

    # 2. Line directly after sender's name in footer (look in last 40 lines)
    if 'rolle' not in info and sender_name:
        last_name = sender_name.split()[-1] if sender_name.split() else ''
        if len(last_name) >= 3:
            lines = body.splitlines()
            tail = lines[-40:] if len(lines) > 40 else lines
            for i, line in enumerate(tail):
                if last_name.lower() in line.lower() and len(line.strip()) < 80:
                    for j in range(i + 1, min(i + 4, len(tail))):
                        candidate = tail[j].strip()
                        # Must be reasonable length, not an email/URL/phone, have title keyword
                        if (10 <= len(candidate) <= 100
                                and not re.search(r'[@://]', candidate)
                                and not re.search(r'\d{5,}', candidate)
                                and _TITLE_KW_RE.search(candidate)):
                            info['rolle'] = candidate
                            break
                    if 'rolle' in info:
                        break

    return info


def _upsert_contact(
    db: Session,
    name: str,
    email_addr: str,
    app_id: int,
    firma: str,
    is_headhunter: bool,
    event_date=None,
    extra: dict | None = None,
) -> None:
    """Create contact if not existing, always ensure link to application.

    extra: optional dict with keys telefon, rolle — applied to new contacts
    and used to fill empty fields on existing ones (existing values win).
    """
    from app import models as _models
    email_addr = (email_addr or "").lower().strip()
    if not email_addr or "@" not in email_addr:
        return
    local = email_addr.split("@")[0].lower().strip(".-_+")
    if local in _SKIP_CONTACT_LOCALS or any(s in local for s in ("noreply", "no-reply", "donotreply")):
        return

    extra = extra or {}

    existing = db.query(_models.Contact).filter(
        func.lower(_models.Contact.email) == email_addr
    ).first()

    app_obj = db.query(_models.Application).get(app_id)
    if not app_obj:
        return

    _LINK_SQL = text(
        "INSERT OR IGNORE INTO contact_application (contact_id, application_id) VALUES (:cid, :aid)"
    )

    if existing:
        if event_date and (existing.letzter_kontakt is None or event_date > existing.letzter_kontakt):
            existing.letzter_kontakt = event_date
        # Fill empty fields from footer — existing values always win
        if not existing.telefon and extra.get('telefon'):
            existing.telefon = extra['telefon']
        if not existing.rolle and extra.get('rolle'):
            existing.rolle = extra['rolle']
        # INSERT OR IGNORE bypasses ORM relationship tracking — no autoflush race
        db.execute(_LINK_SQL, {"cid": existing.id, "aid": app_id})
        return

    contact = _models.Contact(
        name=(name.strip() or email_addr.split("@")[0]),
        email=email_addr,
        firma=firma or None,
        typ="Headhunter" if is_headhunter else None,
        letzter_kontakt=event_date,
        telefon=extra.get('telefon') or None,
        rolle=extra.get('rolle') or None,
    )
    db.add(contact)
    db.flush()  # get contact.id
    db.execute(_LINK_SQL, {"cid": contact.id, "aid": app_id})


def upsert_contact_from_sender(
    db: Session,
    raw_sender: str,
    app_id: int,
    firma: str,
    is_headhunter: bool,
    event_date=None,
    body: str = "",
) -> None:
    """Parse 'Display Name <email@host>', extract footer info, and upsert contact."""
    name, addr = parseaddr(raw_sender or "")
    extra = _extract_footer_info(body, name) if body else {}
    _upsert_contact(db, name, addr, app_id, firma, is_headhunter, event_date, extra)


# ── In-memory progress tracking ───────────────────────────────────────────────

@dataclass
class SyncProgress:
    label: str
    step: str = "Starte…"
    current: int = 0
    total: int = 0
    done: bool = False

# module-level dict; safe for single-worker uvicorn (this is a single-user app)
_progress: dict[str, SyncProgress] = {}

# Batch sync result store: source → SyncResult dict (set when background task finishes)
_batch_results: dict[str, dict] = {}


def init_progress(source: str, label: str, step: str = "Starte…") -> None:
    _progress[source] = SyncProgress(label=label, step=step)


def update_progress(source: str, current: int, total: int, step: str = "") -> None:
    p = _progress.get(source)
    if p:
        p.current = current
        p.total = total
        if step:
            p.step = step


def finish_progress(source: str, step: str = "Fertig") -> None:
    p = _progress.get(source)
    if p:
        p.done = True
        p.step = step


def get_batch_results() -> dict:
    return dict(_batch_results)


def set_batch_result(source: str, result: dict) -> None:
    _batch_results[source] = result


def clear_batch_results() -> None:
    _batch_results.clear()


def get_all_progress() -> dict:
    return {
        src: {
            "label": p.label,
            "step": p.step,
            "current": p.current,
            "total": p.total,
            "percent": round(p.current / p.total * 100) if p.total else (100 if p.done else 0),
            "done": p.done,
        }
        for src, p in _progress.items()
    }

# ── Confidence thresholds ─────────────────────────────────────────────────────

MIN_CONFIDENCE   = 0.60   # auto-create event
REVIEW_THRESHOLD = 0.20   # queue for manual review; below = discard


# ── SyncedItem helpers ────────────────────────────────────────────────────────

def is_synced(db: Session, source: str, external_id: str) -> bool:
    return db.query(models.SyncedItem).filter_by(
        source=source, external_id=external_id
    ).first() is not None


def mark_synced(db: Session, source: str, external_id: str) -> None:
    db.add(models.SyncedItem(source=source, external_id=external_id))


def purge_source(db: Session, source: str) -> None:
    """Clear SyncedItem records so items get reprocessed on next sync.
    Events are intentionally kept — deleting them causes permanent data loss
    when the re-sync window doesn't cover all previously-synced items."""
    db.query(models.SyncedItem).filter_by(source=source).delete()


# ── Text helpers ──────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def decode_b64(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")


# ── Firm / contact indexes ────────────────────────────────────────────────────

_CORP_SUFFIXES = {
    "group", "gmbh", "ag", "se", "ltd", "inc", "corp", "plc", "llc", "lp",
    "kg", "co", "sa", "nv", "ges", "mbh", "technologies", "technology",
    "solutions", "consulting", "services", "management", "partners", "partner",
    "executive",
}

_COMMON_FIRST_NAMES = {
    "robert", "thomas", "stefan", "peter", "michael", "daniel", "martin",
    "markus", "andreas", "christian", "alexander", "johannes", "nicolas",
    "oliver", "frank", "jan", "david", "tim", "tobias", "hans", "georg",
    "james", "john", "richard", "william", "henry", "charles", "george",
}

_GENERIC_EMAIL_DOMAINS = frozenset([
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.de",
    "outlook.com", "hotmail.com", "hotmail.de", "live.com",
    "web.de", "gmx.de", "gmx.net", "gmx.com",
    "t-online.de", "icloud.com", "me.com", "mac.com",
    "msn.com", "aol.com", "protonmail.com", "pm.me",
])


def term_variants(raw_term: str) -> list[str]:
    """Return the term plus shorter variants stripped of trailing corporate suffixes."""
    base = raw_term.strip()
    variants = [base]
    words = base.split()
    stripped = list(words)
    while len(stripped) > 1 and stripped[-1].lower().rstrip(".") in _CORP_SUFFIXES:
        stripped = stripped[:-1]
        candidate = " ".join(stripped)
        if len(candidate) >= 3 and candidate not in variants:
            variants.append(candidate)
    if len(stripped) >= 2:
        first = stripped[0]
        if (len(first) >= 6
                and first.lower() not in _COMMON_FIRST_NAMES
                and first.lower() not in _CORP_SUFFIXES
                and first not in variants):
            variants.append(first)
    return variants


def build_firm_index(db: Session) -> tuple[str, dict[str, list[dict]]]:
    """Build a search-term clause and reverse index term→apps from all applications."""
    active = db.query(models.Application).all()
    term_to_apps: dict[str, list[dict]] = {}
    for a in active:
        app_dict = {"id": a.id, "firma": a.firma, "rolle": a.rolle}
        for raw_term in [a.firma, a.zielfirma_bei_hh, a.wurde_besetzt_von]:
            if raw_term and len(raw_term.strip()) >= 3:
                for key in term_variants(raw_term):
                    term_to_apps.setdefault(key, [])
                    if app_dict not in term_to_apps[key]:
                        term_to_apps[key].append(app_dict)
    clause = " OR ".join(f'"{t}"' for t in term_to_apps)
    return clause, term_to_apps


def extract_email_domains(text: str) -> list[str]:
    """Extract unique non-generic email domains from a text blob."""
    raw_domains = re.findall(r'[\w.+-]+@([\w.-]+\.[a-zA-Z]{2,})', text)
    seen: set[str] = set()
    result: list[str] = []
    for d in raw_domains:
        dl = d.lower()
        if dl not in _GENERIC_EMAIL_DOMAINS and dl not in seen:
            seen.add(dl)
            result.append(dl)
    return result


def build_contact_domain_index(db: Session) -> dict[str, list[dict]]:
    """Map email-domain → [app_dict] from contacts linked to applications."""
    index: dict[str, list[dict]] = {}
    for c in db.query(models.Contact).all():
        if not c.email or "@" not in c.email:
            continue
        domain = c.email.split("@")[-1].lower()
        if domain in _GENERIC_EMAIL_DOMAINS:
            continue
        for app in (c.applications or []):
            app_dict = {"id": app.id, "firma": app.firma, "rolle": app.rolle}
            bucket = index.setdefault(domain, [])
            if app_dict not in bucket:
                bucket.append(app_dict)
    return index


def find_hint_apps(
    raw_text: str,
    term_to_apps: dict[str, list[dict]],
    contact_domain_index: Optional[dict[str, list[dict]]] = None,
) -> list[dict]:
    """Return apps matched by firm-name substring, contact email domain, or firm-in-domain."""
    text_lower = raw_text.lower()
    seen_ids: set[int] = set()
    hints: list[dict] = []

    def _add(app_dict: dict) -> None:
        if app_dict["id"] not in seen_ids:
            hints.append(app_dict)
            seen_ids.add(app_dict["id"])

    for term, apps in term_to_apps.items():
        if term.lower() in text_lower:
            for a in apps:
                _add(a)

    for domain in extract_email_domains(raw_text):
        if contact_domain_index:
            for a in contact_domain_index.get(domain, []):
                _add(a)
        domain_core = domain.split(".")[0]
        for term, apps in term_to_apps.items():
            tl = term.lower()
            if len(tl) >= 4 and (tl in domain or domain_core in tl):
                for a in apps:
                    _add(a)

    return hints


# ── Core item pipeline ────────────────────────────────────────────────────────

def _map_event_type(et: str) -> str:
    return {
        "interview_scheduled": "status",
        "interview_done":      "status",
        "rejection":           "status",
        "offer":               "status",
        "callback":            "notiz",
        "note":                "notiz",
        "application":         "bewerbung",
    }.get(et, "notiz")


async def process_item(
    db: Session,
    source: str,
    external_id: str,
    raw_text: str,
    date_hint: Optional[datetime] = None,
    hint_apps: Optional[list[dict]] = None,
) -> bool:
    """Run AI analysis and persist event or review queue entry. Returns True if event was created."""
    if is_synced(db, source, external_id):
        return False

    # Send only active apps to AI to conserve tokens.
    # Rejected hint_apps are appended so they can still be matched (e.g. follow-up mails).
    active = db.query(models.Application).filter_by(abgesagt=False).all()
    app_list = [
        {
            "id": a.id,
            "firma": a.firma,
            "rolle": a.rolle,
            **({"zielfirma": a.zielfirma_bei_hh} if a.zielfirma_bei_hh else {}),
            **({"besetzt_von": a.wurde_besetzt_von} if a.wurde_besetzt_von else {}),
        }
        for a in active
    ]
    if hint_apps:
        active_ids = {e["id"] for e in app_list}
        for h in hint_apps:
            if h["id"] not in active_ids:
                app_list.append(h)

    try:
        result = await match_and_classify(db, source, raw_text, app_list, hint_apps=hint_apps)
    except (AINotConfigured, AIRateLimited):
        raise
    except Exception:
        return False

    confidence = float(result.get("confidence") or 0)
    app_id = result.get("application_id")

    autor = None
    for line in raw_text.splitlines():
        if line.startswith("Von: ") or line.startswith("From: "):
            autor = line.split(": ", 1)[1].strip() or None
            break

    if date_hint:
        datum = date_hint.date()
    elif result.get("datum"):
        try:
            datum = datetime.fromisoformat(result["datum"]).date()
        except ValueError:
            datum = None
    else:
        datum = None

    if confidence < REVIEW_THRESHOLD:
        mark_synced(db, source, external_id)
        return False

    if confidence < MIN_CONFIDENCE or not app_id:
        mark_synced(db, source, external_id)
        db.add(models.PendingMatch(
            source=source,
            external_id=external_id,
            confidence=int(confidence * 100),
            event_type=result.get("event_type"),
            datum=datum,
            titel=result.get("titel"),
            extract=result.get("extract"),
            raw_content=raw_text,
            suggested_app_id=app_id,
            suggested_main_status=result.get("suggested_main_status"),
            suggested_sub_status=result.get("suggested_sub_status"),
        ))
        return False

    db.add(models.Event(
        application_id=app_id,
        typ=_map_event_type(result.get("event_type", "note")),
        datum=datum,
        titel=result.get("titel") or source,
        notiz=result.get("extract"),
        autor=autor,
        source=source,
    ))
    mark_synced(db, source, external_id)

    new_main = result.get("suggested_main_status")
    new_sub  = result.get("suggested_sub_status")
    if new_main:
        app = db.query(models.Application).get(app_id)
        if app and app.main_status != new_main:
            db.add(models.PendingMatch(
                source=source,
                external_id=f"{external_id}__status",
                confidence=int(confidence * 100),
                event_type="status_change",
                datum=datum,
                titel=f"Status: {app.main_status} → {new_main}",
                extract=result.get("extract"),
                raw_content=raw_text,
                suggested_app_id=app_id,
                suggested_main_status=new_main,
                suggested_sub_status=new_sub,
                status_only=True,
            ))

    return True


def save_classified_event(
    db: Session,
    source: str,
    external_id: str,
    result: dict,
    raw_text: str,
    date_hint: Optional[datetime],
    target_app: dict,
    extra_notiz: Optional[str] = None,
) -> bool:
    """Persist a pre-classified result as an event. Returns True if event was created."""
    confidence = float(result.get("confidence") or 0)
    if not result.get("relevant", True) or confidence < 0.55:
        mark_synced(db, source, external_id)
        return False

    autor = None
    for line in raw_text.splitlines():
        if line.startswith("Von: ") or line.startswith("From: "):
            autor = line.split(": ", 1)[1].strip() or None
            break

    if date_hint:
        datum = date_hint.date()
    elif result.get("datum"):
        try:
            datum = datetime.fromisoformat(result["datum"]).date()
        except ValueError:
            datum = None
    else:
        datum = None

    ai_extract = result.get("extract") or None
    if not ai_extract:
        # Use subject line as fallback — never fall back to raw email body
        for line in raw_text.splitlines():
            line = line.strip()
            if line.startswith("Betreff:") or line.startswith("Subject:"):
                subject = line.split(":", 1)[1].strip()
                if subject:
                    ai_extract = subject[:200]
                break

    time_pfx = _time_prefix(date_hint)
    body = f"{extra_notiz}\n{ai_extract}" if extra_notiz and ai_extract else (extra_notiz or ai_extract or "")
    notiz = f"{time_pfx}{body}" if time_pfx else (body or None)

    db.add(models.Event(
        application_id=target_app["id"],
        typ=_map_event_type(result.get("event_type", "note")),
        datum=datum,
        titel=result.get("titel") or source,
        notiz=notiz,
        autor=autor,
        source=source,
    ))
    mark_synced(db, source, external_id)

    # Auto-create contact from sender, extract phone/role from mail footer
    if autor:
        upsert_contact_from_sender(
            db, autor,
            app_id=target_app["id"],
            firma=target_app.get("firma", ""),
            is_headhunter=target_app.get("is_headhunter", False),
            event_date=datum,
            body=raw_text,
        )

    return True


async def process_item_for_app(
    db: Session,
    source: str,
    external_id: str,
    raw_text: str,
    date_hint: Optional[datetime],
    target_app: dict,
    extra_notiz: Optional[str] = None,
) -> bool:
    """Like process_item but scoped to a single known application. No review queue."""
    if is_synced(db, source, external_id):
        return False

    from app.ai.tasks import classify_for_app
    try:
        result = await classify_for_app(db, source, raw_text, target_app)
    except (AINotConfigured, AIRateLimited):
        raise
    except Exception:
        return False

    return save_classified_event(db, source, external_id, result, raw_text, date_hint, target_app, extra_notiz)
