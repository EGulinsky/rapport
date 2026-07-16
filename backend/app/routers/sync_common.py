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
from datetime import date, datetime
from email.utils import parseaddr
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import models
from app.audit import add_audit
from app.i18n_strings import resolve_ui_language, t
from app.logger import get_logger

log = get_logger("sync", source="targeted")
_TZ_BERLIN = ZoneInfo("Europe/Berlin")


def _predates_bewerbung(datum: Optional[date], app: models.Application) -> bool:
    """True if datum is set and lies strictly before the application submission date."""
    if datum is None or app.datum_bewerbung is None:
        return False
    return datum < app.datum_bewerbung


def earliest_bewerbung_date(db: Session) -> Optional[date]:
    """Return the oldest datum_bewerbung across all applications (used as global sync cutoff)."""
    from sqlalchemy import func as _func
    return db.query(_func.min(models.Application.datum_bewerbung)).scalar()


def _time_prefix(date_hint: Optional[datetime]) -> str:
    """Return 'HH:MM Uhr\n' in Berlin time if date_hint has a meaningful time, else ''."""
    if date_hint is None:
        return ""
    local = date_hint.astimezone(_TZ_BERLIN)
    if local.hour == 0 and local.minute == 0:
        return ""
    return f"{local.hour}:{local.minute:02d} Uhr\n"


