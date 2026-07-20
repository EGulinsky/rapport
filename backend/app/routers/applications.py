import json
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from typing import List, Optional
from datetime import date, datetime

from app.database import get_db
from app import models, schemas
from app.auth.dependencies import get_current_user
from app.models import MAIN_STATUS_LABELS, SUB_STATUS_LABELS
from app.audit import add_audit
from app.dedup import norm_firma
from app.error_keys import ErrorKey, api_error
from app.routers.sync_common import _berlin_naive_to_utc_naive
from app.routers.geo import _get_maps_api_key, geocode_one, driving_route


def _delete_call_events_for_contact(db: Session, app_id: int, contact: "models.Contact", user_id: Optional[int]) -> int:
    """Calls sync has no live FK to Contact — the caller's name is baked into
    the event's titel as plain text at sync time (see sync_targeted.py's
    _sync_calls_for_app / sync_icloud.py's global calls sync). Matching on
    that embedded name is the only way to find "calls from/to this contact"
    for this application after the fact."""
    name = contact.display_name
    if not name:
        return 0
    events = db.query(models.Event).filter(
        models.Event.application_id == app_id,
        models.Event.source == "icloud_calls",
        models.Event.titel.contains(name),
    ).all()
    for event in events:
        add_audit(db, "delete", "user", app_id=app_id, event_id=event.id,
                  old_value=event.titel, user_id=user_id)
        db.delete(event)
    return len(events)


def _validate_salary_pair(min_v: Optional[int], max_v: Optional[int], label: str) -> None:
    if max_v is None:
        return
    if min_v is None:
        raise api_error(400, ErrorKey.APPLICATION_SALARY_RANGE_INVALID,
                         f"{label}: Max ohne Min nicht erlaubt")
    if max_v < min_v:
        raise api_error(400, ErrorKey.APPLICATION_SALARY_RANGE_INVALID,
                         f"{label}: Max muss >= Min sein")


def _validate_salary_breakdown(fixed: Optional[int], bonus: Optional[int], total: Optional[int], label: str) -> None:
    if fixed is None and bonus is None:
        return
    if fixed is None or bonus is None:
        raise api_error(400, ErrorKey.APPLICATION_SALARY_RANGE_INVALID,
                         f"{label}: Fixum und Bonus müssen beide gesetzt sein")
    if total != fixed + bonus:
        raise api_error(400, ErrorKey.APPLICATION_SALARY_RANGE_INVALID,
                         f"{label}: Summe aus Fixum und Bonus muss dem Gesamtbetrag entsprechen")


def _status_label(main: str, sub: str | None) -> str:
    label = MAIN_STATUS_LABELS.get(main, main)
    if sub:
        label += f" – {SUB_STATUS_LABELS.get(sub, sub)}"
    return label


def _compute_naechster_schritt(
    app,
    next_interview: Optional[date],
    last_interview: Optional[date],
    today: date,
) -> str:
    status = app.main_status or ""

    if status == "rejected":
        return ""

    if next_interview:
        delta = (next_interview - today).days
        when = next_interview.strftime("%d.%m.%Y")
        if delta == 0:
            return f"Gespräch heute ({when})"
        if delta == 1:
            return f"Gespräch morgen ({when})"
        return f"Gespräch am {when} (in {delta} Tagen)"

    if status == "signed":
        return "Onboarding vorbereiten"

    if status == "negotiating":
        return "Vertragsdetails klären"

    if last_interview:
        days = (today - last_interview).days
        if days <= 7:
            return "Warte auf Feedback"
        if days <= 21:
            return f"Feedback ausstehend — evtl. nachfassen ({days} Tage)"
        return f"Kein Feedback seit {days} Tagen — evtl. Ghosting"

    if status in ("hr", "fb"):
        return "Terminvereinbarung ausstehend"

    if status == "waiting":
        return "Warte auf Rückmeldung"

    if status == "applied":
        days_since = (today - app.datum_bewerbung).days if app.datum_bewerbung else 0
        if days_since < 14:
            return "Warte auf Einladung"
        if days_since < 30:
            return f"Evtl. nachfassen ({days_since} Tage ohne Reaktion)"
        return f"Keine Reaktion seit {days_since} Tagen"

    if status == "prospecting":
        return "Bewerbung vorbereiten"

    return ""

def _find_or_create_company_profile(db: Session, firma_name: str, user_id: int) -> tuple[models.CompanyProfile, bool]:
    """Match an existing CompanyProfile by normalized name or create a new one.

    Returns (profile, created) — created=True means a fresh "pending" profile
    was inserted and still needs its background data fetch.
    """
    key = norm_firma(firma_name)
    profile = db.query(models.CompanyProfile).filter(
        models.CompanyProfile.name_norm == key,
        models.CompanyProfile.user_id == user_id,
    ).first()
    if profile:
        return profile, False
    profile = models.CompanyProfile(
        name_norm=key,
        name_display=firma_name,
        sync_status="pending",
        user_id=user_id,
    )
    db.add(profile)
    db.flush()
    return profile, True


