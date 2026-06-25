from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date

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
    sync_status: str
    last_synced_at: Optional[datetime] = None
    app_count: int

    model_config = {"from_attributes": True}


class CompanyApplicationRef(BaseModel):
    id: int
    firma: str
    rolle: str
    main_status: str
    datum_bewerbung: Optional[date] = None

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
    applications: List[CompanyApplicationRef] = []

    model_config = {"from_attributes": True}


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

    def app_count(p: CompanyProfile) -> int:
        ids = {a.id for a in p.applications} | {a.id for a in p.hh_applications}
        return len(ids)

    def sort_key(p: CompanyProfile):
        if sort == "industry":
            return (p.industry or "").lower()
        if sort == "apps":
            return app_count(p)
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
            sync_status=p.sync_status,
            last_synced_at=p.last_synced_at,
            app_count=app_count(p),
        )
        for p in profiles
    ]


@router.get("/{company_id}", response_model=CompanyProfileDetail)
def get_company(company_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
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
        applications=apps,
    )
