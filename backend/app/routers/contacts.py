from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel

from app.audit import add_audit
from app.database import get_db
from app import models, schemas
from app.auth.dependencies import get_current_user
from app.error_keys import ErrorKey, api_error

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("/", response_model=List[schemas.ContactWithApp])
def list_all_contacts(
    search: Optional[str] = Query(None),
    company_profile_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Contact).options(joinedload(models.Contact.applications))
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                models.Contact.name.ilike(term),
                models.Contact.vorname.ilike(term),
                models.Contact.email.ilike(term),
                models.Contact.firma.ilike(term),
                models.Contact.rolle.ilike(term),
            )
        )
    if company_profile_id:
        # Matches by FK (direct link, or via any linked application's company),
        # not by the free-text firma column above -- mirrors _collect_contacts()
        # in companies.py, which is what the company's own contact-count badge
        # is computed from. A text match can silently miss contacts that are
        # correctly linked but whose firma text isn't a substring of the
        # company's display name.
        q = q.filter(
            or_(
                models.Contact.company_profile_id == company_profile_id,
                models.Contact.applications.any(
                    or_(
                        models.Application.company_profile_id == company_profile_id,
                        models.Application.target_company_profile_id == company_profile_id,
                    )
                ),
            )
        )
    contacts = q.order_by(models.Contact.name).all()

    # Attach company website and name_display from linked application company profiles
    cp_ids = {a.company_profile_id for c in contacts for a in c.applications if a.company_profile_id}
    if cp_ids:
        profiles = (
            db.query(models.CompanyProfile.id, models.CompanyProfile.website, models.CompanyProfile.name_display)
            .filter(models.CompanyProfile.id.in_(cp_ids))
            .all()
        )
        website_map = {p.id: p.website for p in profiles}
        name_map = {p.id: p.name_display for p in profiles}
        for c in contacts:
            for a in c.applications:
                if a.company_profile_id:
                    a.company_name_display = name_map.get(a.company_profile_id)
                    if not getattr(c, 'company_website', None) and website_map.get(a.company_profile_id):
                        c.company_website = website_map[a.company_profile_id]

    return contacts


class ContactEventItem(BaseModel):
    id: int
    application_id: int
    company_name: Optional[str] = None
    rolle: Optional[str] = None
    typ: str
    datum: Optional[date] = None
    titel: Optional[str] = None
    notiz: Optional[str] = None
    source: Optional[str] = None
    external_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ContactEventsResponse(BaseModel):
    calls: List[ContactEventItem]
    mails: List[ContactEventItem]
    messages: List[ContactEventItem]


def _sort_newest_first(events: List[models.Event]) -> List[models.Event]:
    """Newest-dated first; undated events sort last. Ties break on id (higher
    id = synced/created later) rather than created_at, to sidestep comparing
    naive vs. timezone-aware datetimes across differently-sourced events."""
    return sorted(events, key=lambda e: (e.datum or date.min, e.id), reverse=True)