# ── Contact name helpers ──────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Return a canonical sorted-token fingerprint for order-independent name comparison.

    "Mehra, Malvika" and "Malvika Mehra" both become frozenset → sorted str.
    """
    tokens = sorted(t.strip().lower() for t in re.split(r"[,\s]+", name) if t.strip())
    return " ".join(tokens)


def _split_name(name: str) -> tuple[str, str]:
    """Return (nachname, vorname) by best-effort parsing.

    Handles "Mehra, Malvika" (comma-separated, last first),
    "Malvika Mehra" (first last), and single-token names.
    Returns (name, "") for unrecognised patterns.
    """
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        return parts[0], parts[1]
    tokens = name.strip().split()
    if len(tokens) >= 2:
        return tokens[-1], " ".join(tokens[:-1])
    return name.strip(), ""


# ── Contact auto-creation ─────────────────────────────────────────────────────

_SKIP_CONTACT_LOCALS = frozenset({
    "noreply", "no-reply", "donotreply", "notifications", "notification",
    "mailer-daemon", "postmaster", "support", "hello", "info", "contact",
    "newsletter", "automatisch", "automated", "reply", "bounce",
    # Generic HR / department mailboxes — not a real person
    "career", "careers", "jobs", "job", "apply", "application", "applications",
    "recruiting", "recruitment", "recruiter", "talent", "talentacquisition",
    "hr", "humanresources", "personalwesen", "personal",
    "bewerbung", "bewerbungen", "bewerber", "bewerbungsmanagement",
    "stellenangebot", "stellenangebote", "jobangebot", "jobangebote",
    "work", "hiring", "jobapplication",
})

# Substrings that mark a local part as a generic mailbox even when combined
# e.g. "career-jobs", "recruiting-team", "hr.europe"
_SKIP_CONTACT_SUBSTRINGS = (
    "noreply", "no-reply", "donotreply",
    "career", "recruiting", "recruitment", "bewerbung", "bewerber",
)

# ATS systems use per-message tracking addresses — the email is not the person's real address.
_ATS_TRACKING_DOMAINS = frozenset({
    "talent.icims.com", "icims.com", "greenhouse-mail.io",
    "workablemail.com", "jobvite.com", "lever.co", "smartrecruiters.com",
    "successfactors.com", "taleo.net", "myworkday.com",
})


def _get_owner_emails(db: Session) -> frozenset[str]:
    """Return all email addresses that belong to the app owner (from configured accounts)."""
    own: set[str] = set()

    google = db.query(models.GoogleSync).first()
    if google and getattr(google, "gmail_email", None):
        own.add(google.gmail_email.lower().strip())

    icloud = db.query(models.ICloudSync).first()
    if icloud:
        for addr in (icloud.apple_id, icloud.icloud_email):
            if addr:
                own.add(addr.lower().strip())

    linkedin = db.query(models.LinkedInSync).first()
    if linkedin and getattr(linkedin, "email", None):
        own.add(linkedin.email.lower().strip())

    # googlemail.com and gmail.com are the same account — add both variants
    extra: set[str] = set()
    for addr in own:
        local, _, domain = addr.partition("@")
        if domain == "googlemail.com":
            extra.add(f"{local}@gmail.com")
        elif domain == "gmail.com":
            extra.add(f"{local}@googlemail.com")
    own |= extra

    return frozenset(own)

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
    user_id: Optional[int] = None,
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
    if local in _SKIP_CONTACT_LOCALS or any(s in local for s in _SKIP_CONTACT_SUBSTRINGS):
        return
    if email_addr in _get_owner_emails(db):
        return

    extra = extra or {}

    domain = email_addr.split("@", 1)[1] if "@" in email_addr else ""
    is_ats_tracking = domain in _ATS_TRACKING_DOMAINS

    existing = db.query(_models.Contact).filter(
        func.lower(_models.Contact.email) == email_addr
    ).first()

    # Fallback: same person by name+company — normalize ordering (Mehra, Malvika == Malvika Mehra)
    if not existing and name and firma:
        norm_new = _normalize_name(name)
        candidates = db.query(_models.Contact).filter(
            func.lower(_models.Contact.firma) == firma.strip().lower(),
        ).all()
        for c in candidates:
            if _normalize_name(c.name) == norm_new:
                existing = c
                break
        if existing and not is_ats_tracking and not existing.email:
            existing.email = email_addr

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
            old_v, existing.telefon = existing.telefon, extra['telefon']
            add_audit(db, "update", "sync", contact_id=existing.id, app_id=app_id,
                      field="telefon", old_value=old_v, new_value=existing.telefon, user_id=user_id)
        if not existing.rolle and extra.get('rolle'):
            old_v, existing.rolle = existing.rolle, extra['rolle']
            add_audit(db, "update", "sync", contact_id=existing.id, app_id=app_id,
                      field="rolle", old_value=old_v, new_value=existing.rolle, user_id=user_id)
        # INSERT OR IGNORE bypasses ORM relationship tracking — no autoflush race
        db.execute(_LINK_SQL, {"cid": existing.id, "aid": app_id})
        return

    raw_name = name.strip() or email_addr.split("@")[0]
    nachname, vorname = _split_name(raw_name)
    contact = _models.Contact(
        name=raw_name,
        vorname=vorname or None,
        email=None if is_ats_tracking else email_addr,
        firma=firma or None,
        typ="Headhunter" if is_headhunter else None,
        letzter_kontakt=event_date,
        telefon=extra.get('telefon') or None,
        rolle=extra.get('rolle') or None,
        user_id=user_id,
    )
    db.add(contact)
    db.flush()  # get contact.id
    db.execute(_LINK_SQL, {"cid": contact.id, "aid": app_id})
    add_audit(db, "create", "sync", contact_id=contact.id, app_id=app_id,
              new_value=contact.name, reason_key="contact_from_email_sync", user_id=user_id)


def upsert_contact_from_sender(
    db: Session,
    raw_sender: str,
    app_id: int,
    firma: str,
    is_headhunter: bool,
    event_date=None,
    body: str = "",
    user_id: Optional[int] = None,
) -> None:
    """Parse 'Display Name <email@host>', extract footer info, and upsert contact."""
    name, addr = parseaddr(raw_sender or "")
    extra = _extract_footer_info(body, name) if body else {}
    _upsert_contact(db, name, addr, app_id, firma, is_headhunter, event_date, extra, user_id=user_id)


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


def init_progress(source: str, label: str, step: Optional[str] = None, lang: str = "de") -> None:
    _progress[source] = SyncProgress(label=label, step=step or t("starting", lang))


def update_progress(source: str, current: int, total: int, step: str = "") -> None:
    p = _progress.get(source)
    if p:
        p.current = current
        p.total = total
        if step:
            p.step = step


def finish_progress(source: str, step: Optional[str] = None, lang: str = "de") -> None:
    p = _progress.get(source)
    if p:
        p.done = True
        p.step = step or t("done", lang)


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

def load_synced_ids(db: Session, source: str) -> set[str]:
    """Load all already-synced external IDs for a source into a set for O(1) lookups."""
    rows = db.query(models.SyncedItem.external_id).filter_by(source=source).all()
    return {r[0] for r in rows}


def is_synced(db: Session, source: str, external_id: str) -> bool:
    return db.query(models.SyncedItem).filter_by(
        source=source, external_id=external_id
    ).first() is not None


def mark_synced(db: Session, source: str, external_id: str, user_id: Optional[int] = None) -> None:
    db.add(models.SyncedItem(source=source, external_id=external_id, user_id=user_id))


def purge_source(db: Session, source: str, user_id: Optional[int] = None) -> None:
    """Clear SyncedItem records so items get reprocessed on next sync.
    Events are intentionally kept — deleting them causes permanent data loss
    when the re-sync window doesn't cover all previously-synced items.

    user_id: bulk .delete() umgeht (wie jedes Query.delete()) den zentralen
    Mandanten-Filter — daher hier optional explizit gefiltert. None (noch
    nicht auf Mandantentrennung umgestellte Aufrufer) erhält das bisherige,
    ungescopte Verhalten."""
    q = db.query(models.SyncedItem).filter_by(source=source)
    if user_id is not None:
        q = q.filter_by(user_id=user_id)
    q.delete()


# ── Text helpers ──────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def decode_b64(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")


def vobj_str(vobj, attr: str) -> str:
    """Extract plain string value from a vObject attribute (e.g. a VEVENT/VTODO's
    summary/description/uid). Calling str() directly on the ContentLine object
    itself yields its debug repr (e.g. '<SUMMARY{}Interview bei Contoso>')
    instead of the actual text — always go through .value."""
    obj = getattr(vobj, attr, None)
    if obj is None:
        return ""
    return str(getattr(obj, "value", None) or obj or "")


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

# A role title that IS (in full, not just contains) one of these generic
# words is rejected as a search/match term — regression found live
# 2026-07-16: application #230's role "Senior SW Projektleiter BMW" got
# word-split (see sync_targeted.py's now-removed _role_query_words()) into
# standalone terms "Senior"/"Projektleiter", each generic enough to match
# hundreds of unrelated emails (LinkedIn digests, other companies'
# recruiting mail), all wrongly attributed to that one application — 328
# junk timeline events in a single sync run. A multi-word role ("Senior SW
# Projektleiter BMW") stays specific enough to use as one whole phrase (see
# build_firm_index() below); only a role that's JUST one of these words is
# excluded entirely, since it wouldn't narrow anything.
_GENERIC_ROLE_TERMS = frozenset({
    "senior", "junior", "lead", "manager", "director", "head", "chief",
    "specialist", "engineer", "consultant", "analyst", "associate",
    "assistant", "coordinator", "executive", "officer", "president",
    "vp", "svp", "principal", "staff", "architect", "expert", "trainee",
    "intern", "praktikant", "praktikantin", "werkstudent", "werkstudentin",
    "leiter", "leiterin", "mitarbeiter", "mitarbeiterin", "berater",
    "beraterin", "referent", "referentin", "sachbearbeiter",
    "sachbearbeiterin", "teamleiter", "teamleiterin", "abteilungsleiter",
    "abteilungsleiterin", "geschaeftsfuehrer", "geschäftsführer",
    "geschäftsführerin",
})

_GENERIC_EMAIL_DOMAINS = frozenset([
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.de",
    "outlook.com", "hotmail.com", "hotmail.de", "live.com",
    "web.de", "gmx.de", "gmx.net", "gmx.com",
    "t-online.de", "icloud.com", "me.com", "mac.com",
    "msn.com", "aol.com", "protonmail.com", "pm.me",
])

# ── Deterministic event-type patterns (keyword matching, no AI) ───────────────

_RE_REJECTION = re.compile(
    r'\b(absage|abgelehnt|leider nicht|leider haben|bedauern|nicht berücksichtigt|'
    r'nicht in betracht|nicht weiterverfolgen|anderweitig besetzt|anderen kandidaten|'
    r'no longer|unfortunately|not moving forward|unsuccessful|regret to inform|'
    r'not be moving|have decided not|we have filled|position has been filled)\b',
    re.IGNORECASE,
)
_RE_INVITATION = re.compile(
    r'\b(einladung|einladen|interview|vorstellungsgespräch|kennenlerngespräch|'
    r'kennenlernen|probearbeitstag|assessment.?center|telefoninterview|'
    r'invitation|schedule an interview|would like to meet|discuss your application|'
    r'next round|nächste runde|telefonat vereinbaren|gespräch einladen|'
    r'möchten sie einladen|freuen uns auf ein gespräch)\b',
    re.IGNORECASE,
)
_RE_OFFER = re.compile(
    r'\b(vertragsangebot|jobangebot|angebot erhalten|angebot unterbreiten|zusage|'
    r'freuen uns ihnen anzubieten|pleased to offer|job offer|offer of employment|'
    r'employment offer|offer letter|we would like to offer)\b',
    re.IGNORECASE,
)
_RE_ACK = re.compile(
    r'\b(bewerbung erhalten|eingang bestätigt|eingegangen|bewerbung eingegangen|'
    r'received your application|thank you for applying|danke für ihre bewerbung|'
    r'bestätigen den eingang|haben ihre bewerbung|bewerbung ist bei uns angekommen)\b',
    re.IGNORECASE,
)


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
        if (len(first) >= 4
                and first.lower() not in _COMMON_FIRST_NAMES
                and first.lower() not in _CORP_SUFFIXES
                and first not in variants):
            variants.append(first)
    return variants


def build_firm_index(db: Session) -> tuple[str, dict[str, list[dict]]]:
    """Build a search-term clause and reverse index term→apps from all applications.

    Terms are the company name (+ corporate-suffix-stripped variants via
    term_variants), the headhunter target/filled-by firm, past merge-alias
    names, and the role title (whole phrase, not split into words — see
    _GENERIC_ROLE_TERMS) — each an independent OR-criterion, same as the
    others. A role title alone (no company-name match) is enough to hit an
    application; a role that's just one generic word ("Manager") is
    excluded entirely (see _GENERIC_ROLE_TERMS), but a multi-word role
    sharing surface words with another application's role can still
    over-match (resolved the same way a firm-name collision already is: the
    caller picks the first matching app — see _classify_deterministic)."""
    active = db.query(models.Application).filter(models.Application.main_status != "rejected").all()
    active_ids = {a.id for a in active}
    app_by_id = {a.id: a for a in active}
    term_to_apps: dict[str, list[dict]] = {}
    for a in active:
        app_dict = {"id": a.id, "firma": a.firma, "rolle": a.rolle}
        for raw_term in [a.firma, a.zielfirma_bei_hh, a.wurde_besetzt_von]:
            if raw_term and len(raw_term.strip()) >= 3:
                for key in term_variants(raw_term):
                    term_to_apps.setdefault(key, [])
                    if app_dict not in term_to_apps[key]:
                        term_to_apps[key].append(app_dict)
        if a.rolle and len(a.rolle.strip()) >= 3 and a.rolle.strip().lower() not in _GENERIC_ROLE_TERMS:
            role_key = a.rolle.strip()
            term_to_apps.setdefault(role_key, [])
            if app_dict not in term_to_apps[role_key]:
                term_to_apps[role_key].append(app_dict)

    # Also index alias firma names from past merges so old names still match
    for alias in db.query(models.MergeAlias).filter(
        models.MergeAlias.entity_type == "application",
        models.MergeAlias.alias_firma.isnot(None),
    ).all():
        if alias.canonical_id not in active_ids:
            continue
        canonical = app_by_id[alias.canonical_id]
        app_dict = {"id": canonical.id, "firma": canonical.firma, "rolle": canonical.rolle}
        for key in term_variants(alias.alias_firma):
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


_ADDR_RE = re.compile(r'[\w.+\-]+@[\w.\-]+\.[a-zA-Z]{2,}')


def extract_email_addresses(header_val: str) -> list[str]:
    """Extract all email addresses from a header value string."""
    return [m.lower() for m in _ADDR_RE.findall(header_val)]


def build_contact_email_index(db: Session) -> dict[str, list[dict]]:
    """Map exact contact email → [app_dict] for contacts linked to applications."""
    index: dict[str, list[dict]] = {}
    for c in db.query(models.Contact).all():
        if not c.email or "@" not in c.email:
            continue
        email_lower = c.email.lower()
        domain = email_lower.split("@")[-1]
        if domain in _GENERIC_EMAIL_DOMAINS:
            continue
        for app in (c.applications or []):
            app_dict = {"id": app.id, "firma": app.firma, "rolle": app.rolle}
            bucket = index.setdefault(email_lower, [])
            if app_dict not in bucket:
                bucket.append(app_dict)
    return index


def find_apps_from_addresses(
    from_val: str,
    to_cc_val: str,
    contact_email_index: dict[str, list[dict]],
    contact_domain_index: dict[str, list[dict]],
) -> list[dict]:
    """Match applications by FROM/TO/CC email addresses only — no content analysis."""
    seen_ids: set[int] = set()
    result: list[dict] = []

    def _add(app_dict: dict) -> None:
        if app_dict["id"] not in seen_ids:
            result.append(app_dict)
            seen_ids.add(app_dict["id"])

    for addr in extract_email_addresses(from_val + "," + to_cc_val):
        for app_dict in contact_email_index.get(addr, []):
            _add(app_dict)
        if "@" in addr:
            domain = addr.split("@")[1]
            if domain not in _GENERIC_EMAIL_DOMAINS:
                for app_dict in contact_domain_index.get(domain, []):
                    _add(app_dict)

    return result


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


def find_matching_apps(
    from_val: str,
    to_cc_val: str,
    raw_text: str,
    contact_email_index: dict[str, list[dict]],
    contact_domain_index: dict[str, list[dict]],
    term_to_apps: dict[str, list[dict]],
) -> list[dict]:
    """Unified mail-matching used identically by both Gmail and iCloud Mail
    (bulk and targeted) — combines find_apps_from_addresses() (exact contact
    email / contact domain from the From/To/Cc headers) with find_hint_apps()
    (company-name — incl. corporate-suffix variants — and role-title
    substring match, plus firm-name-in-domain, against the full text). Before
    this, Gmail only matched by address and iCloud only by text/domain —
    each missed what the other caught (Gmail missed company/role mentions
    from senders with no saved contact; iCloud missed exact-contact-address
    hits it never checked). raw_text should be the fullest text available at
    the call site (subject-only at a cheap header-only pass, subject+body
    once fetched) — callers should re-run this once the body is available
    even if an earlier pass already matched, since body-only company/role
    mentions can add matches a header-only pass couldn't see."""
    seen_ids: set[int] = set()
    result: list[dict] = []

    def _add(app_dict: dict) -> None:
        if app_dict["id"] not in seen_ids:
            result.append(app_dict)
            seen_ids.add(app_dict["id"])

    for a in find_apps_from_addresses(from_val, to_cc_val, contact_email_index, contact_domain_index):
        _add(a)
    for a in find_hint_apps(raw_text, term_to_apps, contact_domain_index):
        _add(a)

    return result