def _ensure_company_profile(db: Session, app: models.Application) -> None:
    """Create or link CompanyProfile for the application's firma (and zielfirma if HH)."""
    if app.firma:
        profile, _ = _find_or_create_company_profile(db, app.firma, app.user_id)
        app.company_profile_id = profile.id

    if app.is_headhunter and app.zielfirma_bei_hh:
        zprofile, _ = _find_or_create_company_profile(db, app.zielfirma_bei_hh, app.user_id)
        app.target_company_profile_id = zprofile.id


_LINKEDIN_WORK_MODE_RE = re.compile(r'\s*\((?:on-site|onsite|hybrid|remote)\)\s*$', re.IGNORECASE)


def _strip_work_mode_suffix(ort_value: str) -> str:
    """Strip a trailing "(On-site)"/"(Hybrid)"/"(Remote)" suffix -- LinkedIn
    appends this work-mode tag to the location on every job posting it
    imports, and neither Nominatim nor Google's Geocoding API can resolve an
    address with it still attached (confirmed against production data: e.g.
    "Krefeld (Hybrid)" returns zero results, plain "Krefeld" geocodes fine)."""
    return _LINKEDIN_WORK_MODE_RE.sub('', ort_value)


async def _geocode_ort(db: Session, app: models.Application, ort_value: Optional[str], user_id: int) -> None:
    """Geocode `ort`, caching the result in ort_lat/ort_lng for the
    distance-to-job feature (KanbanBoard/ApplicationModal) -- avoids
    re-geocoding on every distance calculation. Callers only invoke this when
    `ort` is actually part of the request (new application, or `ort` present
    in an update payload), not on every save. Best-effort: a geocoding
    failure (or no Maps key + Nominatim miss) just leaves the coordinates
    unset rather than blocking the save."""
    if not ort_value or not ort_value.strip():
        app.ort_lat = None
        app.ort_lng = None
        return
    api_key = _get_maps_api_key(db, user_id)
    coords = await geocode_one(_strip_work_mode_suffix(ort_value), api_key)
    app.ort_lat = coords[0] if coords else None
    app.ort_lng = coords[1] if coords else None


async def _update_drive_distance(db: Session, app: models.Application, user: models.User) -> None:
    """Recompute the cached car-navigation distance/duration from the
    account's home location to `app.ort` (Application.drive_distance_km/
    drive_duration_min — see their docstring in models.py). Callers invoke
    this only when app.ort_lat/lng just changed (via _geocode_ort), not on
    every save. When home_location changes instead, every application's
    cached distance is cleared in bulk (see auth.py's update_profile()) and
    recomputed via backfill_drive_distance() rather than live here, since
    that would mean one routing call per application on a single profile
    save. Best-effort: a routing failure just leaves the cache unset."""
    if app.ort_lat is None or app.ort_lng is None or user.home_lat is None or user.home_lng is None:
        app.drive_distance_km = None
        app.drive_duration_min = None
        return
    api_key = _get_maps_api_key(db, user.id)
    route = await driving_route(user.home_lat, user.home_lng, app.ort_lat, app.ort_lng, api_key)
    app.drive_distance_km = route[0] if route else None
    app.drive_duration_min = route[1] if route else None


async def backfill_ort_geocode(db: Session, user_id: int) -> dict:
    """One-time repair for the distance-to-job feature (KanbanBoard/
    ApplicationModal): _geocode_ort() only ever runs when `ort` is actually
    part of a create/update request, so any application whose `ort` was set
    before v4.6.23 introduced ort_lat/ort_lng (or hasn't been touched since)
    is stuck with no cached coordinates forever -- silently showing no
    distance even once the account's home_location is set, since nothing
    ever re-triggers the geocode for an untouched row. Paced at ~1
    request/sec between calls (Nominatim's free usage policy caps lookups
    at that rate; harmless extra latency if a Google Maps key is configured
    instead, see _get_maps_api_key())."""
    import asyncio

    api_key = _get_maps_api_key(db, user_id)
    apps = db.query(models.Application).filter(
        models.Application.user_id == user_id,
        models.Application.ort.isnot(None),
        models.Application.ort != "",
        models.Application.ort_lat.is_(None),
    ).all()

    updated = 0
    errors: list[str] = []
    for i, app in enumerate(apps):
        if i > 0:
            await asyncio.sleep(1)
        try:
            coords = await geocode_one(_strip_work_mode_suffix(app.ort), api_key)
        except Exception as e:
            errors.append(f"{app.firma}: {e}")
            continue
        if coords:
            app.ort_lat, app.ort_lng = coords
            updated += 1

    db.commit()
    return {"total": len(apps), "updated": updated, "errors": errors}


