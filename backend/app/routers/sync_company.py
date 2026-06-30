"""Company profile sync via Wikidata (Search API + batch SPARQL)."""
import asyncio
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
_SPARQL_BATCH = 40   # Q-IDs per SPARQL query (well under Wikidata's complexity limit)
_LOGO_CONCURRENCY = 3


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


async def _throttled_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    max_retries: int = 4,
    base_delay: float = 5.0,
) -> httpx.Response:
    """GET with retry on 429/503; respects Retry-After header."""
    for attempt in range(max_retries):
        resp = await client.get(url, params=params)
        if resp.status_code in (429, 503):
            retry_after = float(resp.headers.get("Retry-After", base_delay * (2 ** attempt)))
            log.warning("Rate-limit ({}) von {} — warte {:.0f}s", resp.status_code, url, retry_after)
            await asyncio.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"Max retries erreicht für {url}")


async def _wikidata_search_one(client: httpx.AsyncClient, name: str) -> tuple[str, str] | None:
    """Return (qid, description) for the top Wikidata hit, or None."""
    try:
        resp = await _throttled_get(
            client,
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "de",
                "type": "item",
                "format": "json",
                "limit": "1",
            },
        )
        hits = resp.json().get("search", [])
        if hits:
            return hits[0]["id"], hits[0].get("description", "")
    except Exception as e:
        log.debug("Search-API Fehler für '{}': {}", name, e)
    return None


async def _wikidata_sparql_batch(qids: list[str]) -> dict[str, dict]:
    """One SPARQL query for all qids. Returns {qid: field_dict}."""
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
SELECT
  ?company ?hqLabel ?countryLabel ?founded
  (MAX(?emp) AS ?employees)
  (SAMPLE(?site) AS ?website)
  (SAMPLE(?liId) AS ?linkedinId)
  (SAMPLE(?logo) AS ?logo)
  ?industryLabel
