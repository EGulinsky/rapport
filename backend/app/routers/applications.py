import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from typing import List, Optional
from datetime import date, datetime

from app.database import get_db
from app import models, schemas
from app.models import MAIN_STATUS_LABELS, SUB_STATUS_LABELS
from app.audit import add_audit
from app.dedup import norm_firma


def _status_label(main: str, sub: str | None) -> str:
    label = MAIN_STATUS_LABELS.get(main, main)
    if sub:
        label += f" – {SUB_STATUS_LABELS.get(sub, sub)}"
    return label


def _compute_naechster_schritt(
    app,
    next_interview: Optional[date],
    last_interview: Optional[date],
    today: date,
) -> str:
    status = app.main_status or ""

    if status == "rejected":
        return ""

    if next_interview:
        delta = (next_interview - today).days
        when = next_interview.strftime("%d.%m.%Y")
        if delta == 0:
            return f"Gespräch heute ({when})"
        if delta == 1:
            return f"Gespräch morgen ({when})"
        return f"Gespräch am {when} (in {delta} Tagen)"

    if status == "signed":
        return "Onboarding vorbereiten"

    if status == "negotiating":
        return "Vertragsdetails klären"

    if last_interview:
        days = (today - last_interview).days
        if days <= 7:
            return "Warte auf Feedback"
        if days <= 21:
            return f"Feedback ausstehend — evtl. nachfassen ({days} Tage)"
        return f"Kein Feedback seit {days} Tagen — evtl. Ghosting"

    if status in ("hr", "fb"):
        return "Terminvereinbarung ausstehend"

    if status == "waiting":
        return "Warte auf Rückmeldung"

    if status == "applied":
        days_since = (today - app.datum_bewerbung).days if app.datum_bewerbung else 0
        if days_since < 14:
            return "Warte auf Einladung"
        if days_since < 30:
            return f"Evtl. nachfassen ({days_since} Tage ohne Reaktion)"
        return f"Keine Reaktion seit {days_since} Tagen"

    if status == "prospecting":
        return "Bewerbung vorbereiten"

    return ""

def _ensure_company_profile(db: Session, app: models.Application) -> None:
    """Create or link CompanyProfile for the application's firma (and zielfirma if HH)."""
    if app.firma:
        key = norm_firma(app.firma)
        profile = db.query(models.CompanyProfile).filter(
            models.CompanyProfile.name_norm == key
        ).first()
        if not profile:
            profile = models.CompanyProfile(
                name_norm=key,
                name_display=app.firma,
                sync_status="pending",
            )
            db.add(profile)
            db.flush()
        app.company_profile_id = profile.id

    if app.is_headhunter and app.zielfirma_bei_hh:
        zkey = norm_firma(app.zielfirma_bei_hh)
        zprofile = db.query(models.CompanyProfile).filter(
            models.CompanyProfile.name_norm == zkey
        ).first()
        if not zprofile:
            zprofile = models.CompanyProfile(
                name_norm=zkey,
                name_display=app.zielfirma_bei_hh,
                sync_status="pending",
            )
            db.add(zprofile)
            db.flush()
        app.target_company_profile_id = zprofile.id


