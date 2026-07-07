import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PendingMatch, Event, Application, Contact, User
from app.routers.applications import _status_label
from app.schemas import PendingMatchRead, ApproveMatch
from app.audit import add_audit
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/count")
def get_pending_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    count = db.query(PendingMatch).filter(PendingMatch.review_status == "pending").count()
    return {"count": count}


@router.get("/", response_model=list[PendingMatchRead])
def list_pending(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
async def approve_match(
    match_id: int,
    body: ApproveMatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    match = db.query(PendingMatch).filter(PendingMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # ── Firmensync: mehrdeutiger LinkedIn-Treffer, User hat einen gewählt ────
    if match.event_type == "company_candidate":
        from app.routers.sync_company import resolve_company_candidate
        try:
            payload = json.loads(match.raw_content or "{}")
            profile_id = payload.get("company_profile_id")
        except Exception:
            profile_id = None
        if profile_id and body.linkedin_url:
            await resolve_company_candidate(db, profile_id, body.linkedin_url, current_user.id)
        match.review_status = "approved"
        db.commit()
        return {"status": "approved", "event_id": None}

    # ── Cleanup duplicates (no application required) ─────────────────────────
    if match.event_type == "duplicate_contact":
        try:
            payload = json.loads(match.raw_content or "{}")
            keeper_id = payload.get("keeper_contact_id")
            dup_id = payload.get("dup_contact_id")
        except Exception:
            keeper_id = dup_id = None
        if keeper_id and dup_id:
            keeper = db.query(Contact).filter_by(id=keeper_id, user_id=current_user.id).first()
            dup = db.query(Contact).filter_by(id=dup_id, user_id=current_user.id).first()
            if keeper and dup:
                keeper_app_ids = {a.id for a in keeper.applications}
                for app in list(dup.applications):
                    if app.id not in keeper_app_ids:
                        keeper.applications.append(app)
                dup.applications.clear()
                db.flush()
                db.delete(dup)
        match.review_status = "approved"
        db.commit()
        return {"status": "approved", "event_id": None}

    app = db.query(Application).filter(Application.id == body.application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if match.event_type == "duplicate_event":
        try:
            payload = json.loads(match.raw_content or "{}")
            dup_event_id = payload.get("dup_event_id")
        except Exception:
            dup_event_id = None
        if dup_event_id:
            ev = db.query(Event).filter_by(id=dup_event_id, user_id=current_user.id).first()
            if ev:
                db.delete(ev)
        match.review_status = "approved"
        db.commit()
        return {"status": "approved", "event_id": None}

    if match.status_only:
        # Apply the suggested status change and record a status event
        new_main = match.suggested_main_status
        new_sub  = match.suggested_sub_status
        if new_main:
            old_main = app.main_status
            if new_main == "rejected" and app.main_status != "rejected":
                app.pre_rejection_status = app.main_status
            app.main_status = new_main
            if new_sub:
                app.sub_status = new_sub
            elif new_main not in ("hr", "fb"):
                app.sub_status = None
            app.letztes_update = date.today()
            status_event = Event(
                application_id=app.id,
                typ="status",
                datum=date.today(),
                titel=_status_label(new_main, new_sub),
                source=match.source,
                user_id=current_user.id,
            )
            db.add(status_event)
            add_audit(db, "status_change", match.source or "user",
                      app_id=app.id, field="main_status",
                      old_value=old_main, new_value=new_main,
                      reason="PendingMatch genehmigt", user_id=current_user.id)
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
        user_id=current_user.id,
    )
    db.add(event)
    match.review_status = "approved"
    db.commit()
    return {"status": "approved", "event_id": event.id}


@router.delete("/{match_id}")
async def reject_match(
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    match = db.query(PendingMatch).filter(PendingMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # ── Firmensync: "keiner davon" → Wikidata-Fallback für diese eine Firma ──
    if match.event_type == "company_candidate":
        from app.routers.sync_company import resolve_company_candidate
        try:
            payload = json.loads(match.raw_content or "{}")
            profile_id = payload.get("company_profile_id")
        except Exception:
            profile_id = None
        if profile_id:
            await resolve_company_candidate(db, profile_id, None, current_user.id)
        match.review_status = "rejected"
        db.commit()
        return {"status": "rejected"}

    match.review_status = "rejected"
    db.commit()
    return {"status": "rejected"}


@router.post("/cleanup-calendar-status")
def cleanup_calendar_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Reject all pending status-change suggestions from calendar sources."""
    result = (
        db.query(PendingMatch)
        .filter(
            PendingMatch.review_status == "pending",
            PendingMatch.status_only.is_(True),
            PendingMatch.source.in_(["gcal", "icloud_cal"]),
            PendingMatch.user_id == current_user.id,
        )
        .update({"review_status": "rejected"}, synchronize_session=False)
    )
    db.commit()
    return {"cleaned": result}
