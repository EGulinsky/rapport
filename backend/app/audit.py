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


def _infer_entity_type(app_id, contact_id, company_profile_id, event_id) -> Optional[str]:
    """Same contact>company>event>application precedence the frontend used to
    infer a type client-side — used as the default when entity_type isn't
    passed explicitly. Multiple FKs can be set at once (e.g. a contact created
    in the context of an application); the entity that was actually created/
    changed takes precedence over the context it happened in."""
    if contact_id is not None:
        return "contact"
    if company_profile_id is not None:
        return "company"
    if event_id is not None:
        return "event"
    if app_id is not None:
        return "application"
    return None


def add_audit(
    db: Session,
    action: str,
    source: str,
    *,
    app_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    company_profile_id: Optional[int] = None,
    event_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    field: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    reason: Optional[str] = None,
    user_id: Optional[int] = None,
) -> None:
    """Append one audit entry if the current log level permits it.

    action values: create | update | delete | status_change | merge | import
    source values: user | gmail | icloud_mail | linkedin | import | merge | system | …
    app_id/contact_id/company_profile_id/event_id: welche Entität betroffen ist —
    mehrere können gleichzeitig gesetzt sein (z.B. ein Kontakt-Update im Kontext
    einer Bewerbung), müssen es aber nicht.
    entity_type: application | contact | company | event — welche Art von Eintrag
    das eigentlich ist (unabhängig davon, welche FKs zusätzlich gesetzt sind).
    Wird bei fehlender Angabe aus den gesetzten FKs abgeleitet (siehe
    _infer_entity_type), muss also nur explizit gesetzt werden, wenn die
    Ableitung für den konkreten Aufruf nicht passt.
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
        contact_id=contact_id,
        company_profile_id=company_profile_id,
        event_id=event_id,
        entity_type=entity_type or _infer_entity_type(app_id, contact_id, company_profile_id, event_id),
        action=action,
        field=field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        source=source,
        reason=reason,
        user_id=user_id,
    ))
