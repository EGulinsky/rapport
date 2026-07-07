from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date
import base64

from app.database import get_db, SessionLocal, set_session_user
from app.models import CompanyProfile, User
from app.auth.dependencies import get_current_user
from app.logger import get_logger

log = get_logger("sync", source="company")

router = APIRouter(prefix="/api/companies", tags=["companies"])

_LINK_RUNNING = False
_LINK_CANCEL = False
_LINK_PROGRESS: dict = {"linked": 0, "created": 0, "total": 0, "done": False, "cancelled": False}


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
    parent_company_id: Optional[int] = None
    parent_name: Optional[str] = None

    model_config = {"from_attributes": True}


class CompanySubsidiaryRef(BaseModel):
    id: int
    name_display: Optional[str] = None
    name_norm: str

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
    parent_company_id: Optional[int] = None
    parent_name: Optional[str] = None
    subsidiaries: List[CompanySubsidiaryRef] = []
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
    parent_company_id: Optional[int] = None


def _app_count(p: CompanyProfile) -> int:
    ids = {a.id for a in p.applications} | {a.id for a in p.hh_applications}
    return len(ids)


def _collect_contacts(p: CompanyProfile) -> list:
    seen: set[int] = set()
    contacts = []
    for c in getattr(p, 'direct_contacts', []):
        if c.id not in seen:
            seen.add(c.id)
            contacts.append(c)
    for a in list(p.applications) + list(p.hh_applications):
        for c in a.contacts:
            if c.id not in seen:
                seen.add(c.id)
                contacts.append(c)
    return contacts


class CompanyCreateRequest(BaseModel):
    name: str