async def backfill_drive_distance(db: Session, user_id: int) -> dict:
    """One-time repair for the distance-to-job feature (KanbanBoard/
    ApplicationModal): recomputes drive_distance_km/drive_duration_min for
    every application that has ort_lat/lng but no cached driving distance
    yet -- either because it was never computed (created before this
    feature, or before backfill_ort_geocode() filled in ort_lat/lng), or
    because auth.py's update_profile() just cleared every application's
    cache after home_location changed. Paced at ~1 request/sec between
    calls, same reasoning as backfill_ort_geocode()."""
    import asyncio

    user = db.query(models.User).filter_by(id=user_id).first()
    if not user or user.home_lat is None or user.home_lng is None:
        return {"total": 0, "updated": 0, "errors": []}

    api_key = _get_maps_api_key(db, user_id)
    apps = db.query(models.Application).filter(
        models.Application.user_id == user_id,
        models.Application.ort_lat.isnot(None),
        models.Application.ort_lng.isnot(None),
        models.Application.drive_distance_km.is_(None),
    ).all()

    updated = 0
    errors: list[str] = []
    for i, app in enumerate(apps):
        if i > 0:
            await asyncio.sleep(1)
        try:
            route = await driving_route(user.home_lat, user.home_lng, app.ort_lat, app.ort_lng, api_key)
        except Exception as e:
            errors.append(f"{app.firma}: {e}")
            continue
        if route:
            app.drive_distance_km, app.drive_duration_min = route
            updated += 1

    db.commit()
    return {"total": len(apps), "updated": updated, "errors": errors}