# ── Deterministic classification helpers ─────────────────────────────────────

def _classify_type_from_text(text: str, lang: str = "de") -> tuple[str, Optional[str], str]:
    """Returns (event_typ, suggested_main_status|None, reason) using keyword patterns."""
    if _RE_REJECTION.search(text):
        return 'status', 'rejected', t("rejection_keyword", lang)
    if _RE_OFFER.search(text):
        return 'status', 'negotiating', t("offer_keyword", lang)
    if _RE_INVITATION.search(text):
        return 'gespräch', None, t("invitation_keyword", lang)
    if _RE_ACK.search(text):
        return 'status', None, t("ack_keyword", lang)
    return 'notiz', None, t("no_keyword_note", lang)


def _extract_title_from_raw(raw_text: str) -> str:
    """Extract Betreff/Titel/Datei/Erinnerung header value from raw text."""
    for line in raw_text.splitlines():
        line = line.strip()
        for prefix in ('Betreff:', 'Subject:', 'Titel:', 'Datei:', 'Erinnerung:'):
            if line.startswith(prefix):
                val = line.split(':', 1)[1].strip()
                if val:
                    return val[:200]
    return ''


def _extract_body_preview(raw_text: str, max_len: int = 300) -> Optional[str]:
    """Return text after the first blank line (body after headers)."""
    lines = raw_text.splitlines()
    past_headers = False
    body_lines: list[str] = []
    for line in lines:
        if not past_headers:
            if not line.strip():
                past_headers = True
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return body[:max_len] if body else None


