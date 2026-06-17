"""
Duplicate detection and cleanup for Applications, Contacts, and Events.

Strategy:
  Applications  – group by (firma.lower(), rolle.lower()); keep highest-scored entry;
                  merge events + contacts onto the keeper, then delete the rest.
  Contacts      – group by name.lower(); send to PendingMatch for manual review.
  Events        – group by (application_id, typ, datum, titel.lower()) → auto-delete.
                  Cross-application duplicates (same external_id) → PendingMatch.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.routers.sync_common import (
    init_progress, update_progress, finish_progress, get_all_progress,
)

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])

PROGRESS_KEY = "cleanup"


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


def _event_score(e: models.Event) -> int:
    return (1 if e.notiz else 0) * 2 + (1 if e.autor else 0)


# ── duplicate finders ─────────────────────────────────────────────────────────

def _find_app_groups(db: Session) -> list[dict]:
    apps = db.query(models.Application).all()
    buckets: dict[tuple, list[models.Application]] = {}
    for a in apps:
        key = (a.firma.strip().lower(), (a.rolle or "").strip().lower())
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
    """Group contacts by name-only (simple, cross-firm, cross-application)."""
    contacts = db.query(models.Contact).all()
    buckets: dict[str, list[models.Contact]] = {}
    for c in contacts:
        key = c.name.strip().lower()
        buckets.setdefault(key, []).append(c)

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


def _find_event_groups(db: Session) -> list[dict]:
    """Find within-application event duplicates (same typ+datum+titel)."""
    events = db.query(models.Event).all()
    buckets: dict[tuple, list[models.Event]] = {}
    for e in events:
        key = (
            e.application_id,
            (e.typ or "").strip().lower(),
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


def _find_cross_app_event_groups(db: Session) -> list[dict]:
    """Find cross-application event duplicates by external_id."""
    events = (
        db.query(models.Event)
        .filter(models.Event.external_id.isnot(None))
        .all()
    )
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
def cleanup_preview(db: Session = Depends(get_db)):
    """Dry-run: return what would be merged/deleted, without changing anything."""
    return {
        "applications":    _find_app_groups(db),
        "contacts":        _find_contact_groups(db),
        "events":          _find_event_groups(db),
        "cross_app_events": _find_cross_app_event_groups(db),
    }


@router.get("/progress")
def cleanup_progress_endpoint():
    return get_all_progress()


@router.post("/run")
async def cleanup_run(db: Session = Depends(get_db)):
    """Execute deduplication. Returns counts of deleted rows per category."""
    init_progress(PROGRESS_KEY, "Bereinigung", "Analysiere Duplikate…")

    # ── 1. Applications ───────────────────────────────────────────────────────
    update_progress(PROGRESS_KEY, 0, 3, "Bewerbungen werden bereinigt…")
    app_groups = _find_app_groups(db)
    deleted_apps = 0

    for g in app_groups:
        keeper_id = g["keep"]["id"]
        for rem in g["remove"]:
            dup = db.query(models.Application).get(rem["id"])
            if not dup:
                continue
            # Reassign events
            for ev in list(dup.events):
                ev.application_id = keeper_id
            # Reassign contact links (avoid duplicating existing links)
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

    await asyncio.sleep(0)  # yield to event loop

    # ── 2. Contacts → PendingMatch (manual review) ────────────────────────────
    update_progress(PROGRESS_KEY, 1, 4, "Kontakte werden analysiert…")
    contact_groups = _find_contact_groups(db)
    queued_contacts = 0

    from datetime import date as _date
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

    # ── 3. Events (same app) → auto-delete ────────────────────────────────────
    update_progress(PROGRESS_KEY, 2, 4, "Timeline-Einträge werden bereinigt…")
    event_groups = _find_event_groups(db)
    deleted_events = 0

    for g in event_groups:
        for rem in g["remove"]:
            ev = db.query(models.Event).get(rem["id"])
            if ev:
                db.delete(ev)
                deleted_events += 1
    db.commit()

    await asyncio.sleep(0)

    # ── 4. Cross-app Events → PendingMatch ───────────────────────────────────
    update_progress(PROGRESS_KEY, 3, 4, "Bewerbungsübergreifende Duplikate werden analysiert…")
    cross_groups = _find_cross_app_event_groups(db)
    queued_events = 0

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
        "deleted_applications":   deleted_apps,
        "queued_contacts":        queued_contacts,
        "deleted_events":         deleted_events,
        "queued_cross_app_events": queued_events,
        "merged_app_groups":      len(app_groups),
        "contact_groups_queued":  len(contact_groups),
        "merged_event_groups":    len(event_groups),
        "cross_app_event_groups": len(cross_groups),
    }
