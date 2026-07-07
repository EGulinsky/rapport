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
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc())
    if app_id is not None:
        q = q.filter(models.AuditLog.app_id == app_id)
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