def _classify_deterministic(
    source: str,
    raw_text: str,
    date_hint: Optional[datetime],
    hint_apps: list[dict],
    lang: str = "de",
) -> Optional[dict]:
    """
    Classify an item without AI.

    Returns a result dict {app_id, typ, titel, status, notiz} when confident,
    or None when AI disambiguation is required (2+ hint_apps for a non-calendar source).
    """
    # Calendar events: always a gespräch
    if source in ('gcal', 'icloud_cal'):
        return {
            'app_id': hint_apps[0]['id'],
            'typ': 'gespräch',
            'titel': _extract_title_from_raw(raw_text) or 'Termin',
            'status': None,
            'notiz': None,
            'reason': t("calendar_always_interview", lang),
        }

    # Local documents: firm from filename/folder name, always notiz
    if source == 'local_files':
        if len(hint_apps) == 1:
            return {
                'app_id': hint_apps[0]['id'],
                'typ': 'notiz',
                'titel': _extract_title_from_raw(raw_text) or 'Dokument',
                'status': None,
                'notiz': None,
                'reason': t("local_file_note", lang),
            }
        return None  # multiple matches for a file → skip

    # Single firm match: classify event type by keywords
    if len(hint_apps) == 1:
        typ, status, reason = _classify_type_from_text(raw_text, lang)
        notiz: Optional[str] = None
        if source == 'icloud_notes':
            notiz = _extract_body_preview(raw_text, max_len=300)
        return {
            'app_id': hint_apps[0]['id'],
            'typ': typ,
            'titel': _extract_title_from_raw(raw_text) or source,
            'status': status,
            'notiz': notiz,
            'reason': reason,
        }

    # Multiple firm matches → pick first app
    first_app = hint_apps[0]
    typ, status, reason = _classify_type_from_text(raw_text, lang)
    notiz: Optional[str] = None
    if source == 'icloud_notes':
        notiz = _extract_body_preview(raw_text, max_len=300)
    return {
        'app_id': first_app['id'],
        'typ': typ,
        'titel': _extract_title_from_raw(raw_text) or source,
        'status': status,
        'notiz': notiz,
        'reason': t("reason_with_match_count", lang, reason=reason, count=len(hint_apps)),
    }


