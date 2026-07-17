from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/")
def list_audit(
    db: Session = Depends(get_db),
    app_id: Optional[int] = Query(None),
    contact_id: Optional[int] = Query(None),
    company_profile_id: Optional[int] = Query(None),
    event_id: Optional[int] = Query(None),
    entity_type: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc())
    if app_id is not None:
        q = q.filter(models.AuditLog.app_id == app_id)
    if contact_id is not None:
        q = q.filter(models.AuditLog.contact_id == contact_id)
    if company_profile_id is not None:
        q = q.filter(models.AuditLog.company_profile_id == company_profile_id)
    if event_id is not None:
        q = q.filter(models.AuditLog.event_id == event_id)
    if entity_type is not None:
        q = q.filter(models.AuditLog.entity_type == entity_type)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "app_id": r.app_id,
                "app_firma": r.application.firma if r.application else None,
                "app_rolle": r.application.rolle if r.application else None,
                "contact_id": r.contact_id,
                "contact_name": r.contact.display_name if r.contact else None,
                "company_profile_id": r.company_profile_id,
                "company_name": (r.company_profile.name_display or r.company_profile.name_norm) if r.company_profile else None,
                "event_id": r.event_id,
                "event_titel": r.event.titel if r.event else None,
                "entity_type": r.entity_type,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "action": r.action,
                "field": r.field,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "source": r.source,
                "reason": r.reason,
            }
            for r in rows
        ],
    }


@router.delete("/")
def clear_audit(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    deleted = db.query(models.AuditLog).filter(models.AuditLog.user_id == current_user.id).delete()
    db.commit()
    return {"deleted": deleted}
