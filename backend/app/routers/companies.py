from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date
import base64

from app.database import get_db
from app.models import CompanyProfile

router = APIRouter(prefix="/api/companies", tags=["companies"])


class CompanyProfileListItem(BaseModel):
    id: int
    name_display: Optional[str] = None
    name_norm: str
    industry: Optional[str] = None
    company_type: Optional[str] = None
    employee_range: Optional[str] = None
    hq_city: Optional[str] = None
    hq_country: Optional[str] = None
    website: Optional[str] = None
    sync_status: str
    last_synced_at: Optional[datetime] = None
    app_count: int
    contact_count: int = 0
    has_logo: bool = False

    model_config = {"from_attributes": True}


class CompanyApplicationRef(BaseModel):
    id: int
    firma: str
    rolle: str
    main_status: str
    datum_bewerbung: Optional[date] = None

    model_config = {"from_attributes": True}


class CompanyContactRef(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    telefon: Optional[str] = None
    linkedin_url: Optional[str] = None
    firma: Optional[str] = None
    rolle: Optional[str] = None
    typ: Optional[str] = None

    model_config = {"from_attributes": True}


class CompanyProfileDetail(BaseModel):
    id: int
    name_display: Optional[str] = None
    name_norm: str
    industry: Optional[str] = None
    company_type: Optional[str] = None
    employee_range: Optional[str] = None
    employee_count: Optional[int] = None
    founded_year: Optional[int] = None
    hq_city: Optional[str] = None
    hq_country: Optional[str] = None
    website: Optional[str] = None
    linkedin_company_url: Optional[str] = None
    description: Optional[str] = None
    sync_source: Optional[str] = None
    sync_status: str
    sync_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    app_count: int
    contact_count: int = 0
    logo_data: Optional[str] = None
    applications: List[CompanyApplicationRef] = []
    contacts: List[CompanyContactRef] = []

    model_config = {"from_attributes": True}


class CompanyUpdateRequest(BaseModel):
    name_display: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[str] = None
    employee_range: Optional[str] = None
    employee_count: Optional[int] = None
    founded_year: Optional[int] = None
    hq_city: Optional[str] = None
    hq_country: Optional[str] = None
    website: Optional[str] = None
    linkedin_company_url: Optional[str] = None
    description: Optional[str] = None


def _app_count(p: CompanyProfile) -> int:
    ids = {a.id for a in p.applications} | {a.id for a in p.hh_applications}
    return len(ids)


def _collect_contacts(p: CompanyProfile) -> list:
    all_apps = list(p.applications) + list(p.hh_applications)
    seen_contact_ids = set()
    contacts = []
    for a in all_apps:
        for c in a.contacts:
            if c.id not in seen_contact_ids:
                seen_contact_ids.add(c.id)
                contacts.append(c)
    return contacts


@router.get("", response_model=List[CompanyProfileListItem])
def list_companies(
    search: Optional[str] = Query(None),
    sort: str = Query("name"),
    order: str = Query("asc"),
    db: Session = Depends(get_db),
):
    profiles = db.query(CompanyProfile).all()

    if search:
        q = search.lower()
        profiles = [
            p for p in profiles
            if q in (p.name_display or "").lower()
            or q in (p.name_norm or "").lower()
            or q in (p.industry or "").lower()
            or q in (p.hq_city or "").lower()
            or q in (p.hq_country or "").lower()
        ]

    def sort_key(p: CompanyProfile):
        if sort == "industry":
            return (p.industry or "").lower()
        if sort == "apps":
            return _app_count(p)
        if sort == "sync_status":
            return p.sync_status or ""
        return (p.name_display or p.name_norm or "").lower()

    profiles.sort(key=sort_key, reverse=(order == "desc"))

    return [
        CompanyProfileListItem(
            id=p.id,
            name_display=p.name_display,
            name_norm=p.name_norm,
            industry=p.industry,
            company_type=p.company_type,
            employee_range=p.employee_range,
            hq_city=p.hq_city,
            hq_country=p.hq_country,
            website=p.website,
            sync_status=p.sync_status,
            last_synced_at=p.last_synced_at,
            app_count=_app_count(p),
            contact_count=len(_collect_contacts(p)),
            has_logo=bool(p.logo_data),
        )
        for p in profiles
    ]


@router.get("/{company_id}", response_model=CompanyProfileDetail)
def get_company(company_id: int, db: Session = Depends(get_db)):
    profile = db.query(CompanyProfile).filter(CompanyProfile.id == company_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Company not found")

    seen = set()
    apps = []
    for a in list(profile.applications) + list(profile.hh_applications):
        if a.id not in seen:
            seen.add(a.id)
            apps.append(CompanyApplicationRef(
                id=a.id,
                firma=a.firma,
                rolle=a.rolle,
                main_status=a.main_status,
                datum_bewerbung=a.datum_bewerbung,
            ))

    contacts_raw = _collect_contacts(profile)
    contacts = [
        CompanyContactRef(
            id=c.id,
            name=c.name,
            email=c.email,
            telefon=c.telefon,
            linkedin_url=c.linkedin_url,
            firma=c.firma,
            rolle=c.rolle,
            typ=c.typ,
        )
        for c in contacts_raw
    ]

    ids = {a.id for a in profile.applications} | {a.id for a in profile.hh_applications}

    return CompanyProfileDetail(
        id=profile.id,
        name_display=profile.name_display,
        name_norm=profile.name_norm,
        industry=profile.industry,
        company_type=profile.company_type,
        employee_range=profile.employee_range,
        employee_count=profile.employee_count,
        founded_year=profile.founded_year,
        hq_city=profile.hq_city,
        hq_country=profile.hq_country,
        website=profile.website,
        linkedin_company_url=profile.linkedin_company_url,
        description=profile.description,
        sync_source=profile.sync_source,
        sync_status=profile.sync_status,
        sync_error=profile.sync_error,
        last_synced_at=profile.last_synced_at,
        app_count=len(ids),
        contact_count=len(contacts),
        logo_data=profile.logo_data,
        applications=apps,
        contacts=contacts,
    )


@router.patch("/{company_id}", response_model=CompanyProfileDetail)
def update_company(company_id: int, body: CompanyUpdateRequest, db: Session = Depends(get_db)):
    profile = db.query(CompanyProfile).filter(CompanyProfile.id == company_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Company not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value or None)

    db.commit()
    db.refresh(profile)

    # Re-use get_company logic
    return get_company(company_id, db)


@router.post("/link-contacts")
def link_contacts_to_companies(db: Session = Depends(get_db)):
    from app.dedup import norm_firma
    from app import models
    contacts = db.query(models.Contact).all()
    linked = 0
    created = 0
    for c in contacts:
        if not c.firma:
            continue
        nname = norm_firma(c.firma)
        profile = db.query(CompanyProfile).filter(CompanyProfile.name_norm == nname).first()
        if not profile:
            profile = CompanyProfile(name_norm=nname, name_display=c.firma, sync_status="pending")
            db.add(profile)
            db.flush()
            created += 1
        if c.company_profile_id != profile.id:
            c.company_profile_id = profile.id
            linked += 1
    db.commit()
    return {"linked": linked, "created": created}


@router.post("/{company_id}/logo")
async def upload_company_logo(company_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    profile = db.get(CompanyProfile, company_id)
    if not profile:
        raise HTTPException(404)
    data = await file.read()
    mime = file.content_type or "image/png"
    b64 = base64.b64encode(data).decode()
    profile.logo_data = f"data:{mime};base64,{b64}"
    db.commit()
    return {"ok": True}


@router.delete("/{company_id}/logo")
def delete_company_logo(company_id: int, db: Session = Depends(get_db)):
    profile = db.get(CompanyProfile, company_id)
    if not profile:
        raise HTTPException(404)
    profile.logo_data = None
    db.commit()
    return {"ok": True}
