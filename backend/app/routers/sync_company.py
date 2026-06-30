"""Company profile sync via DuckDuckGo Instant Answer API."""
import base64
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models
from app.logger import get_logger

log = get_logger("sync", source="company")

router = APIRouter(prefix="/api/sync/company", tags=["sync_company"])

_SYNC_RUNNING = False
_CURRENT_COMPANY: str | None = None

_UA = "JobTracker/1.0 (personal job-application tracker; contact: private)"
_DDG_URL = "https://api.duckduckgo.com/"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _employee_range(n: int) -> str:
    for limit, label in ((10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
                         (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000")):
        if n <= limit:
            return label
    return "10001+"


def _parse_year(s: str) -> int | None:
    m = re.search(r"\d{4}", s)
    if m:
        y = int(m.group())
        return y if 1700 <= y <= 2100 else None
    return None


def _parse_employee_count(s: str) -> int | None:
    # "123,456" / "123.456" / "~50,000" / "50000"
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


async def _ddg_fetch(name: str) -> dict:
    """Query DuckDuckGo Instant Answer API. Returns normalized field dict."""
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA},
                                 follow_redirects=True) as client:
        resp = await client.get(_DDG_URL, params={
            "q": name,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
            "skip_disambig": "1",
        })
        resp.raise_for_status()

    data = resp.json()
    result: dict = {}

    abstract = data.get("AbstractText") or data.get("Abstract") or ""
    if abstract:
        result["description"] = abstract[:2000]

    img = data.get("Image") or ""
    if img:
        result["logo_url"] = img if img.startswith("http") else f"https://duckduckgo.com{img}"

    # Infobox: list of {label, value} items from Wikipedia infobox
    for item in (data.get("Infobox") or {}).get("content", []):
        label = (item.get("label") or "").lower()
        value = str(item.get("value") or "").strip()
        if not value or value == "None":
            continue
        if any(k in label for k in ("headquarter", "hauptsitz", "location", "sitz")):
            result.setdefault("hq_city", value)
        elif any(k in label for k in ("founded", "gegründet", "formation")):
            result.setdefault("founded_year", _parse_year(value))
        elif any(k in label for k in ("employee", "mitarbeiter", "staff", "personnel")):
            n = _parse_employee_count(value)
            if n:
                result.setdefault("employee_count", n)
        elif any(k in label for k in ("industry", "branche", "type", "sector")):
            result.setdefault("industry", value)
        elif any(k in label for k in ("website", "webseite", "url", "homepage")):
            result.setdefault("website", value)

    return result


async def _fetch_logo(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA},
                                     follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/png").split(";")[0].strip()
            return f"data:{ct};base64,{base64.b64encode(resp.content).decode()}"
    except Exception as e:
        log.debug("Logo-Download fehlgeschlagen ({}): {}", url, e)
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def company_sync_status(db: Session = Depends(get_db)):
    profiles = db.query(models.CompanyProfile).all()
    pending = [p for p in profiles if p.sync_status == "pending"]
    done    = [p for p in profiles if p.sync_status == "done"]
    failed  = [p for p in profiles if p.sync_status == "failed"]
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
    force: bool = False,
):
    global _SYNC_RUNNING
    if _SYNC_RUNNING:
        return {"started": False, "count": 0, "message": "Sync already running"}

    if force:
        db.query(models.CompanyProfile).update({"sync_status": "pending", "sync_error": None})
        db.commit()

    pending = db.query(models.CompanyProfile).filter(
        models.CompanyProfile.sync_status == "pending"
    ).all()

    if not force:
        incomplete = db.query(models.CompanyProfile).filter(
            models.CompanyProfile.sync_status == "done",
            (
                models.CompanyProfile.description.is_(None)
                | models.CompanyProfile.logo_data.is_(None)
            ),
        ).all()
        seen = {p.id for p in pending}
        for p in incomplete:
            if p.id not in seen:
                p.sync_status = "pending"
                pending.append(p)
        if incomplete:
            db.commit()

    count = len(pending)
    if count == 0:
        return {"started": False, "count": 0, "message": "Kein Sync nötig."}

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
    from fastapi import HTTPException
    profile = db.query(models.CompanyProfile).filter(
        models.CompanyProfile.id == profile_id
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.sync_status = "pending"
    profile.sync_error = None
    db.commit()
    return {"ok": True, "id": profile_id}


# ── Batch runner ──────────────────────────────────────────────────────────────

async def _run_sync_batch(profile_ids: list[int]):
    global _SYNC_RUNNING, _CURRENT_COMPANY
    _SYNC_RUNNING = True
    _CURRENT_COMPANY = None
    now = datetime.now(timezone.utc)

    try:
        for pid in profile_ids:
            db = SessionLocal()
            p = db.query(models.CompanyProfile).get(pid)
            if not p:
                db.close()
                continue

            name = p.name_display or p.name_norm
            _CURRENT_COMPANY = name
            log.debug("DDG-Sync: '{}'", name)

            try:
                data = await _ddg_fetch(name)

                if data.get("description") and not p.description:
                    p.description = data["description"]
                if data.get("hq_city") and not p.hq_city:
                    p.hq_city = data["hq_city"][:200]
                if data.get("industry") and not p.industry:
                    p.industry = data["industry"][:200]
                if data.get("employee_count") and not p.employee_count:
                    p.employee_count = data["employee_count"]
                    p.employee_range = _employee_range(data["employee_count"])
                if data.get("founded_year") and not p.founded_year:
                    p.founded_year = data["founded_year"]
                if data.get("website") and not p.website:
                    p.website = data["website"][:500]

                if data.get("logo_url") and not p.logo_data:
                    logo_b64 = await _fetch_logo(data["logo_url"])
                    if logo_b64:
                        p.logo_data = logo_b64

                p.sync_source = "duckduckgo"
                p.sync_status = "done"
                p.sync_error = None
                p.last_synced_at = now
                log.info("Synced '{}': desc={} logo={} hq={} emp={}",
                         name,
                         bool(data.get("description")),
                         bool(data.get("logo_url")),
                         data.get("hq_city"),
                         data.get("employee_count"))

            except Exception as e:
                log.error("DDG-Fehler für '{}': {}", name, e)
                p.sync_status = "failed"
                p.sync_error = str(e)[:500]
                p.last_synced_at = now

            db.commit()
            db.close()

        log.info("Firmensync abgeschlossen: {} Firmen", len(profile_ids))

    except Exception as e:
        log.error("Firmensync Fehler: {}", e)
    finally:
        _SYNC_RUNNING = False
        _CURRENT_COMPANY = None