WHERE {{
  VALUES ?company {{ {values} }}
  OPTIONAL {{ ?company wdt:P159 ?hq . }}
  OPTIONAL {{ ?company wdt:P17 ?country . }}
  OPTIONAL {{ ?company wdt:P571 ?founded . }}
  OPTIONAL {{ ?company wdt:P1128 ?emp . }}
  OPTIONAL {{ ?company wdt:P856 ?site . }}
  OPTIONAL {{ ?company wdt:P3220 ?liId . }}
  OPTIONAL {{ ?company wdt:P154 ?logo . }}
  OPTIONAL {{ ?company wdt:P452 ?industry . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en" . }}
}}
GROUP BY ?company ?hqLabel ?countryLabel ?founded ?industryLabel
"""
    async with httpx.AsyncClient(timeout=60.0, headers={"User-Agent": _UA}) as client:
        resp = await _throttled_get(
            client,
            "https://query.wikidata.org/sparql",
            params={"query": sparql, "format": "json"},
        )

    result: dict[str, dict] = {}
    for row in resp.json().get("results", {}).get("bindings", []):
        def v(key: str) -> str:
            return row.get(key, {}).get("value", "")

        qid = v("company").split("/")[-1]
        entry: dict = {}
        if v("hqLabel"):
            entry["hq_city"] = v("hqLabel")
        if v("countryLabel"):
            entry["hq_country"] = v("countryLabel")
        if v("website"):
            entry["website"] = v("website")
        if v("logo"):
            entry["logo_url"] = v("logo")
        if v("industryLabel"):
            entry["industry"] = v("industryLabel")
        if v("linkedinId"):
            li = v("linkedinId")
            entry["linkedin_company_url"] = li if li.startswith("http") \
                else f"https://www.linkedin.com/company/{li}"
        if v("employees"):
            try:
                entry["employee_count"] = int(float(re.sub(r"[^\d.]", "", v("employees"))))
            except (ValueError, TypeError):
                pass
        if v("founded"):
            entry["founded_year"] = _parse_year(v("founded"))
        result[qid] = entry

    return result


async def _fetch_logo(url: str, sem: asyncio.Semaphore) -> str | None:
    async with sem:
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
    now = datetime.now(timezone.utc)

    try:
        # Load all profiles
        db = SessionLocal()
        profiles = {
            p.id: p
            for p in db.query(models.CompanyProfile)
                       .filter(models.CompanyProfile.id.in_(profile_ids)).all()
        }
        db.close()

        # Phase 1: Search API → Q-IDs (sequential, 0.3s apart — lenient rate limit)
        qid_map: dict[int, str] = {}       # profile_id → qid
        desc_map: dict[int, str] = {}      # profile_id → description snippet
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA}) as client:
            for pid in profile_ids:
                p = profiles.get(pid)
                if not p:
                    continue
                name = p.name_display or p.name_norm
                _CURRENT_COMPANY = name
                hit = await _wikidata_search_one(client, name)
                if hit:
                    qid_map[pid], desc_map[pid] = hit
                    log.debug("'{}' → {}", name, qid_map[pid])
                else:
                    log.info("Kein Wikidata-Treffer für '{}'", name)
                await asyncio.sleep(1.0)

        # Mark not-found profiles
        db = SessionLocal()
        for pid in profile_ids:
            if pid not in qid_map:
                p = db.query(models.CompanyProfile).get(pid)
                if p:
                    p.sync_status = "done"
                    p.sync_source = "wikidata"
                    p.sync_error = "Kein Wikidata-Eintrag gefunden"
                    p.last_synced_at = now
        db.commit()
        db.close()

        # Phase 2: Batch SPARQL — _SPARQL_BATCH Q-IDs per query
        found_pids = list(qid_map.keys())
        sparql_data: dict[str, dict] = {}  # qid → field dict

        for i in range(0, len(found_pids), _SPARQL_BATCH):
            chunk_pids = found_pids[i:i + _SPARQL_BATCH]
            chunk_qids = [qid_map[pid] for pid in chunk_pids]
            log.info("SPARQL-Batch {}/{}: {} Firmen", i // _SPARQL_BATCH + 1,
                     -(-len(found_pids) // _SPARQL_BATCH), len(chunk_qids))
            try:
                batch_result = await _wikidata_sparql_batch(chunk_qids)
                sparql_data.update(batch_result)
            except Exception as e:
                log.error("SPARQL-Batch Fehler: {}", e)
                # Mark affected profiles as failed
                db = SessionLocal()
                for pid in chunk_pids:
                    p = db.query(models.CompanyProfile).get(pid)
                    if p:
                        p.sync_status = "failed"
                        p.sync_error = f"SPARQL: {e}"[:500]
                        p.last_synced_at = now
                db.commit()
                db.close()
            if i + _SPARQL_BATCH < len(found_pids):
                await asyncio.sleep(5.0)  # pause between SPARQL batches

        # Phase 3: Logo downloads — parallel with semaphore
        sem = asyncio.Semaphore(_LOGO_CONCURRENCY)
        logo_tasks = {}
        for pid in found_pids:
            qid = qid_map[pid]
            logo_url = sparql_data.get(qid, {}).get("logo_url")
            p = profiles.get(pid)
            if logo_url and p and not p.logo_data:
                logo_tasks[pid] = asyncio.create_task(_fetch_logo(logo_url, sem))

        if logo_tasks:
            await asyncio.gather(*logo_tasks.values(), return_exceptions=True)

        # Phase 4: Write all results to DB
        db = SessionLocal()
        for pid in found_pids:
            p = db.query(models.CompanyProfile).get(pid)
            if not p:
                continue
            qid = qid_map[pid]
            data = sparql_data.get(qid, {})

            if desc_map.get(pid) and not p.description:
                p.description = desc_map[pid][:2000]
            if data.get("hq_city"):
                p.hq_city = data["hq_city"][:200]
            if data.get("hq_country"):
                p.hq_country = data["hq_country"][:200]
            if data.get("industry"):
                p.industry = data["industry"][:200]
            if data.get("employee_count"):
                p.employee_count = data["employee_count"]
                p.employee_range = _employee_range(data["employee_count"])
            if data.get("founded_year"):
                p.founded_year = data["founded_year"]
            if data.get("website") and not p.website:
                p.website = data["website"][:500]
            if data.get("linkedin_company_url") and not p.linkedin_company_url:
                p.linkedin_company_url = data["linkedin_company_url"][:500]
            logo_result = logo_tasks.get(pid)
            if logo_result and not logo_result.cancelled():
                try:
                    logo_b64 = logo_result.result()
                    if logo_b64:
                        p.logo_data = logo_b64
                except Exception:
                    pass

            p.sync_source = f"wikidata:{qid}"
            p.sync_status = "done"
            p.sync_error = None
            p.last_synced_at = now
            log.info("Synced '{}' ({}): hq={}/{} emp={} founded={}",
                     p.name_display, qid, data.get("hq_city"), data.get("hq_country"),
                     data.get("employee_count"), data.get("founded_year"))

        db.commit()
        db.close()
        log.info("Firmensync abgeschlossen: {} Firmen", len(profile_ids))

    except Exception as e:
        log.error("Firmensync Fehler: {}", e)
    finally:
        _SYNC_RUNNING = False
        _CURRENT_COMPANY = None
