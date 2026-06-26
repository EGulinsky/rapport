from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("/", response_model=List[schemas.ContactWithApp])
def list_all_contacts(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
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

    # Attach company website from first linked application's company profile
    cp_ids = {a.company_profile_id for c in contacts for a in c.applications if a.company_profile_id}
    if cp_ids:
        website_map = dict(
            db.query(models.CompanyProfile.id, models.CompanyProfile.website)
            .filter(models.CompanyProfile.id.in_(cp_ids))
            .all()
        )
        for c in contacts:
            for a in c.applications:
                if a.company_profile_id and website_map.get(a.company_profile_id):
                    c.company_website = website_map[a.company_profile_id]
                    break

    return contacts


class ContactPatch(BaseModel):
    company_profile_id: Optional[int] = None
    firma: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    linkedin_url: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None
    notizen: Optional[str] = None


@router.patch("/{contact_id}")
def patch_contact(contact_id: int, body: ContactPatch, db: Session = Depends(get_db)):
    contact = db.get(models.Contact, contact_id)
    if not contact:
        raise HTTPException(404)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    db.commit()
    return {"ok": True}


class BulkDeleteBody(BaseModel):
    ids: List[int]
    all: bool = False


@router.delete("/bulk", status_code=200)
def bulk_delete_contacts(body: BulkDeleteBody, db: Session = Depends(get_db)):
    if body.all:
        deleted = db.query(models.Contact).delete()
    else:
        deleted = db.query(models.Contact).filter(models.Contact.id.in_(body.ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
