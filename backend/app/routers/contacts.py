from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app import models, schemas
from app.models import CompanyProfile

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