router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("/", response_model=List[schemas.ApplicationListItem])
def list_applications(
    main_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    show_rejected: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(models.Application)

    if main_status:
        q = q.filter(models.Application.main_status == main_status)

    if not show_rejected:
        q = q.filter(models.Application.main_status != "rejected")

    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                models.Application.firma.ilike(term),
                models.Application.rolle.ilike(term),
                models.Application.quelle.ilike(term),
            )
        )

    latest_event = (
        db.query(
            models.Event.application_id,
            func.max(models.Event.created_at).label("latest_activity"),
        )
        .group_by(models.Event.application_id)
        .subquery()
    )
    q = q.outerjoin(latest_event, models.Application.id == latest_event.c.application_id)
    apps = q.order_by(
        func.coalesce(latest_event.c.latest_activity, models.Application.datum_bewerbung).desc()
    ).all()

    if apps:
        today = date.today()
        app_ids = [a.id for a in apps]

        max_event_dates = dict(
            db.query(models.Event.application_id, func.max(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                models.Event.datum <= today,
            )
            .group_by(models.Event.application_id)
            .all()
        )

        # Calendar events (gcal/icloud_cal) represent scheduled appointments and
        # should be treated as interview dates — same logic as PDF Terminübersicht.
        _is_interview = or_(
            models.Event.typ == "gespräch",
            models.Event.source.in_(["gcal", "icloud_cal"]),
        )

        next_interviews = dict(
            db.query(models.Event.application_id, func.min(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                _is_interview,
                models.Event.datum > today,
            )
            .group_by(models.Event.application_id)
            .all()
        )

        last_interviews = dict(
            db.query(models.Event.application_id, func.max(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                _is_interview,
                models.Event.datum <= today,
            )
            .group_by(models.Event.application_id)
            .all()
        )

        earliest_bewerbung_events = dict(
            db.query(models.Event.application_id, func.min(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                models.Event.typ == "bewerbung",
            )
            .group_by(models.Event.application_id)
            .all()
        )

        fixed_any = False
        for app in apps:
            if app.datum_bewerbung is None:
                eb = earliest_bewerbung_events.get(app.id)
                if eb:
                    app.datum_bewerbung = eb
                    fixed_any = True
            # Compute ghosting from DB letztes_update BEFORE overwriting it in-memory.
            # A "Bewerbung eingereicht" event with datum=today (set by sync) would
            # otherwise push letztes_update to today and suppress ghosting.
            app._ghosting_override = app.ghosting
            md = max_event_dates.get(app.id)
            if md:
                app.letztes_update = md
            app.naechster_schritt = _compute_naechster_schritt(
                app,
                next_interviews.get(app.id),
                last_interviews.get(app.id),
                today,
            )
        if fixed_any:
            db.commit()

    # Attach company website + display name for logo display and name override
    cp_ids = {a.company_profile_id for a in apps if a.company_profile_id}
    tcp_ids = {a.target_company_profile_id for a in apps if a.target_company_profile_id}
    all_ids = cp_ids | tcp_ids
    if all_ids:
        profiles = (
            db.query(models.CompanyProfile.id, models.CompanyProfile.website, models.CompanyProfile.name_display)
            .filter(models.CompanyProfile.id.in_(all_ids))
            .all()
        )
        website_map = {p.id: p.website for p in profiles}
        name_map = {p.id: p.name_display for p in profiles}
        for a in apps:
            a.company_website = website_map.get(a.company_profile_id)
            a.target_company_website = website_map.get(a.target_company_profile_id)
            a.company_name_display = name_map.get(a.company_profile_id)
            a.target_company_name_display = name_map.get(a.target_company_profile_id)

    return apps


@router.get("/stats", response_model=schemas.StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    all_apps = db.query(models.Application).all()
    total = len(all_apps)
    rejected = sum(1 for a in all_apps if a.main_status == "rejected")
    active = total - rejected

    by_status: dict = {}
    for a in all_apps:
        key = a.main_status
        by_status[key] = by_status.get(key, 0) + 1

    return schemas.StatsResponse(
        total=total,
        active=active,
        rejected=rejected,
        by_status=by_status,
    )


@router.get("/ai-assess-all")
async def ai_assess_all(db: Session = Depends(get_db)):
    import asyncio
    from app.models import AiSettings
    from app.ai.tasks import assess_application
    from app.ai.provider import AINotConfigured, AIRateLimited, AIBadRequest

    cfg = db.query(AiSettings).first()
    # Throttle: Gemini free tier = 15 RPM, Groq = 30 RPM — use 5s gap to stay safe
    provider_id = (cfg.provider if cfg else "") or ""
    delay_s = 5.0 if provider_id in ("gemini", "groq") else 1.0

    async def _stream():
        apps = (
            db.query(models.Application)
            .options(joinedload(models.Application.events))
            .filter(models.Application.main_status != "rejected")
            .all()
        )
        total = len(apps)
        updated = 0
        errors: list[str] = []
        yield f"data: {json.dumps({'status': 'start', 'total': total})}\n\n"
        for i, app in enumerate(apps):
            if i > 0:
                await asyncio.sleep(delay_s)
            try:
                result = await assess_application(db, app)
                app.ai_color = result["color"]
                app.ai_next_step = result["next_step"]
                app.ai_reasoning = result.get("reasoning", "")
                app.ai_assessed_at = datetime.utcnow()
                db.commit()
                updated += 1
                yield f"data: {json.dumps({'status': 'progress', 'done': i + 1, 'total': total, 'firma': app.firma})}\n\n"
            except (AINotConfigured, AIRateLimited, AIBadRequest) as e:
                errors.append(str(e))
                yield f"data: {json.dumps({'status': 'progress', 'done': i + 1, 'total': total, 'firma': app.firma, 'error': str(e)})}\n\n"
                break
            except Exception as e:
                errors.append(f"#{app.id} {app.firma}: {e}")
                yield f"data: {json.dumps({'status': 'progress', 'done': i + 1, 'total': total, 'firma': app.firma, 'error': str(e)})}\n\n"
        db.commit()
        yield f"data: {json.dumps({'status': 'done', 'updated': updated, 'errors': errors})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/extract-from-linkedin-url")
async def extract_from_linkedin_url(payload: schemas.ExtractFromUrlRequest, db: Session = Depends(get_db)):
    if "linkedin.com" not in payload.url:
        raise HTTPException(400, "Bitte einen LinkedIn-Job-Link angeben.")

    from app.linkedin_job_description import load_job_description
    from app.ai.tasks import extract_application_from_text
    from app.ai.provider import AINotConfigured, AIRateLimited, AIBadRequest

    try:
        description = await load_job_description(payload.url, db)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        result = await extract_application_from_text(db, description)
    except AINotConfigured as e:
        raise HTTPException(400, str(e))
    except AIRateLimited:
        raise HTTPException(429, "Rate-Limit des KI-Anbieters erreicht — bitte in 30–60 Sekunden nochmal versuchen.")
    except AIBadRequest as e:
        raise HTTPException(400, str(e))

    result["stellenanzeige_url"] = payload.url
    return result


@router.get("/{app_id}", response_model=schemas.ApplicationRead)
def get_application(app_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    for cp_id, attr_name, attr_target in [
        (app.company_profile_id, "company_name_display", "company_website"),
        (app.target_company_profile_id, "target_company_name_display", "target_company_website"),
    ]:
        if cp_id:
            cp = db.get(models.CompanyProfile, cp_id)
            if cp:
                setattr(app, attr_name, cp.name_display)
                setattr(app, attr_target, cp.website)
    return app


@router.post("/", response_model=schemas.ApplicationRead, status_code=201)
def create_application(payload: schemas.ApplicationCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    app = models.Application(**data)
    app.letztes_update = data.get("datum_bewerbung") or date.today()
    db.add(app)
    db.flush()  # get app.id before creating event
    _ensure_company_profile(db, app)
    event = models.Event(
        application_id=app.id,
        typ="bewerbung",
        datum=app.datum_bewerbung or date.today(),
        titel="Bewerbung eingereicht",
    )
    db.add(event)
    add_audit(db, "create", "user", app_id=app.id,
              new_value=f"{app.firma} – {app.rolle}")
    db.commit()
    db.refresh(app)
    return app


@router.patch("/{app_id}", response_model=schemas.ApplicationRead)
def update_application(app_id: int, payload: schemas.ApplicationUpdate, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")

    update_data = payload.model_dump(exclude_unset=True)

    old_main = app.main_status
    old_sub  = app.sub_status

    # Clear sub_status when switching to a stage that doesn't use it
    if "main_status" in update_data and update_data["main_status"] not in ("hr", "fb"):
        update_data.setdefault("sub_status", None)

    # Record the last active status before rejection so the UI can place the card in the right column
    if update_data.get("main_status") == "rejected" and old_main != "rejected":
        update_data["pre_rejection_status"] = old_main

    # Capture field-level changes before applying them (verbose mode)
    AUDIT_FIELDS = {"firma", "rolle", "zielfirma_bei_hh", "wurde_besetzt_von", "quelle",
                    "datum_bewerbung", "kommentar", "stellenanzeige_url"}
    for f, v in update_data.items():
        if f in AUDIT_FIELDS:
            old_v = getattr(app, f, None)
            if str(old_v or "") != str(v or ""):
                add_audit(db, "update", "user", app_id=app_id,
                          field=f, old_value=str(old_v or ""), new_value=str(v or ""))

    # Direct company profile assignment: look up name and skip _ensure_company_profile
    direct_cp_id = update_data.pop("company_profile_id", None)
    direct_tcp_id = update_data.pop("target_company_profile_id", None)

    firma_changed = "firma" in update_data or "zielfirma_bei_hh" in update_data or "is_headhunter" in update_data
    for field, value in update_data.items():
        setattr(app, field, value)

    if direct_cp_id is not None:
        cp = db.get(models.CompanyProfile, direct_cp_id)
        if cp:
            app.company_profile_id = cp.id
            app.firma = cp.name_display or cp.name_norm
        firma_changed = False  # profile already set, no need to re-derive
    elif firma_changed:
        _ensure_company_profile(db, app)

    if direct_tcp_id is not None:
        tcp = db.get(models.CompanyProfile, direct_tcp_id)
        if tcp:
            app.target_company_profile_id = tcp.id
            app.zielfirma_bei_hh = tcp.name_display or tcp.name_norm

    new_main = app.main_status
    new_sub  = app.sub_status
    if new_main != old_main or new_sub != old_sub:
        db.add(models.Event(
            application_id=app_id,
            typ="status",
            datum=date.today(),
            titel=_status_label(new_main, new_sub),
        ))
        add_audit(db, "status_change", "user", app_id=app_id,
                  field="main_status", old_value=old_main, new_value=new_main,
                  reason="manuell geändert")

    db.commit()
    db.refresh(app)
    return app


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    add_audit(db, "delete", "user", app_id=app_id,
              old_value=f"{app.firma} – {app.rolle}")
    db.delete(app)
    db.commit()


# ── AI Assessment ────────────────────────────────────────────────────────
@router.post("/{app_id}/ai-assess")
async def ai_assess_single(app_id: int, db: Session = Depends(get_db)):
    app = (
        db.query(models.Application)
        .options(joinedload(models.Application.events))
        .filter(models.Application.id == app_id)
        .first()
    )
    if not app:
        raise HTTPException(404, "Bewerbung nicht gefunden")
    from app.ai.tasks import assess_application, assess_rejected_application
    from app.ai.provider import AINotConfigured, AIRateLimited, AIBadRequest
    try:
        if app.abgesagt:
            result = await assess_rejected_application(db, app)
        else:
            result = await assess_application(db, app)
    except AINotConfigured as e:
        raise HTTPException(400, str(e))
    except AIRateLimited:
        raise HTTPException(429, "Rate-Limit des KI-Anbieters erreicht — bitte in 30–60 Sekunden nochmal versuchen.")
    except AIBadRequest as e:
        raise HTTPException(400, str(e))
    app.ai_color = result["color"]
    app.ai_next_step = result["next_step"]
    app.ai_reasoning = result.get("reasoning", "")
    app.ai_assessed_at = datetime.utcnow()
    db.commit()
    return result


# ── Events ──────────────────────────────────────────────────────────────
@router.get("/{app_id}/events", response_model=List[schemas.EventRead])
def list_events(app_id: int, db: Session = Depends(get_db)):
    return db.query(models.Event).filter(models.Event.application_id == app_id).order_by(models.Event.datum.desc()).all()


@router.post("/{app_id}/events", response_model=schemas.EventRead, status_code=201)
def add_event(app_id: int, payload: schemas.EventBase, db: Session = Depends(get_db)):
    event = models.Event(application_id=app_id, **payload.model_dump())
    db.add(event)
    # Sync datum_bewerbung when a bewerbung event is added
    if event.typ == "bewerbung" and event.datum:
        app = db.query(models.Application).get(app_id)
        if app:
            app.datum_bewerbung = event.datum
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{app_id}/events/{event_id}", status_code=204)
def delete_event(app_id: int, event_id: int, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.application_id == app_id,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")
    was_bewerbung = event.typ == "bewerbung"
    db.delete(event)
    # If the deleted event was a bewerbung event, recalculate datum_bewerbung from remaining events
    if was_bewerbung:
        app = db.query(models.Application).get(app_id)
        if app:
            remaining = (
                db.query(models.Event)
                .filter(models.Event.application_id == app_id, models.Event.typ == "bewerbung", models.Event.id != event_id)
                .order_by(models.Event.datum)
                .first()
            )
            app.datum_bewerbung = remaining.datum if remaining else None
    db.commit()


@router.patch("/{app_id}/events/{event_id}", response_model=schemas.EventRead)
def update_event(app_id: int, event_id: int, payload: schemas.EventUpdate, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.application_id == app_id,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    # Sync datum_bewerbung when a bewerbung event date changes
    if event.typ == "bewerbung" and event.datum:
        app = db.query(models.Application).get(app_id)
        if app:
            app.datum_bewerbung = event.datum
    db.commit()
    db.refresh(event)
    return event


# ── Contacts ─────────────────────────────────────────────────────────────
@router.get("/{app_id}/contacts", response_model=List[schemas.ContactRead])
def list_contacts(app_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    return app.contacts


@router.post("/{app_id}/contacts", response_model=schemas.ContactRead, status_code=201)
def add_contact(app_id: int, payload: schemas.ContactBase, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    contact = models.Contact(**payload.model_dump())
    db.add(contact)
    db.flush()
    app.contacts.append(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.patch("/{app_id}/contacts/{contact_id}", response_model=schemas.ContactRead)
def update_contact(app_id: int, contact_id: int, payload: schemas.ContactUpdate, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    contact = next((c for c in app.contacts if c.id == contact_id), None)
    if not contact:
        raise HTTPException(status_code=404, detail="Kontakt nicht gefunden")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@router.put("/{app_id}/contacts/{contact_id}", response_model=schemas.ContactRead)
def link_contact(app_id: int, contact_id: int, db: Session = Depends(get_db)):
    """Link an existing contact to an application (no-op if already linked)."""
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Kontakt nicht gefunden")
    if contact not in app.contacts:
        app.contacts.append(contact)
        db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{app_id}/contacts/{contact_id}", status_code=204)
def delete_contact(app_id: int, contact_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    contact = next((c for c in app.contacts if c.id == contact_id), None)
    if not contact:
        raise HTTPException(status_code=404, detail="Kontakt nicht gefunden")
    # Remove link; delete contact entirely if no other application links remain
    app.contacts.remove(contact)
    db.flush()
    if not contact.applications:
        db.delete(contact)
    db.commit()
