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

from app.audit import add_audit
from app.i18n_strings import resolve_ui_language, t
from app.database import get_db, SessionLocal, set_session_user
from app import models, schemas
from app.auth.dependencies import get_current_user
from app.routers.sync_common import (
    is_synced, mark_synced, strip_html,
    term_variants, process_item, process_item_for_app,
    init_progress, update_progress, finish_progress,
    upsert_contact_from_sender, vobj_str, _GENERIC_ROLE_TERMS,
)
from app.logger import get_logger

log = get_logger("sync", source="targeted")
router = APIRouter(prefix="/api/sync/targeted", tags=["sync"])

# Circuit breaker: a targeted-sync run for one application matching more mail
# than this is treated as a sign the search terms turned out too generic
# rather than a genuinely large number of relevant messages — see #230's
# incident (328 unrelated emails from one run) in _search_terms()'s
# docstring. The run is aborted (nothing saved) rather than silently
# flooding the timeline; the error surfaces in the sync result for the user
# to notice and investigate (e.g. edit the role/company name).
_MAX_TARGETED_MAIL_MATCHES = 30


def _search_terms(app: models.Application, db: Session) -> list[str]:
    """All unique search terms for this application (firm + zielfirma variants,
    plus the role title as one whole phrase — not split into words, see
    _GENERIC_ROLE_TERMS's docstring in sync_common.py for why: word-splitting
    a role like "Senior SW Projektleiter BMW" into standalone terms "Senior"/
    "Projektleiter" caused a real false-positive flood, 328 unrelated emails
    wrongly attributed to one application in a single sync run).

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
    if app.rolle and len(app.rolle.strip()) >= 3 and app.rolle.strip().lower() not in _GENERIC_ROLE_TERMS:
        role = app.rolle.strip()
        if role.lower() not in seen:
            seen.add(role.lower())
            result.append(role)
    return result


def _app_dict(app: models.Application) -> dict:
    d: dict = {"id": app.id, "firma": app.firma, "rolle": app.rolle, "is_headhunter": app.is_headhunter}
    if app.zielfirma_bei_hh:
        d["zielfirma"] = app.zielfirma_bei_hh
    return d


_PERSONAL_DOMAINS = {
    'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.de', 'hotmail.com',
    'hotmail.de', 'outlook.com', 'outlook.de', 'gmx.de', 'gmx.net', 'gmx.at',
    'web.de', 'icloud.com', 'me.com', 't-online.de', 'freenet.de',
}


def _domain_from_website(website: Optional[str]) -> Optional[str]:
    """Extract bare domain from a website URL, e.g. 'https://www.here.com/' → 'here.com'."""
    if not website:
        return None
    try:
        from urllib.parse import urlparse
        host = urlparse(website).hostname or ""
        host = host.lower().removeprefix("www.")
        return host if host and '.' in host else None
    except Exception:
        return None


def _company_domains_for_app(
    app: models.Application, terms: list[str], db: Session, contacts: Optional[list] = None,
) -> list[str]:
    """Email domains for this application, derived from linked CompanyProfile websites
    AND from already-confirmed contact email addresses.

    - Direct application: domain from app.company_profile.website
    - HH application: domain from app.target_company_profile.website (the actual employer),
      plus app.company_profile.website (the HH firm) so HH mails are also captured.
    - Contact emails are added too — these are manually verified/confirmed addresses and
      take precedence over web-enrichment guesses, which can point to the wrong domain
      (e.g. a similarly-named company with a different TLD).
    Personal/freemail domains are excluded.

    `contacts` defaults to the live `app.contacts` relationship, but callers running
    several sources in the same sync pass a pre-sync snapshot instead — see
    _do_sync()'s docstring/comment for why: within one asyncio.gather() call sharing
    one DB session, a contact one source (e.g. mail) creates from a false-positive
    match becomes visible to app.contacts immediately (flushed, not yet committed),
    so another source computing its own domain list moments later would otherwise
    treat that brand-new, unverified contact's domain as trustworthy — this is
    exactly how application #230's mail false-positive flood (2026-07-16) cascaded
    into wrongly-matched calendar events: the domains involved (e.g. exxeta.com,
    ipg-automotive's domain) all came from contacts mail sync had just created
    moments earlier in the same run, not from any real Qorix-related signal."""
    domains: set[str] = set()

    def _add_profile(profile) -> None:
        if profile:
            d = _domain_from_website(profile.website)
            if d and d not in _PERSONAL_DOMAINS:
                domains.add(d)

    if app.is_headhunter:
        _add_profile(app.target_company_profile)   # Zielfirma (may be None)
        _add_profile(app.company_profile)           # HH-Firma
    else:
        _add_profile(app.company_profile)

    for contact in (contacts if contacts is not None else app.contacts):
        if not contact.email or "@" not in contact.email:
            continue
        d = contact.email.split("@", 1)[1].strip().lower()
        if d and d not in _PERSONAL_DOMAINS:
            domains.add(d)

    return sorted(domains)


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


# ── Gmail ─────────────────────────────────────────────────────────────────────

async def _sync_gmail_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
    from app.routers.sync_google import _get_cfg as _get_google_cfg, _refresh_if_needed, _gmail_body
    cfg = _get_google_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        return 0, 0, []

    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    app_id = app.id
    pfx = f"[SYNC #{app_id} gmail]"
    app_domains = app_dict.get("_domain_snapshot")
    if app_domains is None:
        app_domains = _company_domains_for_app(app, terms, db)
    text_terms = [w for w in (_query_safe(term) for term in terms) if w]
    if not app_domains and not text_terms:
        log.debug("{} keine Unternehmens-Domain und keine Suchbegriffe → übersprungen", pfx)
        return 0, 0, []

    since = app.datum_bewerbung or (datetime.now(timezone.utc) - timedelta(days=365)).date()
    after_ts = int(datetime(since.year, since.month, since.day, tzinfo=timezone.utc).timestamp())
    # Domain clause (from:/to:) plus company-name/role phrase clause — a mail
    # mentioning the company or role by name from a sender with no known
    # company domain would otherwise never even be listed, let alone matched.
    parts = [f"(from:{d} OR to:{d})" for d in app_domains]
    parts += [f'"{w}"' for w in text_terms]
    query = f"after:{after_ts} ({' OR '.join(parts)})"
    log.debug("{} domains: {}  query: {}", pfx, app_domains, query)

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

    log.debug("{} {} Nachrichten gefunden", pfx, len(messages))
    lang = resolve_ui_language(db, user_id)
    created = skipped = 0
    errors: list[str] = []
    total = len(messages)

    pending: list[dict] = []
    for i, msg_ref in enumerate(messages):
        update_progress("targeted_gmail", i, total, t("gmail_loading_progress", lang, current=i + 1, total=total))
        msg_id = msg_ref["id"]
        if is_synced(db, "gmail", msg_id):
            log.debug("{} {} → SKIP bereits synced", pfx, msg_id)
            skipped += 1
            continue
        try:
            msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        except Exception as e:
            errors.append(f"gmail/{msg_id}: {e}")
            continue

        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        sender  = headers.get("from", "")
        subject = headers.get("subject", "(kein Betreff)")
        date_str = headers.get("date", "")
        body = _gmail_body(msg["payload"])[:1500]

        date_hint = None
        try:
            from email.utils import parsedate_to_datetime
            date_hint = parsedate_to_datetime(date_str).astimezone(timezone.utc)
        except Exception:
            pass

        raw = f"Von: {sender}\nBetreff: {subject}\n\n{body}"
        # Re-verify the fetched message actually contains one of the real
        # terms/domains that justified fetching it — the query above is a
        # coarse pre-filter (it can OR in a fairly broad clause), not proof
        # of relevance; without this check every message the query returns
        # gets unconditionally attributed to this one application below
        # (hint_apps is hardcoded to it), which is exactly how #230's false-
        # positive flood happened.
        if not _text_matches(raw, terms) and not any(d in raw.lower() for d in app_domains):
            log.debug("{} {} SUBJ:{!r} FROM:{!r} → SKIP kein Begriff im Volltext bestätigt", pfx, msg_id, subject, sender)
            skipped += 1
            continue

        log.debug("{} {} SUBJ:{!r} FROM:{!r} → pending", pfx, msg_id, subject, sender)
        pending.append({"id": msg_id, "raw": raw, "date_hint": date_hint})

    if len(pending) > _MAX_TARGETED_MAIL_MATCHES:
        log.warning("{} {} Treffer übersteigt das Limit ({}) — Suchbegriffe vermutlich zu generisch, Lauf abgebrochen",
                    pfx, len(pending), _MAX_TARGETED_MAIL_MATCHES)
        return 0, total, [t("targeted_mail_too_many_matches", lang, count=len(pending), limit=_MAX_TARGETED_MAIL_MATCHES)]

    for i, item in enumerate(pending):
        update_progress("targeted_gmail", i, len(pending), t("gmail_progress", lang, current=i + 1, total=len(pending)))
        try:
            ok = await process_item(db, "gmail", item["id"], item["raw"], item["date_hint"], hint_apps=[app_dict], user_id=user_id)
            if ok:
                created += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"gmail/{item['id']}: {e}")

    log.debug("{} fertig: {} erstellt, {} übersprungen, {} fehler", pfx, created, skipped, len(errors))
    return created, total, errors


# ── Google Calendar ───────────────────────────────────────────────────────────

async def _sync_gcal_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
    from app.routers.sync_google import _get_cfg as _get_google_cfg, _refresh_if_needed
    cfg = _get_google_cfg(db)
    if not cfg or not cfg.refresh_token_enc:
        return 0, 0, []

    from googleapiclient.discovery import build
    creds = _refresh_if_needed(cfg, db)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    app_id = app.id
    pfx = f"[SYNC #{app_id} gcal]"
    app_domains = app_dict.get("_domain_snapshot")
    if app_domains is None:
        app_domains = _company_domains_for_app(app, terms, db)
    if not app_domains:
        log.debug("{} keine Unternehmens-Domain → übersprungen", pfx)
        return 0, 0, []

    since = app.datum_bewerbung or (datetime.now(timezone.utc) - timedelta(days=365)).date()
    now = datetime.now(timezone.utc)
    try:
        events_result = service.events().list(
            calendarId="primary",
            timeMin=datetime(since.year, since.month, since.day, tzinfo=timezone.utc).isoformat(),
            timeMax=(now + timedelta(days=90)).isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=500,
        ).execute()
    except Exception as e:
        return 0, 0, [f"Google Calendar: {e}"]

    def _ev_matches_domain(ev: dict) -> bool:
        emails = [((ev.get("organizer") or {}).get("email") or "")]
        emails += [(a.get("email") or "") for a in (ev.get("attendees") or [])]
        return any(
            e and '@' in e and e.split('@', 1)[1].lower() in app_domains
            for e in emails
        )

    log.debug("{} domains: {}", pfx, app_domains)
    all_events = events_result.get("items", [])
    cal_events = [ev for ev in all_events if _ev_matches_domain(ev)]
    log.debug("{} {} Termine gesamt, {} Domain-Match", pfx, len(all_events), len(cal_events))
    created = skipped = 0
    errors: list[str] = []

    for ev in cal_events:
        ev_id = ev.get("id", "")
        if is_synced(db, "gcal", ev_id):
            log.debug("{} {} SUMMARY:{!r} → SKIP bereits synced", pfx, ev_id, ev.get("summary"))
            skipped += 1
            continue

        log.debug("{} {} SUMMARY:{!r} → pending", pfx, ev_id, ev.get("summary"))
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
            gcal_titel = summary or "Kalendertermin"
            gcal_event = models.Event(
                application_id=app_dict["id"],
                typ="gespräch",
                datum=date_hint.date() if date_hint else None,
                titel=gcal_titel,
                notiz=notiz,
                source="gcal",
                external_id=ev_id,
                user_id=user_id,
            )
            db.add(gcal_event)
            db.flush()
            add_audit(db, "create", "gcal", app_id=app_dict["id"], event_id=gcal_event.id,
                      new_value=gcal_titel, user_id=user_id)
            mark_synced(db, "gcal", ev_id, user_id)
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
                    user_id=user_id,
                )
        except Exception as e:
            errors.append(f"gcal/{summary}: {e}")

    return created, len(cal_events), errors


# ── iCloud Mail ───────────────────────────────────────────────────────────────

async def _sync_icloud_mail_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
    from app.routers.sync_icloud import _get_cfg as _get_icloud_cfg, _imap_body, _imap_connect_select
    cfg = _get_icloud_cfg(db)
    if not cfg:
        return 0, 0, []

    app_id = app.id
    pfx = f"[SYNC #{app_id} icloud_mail]"
    app_domains = app_dict.get("_domain_snapshot")
    if app_domains is None:
        app_domains = _company_domains_for_app(app, terms, db)
    text_terms = [w for w in (_query_safe(term) for term in terms) if w]
    if not app_domains and not text_terms:
        log.debug("{} keine Unternehmens-Domain und keine Suchbegriffe → übersprungen", pfx)
        return 0, 0, []

    def _imap_or(criteria: list[str]) -> str:
        if len(criteria) == 1:
            return f'TEXT "{criteria[0]}"'
        if len(criteria) == 2:
            return f'(OR TEXT "{criteria[0]}" TEXT "{criteria[1]}")'
        return f'(OR TEXT "{criteria[0]}" {_imap_or(criteria[1:])})'

    # Domain criteria plus company-name/role text criteria — same reasoning
    # as _sync_gmail_for_app above: a mail mentioning the company/role by
    # name without a known company domain would otherwise never match.
    search_criteria = (app_domains + text_terms)[:15]
    imap_query = _imap_or(search_criteria)
    since = app.datum_bewerbung
    if since:
        imap_query = f'(SINCE "{since.strftime("%d-%b-%Y")}" {imap_query})'
    log.debug("{} domains: {} terms: {}  query: {}", pfx, app_domains, text_terms, imap_query)

    created = skipped = 0
    errors: list[str] = []

    try:
        imap = await asyncio.to_thread(_imap_connect_select, cfg)
        _, msg_ids = await asyncio.to_thread(imap.search, None, imap_query)
        ids = msg_ids[0].split() if msg_ids[0] else []
    except Exception as e:
        return 0, 0, [f"iCloud Mail IMAP: {e}"]

    total = len(ids)
    log.debug("{} {} Nachrichten gefunden", pfx, total)
    lang = resolve_ui_language(db, user_id)

    pending: list[dict] = []
    for i, msg_id_bytes in enumerate(ids):
        update_progress("targeted_icloud_mail", i, total, t("icloud_mail_loading_progress", lang, current=i + 1, total=total))
        msg_id = msg_id_bytes.decode()
        if is_synced(db, "icloud_mail", msg_id):
            log.debug("{} {} → SKIP bereits synced", pfx, msg_id)
            skipped += 1
            continue
        try:
            _, data = await asyncio.to_thread(imap.fetch, msg_id_bytes, "(RFC822)")
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
        # Re-verify — see the matching comment in _sync_gmail_for_app above.
        # IMAP's TEXT search already did server-side content matching, so
        # this is mostly defense-in-depth here, but keeps both sources
        # symmetric and guards against any IMAP TEXT-matching quirk.
        if not _text_matches(raw, terms) and not any(d in raw.lower() for d in app_domains):
            log.debug("{} {} SUBJ:{!r} FROM:{!r} → SKIP kein Begriff im Volltext bestätigt", pfx, msg_id, subject, sender)
            skipped += 1
            continue

        log.debug("{} {} SUBJ:{!r} FROM:{!r} → pending", pfx, msg_id, subject, sender)
        pending.append({"id": msg_id, "raw": raw, "date_hint": date_hint})

    try:
        await asyncio.to_thread(imap.logout)
    except Exception:
        pass

    if len(pending) > _MAX_TARGETED_MAIL_MATCHES:
        log.warning("{} {} Treffer übersteigt das Limit ({}) — Suchbegriffe vermutlich zu generisch, Lauf abgebrochen",
                    pfx, len(pending), _MAX_TARGETED_MAIL_MATCHES)
        return 0, total, [t("targeted_mail_too_many_matches", lang, count=len(pending), limit=_MAX_TARGETED_MAIL_MATCHES)]

    for i, item in enumerate(pending):
        update_progress("targeted_icloud_mail", i, len(pending), t("icloud_mail_progress", lang, current=i + 1, total=len(pending)))
        try:
            ok = await process_item(db, "icloud_mail", item["id"], item["raw"], item["date_hint"], hint_apps=[app_dict], user_id=user_id)
            if ok:
                created += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"icloud_mail/{item['id']}: {e}")

    log.debug("{} fertig: {} erstellt, {} übersprungen, {} fehler", pfx, created, skipped, len(errors))
    return created, total, errors


_vobj_str = vobj_str  # lokaler Alias, historisch unter diesem Namen hier verwendet


# ── iCloud Calendar ───────────────────────────────────────────────────────────

async def _sync_icloud_cal_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
    from app.routers.sync_icloud import _get_cfg as _get_icloud_cfg, _caldav_calendars
    cfg = _get_icloud_cfg(db)
    if not cfg:
        return 0, 0, []

    try:
        import caldav  # noqa: F401 -- import-only check for the friendlier "not installed" message below
    except ImportError:
        return 0, 0, ["caldav nicht installiert"]

    app_id = app.id
    pfx = f"[SYNC #{app_id} icloud_cal]"
    app_domains = app_dict.get("_domain_snapshot")
    if app_domains is None:
        app_domains = _company_domains_for_app(app, terms, db)
    if not app_domains:
        log.debug("{} keine Unternehmens-Domain → übersprungen", pfx)
        return 0, 0, []

    def _ev_matches_domain_icloud(vevent) -> bool:
        emails: list[str] = []
        org_val = getattr(vevent, "organizer", None)
        if org_val:
            v = str(getattr(org_val, "value", org_val) or "")
            emails.append(v.lower().replace("mailto:", "").strip())
        for att in vevent.contents.get("attendee", []):
            v = str(getattr(att, "value", att) or "")
            emails.append(v.lower().replace("mailto:", "").strip())
        return any(
            '@' in e and e.split('@', 1)[1] in app_domains
            for e in emails
        )

    since = app.datum_bewerbung
    now = datetime.now(timezone.utc)
    start_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc) if since else now - timedelta(days=365)

    created = skipped = 0
    errors: list[str] = []

    try:
        calendars = await asyncio.to_thread(_caldav_calendars, cfg)
    except Exception as e:
        return 0, 0, [f"iCloud CalDAV: {e}"]

    log.debug("{} domains: {}", pfx, app_domains)

    def _collect_and_match(calendars) -> tuple[list, list, list[str]]:
        """Synchronous per-calendar date_search + domain-match, run via
        asyncio.to_thread() below — see _caldav_calendars()' docstring in
        sync_icloud.py for why. A local closure (not a shared helper) since
        it captures _ev_matches_domain_icloud/app_domains."""
        all_events: list = []
        matched: list = []
        errs: list[str] = []
        for cal in calendars:
            try:
                for ev in cal.date_search(start=start_dt, end=now + timedelta(days=90), expand=True):
                    try:
                        vevent = ev.vobject_instance.vevent
                        all_events.append(ev)
                        if _ev_matches_domain_icloud(vevent):
                            matched.append(ev)
                    except Exception:
                        continue
            except Exception as e:
                errs.append(f"Kalender {cal.name}: {e}")
        return all_events, matched, errs

    all_cal_events, matched_events, collect_errors = await asyncio.to_thread(_collect_and_match, calendars)
    errors.extend(collect_errors)

    log.debug("{} {} Termine gesamt, {} Domain-Match", pfx, len(all_cal_events), len(matched_events))

    for ev in matched_events:
        try:
            vevent = ev.vobject_instance.vevent
            summary = _vobj_str(vevent, "summary")
            desc = _vobj_str(vevent, "description")
            uid = _vobj_str(vevent, "uid") or str(ev.url)
        except Exception:
            continue

        if is_synced(db, "icloud_cal", uid):
            log.debug("{} {} SUMMARY:{!r} → SKIP bereits synced", pfx, uid[:16], summary)
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

        log.debug("{} {!r} → CREATED gespräch (Kalendertermin, Adress-Match)", pfx, summary)
        try:
            ical_titel = summary or "Kalendertermin"
            ical_event = models.Event(
                application_id=app_dict["id"],
                typ="gespräch",
                datum=date_hint.date() if date_hint else None,
                titel=ical_titel,
                notiz=notiz,
                source="icloud_cal",
                external_id=uid,
                user_id=user_id,
            )
            db.add(ical_event)
            db.flush()
            add_audit(db, "create", "icloud_cal", app_id=app_dict["id"], event_id=ical_event.id,
                      new_value=ical_titel, user_id=user_id)
            mark_synced(db, "icloud_cal", uid, user_id)
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
                    user_id=user_id,
                )
            continue
        except Exception as e:
            errors.append(f"icloud_cal/{summary}: {e}")
            continue
    log.debug("{} fertig: {} erstellt, {} übersprungen, {} fehler", pfx, created, skipped, len(errors))
    return created, len(matched_events), errors


# ── iCloud Notes ──────────────────────────────────────────────────────────────

async def _sync_icloud_notes_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
    from app.agent_client import agent_get

    pfx = f"[SYNC #{app.id} icloud_notes]"
    created = skipped = 0
    errors: list[str] = []

    try:
        resp = await agent_get(db, "/notes", timeout=30)
        if resp.status_code != 200:
            return 0, 0, [f"Agent (Notizen): {resp.text[:200]}"]
        notes = resp.json()
    except Exception as e:
        return 0, 0, [f"Rapport Agent nicht erreichbar: {e}"]

    # Smart filter: always include text-matching notes (company/role in title/body) +
    # the 30 most recent notes (relevant notes often don't mention the company by name).
    # This avoids sending hundreds of old unrelated notes through AI on every targeted sync.
    log.debug("{} text-Match-Begriffe: {}", pfx, terms)
    candidates = [n for n in notes if _text_matches((n.get("name") or "") + " " + (n.get("body") or ""), terms)]
    log.debug("{} {} Notizen gesamt, {} text-Match", pfx, len(notes), len(candidates))

    for note in candidates:
        title = (note.get("name") or "").strip()
        body = (note.get("body") or "").strip()
        uid = note.get("id") or title
        note_key = hashlib.md5(uid.encode()).hexdigest()[:16]

        if is_synced(db, "icloud_notes", note_key):
            log.debug("{} {} TITLE:{!r} → SKIP bereits synced", pfx, note_key, title)
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

        log.debug("{} {} TITLE:{!r} → pending", pfx, note_key, title)
        raw = f"Titel: {title}\n\n{body[:2000]}"
        try:
            ok = await process_item_for_app(db, "icloud_notes", note_key, raw, date_hint, app_dict, user_id=user_id)
        except Exception as e:
            errors.append(f"note/{title}: {e}")
            continue
        if ok:
            created += 1
        else:
            skipped += 1

    log.debug("{} fertig: {} erstellt, {} übersprungen, {} fehler", pfx, created, skipped, len(errors))
    return created, len(candidates), errors


# ── iCloud Contacts ───────────────────────────────────────────────────────────

async def _sync_contacts_for_app(app: models.Application, terms: list[str], db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
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

    lang = resolve_ui_language(db, user_id)
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

            # Email is required — contacts without it are useless for domain matching.
            if not email_val:
                skipped += 1
                continue

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

            match_reason = t("mentioned_in_app_text_or_email", lang) if name_in_app_text else t("company_matches_application", lang, org=org_val, app=app.firma)

            if existing:
                if linkedin_url and not existing.linkedin_url:
                    add_audit(db, "update", "sync", contact_id=existing.id, app_id=app.id,
                              field="linkedin_url", old_value=None, new_value=linkedin_url,
                              reason_key="contact_from_targeted_icloud_sync", reason_params={"match_reason": match_reason}, user_id=user_id)
                    existing.linkedin_url = linkedin_url
                if tel_val and not existing.telefon:
                    add_audit(db, "update", "sync", contact_id=existing.id, app_id=app.id,
                              field="telefon", old_value=None, new_value=tel_val,
                              reason_key="contact_from_targeted_icloud_sync", reason_params={"match_reason": match_reason}, user_id=user_id)
                    existing.telefon = tel_val
                if org_val and not existing.firma:
                    add_audit(db, "update", "sync", contact_id=existing.id, app_id=app.id,
                              field="firma", old_value=None, new_value=org_val,
                              reason_key="contact_from_targeted_icloud_sync", reason_params={"match_reason": match_reason}, user_id=user_id)
                    existing.firma = org_val
                if title_val and not existing.rolle:
                    add_audit(db, "update", "sync", contact_id=existing.id, app_id=app.id,
                              field="rolle", old_value=None, new_value=title_val,
                              reason_key="contact_from_targeted_icloud_sync", reason_params={"match_reason": match_reason}, user_id=user_id)
                    existing.rolle = title_val
                if name_in_app_text:
                    db.execute(text(
                        "INSERT OR IGNORE INTO contact_application (contact_id, application_id) VALUES (:c, :a)"
                    ), {"c": existing.id, "a": app.id})
            else:
                contact = models.Contact(
                    name=name, email=email_val, telefon=tel_val,
                    firma=org_val, rolle=title_val, linkedin_url=linkedin_url,
                    user_id=user_id,
                )
                db.add(contact)
                db.flush()
                add_audit(db, "create", "sync", contact_id=contact.id, app_id=app.id,
                          new_value=contact.name,
                          reason_key="contact_created_targeted_icloud_sync", reason_params={"match_reason": match_reason},
                          user_id=user_id)
                if name_in_app_text:
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

async def _sync_icloud_reminders_for_app(app: models.Application, app_dict: dict, terms: list[str], db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
    from app.routers.sync_icloud import _get_cfg as _get_icloud_cfg, _caldav_calendars
    pfx = f"[SYNC #{app.id} icloud_todo]"
    cfg = _get_icloud_cfg(db)
    if not cfg:
        return 0, 0, []

    try:
        import caldav  # noqa: F401 -- import-only check for the friendlier "not installed" message below
    except ImportError:
        return 0, 0, ["caldav nicht installiert"]

    created = skipped = 0
    errors: list[str] = []

    try:
        calendars = await asyncio.to_thread(_caldav_calendars, cfg)
    except Exception as e:
        return 0, 0, [f"iCloud Reminders CalDAV: {e}"]

    def _collect_and_match_todos(calendars) -> tuple[list, list]:
        """Synchronous per-calendar todos() + text-match, run via
        asyncio.to_thread() below — see _caldav_calendars()' docstring in
        sync_icloud.py for why. A local closure since it captures
        _text_matches/terms."""
        all_t: list = []
        matched: list = []
        for cal in calendars:
            try:
                for todo in cal.todos():
                    try:
                        vtodo = todo.vobject_instance.vtodo
                        summary = vobj_str(vtodo, "summary")
                        desc = vobj_str(vtodo, "description")
                        all_t.append(todo)
                        if _text_matches(summary + " " + desc, terms):
                            matched.append(todo)
                    except Exception:
                        continue
            except Exception:
                pass
        return all_t, matched

    all_todos, matched_todos = await asyncio.to_thread(_collect_and_match_todos, calendars)

    log.debug("{} text-Match-Begriffe: {}", pfx, terms)
    log.debug("{} {} Todos gesamt, {} text-Match", pfx, len(all_todos), len(matched_todos))

    for todo in matched_todos:
        try:
            vtodo = todo.vobject_instance.vtodo
            summary = vobj_str(vtodo, "summary")
            desc = vobj_str(vtodo, "description")
            uid = vobj_str(vtodo, "uid") or str(todo.url)
        except Exception:
            continue

        if is_synced(db, "icloud_todo", uid):
            log.debug("{} {} SUMMARY:{!r} → SKIP bereits synced", pfx, uid[:16], summary)
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

        log.debug("{} {} SUMMARY:{!r} → pending", pfx, uid[:16], summary)
        raw = f"Erinnerung: {summary}\n{desc[:800]}"
        try:
            ok = await process_item_for_app(db, "icloud_todo", uid, raw, date_hint, app_dict, user_id=user_id)
        except Exception as e:
            errors.append(f"reminder/{summary}: {e}")
            continue
        if ok:
            created += 1
        else:
            skipped += 1

    log.debug("{} fertig: {} erstellt, {} übersprungen, {} fehler", pfx, created, skipped, len(errors))
    return created, len(matched_todos), errors


# ── Calls ─────────────────────────────────────────────────────────────────────

async def _sync_calls_for_app(app: models.Application, app_dict: dict, db: Session, user_id: Optional[int] = None) -> tuple[int, int, list[str]]:
    from app.agent_client import agent_get

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
        resp = await agent_get(db, "/calls", timeout=15)
        if resp.status_code != 200:
            return 0, 0, [f"Agent (Anrufe): {resp.text[:200]}"]
        calls = resp.json()
    except Exception as e:
        return 0, 0, [f"Rapport Agent nicht erreichbar: {e}"]

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

        call_event = models.Event(
            application_id=app.id,
            typ="notiz",
            datum=date_hint.date() if date_hint else None,
            titel=titel,
            notiz=notiz or None,
            source="icloud_calls",
            user_id=user_id,
        )
        db.add(call_event)
        db.flush()
        add_audit(db, "create", "icloud_calls", app_id=app.id, event_id=call_event.id,
                  new_value=titel, user_id=user_id)
        mark_synced(db, "icloud_calls", call_key, user_id)
        created += 1

    return created, len(calls), errors


# ── Task result store ────────────────────────────────────────────────────────

_task_results: dict[str, dict] = {}  # str(app_id) -> result dict


# ── Reset endpoint ────────────────────────────────────────────────────────────

@router.post("/{app_id}/reset", status_code=200)
def reset_targeted_sync(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = db.query(models.Application).filter_by(id=app_id, user_id=current_user.id).first()
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden.")

    # Bulk .delete() umgeht den zentralen Mandanten-Filter — daher explizit gefiltert.
    deleted_events = db.query(models.Event).filter(
        models.Event.application_id == app_id,
        models.Event.source.isnot(None),
        models.Event.user_id == current_user.id,
    ).delete()

    # Clear ALL source synced_items (für dieses Konto) so everything gets re-evaluated from scratch
    deleted_items = db.query(models.SyncedItem).filter(
        models.SyncedItem.source.in_(
            ["gmail", "gcal", "icloud_mail", "icloud_cal", "icloud_notes", "icloud_todo", "icloud_calls"]
        ),
        models.SyncedItem.user_id == current_user.id,
    ).delete()

    if deleted_events:
        add_audit(db, "delete", "user", app_id=app_id,
                  old_value=f"{deleted_events} synchronisierte Termine",
                  reason_key="targeted_sync_reset_manually", user_id=current_user.id)
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
        user_id = app.user_id
        if user_id is not None:
            set_session_user(db, user_id)
        lang = resolve_ui_language(db, user_id)

        terms = _search_terms(app, db)
        app_dict = _app_dict(app)
        # Snapshot the domain list ONCE, before any source runs — Gmail/GCal/
        # iCloud Mail/iCloud Calendar all run concurrently below in the same
        # asyncio.gather() call, sharing one DB session. Without this, a
        # false-positive contact one source creates becomes visible via the
        # live app.contacts relationship (flushed, not yet committed) to
        # another source computing its own domain list moments later — see
        # _company_domains_for_app()'s docstring for the #230 incident this
        # fixes (a mail false-positive cascaded into wrongly-matched
        # calendar events and call-log entries through exactly this path).
        # Stashed on app_dict since every source already receives it uniformly.
        app_dict["_domain_snapshot"] = _company_domains_for_app(app, terms, db)
        total_created = 0
        total_processed = 0
        all_errors: list[str] = []

        label = f"{app.firma or '?'} | {app.rolle or '?'}"
        log.info("━━━ SYNC START #{} — {} ━━━", app_id, label)
        log.debug("[SYNC #{}] Suchbegriffe: {}", app_id, terms)

        # 1. Mail, Cal, Notes, Reminders — parallel; create events first so contact
        #    sync can find names in event titles/notes when linking contacts.
        sources = [
            ("Gmail",               "targeted_gmail",             _sync_gmail_for_app),
            ("Google Calendar",     "targeted_gcal",              _sync_gcal_for_app),
            ("iCloud Mail",         "targeted_icloud_mail",       _sync_icloud_mail_for_app),
            (t("label_icloud_calendar", lang),  "targeted_icloud_cal",        _sync_icloud_cal_for_app),
            (t("label_icloud_notes", lang),     "targeted_icloud_notes",      _sync_icloud_notes_for_app),
            (t("label_icloud_reminders", lang), "targeted_icloud_reminders",  _sync_icloud_reminders_for_app),
        ]
        for _, pk, _ in sources:
            init_progress(pk, pk.replace("targeted_", "").replace("_", " ").title(), lang=lang)

        async def _run_source(label: str, prog_key: str, fn) -> tuple[int, int, list[str]]:
            try:
                c, p, errs = await fn(app, app_dict, terms, db, user_id)
                finish_progress(prog_key, lang=lang)
                return c, p, errs
            except Exception as e:
                finish_progress(prog_key, lang=lang)
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
        db.commit()

        # 2. Contacts — after events exist, _contact_mentioned_in_app finds names in them
        init_progress("targeted_contacts", t("label_icloud_contacts", lang), lang=lang)
        try:
            # Refresh app so SQLAlchemy sees the newly committed events
            db.refresh(app)
            c, p, errs = await _sync_contacts_for_app(app, terms, db, user_id)
            total_created += c
            total_processed += p
            all_errors.extend(errs)
        except Exception as e:
            all_errors.append(t("contacts_error", lang, error=e))
        finish_progress("targeted_contacts", lang=lang)
        db.commit()

        # 3. Calls (no AI)
        init_progress("targeted_calls", t("label_call_list", lang), lang=lang)
        try:
            c, p, errs = await _sync_calls_for_app(app, app_dict, db, user_id)
            total_created += c
            total_processed += p
            all_errors.extend(errs)
        except Exception as e:
            all_errors.append(t("call_list_error", lang, error=e))
        finish_progress("targeted_calls", lang=lang)

        db.commit()
        log.info("━━━ SYNC ENDE  #{} — {} | {} erstellt, {} geprüft, {} Fehler ━━━",
                 app_id, label, total_created, total_processed, len(all_errors))

        # AI assessment after sync
        try:
            from app.ai.tasks import assess_application
            from app.ai.provider import AINotConfigured, AIRateLimited
            from sqlalchemy.orm import joinedload as _jl
            from datetime import datetime as _dt
            app_with_events = (
                db.query(models.Application)
                .options(_jl(models.Application.events))
                .filter(models.Application.id == app_id)
                .first()
            )
            if app_with_events:
                result = await assess_application(db, app_with_events, lang)
                app_with_events.ai_color = result["color"]
                app_with_events.ai_next_step = result["next_step"]
                app_with_events.ai_reasoning = result.get("reasoning", "")
                app_with_events.ai_assessed_at = _dt.utcnow()
                db.commit()
        except (AINotConfigured, AIRateLimited):
            pass
        except Exception as e:
            log.warning("AI-Bewertung fehlgeschlagen für #{}: {}", app_id, e)

        return {"created": total_created, "processed": total_processed, "errors": all_errors}
    finally:
        db.close()


async def _do_post_create_sync(app_id: int, skip_linkedin: bool = False) -> None:
    """Runs automatically right after a new Application is created — from
    manual creation, the LinkedIn single-link import (extract_from_linkedin_url
    → NewApplicationModal save), or the periodic bulk LinkedIn scrape. See
    applications.py's create_application() and sync_linkedin.py's _async_sync()
    for call sites.

    skip_linkedin=True when the application itself was just sourced from
    LinkedIn (single-link import or bulk scrape) — re-running the per-app
    LinkedIn category search immediately afterward would just re-find the
    listing we already have. Best-effort throughout: a failure here must
    never surface to whatever created the application."""
    try:
        await _do_sync(app_id)
    except Exception as e:
        log.warning("Post-create targeted sync fehlgeschlagen für App #{}: {}", app_id, e)
    if skip_linkedin:
        return
    try:
        from app.routers.sync_linkedin import run_individual_sync_if_idle
        await run_individual_sync_if_idle(app_id)
    except Exception as e:
        log.warning("Post-create LinkedIn-Sync fehlgeschlagen für App #{}: {}", app_id, e)


@router.post("/{app_id}", response_model=schemas.SyncResult)
async def sync_for_app(
    app_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = db.query(models.Application).filter_by(id=app_id, user_id=current_user.id).first()
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    if not _search_terms(app, db):
        raise HTTPException(400, "Keine Suchbegriffe für diese Bewerbung ableitbar.")

    _task_results.pop(str(app_id), None)
    init_progress(f"targeted_{app_id}", t("sync_label", current_user.ui_language, firma=app.firma), lang=current_user.ui_language)

    async def _bg():
        try:
            result = await _do_sync(app_id)
        except Exception as e:
            result = {"created": 0, "processed": 0, "errors": [str(e)]}
        result["done"] = True
        _task_results[str(app_id)] = result
        finish_progress(f"targeted_{app_id}", lang=current_user.ui_language)

    background_tasks.add_task(_bg)
    return schemas.SyncResult(processed=0, created=0, skipped=0, errors=[])


@router.get("/{app_id}/result")
def get_result(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # _task_results ist ein prozessweiter In-Memory-Store ohne eigene
    # Mandanten-Trennung — Ownership hier explizit über die Application prüfen,
    # bevor Sync-Ergebnisse (können Fehlermeldungen mit Inhalten enthalten)
    # herausgegeben werden.
    app = db.query(models.Application).filter_by(id=app_id, user_id=current_user.id).first()
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    return _task_results.get(str(app_id)) or {"done": False}


_SYNC_SOURCES = {"gmail", "gcal", "icloud_mail", "icloud_cal", "icloud_notes", "calls"}


@router.get("/{app_id}/candidates")
def list_candidates(
    app_id: int,
    q: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return items that could be manually assigned to this application.

    Two pools:
    1. PendingMatch rows (not yet assigned anywhere)
    2. Events already assigned to OTHER applications but from a sync source
       (can be re-assigned here)
    Both pools are filtered by the query string (or app search terms if no query).
    """
    app = db.query(models.Application).filter_by(id=app_id, user_id=current_user.id).first()
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
def manual_assign(
    app_id: int,
    body: ManualAssignPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Manually assign a PendingMatch or existing Event to an application.

    Positive match_id → PendingMatch row.
    Negative match_id → abs(match_id) is an Event.id from another application
    (returned by list_candidates when the item is already in Pool 2).
    """
    app = db.query(models.Application).filter_by(id=app_id, user_id=current_user.id).first()
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
            user_id=current_user.id,
        )
        db.add(ev)
        db.flush()
        add_audit(db, "create", "user", app_id=app_id, event_id=ev.id,
                  new_value=ev.titel, reason_key="assigned_manually", user_id=current_user.id)
        mark_synced(db, src, ext_id, current_user.id)
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
        old_app_id = src_event.application_id
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
        add_audit(db, "update", "user", app_id=app_id, event_id=src_event.id,
                  field="application_id", old_value=old_app_id, new_value=app_id,
                  reason_key="reassigned_manually", user_id=current_user.id)
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
        add_audit(db, "delete", "user", app_id=app_id, event_id=conflict_event.id,
                  old_value=conflict_event.titel, reason_key="conflict_removed_manual_assign",
                  user_id=current_user.id)
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
        user_id=current_user.id,
    )
    db.add(ev)
    db.flush()
    add_audit(db, "create", "user", app_id=app_id, event_id=ev.id,
              new_value=ev.titel, reason_key="pending_match_assigned_manually", user_id=current_user.id)
    pm.review_status = "approved"
    db.commit()
    db.refresh(ev)
    return {"conflict": False, "event_id": ev.id}