@router.get("/{contact_id}/events", response_model=ContactEventsResponse)
def get_contact_events(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Calls, mails, and LinkedIn messages connected to this specific contact
    (not just anything on the same application) — mirrors CompanyModal's
    per-tab breakdown, but here scoped to one contact across all of their
    linked applications.

    None of these event types has a direct FK to Contact, so each is matched
    by the same signal already used elsewhere in the codebase: calls and
    LinkedIn messages embed the contact's display name in Event.titel at
    creation time (see _delete_call_events_for_contact() in applications.py
    and attach_linkedin_messages_for_contact() in sync_linkedin.py); mails
    are matched by the sender address in Event.autor (only populated for
    mail events synced after this feature shipped — see
    _save_deterministic_event() in sync_common.py)."""
    contact = db.query(models.Contact).filter_by(id=contact_id).first()
    if not contact:
        raise api_error(404, ErrorKey.CONTACT_NOT_FOUND, "Kontakt nicht gefunden")

    apps = list(contact.applications)
    if not apps:
        return ContactEventsResponse(calls=[], mails=[], messages=[])

    app_ids = [a.id for a in apps]
    company_ids = {a.company_profile_id for a in apps if a.company_profile_id}
    company_names = {}
    if company_ids:
        company_names = dict(
            db.query(models.CompanyProfile.id, models.CompanyProfile.name_display)
            .filter(models.CompanyProfile.id.in_(company_ids))
            .all()
        )
    app_meta = {a.id: a for a in apps}

    def _to_item(e: models.Event) -> ContactEventItem:
        app = app_meta[e.application_id]
        company_name = company_names.get(app.company_profile_id) if app.company_profile_id else None
        return ContactEventItem(
            id=e.id, application_id=e.application_id, company_name=company_name or app.firma,
            rolle=app.rolle, typ=e.typ, datum=e.datum, titel=e.titel, notiz=e.notiz,
            source=e.source, external_id=e.external_id, created_at=e.created_at,
        )

    display_name = contact.display_name

    calls = db.query(models.Event).filter(
        models.Event.application_id.in_(app_ids),
        models.Event.source == "icloud_calls",
        models.Event.titel.contains(display_name),
    ).all()

    messages = db.query(models.Event).filter(
        models.Event.application_id.in_(app_ids),
        models.Event.source == "linkedin_msg",
        models.Event.titel.contains(display_name),
    ).all()

    mails: List[models.Event] = []
    if contact.email:
        mails = db.query(models.Event).filter(
            models.Event.application_id.in_(app_ids),
            models.Event.source.in_(("gmail", "icloud_mail")),
            models.Event.autor.ilike(f"%{contact.email}%"),
        ).all()

    return ContactEventsResponse(
        calls=[_to_item(e) for e in _sort_newest_first(calls)],
        mails=[_to_item(e) for e in _sort_newest_first(mails)],
        messages=[_to_item(e) for e in _sort_newest_first(messages)],
    )


class ContactPhoneIn(BaseModel):
    number: str
    type: str = "other"


def _replace_phones(contact: models.Contact, phones: List[ContactPhoneIn], user_id: int) -> None:
    contact.phones.clear()
    for p in phones:
        contact.phones.append(models.ContactPhone(number=p.number, type=p.type, user_id=user_id))


class ContactCreate(BaseModel):
    name: str
    vorname: Optional[str] = None
    email: Optional[str] = None
    phones: List[ContactPhoneIn] = []
    firma: Optional[str] = None
    company_profile_id: Optional[int] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    linkedin_url: Optional[str] = None


@router.post("/", status_code=201)
def create_contact(
    body: ContactCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = body.model_dump(exclude={"phones"})
    contact = models.Contact(**data, user_id=current_user.id)
    for p in body.phones:
        contact.phones.append(models.ContactPhone(number=p.number, type=p.type, user_id=current_user.id))
    db.add(contact)
    db.flush()
    add_audit(db, "create", "user", contact_id=contact.id,
              new_value=contact.display_name, user_id=current_user.id)
    from app.routers.sync_linkedin import attach_linkedin_messages_for_contact
    attach_linkedin_messages_for_contact(db, contact, current_user.id)
    db.commit()
    db.refresh(contact)
    return {"id": contact.id, "name": contact.name, "firma": contact.firma,
            "company_profile_id": contact.company_profile_id}


class ContactPatch(BaseModel):
    company_profile_id: Optional[int] = None
    firma: Optional[str] = None
    name: Optional[str] = None
    vorname: Optional[str] = None
    email: Optional[str] = None
    phones: Optional[List[ContactPhoneIn]] = None
    linkedin_url: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    notizen: Optional[str] = None
    letzter_kontakt: Optional[date] = None


@router.patch("/{contact_id}")
def patch_contact(
    contact_id: int,
    body: ContactPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    contact = db.query(models.Contact).filter_by(id=contact_id).first()
    if not contact:
        raise api_error(404, ErrorKey.CONTACT_NOT_FOUND, "Kontakt nicht gefunden")
    for field, value in body.model_dump(exclude_unset=True, exclude={"phones"}).items():
        old_v = getattr(contact, field, None)
        if str(old_v or "") != str(value or ""):
            add_audit(db, "update", "user", contact_id=contact.id,
                      field=field, old_value=old_v, new_value=value, user_id=current_user.id)
        setattr(contact, field, value)
    if body.phones is not None:
        _replace_phones(contact, body.phones, current_user.id)
        add_audit(db, "update", "user", contact_id=contact.id,
                  field="phones", old_value=None, new_value=f"{len(body.phones)} Nummer(n)", user_id=current_user.id)
    db.commit()
    return {"ok": True}


class BulkDeleteBody(BaseModel):
    ids: List[int]
    all: bool = False


@router.delete("/bulk", status_code=200)
def bulk_delete_contacts(
    body: BulkDeleteBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Bulk-delete() umgeht (wie jedes Query.delete()/.update()) den ORM-Loader
    # und damit den automatischen Mandanten-Filter — daher hier explizit gefiltert.
    q = db.query(models.Contact).filter(models.Contact.user_id == current_user.id)
    if not body.all:
        q = q.filter(models.Contact.id.in_(body.ids))
    to_delete = q.all()
    for c in to_delete:
        add_audit(db, "delete", "user", contact_id=c.id,
                  old_value=c.display_name, user_id=current_user.id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
