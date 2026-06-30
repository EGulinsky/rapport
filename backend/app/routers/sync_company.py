"""Company profile sync via Wikidata (Search API + SPARQL)."""
import asyncio
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


# ── Wikidata helpers ──────────────────────────────────────────────────────────

def _employee_range(n: int) -> str:
    for limit, label in ((10, "1-10"), (50, "11-50"), (200, "51-200"), (500, "201-500"),
                         (1000, "501-1000"), (5000, "1001-5000"), (10000, "5001-10000")):
        if n <= limit:
            return label
    return "10001+"


async def _wikidata_fetch(name: str) -> dict:
    """Search Wikidata for a company by name, return normalized field dict."""
    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _UA}) as client:
        # 1. Entity search → Q-ID + description snippet
        search = await client.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "de",
                "type": "item",
                "format": "json",
                "limit": "3",
            },
        )
        search.raise_for_status()
        hits = search.json().get("search", [])
        if not hits:
            return {}

        qid = hits[0]["id"]
        snippet_desc = hits[0].get("description", "")
        log.debug("Wikidata search '{}' → {} ({})", name, qid, snippet_desc)

        # 2. SPARQL → all structured fields in one shot
        sparql = f"""
SELECT
  ?hqLabel ?countryLabel ?founded
  (MAX(?emp) AS ?employees)
  (SAMPLE(?site) AS ?website)
  (SAMPLE(?liId) AS ?linkedinId)
  ?industryLabel
WHERE {{
  BIND(wd:{qid} AS ?company)
  OPTIONAL {{ ?company wdt:P159 ?hq . }}
  OPTIONAL {{ ?company wdt:P17 ?country . }}
  OPTIONAL {{ ?company wdt:P571 ?founded . }}
  OPTIONAL {{ ?company wdt:P1128 ?emp . }}
  OPTIONAL {{ ?company wdt:P856 ?site . }}
  OPTIONAL {{ ?company wdt:P3220 ?liId . }}
  OPTIONAL {{ ?company wdt:P452 ?industry . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en" . }}
}}
GROUP BY ?hqLabel ?countryLabel ?founded ?industryLabel
LIMIT 1
"""
        sparql_resp = await client.get(
            "https://query.wikidata.org/sparql",
            params={"query": sparql, "format": "json"},
        )
        sparql_resp.raise_for_status()
        bindings = sparql_resp.json().get("results", {}).get("bindings", [])
        row = bindings[0] if bindings else {}

        def v(key: str) -> str:
            return row.get(key, {}).get("value", "")

        result: dict = {}

        if snippet_desc:
            result["description"] = snippet_desc
        if v("hqLabel"):
            result["hq_city"] = v("hqLabel")
        if v("countryLabel"):
            result["hq_country"] = v("countryLabel")
        if v("website"):
            result["website"] = v("website")
        if v("linkedinId"):
            li_id = v("linkedinId")
            result["linkedin_company_url"] = (
                li_id if li_id.startswith("http") else f"https://www.linkedin.com/company/{li_id}"
            )
        if v("industryLabel"):
            result["industry"] = v("industryLabel")
        if v("employees"):
            try:
                result["employee_count"] = int(float(re.sub(r"[^\d.]", "", v("employees"))))
            except (ValueError, TypeError):
                pass
        if v("founded"):
            m = re.search(r"\d{4}", v("founded"))
            if m:
                year = int(m.group())
                if 1700 <= year <= 2100:
                    result["founded_year"] = year

        result["_qid"] = qid
        return result


# ── Sync endpoints ────────────────────────────────────────────────────────────

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
                models.CompanyProfile.hq_city.is_(None)
                | models.CompanyProfile.industry.is_(None)
                | models.CompanyProfile.description.is_(None)
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
    profile = db.query(models.CompanyProfile).filter(models.CompanyProfile.id == profile_id).first()
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
                log.error("Sync-Fehler Firma {}: {}", pid, e)
            finally:
                db.close()
            await asyncio.sleep(1.2)  # Wikidata SPARQL: max 1 req/s
    finally:
        _SYNC_RUNNING = False
        _CURRENT_COMPANY = None


async def _sync_one_company(db: Session, profile: models.CompanyProfile):
    name = profile.name_display or profile.name_norm
    try:
        data = await _wikidata_fetch(name)

        if not data:
            profile.sync_status = "done"
            profile.sync_source = "wikidata"
            profile.sync_error = "Kein Wikidata-Eintrag gefunden"
            profile.last_synced_at = datetime.now(timezone.utc)
            db.commit()
            log.info("Wikidata: kein Eintrag für '{}'", name)
            return

        if data.get("hq_city"):
            profile.hq_city = str(data["hq_city"])[:200]
        if data.get("hq_country"):
            profile.hq_country = str(data["hq_country"])[:200]
        if data.get("industry"):
            profile.industry = str(data["industry"])[:200]
        if data.get("employee_count"):
            profile.employee_count = data["employee_count"]
            profile.employee_range = _employee_range(data["employee_count"])
        if data.get("founded_year"):
            profile.founded_year = data["founded_year"]
        if data.get("website") and not profile.website:
            profile.website = str(data["website"])[:500]
        if data.get("linkedin_company_url") and not profile.linkedin_company_url:
            profile.linkedin_company_url = str(data["linkedin_company_url"])[:500]
        if data.get("description") and not profile.description:
            profile.description = str(data["description"])[:2000]

        profile.sync_source = f"wikidata:{data['_qid']}"
        profile.sync_status = "done"
        profile.sync_error = None
        profile.last_synced_at = datetime.now(timezone.utc)
        db.commit()
        log.info("Wikidata synced '{}' ({}): hq={}/{} emp={} founded={}",
                 name, data["_qid"], data.get("hq_city"), data.get("hq_country"),
                 data.get("employee_count"), data.get("founded_year"))

    except httpx.HTTPStatusError as e:
        profile.sync_status = "failed"
        profile.sync_error = f"HTTP {e.response.status_code}: {e.request.url}"
        db.commit()
        log.warning("Wikidata HTTP-Fehler für '{}': {}", name, e)
    except Exception as e:
        profile.sync_status = "failed"
        profile.sync_error = str(e)[:500]
        db.commit()
        log.error("Wikidata Fehler für '{}': {}", name, e)
