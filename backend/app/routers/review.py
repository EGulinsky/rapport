from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PendingMatch, Event, Application
from app.routers.applications import _status_label
from app.schemas import PendingMatchRead, ApproveMatch

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/count")
def get_pending_count(db: Session = Depends(get_db)):
    count = db.query(PendingMatch).filter(PendingMatch.review_status == "pending").count()
    return {"count": count}


@router.get("/", response_model=list[PendingMatchRead])
def list_pending(db: Session = Depends(get_db)):
    rows = (
        db.query(PendingMatch)
        .filter(PendingMatch.review_status == "pending")
        .order_by(PendingMatch.created_at.desc())
        .all()
    )
    result = []
    for row in rows:
        item = PendingMatchRead(
            id=row.id,
            source=row.source,
            confidence=row.confidence,
            event_type=row.event_type,
            datum=row.datum,
            titel=row.titel,
            extract=row.extract,
            raw_content=row.raw_content,
            suggested_app_id=row.suggested_app_id,
            suggested_app_firma=row.application.firma if row.application else None,
            suggested_app_rolle=row.application.rolle if row.application else None,
            suggested_main_status=row.suggested_main_status,
            suggested_sub_status=row.suggested_sub_status,
            current_main_status=row.application.main_status if row.application else None,
            status_only=bool(row.status_only),
            created_at=row.created_at,
        )
        result.append(item)
    return result


@router.post("/{match_id}/approve")
def approve_match(match_id: int, body: ApproveMatch, db: Session = Depends(get_db)):
    match = db.query(PendingMatch).filter(PendingMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    app = db.query(Application).filter(Application.id == body.application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if match.status_only:
        # Apply the suggested status change and record a status event
        new_main = match.suggested_main_status
        new_sub  = match.suggested_sub_status
        if new_main:
            app.main_status = new_main
            if new_sub:
                app.sub_status = new_sub
            elif new_main not in ("hr", "fb"):
                app.sub_status = None
            if new_main == "rejected":
                app.abgesagt = True
            else:
                app.abgesagt = False
            app.letztes_update = date.today()
            status_event = Event(
                application_id=app.id,
                typ="status",
                datum=date.today(),
                titel=_status_label(new_main, new_sub),
                source=match.source,
            )
            db.add(status_event)
        match.review_status = "approved"
        db.commit()
        return {"status": "approved", "event_id": status_event.id if new_main else None}

    raw_datum: Optional[date] = body.datum or match.datum
    if raw_datum and app.datum_bewerbung:
        raw_datum = max(raw_datum, app.datum_bewerbung)
    event = Event(
        application_id=body.application_id,
        typ=body.event_type or match.event_type or "notiz",
        datum=raw_datum,
        titel=body.titel or match.titel,
        notiz=match.extract,
        source=match.source,
    )
    db.add(event)
    match.review_status = "approved"
    db.commit()
    return {"status": "approved", "event_id": event.id}


@router.delete("/{match_id}")
def reject_match(match_id: int, db: Session = Depends(get_db)):
    match = db.query(PendingMatch).filter(PendingMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match.review_status = "rejected"
    db.commit()
    return {"status": "rejected"}


@router.post("/cleanup-calendar-status")
def cleanup_calendar_status(db: Session = Depends(get_db)):
    """Reject all pending status-change suggestions from calendar sources."""
    result = (
        db.query(PendingMatch)
        .filter(
            PendingMatch.review_status == "pending",
            PendingMatch.status_only.is_(True),
            PendingMatch.source.in_(["gcal", "icloud_cal"]),
        )
        .update({"review_status": "rejected"}, synchronize_session=False)
    )
    db.commit()
    return {"cleaned": result}
