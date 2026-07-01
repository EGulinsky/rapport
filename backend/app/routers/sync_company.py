"""Company profile sync: DDG → Wikipedia fallback, Clearbit logo fallback."""
import asyncio
import base64
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models
from app.logger import get_logger

log = get_logger("sync", source="company")

router = APIRouter(prefix="/api/sync/company", tags=["sync_company"])

_SYNC_RUNNING = False
_SYNC_CANCEL = False
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
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


def _clean_query(name: str) -> str:
    """Strip pipe/slash agency suffixes: 'Akkodis | inContext AB' → 'Akkodis'."""
    return re.split(r"\s*[|/]\s*", name)[0].strip()


def _domain_from_url(url: str) -> str | None:
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.") or None
    except Exception:
        return None


# ── Source 1: DuckDuckGo ─────────────────────────────────────────────────────

async def _ddg_fetch(name: str) -> dict:
    query = _clean_query(name)
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA},
                                     follow_redirects=True) as client:
            resp = await client.get(_DDG_URL, params={
                "q": query, "format": "json",
                "no_redirect": "1", "no_html": "1", "skip_disambig": "1",
            })
    except (httpx.TimeoutException, httpx.RequestError) as e:
        log.warning("DDG: {} für '{}' — Fallback", type(e).__name__, query)
        raise

    if resp.status_code == 429:
        log.warning("DDG: Rate-limit (429) für '{}'", query)
        return {}
    if resp.status_code != 200:
        log.warning("DDG: HTTP {} für '{}'", resp.status_code, query)
        return {}
    if not resp.content:
        log.warning("DDG: leere Antwort für '{}'", query)
        return {}
    try:
        data = resp.json()
    except Exception as e:
        log.warning("DDG: ungültige JSON für '{}' — {} — Anfang: {!r}",
                    query, e, resp.content[:120])
        return {}

    result: dict = {}
    abstract = data.get("AbstractText") or data.get("Abstract") or ""
    if abstract:
        result["description"] = abstract[:2000]
    img = data.get("Image") or ""
    if img:
        result["logo_url"] = img if img.startswith("http") else f"https://duckduckgo.com{img}"

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


# ── Source 2: Wikipedia REST API ─────────────────────────────────────────────

async def _wikipedia_fetch(name: str) -> dict:
    """Search Wikipedia, then fetch page summary. Returns same field dict as DDG."""
    query = _clean_query(name)
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA}) as client:
        # Step 1: find the right page title
        search = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "format": "json", "srlimit": "1"},
        )
        search.raise_for_status()
        hits = search.json().get("query", {}).get("search", [])
        if not hits:
            log.debug("Wikipedia: kein Treffer für '{}'", query)
            return {}

        title = hits[0]["title"]
        # Step 2: fetch structured summary
        summary = await client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
            headers={"User-Agent": _UA},
        )
        if summary.status_code != 200:
            return {}
        data = summary.json()

    result: dict = {}
    if data.get("extract"):
        result["description"] = data["extract"][:2000]
    thumb = (data.get("thumbnail") or {}).get("source") or \
            (data.get("originalimage") or {}).get("source")
    if thumb:
        result["logo_url"] = thumb
    return result


# ── Logo fallbacks ────────────────────────────────────────────────────────────

async def _clearbit_logo(domain: str) -> str | None:
    """Fetch logo from Clearbit by domain. Returns base64 data URI or None."""
    url = f"https://logo.clearbit.com/{domain}"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                ct = resp.headers.get("content-type", "image/png").split(";")[0].strip()
                return f"data:{ct};base64,{base64.b64encode(resp.content).decode()}"
    except Exception:
        pass
    return None


async def _fetch_logo(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA},
                                     follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/png").split(";")[0].strip()
            return f"data:{ct};base64,{base64.b64encode(resp.content).decode()}"
    except Exception as e:
        log.warning("Logo-Download fehlgeschlagen ({}): {}", url, e)
        return None