def _save_deterministic_event(
    db: Session,
    source: str,
    external_id: str,
    det: dict,
    raw_text: str,
    date_hint: Optional[datetime],
    user_id: Optional[int] = None,
) -> bool:
    """Persist a deterministically classified event. Returns True if event was created."""
    app = db.query(models.Application).get(det['app_id'])
    if not app:
        mark_synced(db, source, external_id, user_id)
        return False

    datum = date_hint.date() if date_hint else None
    pfx = f"[SYNC #{det['app_id']} {source}]"
    if _predates_bewerbung(datum, app):
        log.debug("{} {} → SKIP zu alt ({}  <  Bewerbungsdatum {})", pfx, external_id[:20], datum, app.datum_bewerbung)
        mark_synced(db, source, external_id, user_id)
        return False

    # Time prefix only for mail/note events, not calendar or files
    time_pfx = ""
    if source not in ('gcal', 'icloud_cal', 'local_files'):
        time_pfx = _time_prefix(date_hint)

    notiz = det.get('notiz')
    if time_pfx and notiz:
        notiz = f"{time_pfx.rstrip(chr(10))}\n{notiz}"
    elif time_pfx:
        notiz = time_pfx.rstrip('\n') or None

    log.debug("{} {!r} → CREATED typ={} datum={} ({})", pfx, det['titel'], det['typ'], datum, det.get('reason', '?'))
    new_event = models.Event(
        application_id=det['app_id'],
        typ=det['typ'],
        datum=datum,
        titel=det['titel'] or source,
        notiz=notiz or None,
        source=source,
        external_id=external_id,
        user_id=user_id,
    )
    db.add(new_event)
    db.flush()
    add_audit(db, "create", source, app_id=det['app_id'], event_id=new_event.id,
              new_value=new_event.titel, reason=det.get('reason'), user_id=user_id)
    mark_synced(db, source, external_id, user_id)

    # Auto-create contact from sender (mail events only)
    if source in ('gmail', 'icloud_mail'):
        for line in raw_text.splitlines():
            if line.startswith("Von: ") or line.startswith("From: "):
                sender = line.split(": ", 1)[1].strip()
                if sender:
                    upsert_contact_from_sender(
                        db, sender,
                        app_id=det['app_id'],
                        firma=app.firma,
                        is_headhunter=app.is_headhunter,
                        event_date=datum,
                        body=raw_text,
                        user_id=user_id,
                    )
                break

    # Queue status change for user review (PendingMatch)
    status = det.get('status')
    if status and app.main_status != status:
        exists = db.query(models.PendingMatch).filter_by(
            source=source, external_id=f"{external_id}__status"
        ).first()
        already_reviewed = db.query(models.PendingMatch).filter(
            models.PendingMatch.suggested_app_id == det['app_id'],
            models.PendingMatch.suggested_main_status == status,
            models.PendingMatch.review_status.in_(["approved", "rejected"]),
        ).first()
        if not exists and not already_reviewed:
            db.add(models.PendingMatch(
                source=source,
                external_id=f"{external_id}__status",
                confidence=80,
                event_type="status_change",
                datum=datum,
                titel=f"Status: {app.main_status} → {status}",
                suggested_app_id=det['app_id'],
                suggested_main_status=status,
                status_only=True,
                user_id=user_id,
            ))

    return True


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
    user_id: Optional[int] = None,
) -> bool:
    """Classify and persist event using deterministic rules. No AI."""
    if is_synced(db, source, external_id):
        return False

    if not hint_apps:
        mark_synced(db, source, external_id, user_id)
        return False

    lang = resolve_ui_language(db, user_id)
    det = _classify_deterministic(source, raw_text, date_hint, hint_apps, lang)
    if det is not None:
        return _save_deterministic_event(db, source, external_id, det, raw_text, date_hint, user_id)

    mark_synced(db, source, external_id, user_id)
    return False


