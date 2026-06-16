from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional
from datetime import date

from app.database import get_db
from app import models, schemas
from app.models import MAIN_STATUS_LABELS, SUB_STATUS_LABELS


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

    if app.abgesagt or status == "rejected":
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
        q = q.filter(models.Application.abgesagt.is_(False))

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

        next_interviews = dict(
            db.query(models.Event.application_id, func.min(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                models.Event.typ == "gespräch",
                models.Event.datum > today,
            )
            .group_by(models.Event.application_id)
            .all()
        )

        last_interviews = dict(
            db.query(models.Event.application_id, func.max(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                models.Event.typ == "gespräch",
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
            md = max_event_dates.get(app.id)
            if md and (app.letztes_update is None or md > app.letztes_update):
                app.letztes_update = md
            app.naechster_schritt = _compute_naechster_schritt(
                app,
                next_interviews.get(app.id),
                last_interviews.get(app.id),
                today,
            )
        if fixed_any:
            db.commit()

    return apps


@router.get("/stats", response_model=schemas.StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    all_apps = db.query(models.Application).all()
    total = len(all_apps)
    rejected = sum(1 for a in all_apps if a.abgesagt)
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


@router.get("/{app_id}", response_model=schemas.ApplicationRead)
def get_application(app_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    return app


@router.post("/", response_model=schemas.ApplicationRead, status_code=201)
def create_application(payload: schemas.ApplicationCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if data.get("main_status") == "rejected":
        data["abgesagt"] = True
    app = models.Application(**data)
    app.letztes_update = date.today()
    db.add(app)
    db.flush()  # get app.id before creating event
    event = models.Event(
        application_id=app.id,
        typ="bewerbung",
        datum=app.datum_bewerbung or date.today(),
        titel="Bewerbung eingereicht",
    )
    db.add(event)
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

    # Keep abgesagt in sync with main_status
    if update_data.get("main_status") == "rejected":
        update_data.setdefault("abgesagt", True)
    elif "main_status" in update_data and update_data["main_status"] != "rejected":
        update_data.setdefault("abgesagt", False)

    # Clear sub_status when switching to a stage that doesn't use it
    if "main_status" in update_data and update_data["main_status"] not in ("hr", "fb"):
        update_data.setdefault("sub_status", None)

    for field, value in update_data.items():
        setattr(app, field, value)
    app.letztes_update = date.today()

    new_main = app.main_status
    new_sub  = app.sub_status
    if new_main != old_main or new_sub != old_sub:
        db.add(models.Event(
            application_id=app_id,
            typ="status",
            datum=date.today(),
            titel=_status_label(new_main, new_sub),
        ))

    db.commit()
    db.refresh(app)
    return app


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")
    db.delete(app)
    db.commit()


# ── Events ──────────────────────────────────────────────────────────────
@router.get("/{app_id}/events", response_model=List[schemas.EventRead])
def list_events(app_id: int, db: Session = Depends(get_db)):
    return db.query(models.Event).filter(models.Event.application_id == app_id).order_by(models.Event.datum.desc()).all()


@router.post("/{app_id}/events", response_model=schemas.EventRead, status_code=201)
def add_event(app_id: int, payload: schemas.EventBase, db: Session = Depends(get_db)):
    event = models.Event(application_id=app_id, **payload.model_dump())
    db.add(event)
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
    db.delete(event)
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