async def _fetch_logo_with_clearbit_fallback(logo_url: str | None, website: str | None) -> str | None:
    """Try logo_url first, then Clearbit if domain known."""
    if logo_url:
        result = await _fetch_logo(logo_url)
        if result:
            return result
    if website:
        domain = _domain_from_url(website)
        if domain:
            result = await _clearbit_logo(domain)
            if result:
                log.debug("Logo via Clearbit: {}", domain)
                return result
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
    company_ids: list[int] | None = Query(default=None),
):
    global _SYNC_RUNNING
    if _SYNC_RUNNING:
        return {"started": False, "count": 0, "message": "Sync already running"}

    def _scoped(q):
        return q.filter(models.CompanyProfile.id.in_(company_ids)) if company_ids else q

    if force:
        _scoped(db.query(models.CompanyProfile)).update(
            {"sync_status": "pending", "sync_error": None}, synchronize_session=False
        )
        db.commit()

    pending = _scoped(db.query(models.CompanyProfile)).filter(
        models.CompanyProfile.sync_status == "pending"
    ).all()

    if not force:
        incomplete = _scoped(db.query(models.CompanyProfile)).filter(
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


@router.post("/cancel")
def cancel_sync():
    global _SYNC_CANCEL
    _SYNC_CANCEL = True
    return {"ok": True}


@router.post("/reset-lock")
def reset_lock():
    global _SYNC_RUNNING, _SYNC_CANCEL, _CURRENT_COMPANY
    _SYNC_RUNNING = False
    _SYNC_CANCEL = False
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
    global _SYNC_RUNNING, _SYNC_CANCEL, _CURRENT_COMPANY
    _SYNC_RUNNING = True
    _SYNC_CANCEL = False
    _CURRENT_COMPANY = None
    now = datetime.now(timezone.utc)

    try:
        for pid in profile_ids:
            if _SYNC_CANCEL:
                log.info("Firmensync abgebrochen nach {} Firmen", profile_ids.index(pid))
                break
            db = SessionLocal()
            p = db.query(models.CompanyProfile).get(pid)
            if not p:
                db.close()
                continue

            name = p.name_display or p.name_norm
            _CURRENT_COMPANY = name

            try:
                # Source 1: DDG
                data: dict = {}
                source = "duckduckgo"
                try:
                    data = await _ddg_fetch(name)
                except (httpx.TimeoutException, httpx.RequestError):
                    pass  # fall through to Wikipedia

                # Source 2: Wikipedia fallback when DDG gave nothing useful
                if not data.get("description"):
                    log.debug("Wikipedia-Fallback für '{}'", name)
                    try:
                        wiki = await _wikipedia_fetch(name)
                        if wiki:
                            # merge: wiki fills gaps, doesn't overwrite DDG data
                            for k, v in wiki.items():
                                data.setdefault(k, v)
                            if wiki.get("description"):
                                source = "wikipedia" if not data.get("description") else "duckduckgo+wikipedia"
                    except Exception as e:
                        log.warning("Wikipedia-Fallback Fehler für '{}': {}", name, e)

                # Apply text fields
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

                # Logo: try data source URL, then Clearbit fallback
                if not p.logo_data:
                    website = data.get("website") or p.website
                    logo_b64 = await _fetch_logo_with_clearbit_fallback(
                        data.get("logo_url"), website
                    )
                    if logo_b64:
                        p.logo_data = logo_b64

                p.sync_source = source
                p.sync_status = "done"
                p.sync_error = None
                p.last_synced_at = now
                log.info("Synced '{}' ({}): desc={} logo={} hq={} emp={}",
                         name, source,
                         bool(p.description), bool(p.logo_data),
                         data.get("hq_city"), data.get("employee_count"))

            except httpx.TimeoutException:
                # Both DDG and Wikipedia timed out — retry next run
                p.sync_status = "pending"
                p.sync_error = None
            except Exception as e:
                log.opt(exception=True).error("Sync-Fehler für '{}': {} ({})",
                                              name, e, type(e).__name__)
                p.sync_status = "failed"
                p.sync_error = f"{type(e).__name__}: {e}"[:500]
                p.last_synced_at = now

            db.commit()
            db.close()
            await asyncio.sleep(0.5)

        log.info("Firmensync abgeschlossen: {} Firmen", len(profile_ids))

    except Exception as e:
        log.opt(exception=True).error("Firmensync Fehler: {} ({})", e, type(e).__name__)
    finally:
        _SYNC_RUNNING = False
        _SYNC_CANCEL = False
        _CURRENT_COMPANY = None
