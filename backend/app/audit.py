"""Audit logging helper.

Log levels (stored in SyncSettings.audit_log_level):
  "off"     – nothing logged
  "normal"  – status changes, create, delete, merge, import
  "verbose" – everything above + individual field edits on update
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session


def _log_level(db: Session) -> str:
    from app import models
    s = db.query(models.SyncSettings).first()
    return (s.audit_log_level if s else None) or "normal"


def add_audit(
    db: Session,
    action: str,
    source: str,
    *,
    app_id: Optional[int] = None,
    field: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    reason: Optional[str] = None,
    user_id: Optional[int] = None,
) -> None:
    """Append one audit entry if the current log level permits it.

    action values: create | update | delete | status_change | merge | import
    source values: user | gmail | icloud_mail | linkedin | import | merge | …
    user_id: das anlegende Konto bei Anfragen aus einem HTTP-Request (current_user.id) —
    bei Hintergrund-Sync-Quellen (gmail/icloud_mail/linkedin/…) None, sofern kein
    ausführendes Konto bekannt ist.
    """
    level = _log_level(db)
    if level == "off":
        return
    if level == "normal" and action == "update":
        return  # field-level edits only in verbose mode

    from app import models
    db.add(models.AuditLog(
        app_id=app_id,
        action=action,
        field=field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        source=source,
        reason=reason,
        user_id=user_id,
    ))