router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("/", response_model=List[schemas.ApplicationListItem])
def list_applications(
    main_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    company_profile_id: Optional[int] = Query(None),
    show_rejected: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Application).filter(models.Application.user_id == current_user.id)

    if main_status:
        q = q.filter(models.Application.main_status == main_status)

    if not show_rejected:
        q = q.filter(models.Application.main_status != "rejected")

    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                models.Application.firma.ilike(term),
                models.Application.rolle.ilike(term),
                models.Application.quelle.ilike(term),
                models.Application.zielfirma_bei_hh.ilike(term),
            )
        )

    if company_profile_id:
        # Matches by FK, not by the free-text firma/zielfirma_bei_hh columns
        # above — those can drift from the linked CompanyProfile's name
        # (different spelling, abbreviation, sync source), which previously
        # made "show this company's applications" (from the Companies view)
        # silently miss applications that are correctly linked but whose
        # firma text isn't a substring match for the company's display name.
        q = q.filter(
            or_(
                models.Application.company_profile_id == company_profile_id,
                models.Application.target_company_profile_id == company_profile_id,
            )
        )

    latest_event = (
        db.query(
            models.Event.application_id,
            func.max(models.Event.created_at).label("latest_activity"),
        )
        .group_by(models.Event.application_id)
        .subquery()
    )
    q = q.outerjoin(latest_event, models.Application.id == latest_event.c.application_id)
    apps = q.order_by(
        func.coalesce(latest_event.c.latest_activity, models.Application.datum_bewerbung).desc()
    ).all()

    if apps:
        today = date.today()
        app_ids = [a.id for a in apps]

        max_event_dates = dict(
            db.query(models.Event.application_id, func.max(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                models.Event.datum <= today,
            )
            .group_by(models.Event.application_id)
            .all()
        )

        # Calendar events (gcal/icloud_cal) represent scheduled appointments and
        # should be treated as interview dates — same logic as PDF Terminübersicht.
        _is_interview = or_(
            models.Event.typ == "gespräch",
            models.Event.source.in_(["gcal", "icloud_cal"]),
        )

        next_interviews = dict(
            db.query(models.Event.application_id, func.min(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                _is_interview,
                models.Event.datum > today,
            )
            .group_by(models.Event.application_id)
            .all()
        )

        last_interviews = dict(
            db.query(models.Event.application_id, func.max(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                _is_interview,
                models.Event.datum <= today,
            )
            .group_by(models.Event.application_id)
            .all()
        )

        earliest_bewerbung_events = dict(
            db.query(models.Event.application_id, func.min(models.Event.datum))
            .filter(
                models.Event.application_id.in_(app_ids),
                models.Event.typ == "bewerbung",
            )
            .group_by(models.Event.application_id)
            .all()
        )

        fixed_any = False
        for app in apps:
            if app.datum_bewerbung is None:
                eb = earliest_bewerbung_events.get(app.id)
                if eb:
                    app.datum_bewerbung = eb
                    fixed_any = True
                    add_audit(db, "update", "system", app_id=app.id,
                              field="datum_bewerbung", old_value=None, new_value=str(eb),
                              reason_key="date_from_earliest_event",
                              user_id=current_user.id)
            # Compute ghosting from DB letztes_update BEFORE overwriting it in-memory.
            # A "Bewerbung eingereicht" event with datum=today (set by sync) would
            # otherwise push letztes_update to today and suppress ghosting.
            app._ghosting_override = app.ghosting
            md = max_event_dates.get(app.id)
            if md:
                app.letztes_update = md
            app.naechster_schritt = _compute_naechster_schritt(
                app,
                next_interviews.get(app.id),
                last_interviews.get(app.id),
                today,
            )
        if fixed_any:
            db.commit()

    # Attach company website + display name for logo display and name override
    cp_ids = {a.company_profile_id for a in apps if a.company_profile_id}
    tcp_ids = {a.target_company_profile_id for a in apps if a.target_company_profile_id}
    all_ids = cp_ids | tcp_ids
    if all_ids:
        profiles = (
            db.query(models.CompanyProfile.id, models.CompanyProfile.website, models.CompanyProfile.name_display)
            .filter(models.CompanyProfile.id.in_(all_ids))
            .all()
        )
        website_map = {p.id: p.website for p in profiles}
        name_map = {p.id: p.name_display for p in profiles}
        for a in apps:
            a.company_website = website_map.get(a.company_profile_id)
            a.target_company_website = website_map.get(a.target_company_profile_id)
            a.company_name_display = name_map.get(a.company_profile_id)
            a.target_company_name_display = name_map.get(a.target_company_profile_id)

    return apps


@router.get("/stats", response_model=schemas.StatsResponse)
def get_stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    all_apps = db.query(models.Application).filter(models.Application.user_id == current_user.id).all()
    total = len(all_apps)
    rejected = sum(1 for a in all_apps if a.main_status == "rejected")
    active = total - rejected

    by_status: dict = {}
    for a in all_apps:
        key = a.main_status
        by_status[key] = by_status.get(key, 0) + 1

    return schemas.StatsResponse(
        total=total,
        active=active,
        rejected=rejected,
        by_status=by_status,
    )


@router.get("/ai-assess-all")
async def ai_assess_all(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    import asyncio
    from app.models import AiSettings
    from app.ai.tasks import assess_application
    from app.ai.provider import AINotConfigured, AIRateLimited, AIBadRequest

    cfg = db.query(AiSettings).first()
    # Throttle: Gemini free tier = 15 RPM, Groq = 30 RPM — use 5s gap to stay safe
    provider_id = (cfg.provider if cfg else "") or ""
    delay_s = 5.0 if provider_id in ("gemini", "groq") else 1.0

    # Both cached on the user row (extracted/scraped once at upload/sync
    # time, not per assessment) — see User.cv_extracted_text's docstring in
    # models.py for why re-extracting per assessment was a real problem.
    cv_text = current_user.cv_extracted_text
    linkedin_text = current_user.linkedin_profile_text

    async def _stream():
        apps = (
            db.query(models.Application)
            .options(joinedload(models.Application.events))
            .filter(models.Application.main_status != "rejected")
            .all()
        )
        total = len(apps)
        updated = 0
        errors: list[str] = []
        yield f"data: {json.dumps({'status': 'start', 'total': total})}\n\n"
        for i, app in enumerate(apps):
            if i > 0:
                await asyncio.sleep(delay_s)
            try:
                old_color = app.ai_color
                result = await assess_application(db, app, current_user.ui_language, cv_text, linkedin_text)
                app.ai_color = result["color"]
                app.ai_next_step = result["next_step"]
                app.ai_reasoning = result.get("reasoning", "")
                app.ai_assessed_at = datetime.utcnow()
                if str(old_color or "") != str(app.ai_color or ""):
                    add_audit(db, "update", "user", app_id=app.id,
                              field="ai_color", old_value=old_color, new_value=app.ai_color,
                              reason_key="ai_assessment_with_reason" if app.ai_reasoning else "ai_assessment",
                              reason_params={"reasoning": app.ai_reasoning[:200]} if app.ai_reasoning else None,
                              user_id=current_user.id)
                db.commit()
                updated += 1
                yield f"data: {json.dumps({'status': 'progress', 'done': i + 1, 'total': total, 'firma': app.firma})}\n\n"
            except (AINotConfigured, AIRateLimited, AIBadRequest) as e:
                errors.append(str(e))
                yield f"data: {json.dumps({'status': 'progress', 'done': i + 1, 'total': total, 'firma': app.firma, 'error': str(e)})}\n\n"
                break
            except Exception as e:
                errors.append(f"#{app.id} {app.firma}: {e}")
                yield f"data: {json.dumps({'status': 'progress', 'done': i + 1, 'total': total, 'firma': app.firma, 'error': str(e)})}\n\n"
        db.commit()
        yield f"data: {json.dumps({'status': 'done', 'updated': updated, 'errors': errors})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/extract-from-linkedin-url")
async def extract_from_linkedin_url(
    payload: schemas.ExtractFromUrlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if "linkedin.com" not in payload.url:
        raise api_error(400, ErrorKey.APPLICATION_LINKEDIN_URL_REQUIRED, "Bitte einen LinkedIn-Job-Link angeben.")

    from app.linkedin_job_description import load_job_description
    from app.ai.tasks import extract_application_from_text
    from app.ai.provider import AINotConfigured, AIRateLimited, AIBadRequest
    from app.routers.sync_company import _run_sync_batch

    try:
        page_data = await load_job_description(payload.url, db)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        result = await extract_application_from_text(db, page_data["description"])
    except AINotConfigured as e:
        raise HTTPException(400, str(e))
    except AIRateLimited:
        raise api_error(429, ErrorKey.AI_RATE_LIMIT, "Rate-Limit des KI-Anbieters erreicht — bitte in 30–60 Sekunden nochmal versuchen.")
    except AIBadRequest as e:
        raise HTTPException(400, str(e))

    # The posting company shown in the LinkedIn page header is more reliable than
    # whatever the AI inferred from the (often anonymized) description text —
    # e.g. headhunter postings describe the target company without naming it.
    scraped_company = (page_data.get("company") or "").strip()
    if scraped_company:
        result["firma"] = scraped_company

    result["stellenanzeige_url"] = payload.url
    result["company_profile_id"] = None
    if result.get("firma"):
        profile, created = _find_or_create_company_profile(db, result["firma"], current_user.id)
        db.commit()
        result["company_profile_id"] = profile.id
        result["firma"] = profile.name_display or result["firma"]
        if created:
            background_tasks.add_task(_run_sync_batch, [profile.id])

    return result


@router.get("/{app_id}", response_model=schemas.ApplicationRead)
def get_application(app_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")
    for cp_id, attr_name, attr_target in [
        (app.company_profile_id, "company_name_display", "company_website"),
        (app.target_company_profile_id, "target_company_name_display", "target_company_website"),
    ]:
        if cp_id:
            cp = db.get(models.CompanyProfile, cp_id)
            if cp:
                setattr(app, attr_name, cp.name_display)
                setattr(app, attr_target, cp.website)
    return app


@router.post("/", response_model=schemas.ApplicationRead, status_code=201)
async def create_application(
    payload: schemas.ApplicationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump()
    skip_linkedin_sync = data.pop("created_from_linkedin")
    _validate_salary_pair(data.get("salary_expectation_min"), data.get("salary_expectation_max"), "Gehaltsvorstellung")
    _validate_salary_pair(data.get("salary_budget_min"), data.get("salary_budget_max"), "Budget")
    for slot, label in (
        ("salary_expectation_min", "Gehaltsvorstellung (min)"), ("salary_expectation_max", "Gehaltsvorstellung (max)"),
        ("salary_budget_min", "Budget (min)"), ("salary_budget_max", "Budget (max)"),
    ):
        _validate_salary_breakdown(data.get(f"{slot}_fixed"), data.get(f"{slot}_bonus"), data.get(slot), label)
    app = models.Application(**data, user_id=current_user.id)
    app.letztes_update = data.get("datum_bewerbung") or date.today()
    await _geocode_ort(db, app, app.ort, current_user.id)
    await _update_drive_distance(db, app, current_user)
    db.add(app)
    db.flush()  # get app.id before creating event
    _ensure_company_profile(db, app)
    event = models.Event(
        application_id=app.id,
        typ="bewerbung",
        datum=app.datum_bewerbung or date.today(),
        titel="Bewerbung eingereicht",
        user_id=current_user.id,
    )
    db.add(event)
    db.flush()
    add_audit(db, "create", "user", app_id=app.id,
              new_value=f"{app.firma} – {app.rolle}", user_id=current_user.id)
    add_audit(db, "create", "user", app_id=app.id, event_id=event.id,
              new_value=event.titel, user_id=current_user.id)
    db.commit()
    db.refresh(app)

    from app.routers.sync_targeted import _do_post_create_sync
    background_tasks.add_task(_do_post_create_sync, app.id, skip_linkedin_sync)

    return app


@router.patch("/{app_id}", response_model=schemas.ApplicationRead)
async def update_application(
    app_id: int,
    payload: schemas.ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")

    update_data = payload.model_dump(exclude_unset=True)

    def _effective(field: str) -> Optional[int]:
        return update_data[field] if field in update_data else getattr(app, field)

    if {"salary_expectation_min", "salary_expectation_max"} & update_data.keys():
        _validate_salary_pair(_effective("salary_expectation_min"), _effective("salary_expectation_max"), "Gehaltsvorstellung")
    if {"salary_budget_min", "salary_budget_max"} & update_data.keys():
        _validate_salary_pair(_effective("salary_budget_min"), _effective("salary_budget_max"), "Budget")

    for slot, label in (
        ("salary_expectation_min", "Gehaltsvorstellung (min)"), ("salary_expectation_max", "Gehaltsvorstellung (max)"),
        ("salary_budget_min", "Budget (min)"), ("salary_budget_max", "Budget (max)"),
    ):
        if {slot, f"{slot}_fixed", f"{slot}_bonus"} & update_data.keys():
            _validate_salary_breakdown(_effective(f"{slot}_fixed"), _effective(f"{slot}_bonus"), _effective(slot), label)

    old_main = app.main_status
    old_sub  = app.sub_status

    # Clear sub_status when switching to a stage that doesn't use it
    if "main_status" in update_data and update_data["main_status"] not in ("hr", "fb"):
        update_data.setdefault("sub_status", None)

    # Record the last active status before rejection so the UI can place the card in the right column
    if update_data.get("main_status") == "rejected" and old_main != "rejected":
        update_data["pre_rejection_status"] = old_main

    # Capture field-level changes before applying them (verbose mode)
    AUDIT_FIELDS = {"firma", "rolle", "zielfirma_bei_hh", "wurde_besetzt_von", "quelle",
                    "datum_bewerbung", "letztes_update", "kommentar", "stellenanzeige_url",
                    "ort", "is_headhunter",
                    "gespraech_1", "gespraech_2", "gespraech_3", "gespraech_4", "gespraech_5",
                    "salary_currency", "salary_expectation_min", "salary_expectation_max",
                    "salary_budget_min", "salary_budget_max",
                    "salary_expectation_min_fixed", "salary_expectation_min_bonus",
                    "salary_expectation_max_fixed", "salary_expectation_max_bonus",
                    "salary_budget_min_fixed", "salary_budget_min_bonus",
                    "salary_budget_max_fixed", "salary_budget_max_bonus",
                    "salary_expectation_company_car", "salary_budget_company_car"}
    for f, v in update_data.items():
        if f in AUDIT_FIELDS:
            old_v = getattr(app, f, None)
            if str(old_v or "") != str(v or ""):
                add_audit(db, "update", "user", app_id=app_id,
                          field=f, old_value=str(old_v or ""), new_value=str(v or ""),
                          user_id=current_user.id)

    # Direct company profile assignment: look up name and skip _ensure_company_profile
    direct_cp_id = update_data.pop("company_profile_id", None)
    direct_tcp_id = update_data.pop("target_company_profile_id", None)

    firma_changed = "firma" in update_data or "zielfirma_bei_hh" in update_data or "is_headhunter" in update_data
    ort_changed = "ort" in update_data
    for field, value in update_data.items():
        setattr(app, field, value)

    if ort_changed:
        await _geocode_ort(db, app, app.ort, current_user.id)
        await _update_drive_distance(db, app, current_user)

    if direct_cp_id is not None:
        # Explizit nach user_id gefiltert statt db.get(): verhindert, dass eine
        # fremde CompanyProfile-ID (von einem anderen Konto) übernommen wird —
        # db.get()/Query.get() umgehen den automatischen Mandanten-Filter.
        cp = db.query(models.CompanyProfile).filter_by(id=direct_cp_id, user_id=current_user.id).first()
        if cp:
            old_firma = app.firma
            app.company_profile_id = cp.id
            app.firma = cp.name_display or cp.name_norm
            if str(old_firma or "") != str(app.firma or ""):
                add_audit(db, "update", "user", app_id=app_id,
                          field="firma", old_value=old_firma, new_value=app.firma,
                          reason_key="company_assignment_changed", user_id=current_user.id)
        firma_changed = False  # profile already set, no need to re-derive
    elif firma_changed:
        _ensure_company_profile(db, app)

    if direct_tcp_id is not None:
        tcp = db.query(models.CompanyProfile).filter_by(id=direct_tcp_id, user_id=current_user.id).first()
        if tcp:
            old_ziel = app.zielfirma_bei_hh
            app.target_company_profile_id = tcp.id
            app.zielfirma_bei_hh = tcp.name_display or tcp.name_norm
            if str(old_ziel or "") != str(app.zielfirma_bei_hh or ""):
                add_audit(db, "update", "user", app_id=app_id,
                          field="zielfirma_bei_hh", old_value=old_ziel, new_value=app.zielfirma_bei_hh,
                          reason_key="company_assignment_changed", user_id=current_user.id)

    new_main = app.main_status
    new_sub  = app.sub_status
    if new_main != old_main or new_sub != old_sub:
        status_event = models.Event(
            application_id=app_id,
            typ="status",
            datum=date.today(),
            titel=_status_label(new_main, new_sub),
            user_id=current_user.id,
        )
        db.add(status_event)
        db.flush()
        add_audit(db, "create", "user", app_id=app_id, event_id=status_event.id,
                  new_value=status_event.titel, user_id=current_user.id)
        if new_main != old_main:
            add_audit(db, "status_change", "user", app_id=app_id,
                      field="main_status", old_value=old_main, new_value=new_main,
                      reason_key="changed_manually", user_id=current_user.id)
        if new_sub != old_sub:
            add_audit(db, "status_change", "user", app_id=app_id,
                      field="sub_status", old_value=old_sub, new_value=new_sub,
                      reason_key="changed_manually", user_id=current_user.id)

    db.commit()
    db.refresh(app)
    return app


@router.delete("/{app_id}", status_code=204)
def delete_application(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")
    add_audit(db, "delete", "user", app_id=app_id,
              old_value=f"{app.firma} – {app.rolle}", user_id=current_user.id)
    db.delete(app)
    db.commit()


# ── AI Assessment ────────────────────────────────────────────────────────
@router.post("/{app_id}/ai-assess")
async def ai_assess_single(
    app_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = (
        db.query(models.Application)
        .options(joinedload(models.Application.events))
        .filter(models.Application.id == app_id)
        .first()
    )
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")
    from app.ai.tasks import assess_application, assess_rejected_application
    from app.ai.provider import AINotConfigured, AIRateLimited, AIBadRequest
    cv_text = current_user.cv_extracted_text
    linkedin_text = current_user.linkedin_profile_text
    try:
        if app.abgesagt:
            result = await assess_rejected_application(db, app, current_user.ui_language, cv_text, linkedin_text)
        else:
            result = await assess_application(db, app, current_user.ui_language, cv_text, linkedin_text)
    except AINotConfigured as e:
        raise HTTPException(400, str(e))
    except AIRateLimited:
        raise api_error(429, ErrorKey.AI_RATE_LIMIT, "Rate-Limit des KI-Anbieters erreicht — bitte in 30–60 Sekunden nochmal versuchen.")
    except AIBadRequest as e:
        raise HTTPException(400, str(e))
    old_color = app.ai_color
    app.ai_color = result["color"]
    app.ai_next_step = result["next_step"]
    app.ai_reasoning = result.get("reasoning", "")
    app.ai_assessed_at = datetime.utcnow()
    if str(old_color or "") != str(app.ai_color or ""):
        add_audit(db, "update", "user", app_id=app.id,
                  field="ai_color", old_value=old_color, new_value=app.ai_color,
                  reason_key="ai_assessment_with_reason" if app.ai_reasoning else "ai_assessment",
                  reason_params={"reasoning": app.ai_reasoning[:200]} if app.ai_reasoning else None,
                  user_id=current_user.id)
    db.commit()
    return result


# ── Events ──────────────────────────────────────────────────────────────
@router.get("/{app_id}/events", response_model=List[schemas.EventRead])
def list_events(app_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Event).filter(models.Event.application_id == app_id).order_by(models.Event.datum.desc()).all()


def _get_owned_application(db: Session, app_id: int, current_user: models.User) -> models.Application:
    """Lädt eine Bewerbung und stellt sicher, dass sie dem aktuellen Konto gehört
    — wichtig für Schreib-Operationen mit einer aus dem Request stammenden
    app_id, da der automatische Mandanten-Filter nur Lesezugriffe absichert."""
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")
    return app


@router.post("/{app_id}/events", response_model=schemas.EventRead, status_code=201)
def add_event(
    app_id: int,
    payload: schemas.EventBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = _get_owned_application(db, app_id, current_user)
    event = models.Event(application_id=app_id, **payload.model_dump(), user_id=current_user.id)
    db.add(event)
    db.flush()
    add_audit(db, "create", "user", app_id=app_id, event_id=event.id,
              new_value=event.titel, user_id=current_user.id)
    # Sync datum_bewerbung when a bewerbung event is added
    if event.typ == "bewerbung" and event.datum:
        app.datum_bewerbung = event.datum
    db.commit()
    db.refresh(event)
    return event


class BulkDeleteEventsBody(BaseModel):
    ids: List[int]


@router.delete("/{app_id}/events/bulk", status_code=200)
def bulk_delete_events(
    app_id: int,
    body: BulkDeleteEventsBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    events = db.query(models.Event).filter(
        models.Event.application_id == app_id,
        models.Event.id.in_(body.ids),
    ).all()
    was_bewerbung = False
    for event in events:
        if event.typ == "bewerbung":
            was_bewerbung = True
        add_audit(db, "delete", "user", app_id=app_id, event_id=event.id,
                  old_value=event.titel, user_id=current_user.id)
        db.delete(event)
    # If any deleted event was a bewerbung event, recalculate datum_bewerbung once
    if was_bewerbung:
        db.flush()
        app = db.query(models.Application).filter(models.Application.id == app_id).first()
        if app:
            remaining = (
                db.query(models.Event)
                .filter(models.Event.application_id == app_id, models.Event.typ == "bewerbung")
                .order_by(models.Event.datum)
                .first()
            )
            app.datum_bewerbung = remaining.datum if remaining else None
    db.commit()
    return {"deleted": len(events)}


@router.delete("/{app_id}/events/{event_id}", status_code=204)
def delete_event(
    app_id: int,
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.application_id == app_id,
    ).first()
    if not event:
        raise api_error(404, ErrorKey.EVENT_NOT_FOUND, "Event nicht gefunden")
    was_bewerbung = event.typ == "bewerbung"
    add_audit(db, "delete", "user", app_id=app_id, event_id=event.id,
              old_value=event.titel, user_id=current_user.id)
    db.delete(event)
    # If the deleted event was a bewerbung event, recalculate datum_bewerbung from remaining events
    if was_bewerbung:
        app = db.query(models.Application).filter(models.Application.id == app_id).first()
        if app:
            remaining = (
                db.query(models.Event)
                .filter(models.Event.application_id == app_id, models.Event.typ == "bewerbung", models.Event.id != event_id)
                .order_by(models.Event.datum)
                .first()
            )
            app.datum_bewerbung = remaining.datum if remaining else None
    db.commit()


@router.patch("/{app_id}/events/{event_id}", response_model=schemas.EventRead)
def update_event(
    app_id: int,
    event_id: int,
    payload: schemas.EventUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.application_id == app_id,
    ).first()
    if not event:
        raise api_error(404, ErrorKey.EVENT_NOT_FOUND, "Event nicht gefunden")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "datum_zeit":
            # Manually entered via the timeline event edit form -- arrives as
            # a naive Europe/Berlin wall-clock reading, not UTC.
            value = _berlin_naive_to_utc_naive(value)
            # No longer an unreviewed noon-backfill placeholder either way --
            # the user just deliberately set a real time or cleared it.
            event.datum_zeit_is_placeholder = None
        old_v = getattr(event, field, None)
        if str(old_v or "") != str(value or ""):
            add_audit(db, "update", "user", app_id=app_id, event_id=event.id,
                      field=field, old_value=old_v, new_value=value, user_id=current_user.id)
        setattr(event, field, value)
    # Sync datum_bewerbung when a bewerbung event date changes
    if event.typ == "bewerbung" and event.datum:
        app = db.query(models.Application).filter(models.Application.id == app_id).first()
        if app:
            app.datum_bewerbung = event.datum
    db.commit()
    db.refresh(event)
    return event


# ── Contacts ─────────────────────────────────────────────────────────────
@router.get("/{app_id}/contacts", response_model=List[schemas.ContactRead])
def list_contacts(app_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    app = _get_owned_application(db, app_id, current_user)
    return app.contacts


@router.post("/{app_id}/contacts", response_model=schemas.ContactRead, status_code=201)
def add_contact(
    app_id: int,
    payload: schemas.ContactBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = _get_owned_application(db, app_id, current_user)
    data = payload.model_dump(exclude={"phones"})
    contact = models.Contact(**data, user_id=current_user.id)
    for p in payload.phones:
        contact.phones.append(models.ContactPhone(number=p.number, type=p.type, user_id=current_user.id))
    db.add(contact)
    db.flush()
    app.contacts.append(contact)
    add_audit(db, "create", "user", app_id=app_id, contact_id=contact.id,
              new_value=contact.display_name, user_id=current_user.id)
    from app.routers.sync_linkedin import attach_linkedin_messages_for_contact
    attach_linkedin_messages_for_contact(db, contact, current_user.id)
    db.commit()
    db.refresh(contact)
    return contact


@router.patch("/{app_id}/contacts/{contact_id}", response_model=schemas.ContactRead)
def update_contact(
    app_id: int,
    contact_id: int,
    payload: schemas.ContactUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = _get_owned_application(db, app_id, current_user)
    contact = next((c for c in app.contacts if c.id == contact_id), None)
    if not contact:
        raise api_error(404, ErrorKey.CONTACT_NOT_FOUND, "Kontakt nicht gefunden")
    for field, value in payload.model_dump(exclude_unset=True, exclude={"phones"}).items():
        old_v = getattr(contact, field, None)
        if str(old_v or "") != str(value or ""):
            add_audit(db, "update", "user", app_id=app_id, contact_id=contact.id,
                      field=field, old_value=old_v, new_value=value, user_id=current_user.id)
        setattr(contact, field, value)
    if payload.phones is not None:
        contact.phones.clear()
        for p in payload.phones:
            contact.phones.append(models.ContactPhone(number=p.number, type=p.type, user_id=current_user.id))
    db.commit()
    db.refresh(contact)
    return contact


@router.put("/{app_id}/contacts/{contact_id}", response_model=schemas.ContactRead)
def link_contact(
    app_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Link an existing contact to an application (no-op if already linked)."""
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise api_error(404, ErrorKey.CONTACT_NOT_FOUND, "Kontakt nicht gefunden")
    if contact not in app.contacts:
        app.contacts.append(contact)
        db.commit()
    db.refresh(contact)
    return contact


class BulkDeleteAppContactsBody(BaseModel):
    ids: List[int]


@router.delete("/{app_id}/contacts/bulk", status_code=200)
def bulk_delete_contacts(
    app_id: int,
    body: BulkDeleteAppContactsBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")
    unlinked = 0
    for contact_id in body.ids:
        contact = next((c for c in app.contacts if c.id == contact_id), None)
        if not contact:
            continue
        _delete_call_events_for_contact(db, app_id, contact, current_user.id)
        # Remove link; delete contact entirely if no other application links remain
        app.contacts.remove(contact)
        db.flush()
        if not contact.applications:
            add_audit(db, "delete", "user", app_id=app_id, contact_id=contact.id,
                      old_value=contact.display_name, user_id=current_user.id)
            db.delete(contact)
        unlinked += 1
    db.commit()
    return {"deleted": unlinked}


@router.delete("/{app_id}/contacts/{contact_id}", status_code=204)
def delete_contact(
    app_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not app:
        raise api_error(404, ErrorKey.APPLICATION_NOT_FOUND, "Bewerbung nicht gefunden")
    contact = next((c for c in app.contacts if c.id == contact_id), None)
    if not contact:
        raise api_error(404, ErrorKey.CONTACT_NOT_FOUND, "Kontakt nicht gefunden")
    _delete_call_events_for_contact(db, app_id, contact, current_user.id)
    # Remove link; delete contact entirely if no other application links remain
    app.contacts.remove(contact)
    db.flush()
    if not contact.applications:
        add_audit(db, "delete", "user", app_id=app_id, contact_id=contact.id,
                  old_value=contact.display_name, user_id=current_user.id)
        db.delete(contact)
    db.commit()


@router.post("/backfill-ort-geocode")
async def backfill_ort_geocode_endpoint(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return await backfill_ort_geocode(db, current_user.id)


@router.post("/backfill-drive-distance")
async def backfill_drive_distance_endpoint(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return await backfill_drive_distance(db, current_user.id)