def save_classified_event(
    db: Session,
    source: str,
    external_id: str,
    result: dict,
    raw_text: str,
    date_hint: Optional[datetime],
    target_app: dict,
    extra_notiz: Optional[str] = None,
    user_id: Optional[int] = None,
) -> bool:
    """Persist a pre-classified result as an event. Returns True if event was created."""
    confidence = float(result.get("confidence") or 0)
    if not result.get("relevant", True) or confidence < 0.55:
        mark_synced(db, source, external_id, user_id)
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

    app_obj = db.query(models.Application).get(target_app["id"])
    if app_obj and _predates_bewerbung(datum, app_obj):
        mark_synced(db, source, external_id, user_id)
        return False
    new_event = models.Event(
        application_id=target_app["id"],
        typ=_map_event_type(result.get("event_type", "note")),
        datum=datum,
        titel=result.get("titel") or source,
        notiz=notiz,
        autor=autor,
        source=source,
        external_id=external_id,
        user_id=user_id,
    )
    db.add(new_event)
    db.flush()
    lang = resolve_ui_language(db, user_id)
    if ai_extract:
        ai_reason = t("ai_recognized_with_confidence", lang, extract=ai_extract, confidence=f"{confidence:.0%}")
    else:
        ai_reason = t("ai_classification_with_confidence", lang, confidence=f"{confidence:.0%}")
    add_audit(db, "create", source, app_id=target_app["id"], event_id=new_event.id,
              new_value=new_event.titel, reason=ai_reason, user_id=user_id)
    mark_synced(db, source, external_id, user_id)

    # Auto-create contact from sender, extract phone/role from mail footer
    if autor:
        upsert_contact_from_sender(
            db, autor,
            app_id=target_app["id"],
            firma=target_app.get("firma", ""),
            is_headhunter=target_app.get("is_headhunter", False),
            event_date=datum,
            body=raw_text,
            user_id=user_id,
        )

    # Queue status change for user review (never apply automatically)
    new_main = result.get("suggested_main_status")
    if new_main and app_obj and app_obj.main_status != new_main:
        already = db.query(models.PendingMatch).filter_by(
            source=source, external_id=f"{external_id}__status"
        ).first()
        already_reviewed = db.query(models.PendingMatch).filter(
            models.PendingMatch.suggested_app_id == target_app["id"],
            models.PendingMatch.suggested_main_status == new_main,
            models.PendingMatch.review_status.in_(["approved", "rejected"]),
        ).first()
        if not already and not already_reviewed:
            db.add(models.PendingMatch(
                source=source,
                external_id=f"{external_id}__status",
                confidence=int(confidence * 100),
                event_type="status_change",
                datum=datum,
                titel=f"Status: {app_obj.main_status} → {new_main}",
                extract=result.get("extract"),
                raw_content=raw_text,
                suggested_app_id=target_app["id"],
                suggested_main_status=new_main,
                suggested_sub_status=result.get("suggested_sub_status"),
                status_only=True,
                user_id=user_id,
            ))

    return True


async def process_item_for_app(
    db: Session,
    source: str,
    external_id: str,
    raw_text: str,
    date_hint: Optional[datetime],
    target_app: dict,
    user_id: Optional[int] = None,
) -> bool:
    """Like process_item but scoped to a single known application. No AI."""
    return await process_item(db, source, external_id, raw_text, date_hint, hint_apps=[target_app], user_id=user_id)
