"""Company profile background sync via AI."""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync/company", tags=["sync_company"])

_SYNC_RUNNING = False
_CURRENT_COMPANY: str | None = None


@router.get("/status")
def company_sync_status(db: Session = Depends(get_db)):
    profiles = db.query(models.CompanyProfile).all()
    pending = [p for p in profiles if p.sync_status == "pending"]
    done = [p for p in profiles if p.sync_status == "done"]
    failed = [p for p in profiles if p.sync_status == "failed"]
    return {
        "running": _SYNC_RUNNING,
        "current_company": _CURRENT_COMPANY,
        "pending": len(pending),
        "done": len(done),
        "failed": len(failed),
        "profiles": [
            {
                "id": p.id,
                "name_display": p.name_display,
                "sync_status": p.sync_status,
                "sync_error": p.sync_error,
                "last_synced_at": p.last_synced_at.isoformat() if p.last_synced_at else None,
            }
            for p in profiles
        ],
    }


@router.post("/run")
async def company_sync_run(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    global _SYNC_RUNNING
    if _SYNC_RUNNING:
        return {"started": False, "count": 0, "message": "Sync already running"}

    pending = db.query(models.CompanyProfile).filter(
        models.CompanyProfile.sync_status == "pending"
    ).limit(10).all()

    # No pending left → fresh trigger: reset all done profiles and start over
    if not pending:
        db.query(models.CompanyProfile).filter(
            models.CompanyProfile.sync_status == "done"
        ).update({"sync_status": "pending"})
        db.commit()
        pending = db.query(models.CompanyProfile).filter(
            models.CompanyProfile.sync_status == "pending"
        ).limit(10).all()

    count = len(pending)
    if count == 0:
        return {"started": False, "count": 0, "message": "No pending profiles"}

    ids = [p.id for p in pending]
    background_tasks.add_task(_run_sync_batch, ids)
    return {"started": True, "count": count}


@router.post("/reset-lock")
def reset_lock():
    global _SYNC_RUNNING, _CURRENT_COMPANY
    _SYNC_RUNNING = False
    _CURRENT_COMPANY = None
    return {"ok": True}


@router.post("/reset-failed")
def reset_failed(db: Session = Depends(get_db)):
    """Reset all failed profiles back to pending."""
    updated = db.query(models.CompanyProfile).filter(
        models.CompanyProfile.sync_status == "failed"
    ).all()
    for p in updated:
        p.sync_status = "pending"
        p.sync_error = None
    db.commit()
    return {"reset": len(updated)}


@router.post("/profiles/{profile_id}/reset")
def reset_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(models.CompanyProfile).filter(models.CompanyProfile.id == profile_id).first()
    if not profile:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.sync_status = "pending"
    profile.sync_error = None
    db.commit()
    return {"ok": True, "id": profile_id}


async def _run_sync_batch(profile_ids: list[int]):
    global _SYNC_RUNNING, _CURRENT_COMPANY
    _SYNC_RUNNING = True
    _CURRENT_COMPANY = None
    try:
        for pid in profile_ids:
            db = SessionLocal()
            try:
                profile = db.query(models.CompanyProfile).filter(models.CompanyProfile.id == pid).first()
                if not profile:
                    continue
                _CURRENT_COMPANY = profile.name_display or profile.name_norm
                await _sync_one_company(db, profile)
            except Exception as e:
                logger.error("Sync error for profile %s: %s", pid, e)
            finally:
                db.close()
            await asyncio.sleep(0.5)
    finally:
        _SYNC_RUNNING = False
        _CURRENT_COMPANY = None


async def _sync_one_company(db: Session, profile: models.CompanyProfile):
    """Fetch company data via AI and update profile fields."""
    try:
        from app.ai.provider import complete, AINotConfigured

        name = profile.name_display or profile.name_norm

        result = await complete(
            db,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein Firmendaten-Lookup-Service. "
                        "Gib bekannte Fakten über Unternehmen als JSON zurück. "
                        "Wenn du ein Feld nicht kennst, gib null zurück. Erfinde keine Daten."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f'Gib Firmendaten für "{name}" als JSON zurück:\n'
                        "{\n"
                        '  "hq_city": "Hauptsitz-Stadt oder null",\n'
                        '  "hq_country": "Land auf Deutsch (z.B. Deutschland, USA) oder null",\n'
                        '  "industry": "Branche auf Deutsch (z.B. Softwareentwicklung, Maschinenbau) oder null",\n'
                        '  "company_type": "eines von: startup|kmu|konzern|beratung|headhunter|nonprofit|public|other oder null",\n'
                        '  "employee_range": "z.B. 1001-5000 oder 10001-50000 oder null",\n'
                        '  "founded_year": "Gründungsjahr als Zahl oder null",\n'
                        '  "website": "Haupt-Website-URL oder null",\n'
                        '  "description": "2-3 Sätze Beschreibung auf Deutsch oder null"\n'
                        "}"
                    ),
                },
            ],
            json_mode=True,
            max_tokens=512,
        )

        if result.get("hq_city"):
            profile.hq_city = str(result["hq_city"])[:200]
        if result.get("hq_country"):
            profile.hq_country = str(result["hq_country"])[:200]
        if result.get("industry"):
            profile.industry = str(result["industry"])[:200]
        if result.get("company_type") and result["company_type"] in (
            "startup", "kmu", "konzern", "beratung", "headhunter", "nonprofit", "public", "other"
        ):
            profile.company_type = result["company_type"]
        if result.get("employee_range"):
            profile.employee_range = str(result["employee_range"])[:100]
        if result.get("founded_year"):
            try:
                year = int(result["founded_year"])
                if 1800 <= year <= 2100:
                    profile.founded_year = year
            except (TypeError, ValueError):
                pass
        if result.get("website"):
            profile.website = str(result["website"])[:500]
        if result.get("description"):
            profile.description = str(result["description"])[:2000]

        profile.sync_source = "ai"
        profile.sync_status = "done"
        profile.sync_error = None
        profile.last_synced_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("AI-synced company profile %s: %s", profile.id, profile.name_display)

    except AINotConfigured as e:
        profile.sync_status = "failed"
        profile.sync_error = f"KI nicht konfiguriert: {e}"
        db.commit()
    except Exception as e:
        logger.error("Failed to sync company %s: %s", profile.id, e)
        profile.sync_status = "failed"
        profile.sync_error = str(e)[:500]
        db.commit()
