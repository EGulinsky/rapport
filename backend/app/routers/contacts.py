from datetime import date
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Contact).options(joinedload(models.Contact.applications))
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                models.Contact.name.ilike(term),
                models.Contact.email.ilike(term),
                models.Contact.firma.ilike(term),
                models.Contact.rolle.ilike(term),
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


class ContactCreate(BaseModel):
    name: str
    vorname: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
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
    contact = models.Contact(**body.model_dump(), user_id=current_user.id)
    db.add(contact)
    db.flush()
    add_audit(db, "create", "user", contact_id=contact.id,
              new_value=contact.name, user_id=current_user.id)
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
    telefon: Optional[str] = None
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
    for field, value in body.model_dump(exclude_unset=True).items():
        old_v = getattr(contact, field, None)
        if str(old_v or "") != str(value or ""):
            add_audit(db, "update", "user", contact_id=contact.id,
                      field=field, old_value=old_v, new_value=value, user_id=current_user.id)
        setattr(contact, field, value)
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
                  old_value=c.name, user_id=current_user.id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