@router.post("", response_model=CompanyProfileListItem, status_code=201)
def create_company(
    body: CompanyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.dedup import norm_firma
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")
    key = norm_firma(name)
    existing = db.query(CompanyProfile).filter(CompanyProfile.name_norm == key).first()
    if existing:
        return existing
    profile = CompanyProfile(name_norm=key, name_display=name, sync_status="pending", user_id=current_user.id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    profile.app_count = 0  # type: ignore[assignment]
    return profile


@router.get("", response_model=List[CompanyProfileListItem])
def list_companies(
    search: Optional[str] = Query(None),
    sort: str = Query("name"),
    order: str = Query("asc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profiles = db.query(CompanyProfile).all()
    id_to_name = {p.id: p.name_display or p.name_norm for p in profiles}

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
            parent_company_id=p.parent_company_id,
            parent_name=id_to_name.get(p.parent_company_id) if p.parent_company_id else None,
        )
        for p in profiles
    ]


@router.get("/{company_id}", response_model=CompanyProfileDetail)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    parent_name = (profile.parent.name_display or profile.parent.name_norm) if profile.parent else None
    subs = [CompanySubsidiaryRef(id=s.id, name_display=s.name_display, name_norm=s.name_norm) for s in profile.subsidiaries]

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
        parent_company_id=profile.parent_company_id,
        parent_name=parent_name,
        subsidiaries=subs,
        applications=apps,
        contacts=contacts,
    )


@router.patch("/{company_id}", response_model=CompanyProfileDetail)
def update_company(
    company_id: int,
    body: CompanyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(CompanyProfile).filter(CompanyProfile.id == company_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Company not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "parent_company_id":
            # cycle guard: don't allow a company to be its own ancestor
            if value is not None:
                ancestor = db.query(CompanyProfile).filter_by(id=value, user_id=current_user.id).first()
                visited: set[int] = set()
                while ancestor:
                    if ancestor.id == profile.id:
                        raise HTTPException(400, "Zyklische Hierarchie nicht erlaubt")
                    if ancestor.id in visited:
                        break
                    visited.add(ancestor.id)
                    ancestor = (
                        db.query(CompanyProfile).filter_by(id=ancestor.parent_company_id, user_id=current_user.id).first()
                        if ancestor.parent_company_id else None
                    )
            setattr(profile, field, value)
        else:
            setattr(profile, field, value or None)

    db.commit()
    db.refresh(profile)

    # Re-use get_company logic
    return get_company(company_id, db, current_user)


@router.get("/link-contacts/status")
def link_contacts_status():
    return {"running": _LINK_RUNNING, **_LINK_PROGRESS}


@router.post("/link-contacts/cancel")
def link_contacts_cancel():
    global _LINK_CANCEL
    _LINK_CANCEL = True
    return {"ok": True}


@router.post("/link-contacts")
def link_contacts_to_companies(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_ids: list[int] | None = Query(default=None),
):
    global _LINK_RUNNING
    if _LINK_RUNNING:
        return {"started": False, "message": "Bereits läuft"}
    from app import models

    # Scoped to specific companies: link only unlinked contacts whose firma
    # normalizes to one of the selected companies' names.
    allowed_norms: set[str] | None = None
    if company_ids:
        allowed_norms = {
            n for (n,) in db.query(CompanyProfile.name_norm)
            .filter(CompanyProfile.id.in_(company_ids), CompanyProfile.user_id == current_user.id)
            .all()
        }

    total = db.query(models.Contact).filter(
        models.Contact.company_profile_id.is_(None),
        models.Contact.firma.isnot(None),
        models.Contact.user_id == current_user.id,
    ).count()
    background_tasks.add_task(_run_link_contacts, current_user.id, allowed_norms)
    return {"started": True, "total": total}


def _run_link_contacts(user_id: int, allowed_norms: set[str] | None = None):
    global _LINK_RUNNING, _LINK_CANCEL, _LINK_PROGRESS
    from app.dedup import norm_firma
    from app import models
    _LINK_RUNNING = True
    _LINK_CANCEL = False
    _LINK_PROGRESS = {"linked": 0, "created": 0, "total": 0, "done": False, "cancelled": False}
    try:
        db = SessionLocal()
        set_session_user(db, user_id)
        contacts = db.query(models.Contact).filter(
            models.Contact.company_profile_id.is_(None),
            models.Contact.firma.isnot(None),
            models.Contact.user_id == user_id,
        ).all()
        if allowed_norms is not None:
            contacts = [c for c in contacts if norm_firma(c.firma) in allowed_norms]
        _LINK_PROGRESS["total"] = len(contacts)
        linked = 0
        created = 0
        for c in contacts:
            if _LINK_CANCEL:
                _LINK_PROGRESS["cancelled"] = True
                log.info("Kontaktverknüpfung abgebrochen nach {}/{}", linked + created, len(contacts))
                break
            nname = norm_firma(c.firma)
            profile = db.query(CompanyProfile).filter(
                CompanyProfile.name_norm == nname, CompanyProfile.user_id == user_id
            ).first()
            if not profile:
                # Scoped runs must not silently create new profiles outside the selection.
                if allowed_norms is not None:
                    continue
                profile = CompanyProfile(name_norm=nname, name_display=c.firma, sync_status="pending", user_id=user_id)
                db.add(profile)
                db.flush()
                created += 1
            if c.company_profile_id != profile.id:
                c.company_profile_id = profile.id
                linked += 1
            _LINK_PROGRESS["linked"] = linked
            _LINK_PROGRESS["created"] = created
        db.commit()
        db.close()
        _LINK_PROGRESS["done"] = True
        log.info("Kontaktverknüpfung: {} verknüpft, {} erstellt", linked, created)
    except Exception as e:
        log.error("Kontaktverknüpfung Fehler: {}", e)
    finally:
        _LINK_RUNNING = False
        _LINK_CANCEL = False


@router.post("/{company_id}/logo")
async def upload_company_logo(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(CompanyProfile).filter_by(id=company_id, user_id=current_user.id).first()
    if not profile:
        raise HTTPException(404)
    data = await file.read()
    mime = file.content_type or "image/png"
    b64 = base64.b64encode(data).decode()
    profile.logo_data = f"data:{mime};base64,{b64}"
    db.commit()
    return {"ok": True}


@router.delete("/{company_id}/logo")
def delete_company_logo(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(CompanyProfile).filter_by(id=company_id, user_id=current_user.id).first()
    if not profile:
        raise HTTPException(404)
    profile.logo_data = None
    db.commit()
    return {"ok": True}


@router.post("/{company_id}/contacts/{contact_id}", status_code=200)
def assign_contact_to_company(
    company_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app import models as m
    profile = db.query(CompanyProfile).filter_by(id=company_id, user_id=current_user.id).first()
    if not profile:
        raise HTTPException(404)
    contact = db.query(m.Contact).filter_by(id=contact_id, user_id=current_user.id).first()
    if not contact:
        raise HTTPException(404)
    contact.company_profile_id = company_id
    db.commit()
    return {"ok": True}


@router.delete("/{company_id}/contacts/{contact_id}", status_code=200)
def unassign_contact_from_company(
    company_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app import models as m
    contact = db.query(m.Contact).filter_by(id=contact_id, user_id=current_user.id).first()
    if not contact:
        raise HTTPException(404)
    if contact.company_profile_id == company_id:
        contact.company_profile_id = None
        db.commit()
    return {"ok": True}


class BulkDeleteCompaniesBody(BaseModel):
    ids: List[int]


@router.delete("/bulk", status_code=200)
def bulk_delete_companies(
    body: BulkDeleteCompaniesBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = (
        db.query(CompanyProfile)
        .filter(CompanyProfile.id.in_(body.ids), CompanyProfile.user_id == current_user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}
