"""
Duplicate detection and cleanup for Applications, Contacts, Companies, and Events.

Strategy:
  Applications  – group by dedup_key(firma, rolle) (normalized: strips legal-form
                  suffixes/noise); keep highest-scored entry; merge events +
                  contacts onto the keeper, then delete the rest.
  Contacts      – group by normalized name AND matching company (company_profile_id
                  if both set, else normalized firma text) to avoid merging different
                  people who happen to share a name at different companies;
                  send to PendingMatch for manual review.
  Companies     – name_norm is unique at the DB level, so name-based dupes can't
                  occur; group instead by website domain (same site = same company
                  regardless of name spelling). Reuses merge.py's merge_companies
                  for the actual reassignment + delete.
  Events        – group by (application_id, typ, datum, titel.lower()) → auto-delete.
                  Cross-application duplicates (same external_id) → PendingMatch.

Every finder/executor accepts an optional `scope` so a caller (e.g. the
"Bereinigen" button in a specific view) can restrict work to just one category
instead of scanning + touching everything.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.dedup import dedup_key, norm_firma
from app.routers.sync_common import (
    init_progress, update_progress, finish_progress, get_all_progress,
)
from app.routers.merge import merge_companies, SimpleMergeRequest

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])

PROGRESS_KEY = "cleanup"

Scope = str  # "applications" | "contacts" | "companies" | "events" | None (= all)


# Generic/placeholder domains that don't identify a distinct company —
# matching on these would create false-positive merges.
_GENERIC_DOMAINS = {
    "example.com", "linkedin.com", "google.com", "xing.com",
    "indeed.com", "stepstone.de", "glassdoor.com", "wikipedia.org",
}


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url if "//" in url else f"//{url}").hostname or ""
        host = host.removeprefix("www.")
        return host if host and host not in _GENERIC_DOMAINS else None
    except Exception:
        return None


# ── scoring helpers ───────────────────────────────────────────────────────────

def _app_score(a: models.Application) -> int:
    filled = sum(1 for v in [
        a.zielfirma_bei_hh, a.quelle, a.wurde_besetzt_von, a.kommentar,
        a.datum_bewerbung, a.gespraech_1, a.gespraech_2,
    ] if v)
    return len(a.events) * 3 + len(a.contacts) * 2 + filled


def _contact_score(c: models.Contact) -> int:
    filled = sum(1 for v in [c.email, c.telefon, c.linkedin_url, c.notizen, c.rolle] if v)
    return len(c.applications) * 3 + filled


_GENERIC_EVENT_TYPES = {"status", "notiz"}


def _event_score(e: models.Event) -> int:
    # Bei Cross-typ-Dubletten (siehe _find_event_groups) einen aussagekräftigen
    # typ wie "gespräch"/"termin"/"anruf" gegenüber generischen Klassifikations-
    # Artefakten wie "status"/"notiz" bevorzugen.
    specific_typ = 0 if (e.typ or "").strip().lower() in _GENERIC_EVENT_TYPES else 1
    return specific_typ * 4 + (1 if e.notiz else 0) * 2 + (1 if e.autor else 0)


def _company_score(c: models.CompanyProfile) -> int:
    filled = sum(1 for v in [
        c.description, c.logo_data, c.industry, c.employee_range,
        c.employee_count, c.founded_year, c.hq_city, c.hq_country,
        c.linkedin_company_url,
    ] if v)
    return (len(c.applications) + len(c.hh_applications)) * 3 + len(c.direct_contacts) * 2 + filled


# ── duplicate finders ─────────────────────────────────────────────────────────

def _find_app_groups(db: Session) -> list[dict]:
    apps = db.query(models.Application).all()
    buckets: dict[str, list[models.Application]] = {}
    for a in apps:
        key = dedup_key(a.firma, a.rolle or "")
        buckets.setdefault(key, []).append(a)

    groups = []
    for dups in buckets.values():
        if len(dups) < 2:
            continue
        dups.sort(key=_app_score, reverse=True)
        keeper = dups[0]
        to_remove = dups[1:]
        events_merged = sum(len(r.events) for r in to_remove)
        contacts_merged = sum(len(r.contacts) for r in to_remove)
        groups.append({
            "keep":            _app_dict(keeper),
            "remove":          [_app_dict(r, events_count=len(r.events), contacts_count=len(r.contacts)) for r in to_remove],
            "events_merged":   events_merged,
            "contacts_merged": contacts_merged,
        })
    return groups


def _find_contact_groups(db: Session) -> list[dict]:
    """Group contacts by normalized name + matching company context, to avoid
    conflating different people who share a name at unrelated companies."""
    contacts = db.query(models.Contact).all()
    buckets: dict[tuple, list[models.Contact]] = {}
    for c in contacts:
        name_key = c.name.strip().lower()
        company_key = c.company_profile_id if c.company_profile_id else norm_firma(c.firma or "")
        buckets.setdefault((name_key, company_key), []).append(c)

    groups = []
    for dups in buckets.values():
        if len(dups) < 2:
            continue
        dups.sort(key=_contact_score, reverse=True)
        keeper = dups[0]
        to_remove = dups[1:]
        apps_merged = sum(len(r.applications) for r in to_remove)
        groups.append({
            "keep":        _contact_dict(keeper),
            "remove":      [_contact_dict(r, apps_count=len(r.applications)) for r in to_remove],
            "apps_merged": apps_merged,
        })
    return groups


def _find_company_groups(db: Session) -> list[dict]:
    """name_norm is unique at the DB level, so name-collisions can't happen —
    group by website domain instead (same site = same company regardless of
    how the name was spelled when the profile was created)."""
    profiles = db.query(models.CompanyProfile).filter(models.CompanyProfile.website.isnot(None)).all()
    buckets: dict[str, list[models.CompanyProfile]] = {}
    for p in profiles:
        d = _domain(p.website)
        if not d:
            continue
        buckets.setdefault(d, []).append(p)

    groups = []
    for dups in buckets.values():
        if len(dups) < 2:
            continue
        dups.sort(key=_company_score, reverse=True)
        keeper = dups[0]
        to_remove = dups[1:]
        apps_merged = sum(len(r.applications) + len(r.hh_applications) for r in to_remove)
        contacts_merged = sum(len(r.direct_contacts) for r in to_remove)
        groups.append({
            "keep":            _company_dict(keeper),
            "remove":          [_company_dict(r, apps_count=len(r.applications) + len(r.hh_applications), contacts_count=len(r.direct_contacts)) for r in to_remove],
            "apps_merged":     apps_merged,
            "contacts_merged": contacts_merged,
        })
    return groups


def _calendar_filter(q):
    """Nur echte Kalendereinträge — exakt dieselbe Definition wie routers/calendar.py,
    damit die Kalenderansicht und ihr Bereinigen-Button dieselben Events meinen."""
    return q.filter(
        models.Event.source.in_(models.CALENDAR_SOURCES)
        | models.Event.typ.in_(models.CALENDAR_TYPEN)
    )


def _find_event_groups(db: Session, calendar_only: bool = False) -> list[dict]:
    """Find within-application event duplicates (same source+datum+titel).

    Synced events (source gesetzt) werden bewusst OHNE typ in den Gruppierungs-
    Key aufgenommen: dieselbe Kalender-/Mail-/Anruf-Quelle liefert bei mehreren
    Sync-/Klassifikations-Durchläufen für exakt dasselbe reale Ereignis oft
    unterschiedliche typ-Werte (z.B. "status", "notiz", "gespräch" für denselben
    gcal-Termin — teils sogar mit identischem external_id belegt). Ein Match nur
    auf typ+datum+titel übersah diese Duplikate komplett, weil sie nie exakt
    denselben typ hatten. Für manuell angelegte Einträge (source=None) bleibt
    typ Teil des Keys — dort ist es ein bewusst vom User gesetztes Merkmal und
    keine Klassifikations-Variante desselben Sync-Items.

    calendar_only=True beschränkt auf echte Kalendereinträge (siehe
    _calendar_filter) — genutzt vom "Bereinigen"-Button in der Kalenderansicht,
    damit dort nicht auch Mail-/Anruf-Duplikate auftauchen.
    """
    q = db.query(models.Event)
    if calendar_only:
        q = _calendar_filter(q)
    events = q.all()
    buckets: dict[tuple, list[models.Event]] = {}
    for e in events:
        key = (
            e.application_id,
            (e.typ or "").strip().lower() if not e.source else "",
            (e.source or "").strip().lower(),
            str(e.datum) if e.datum else "",
            (e.titel or "").strip().lower(),
        )
        buckets.setdefault(key, []).append(e)

    groups = []
    for dups in buckets.values():
        if len(dups) < 2:
            continue
        dups.sort(key=_event_score, reverse=True)
        keeper = dups[0]
        to_remove = dups[1:]
        groups.append({
            "keep":   _event_dict(keeper),
            "remove": [_event_dict(r) for r in to_remove],
        })
    return groups


def _find_cross_app_event_groups(db: Session, calendar_only: bool = False) -> list[dict]:
    """Find cross-application event duplicates by external_id."""
    q = db.query(models.Event).filter(models.Event.external_id.isnot(None))
    if calendar_only:
        q = _calendar_filter(q)
    events = q.all()
    buckets: dict[str, list[models.Event]] = {}
    for e in events:
        key = e.external_id.strip()
        buckets.setdefault(key, []).append(e)

    groups = []
    for dups in buckets.values():
        # Only flag if events are from different applications
        app_ids = {e.application_id for e in dups}
        if len(app_ids) < 2:
            continue
        dups.sort(key=_event_score, reverse=True)
        keeper = dups[0]
        to_remove = dups[1:]
        groups.append({
            "keep":   _event_dict(keeper),
            "remove": [_event_dict(r) for r in to_remove],
        })
    return groups


# ── dict serialisers ──────────────────────────────────────────────────────────

def _app_dict(a: models.Application, **extra) -> dict:
    d = {
        "id":          a.id,
        "firma":       a.firma,
        "rolle":       a.rolle,
        "main_status": a.main_status,
        "abgesagt":    a.abgesagt,
        "events":      len(a.events),
        "contacts":    len(a.contacts),
    }
    d.update(extra)
    return d


def _contact_dict(c: models.Contact, **extra) -> dict:
    d = {
        "id":    c.id,
        "name":  c.name,
        "email": c.email,
        "firma": c.firma,
        "apps":  len(c.applications),
    }
    d.update(extra)
    return d


def _company_dict(c: models.CompanyProfile, **extra) -> dict:
    d = {
        "id":      c.id,
        "name":    c.name_display or c.name_norm,
        "website": c.website,
        "apps":    len(c.applications) + len(c.hh_applications),
        "contacts": len(c.direct_contacts),
    }
    d.update(extra)
    return d


def _event_dict(e: models.Event) -> dict:
    return {
        "id":             e.id,
        "application_id": e.application_id,
        "typ":            e.typ,
        "datum":          str(e.datum) if e.datum else None,
        "titel":          e.titel,
        "has_notiz":      bool(e.notiz),
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/preview")
def cleanup_preview(db: Session = Depends(get_db), scope: Scope | None = Query(default=None)):
    """Dry-run: return what would be merged/deleted, without changing anything.

    scope: "applications" | "contacts" | "companies" | "events" | None (= all)
    """
    result: dict = {"applications": [], "contacts": [], "companies": [], "events": [], "cross_app_events": []}
    if scope in (None, "applications"):
        result["applications"] = _find_app_groups(db)
    if scope in (None, "contacts"):
        result["contacts"] = _find_contact_groups(db)
    if scope in (None, "companies"):
        result["companies"] = _find_company_groups(db)
    if scope in (None, "events"):
        # scope="events" wird ausschließlich vom "Bereinigen"-Button der Kalender-
        # ansicht ausgelöst → auf echte Kalendereinträge beschränken. Ungescopte
        # Läufe (scope=None, "alles bereinigen") bleiben bewusst umfassend.
        calendar_only = scope == "events"
        result["events"] = _find_event_groups(db, calendar_only=calendar_only)
        result["cross_app_events"] = _find_cross_app_event_groups(db, calendar_only=calendar_only)
    return result


@router.get("/progress")
def cleanup_progress_endpoint():
    return get_all_progress()


@router.post("/run")
async def cleanup_run(db: Session = Depends(get_db), scope: Scope | None = Query(default=None)):
    """Execute deduplication. Returns counts of deleted rows per category.

    scope: "applications" | "contacts" | "companies" | "events" | None (= all)
    """
    init_progress(PROGRESS_KEY, "Bereinigung", "Analysiere Duplikate…")
    steps = [s for s in ["applications", "contacts", "companies", "events"] if scope in (None, s)]
    total_steps = max(len(steps), 1)
    step_i = 0

    deleted_apps = 0
    queued_contacts = 0
    deleted_companies = 0
    deleted_events = 0
    queued_events = 0
    app_groups: list[dict] = []
    contact_groups: list[dict] = []
    company_groups: list[dict] = []
    event_groups: list[dict] = []
    cross_groups: list[dict] = []

    from datetime import date as _date

    # ── 1. Applications ───────────────────────────────────────────────────────
    if scope in (None, "applications"):
        update_progress(PROGRESS_KEY, step_i, total_steps, "Bewerbungen werden bereinigt…")
        step_i += 1
        app_groups = _find_app_groups(db)
        for g in app_groups:
            keeper_id = g["keep"]["id"]
            for rem in g["remove"]:
                dup = db.query(models.Application).get(rem["id"])
                if not dup:
                    continue
                for ev in list(dup.events):
                    ev.application_id = keeper_id
                keeper = db.query(models.Application).get(keeper_id)
                keeper_contact_ids = {c.id for c in keeper.contacts}
                for contact in list(dup.contacts):
                    if contact.id not in keeper_contact_ids:
                        keeper.contacts.append(contact)
                dup.contacts.clear()
                db.flush()
                db.delete(dup)
                deleted_apps += 1
        db.commit()
        await asyncio.sleep(0)

    # ── 2. Contacts → PendingMatch (manual review) ────────────────────────────
    if scope in (None, "contacts"):
        update_progress(PROGRESS_KEY, step_i, total_steps, "Kontakte werden analysiert…")
        step_i += 1
        contact_groups = _find_contact_groups(db)
        for g in contact_groups:
            keeper = g["keep"]
            for rem in g["remove"]:
                pm_ext_id = f"cleanup_contact_{keeper['id']}_{rem['id']}"
                exists = db.query(models.PendingMatch).filter_by(
                    source="cleanup", external_id=pm_ext_id
                ).first()
                if exists:
                    continue
                db.add(models.PendingMatch(
                    source="cleanup",
                    external_id=pm_ext_id,
                    confidence=90,
                    event_type="duplicate_contact",
                    datum=_date.today(),
                    titel=f"Doppelter Kontakt: {keeper['name']}",
                    extract=f"Behalten: ID {keeper['id']} ({keeper.get('firma') or '–'})\nDuplikat: ID {rem['id']} ({rem.get('firma') or '–'})",
                    raw_content=json.dumps({"keeper_contact_id": keeper["id"], "dup_contact_id": rem["id"]}),
                    suggested_app_id=None,
                ))
                queued_contacts += 1
        db.commit()
        await asyncio.sleep(0)

    # ── 3. Companies → merge directly (reuses merge.py logic) ─────────────────
    if scope in (None, "companies"):
        update_progress(PROGRESS_KEY, step_i, total_steps, "Firmen werden zusammengeführt…")
        step_i += 1
        company_groups = _find_company_groups(db)
        for g in company_groups:
            winner_id = g["keep"]["id"]
            loser_ids = [r["id"] for r in g["remove"]]
            still_exist = {
                c.id for c in db.query(models.CompanyProfile.id)
                .filter(models.CompanyProfile.id.in_([winner_id] + loser_ids)).all()
            }
            loser_ids = [i for i in loser_ids if i in still_exist]
            if winner_id not in still_exist or not loser_ids:
                continue
            merge_companies(SimpleMergeRequest(winner_id=winner_id, loser_ids=loser_ids), db)
            deleted_companies += len(loser_ids)
        await asyncio.sleep(0)

    # ── 4. Events (same app) → auto-delete ────────────────────────────────────
    if scope in (None, "events"):
        # Analog zu /preview: scope="events" kommt ausschließlich vom Kalender-
        # Bereinigen-Button → auf echte Kalendereinträge beschränken.
        calendar_only = scope == "events"
        update_progress(PROGRESS_KEY, step_i, total_steps, "Timeline-Einträge werden bereinigt…")
        step_i += 1
        event_groups = _find_event_groups(db, calendar_only=calendar_only)
        for g in event_groups:
            for rem in g["remove"]:
                ev = db.query(models.Event).get(rem["id"])
                if ev:
                    db.delete(ev)
                    deleted_events += 1
        db.commit()
        await asyncio.sleep(0)

        # Cross-app events → PendingMatch
        cross_groups = _find_cross_app_event_groups(db, calendar_only=calendar_only)
        for g in cross_groups:
            keeper_ev = g["keep"]
            for rem in g["remove"]:
                pm_ext_id = f"cleanup_event_{keeper_ev['id']}_{rem['id']}"
                exists = db.query(models.PendingMatch).filter_by(
                    source="cleanup", external_id=pm_ext_id
                ).first()
                if exists:
                    continue
                db.add(models.PendingMatch(
                    source="cleanup",
                    external_id=pm_ext_id,
                    confidence=95,
                    event_type="duplicate_event",
                    datum=_date.today(),
                    titel=f"Doppelter Eintrag: {keeper_ev.get('titel') or keeper_ev.get('typ')}",
                    extract=f"Bewerbung {keeper_ev['application_id']} (behalten) vs. {rem['application_id']} (Duplikat)",
                    raw_content=json.dumps({"keeper_event_id": keeper_ev["id"], "dup_event_id": rem["id"]}),
                    suggested_app_id=keeper_ev["application_id"],
                ))
                queued_events += 1
        db.commit()

    finish_progress(PROGRESS_KEY)

    return {
        "deleted_applications":    deleted_apps,
        "queued_contacts":         queued_contacts,
        "deleted_companies":       deleted_companies,
        "deleted_events":          deleted_events,
        "queued_cross_app_events": queued_events,
        "merged_app_groups":       len(app_groups),
        "contact_groups_queued":   len(contact_groups),
        "merged_company_groups":   len(company_groups),
        "merged_event_groups":     len(event_groups),
        "cross_app_event_groups":  len(cross_groups),
    }
