"""Company profile sync: Wikidata (primary, Search API + batch SPARQL) → LinkedIn company page (fallback), Clearbit logo fallback."""
import asyncio
import base64
import json
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


def _clean_query(name: str) -> str:
    """Strip pipe/slash agency suffixes: 'Akkodis | inContext AB' → 'Akkodis'."""
    return re.split(r"\s*[|/]\s*", name)[0].strip()


def _domain_from_url(url: str) -> str | None:
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.") or None
    except Exception:
        return None


def _classify_company_type(employee_count: int | None, founded_year: int | None) -> str | None:
    """Grobe Heuristik aus Mitarbeiterzahl + Gründungsjahr — nur wenn frische Daten vorliegen."""
    if not employee_count:
        return None
    now_year = datetime.now(timezone.utc).year
    young = founded_year is not None and (now_year - founded_year) <= 10
    if employee_count >= 5000:
        return "konzern"
    if employee_count <= 200 and young:
        return "startup"
    if employee_count <= 500:
        return "kmu"
    return "konzern"


# ── Source 1: Wikidata (Search API + batch SPARQL) ───────────────────────────

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
                "search": _clean_query(name),
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
        log.debug("Wikidata Search-API Fehler für '{}': {}", name, e)
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


# ── Source 2: LinkedIn company page (fallback für Wikidata-Fehltreffer) ─────

async def _get_linkedin_context():
    """Startet einen Playwright-Browser mit der gespeicherten LinkedIn-Session.

    Nutzt nur eine bestehende, gültige Session (kein Login-Versuch) — Company-Sync
    soll nicht in den 2FA-Flow der Job-Synchronisation eingreifen. Gibt None
    zurück, wenn kein LinkedIn-Sync konfiguriert ist oder keine Session existiert.
    """
    db = SessionLocal()
    try:
        cfg = db.query(models.LinkedInSync).first()
        if not cfg or not cfg.session_cookies:
            return None
        cookies_raw = cfg.session_cookies
    finally:
        db.close()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.debug("LinkedIn-Fallback: Playwright nicht installiert")
        return None

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
            "--disable-blink-features=AutomationControlled", "--disable-infobars",
            "--window-size=1280,800",
        ],
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="de-DE",
        extra_http_headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    try:
        await context.add_cookies(json.loads(cookies_raw))
    except Exception:
        pass
    return playwright, browser, context


async def _linkedin_company_fallback(context, name: str) -> dict:
    """Best-effort Scrape der öffentlichen LinkedIn 'About'-Seite einer Firma.

    Nutzt Text-Muster statt CSS-Klassen (LinkedIn rotiert gehashte Klassennamen
    laufend) — dieselbe Strategie wie sync_linkedin.py. Gibt bei jedem Fehler
    (kein Suchtreffer, Layout-Änderung, Rate-Limit) einfach ein leeres/teilweises
    Dict zurück statt den Sync abzubrechen.
    """
    query = _clean_query(name)
    result: dict = {}
    page = await context.new_page()
    try:
        search_url = f"https://www.linkedin.com/search/results/companies/?keywords={query}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        link = await page.locator("a[href*='/company/']").first.get_attribute("href")
        if not link:
            return result
        company_url = link.split("?")[0].rstrip("/")
        about_url = company_url + "/about/"
        await page.goto(about_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        text = await page.locator("main").inner_text()

        def _after(label: str) -> str | None:
            m = re.search(re.escape(label) + r"\s*\n+\s*([^\n]+)", text, re.IGNORECASE)
            return m.group(1).strip() if m else None

        industry = _after("Industry")
        if industry:
            result["industry"] = industry[:200]

        size_text = _after("Company size")
        if size_text:
            m = re.search(r"([\d,]+)\s*-\s*([\d,]+)|([\d,]+)\+", size_text)
            if m:
                lower = m.group(1) or m.group(3)
                if lower:
                    result["employee_count"] = int(lower.replace(",", ""))

        # Kein hq_city-Feld: LinkedIns 'Headquarters'-Block rendert je nach
        # Sprache/Layout eine unsichtbare Sub-Beschriftung direkt darunter
        # (z.B. "Hauptsitz-Stadt"), die inner_text() mitliest — live an zwei
        # unterschiedlichen Firmenprofilen als Fehlwert beobachtet, ohne dass
        # sich ein zuverlässiges Muster zum Herausfiltern ergab. Hauptsitz kommt
        # zuverlässig über Wikidata (P159); LinkedIn liefert hier nur Branche/
        # Größe/Gründung/Website, wo das Label-Value-Muster stabil war.

        founded = _after("Founded")
        if founded:
            result["founded_year"] = _parse_year(founded)

        website = _after("Website")
        if website:
            result["website"] = website.strip()[:500]

        result["linkedin_company_url"] = company_url
    except Exception as e:
        log.debug("LinkedIn-Fallback Fehler für '{}': {}", name, e)
    finally:
        await page.close()
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
        log.debug("Logo-Download fehlgeschlagen ({}): {}", url, e)
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


def _collect_sync_candidates(
    db: Session, force: bool, company_ids: list[int] | None
) -> list[models.CompanyProfile]:
    """Bestimmt, welche CompanyProfiles bei einem /run-Aufruf verarbeitet werden.

    force=True:  alle (im Scope) werden zurückgesetzt und neu synct — die
                 explizite, absichtliche Art, es nochmal zu versuchen.
    force=False: nur "pending"-Profile (neu angelegt, noch nie versucht).

    Ein "done"-Profil wird NIE automatisch wieder auf "pending" gesetzt, egal
    ob Beschreibung oder Logo fehlen. Wer es trotzdem nochmal versuchen will,
    nutzt bewusst "Re-Sync" (force=True).
    """
    def _scoped(q):
        return q.filter(models.CompanyProfile.id.in_(company_ids)) if company_ids else q

    if force:
        _scoped(db.query(models.CompanyProfile)).update(
            {"sync_status": "pending", "sync_error": None}, synchronize_session=False
        )
        db.commit()

    return _scoped(db.query(models.CompanyProfile)).filter(
        models.CompanyProfile.sync_status == "pending"
    ).all()


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

    pending = _collect_sync_candidates(db, force, company_ids)

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
        db = SessionLocal()
        profiles = {
            p.id: p
            for p in db.query(models.CompanyProfile)
                       .filter(models.CompanyProfile.id.in_(profile_ids)).all()
        }
        db.close()

        # Phase 1: Wikidata Search API → Q-IDs (sequential, 1s apart — lenient rate limit)
        # attempted_pids trackt, welche Profile überhaupt angefasst wurden — bei Abbruch
        # (Cancel) dürfen NIE angefasste Profile NICHT als "done"/"kein Treffer" enden,
        # sonst würden sie beim nächsten normalen Sync nie wieder aufgegriffen
        # (_collect_sync_candidates rührt "done"-Profile nie automatisch an).
        attempted_pids: list[int] = []
        qid_map: dict[int, str] = {}
        desc_map: dict[int, str] = {}
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA}) as client:
            for pid in profile_ids:
                if _SYNC_CANCEL:
                    break
                p = profiles.get(pid)
                if not p:
                    continue
                attempted_pids.append(pid)
                name = p.name_display or p.name_norm
                _CURRENT_COMPANY = name
                hit = await _wikidata_search_one(client, name)
                if hit:
                    qid_map[pid], desc_map[pid] = hit
                else:
                    log.info("Kein Wikidata-Treffer für '{}'", name)
                await asyncio.sleep(1.0)

        # Phase 2: LinkedIn-Fallback für Firmen ohne Wikidata-Treffer
        fallback_data: dict[int, dict] = {}
        missing_pids = [pid for pid in attempted_pids if pid not in qid_map]
        if missing_pids and not _SYNC_CANCEL:
            li_ctx = None
            try:
                li_ctx = await _get_linkedin_context()
            except Exception as e:
                log.warning("LinkedIn-Fallback: Browser-Start fehlgeschlagen: {}", e)
            if li_ctx:
                playwright, browser, context = li_ctx
                try:
                    for pid in missing_pids:
                        if _SYNC_CANCEL:
                            break
                        p = profiles[pid]
                        name = p.name_display or p.name_norm
                        _CURRENT_COMPANY = name
                        try:
                            data = await _linkedin_company_fallback(context, name)
                            if data:
                                fallback_data[pid] = data
                        except Exception as e:
                            log.debug("LinkedIn-Fallback Fehler für '{}': {}", name, e)
                        await asyncio.sleep(1.0)
                finally:
                    await browser.close()
                    await playwright.stop()
            else:
                log.debug("LinkedIn-Fallback übersprungen: keine gültige Session konfiguriert")

        # Phase 3: Batch SPARQL für gefundene Wikidata-Treffer
        found_pids = list(qid_map.keys())
        sparql_failed_pids: set[int] = set()
        sparql_data: dict[str, dict] = {}
        for i in range(0, len(found_pids), _SPARQL_BATCH):
            if _SYNC_CANCEL:
                break
            chunk_pids = found_pids[i:i + _SPARQL_BATCH]
            chunk_qids = [qid_map[pid] for pid in chunk_pids]
            log.info("SPARQL-Batch {}/{}: {} Firmen", i // _SPARQL_BATCH + 1,
                     -(-len(found_pids) // _SPARQL_BATCH), len(chunk_qids))
            try:
                batch_result = await _wikidata_sparql_batch(chunk_qids)
                sparql_data.update(batch_result)
            except Exception as e:
                log.error("SPARQL-Batch Fehler: {}", e)
                db = SessionLocal()
                for pid in chunk_pids:
                    p = db.query(models.CompanyProfile).get(pid)
                    if p:
                        p.sync_status = "failed"
                        p.sync_error = f"SPARQL: {e}"[:500]
                        p.last_synced_at = now
                db.commit()
                db.close()
                sparql_failed_pids.update(chunk_pids)
                found_pids = [pid for pid in found_pids if pid not in chunk_pids]
            if i + _SPARQL_BATCH < len(found_pids):
                await asyncio.sleep(5.0)

        # Phase 4: Logo-Downloads (Wikidata-Bild) — parallel mit Semaphore
        sem = asyncio.Semaphore(_LOGO_CONCURRENCY)

        async def _fetch_with_sem(url: str) -> str | None:
            async with sem:
                return await _fetch_logo(url)

        logo_tasks = {}
        for pid in found_pids:
            qid = qid_map[pid]
            logo_url = sparql_data.get(qid, {}).get("logo_url")
            p = profiles.get(pid)
            if logo_url and p and not p.logo_data:
                logo_tasks[pid] = asyncio.create_task(_fetch_with_sem(logo_url))
        if logo_tasks:
            await asyncio.gather(*logo_tasks.values(), return_exceptions=True)

        # Phase 5: Ergebnisse schreiben — nur für tatsächlich versuchte Profile
        # (siehe attempted_pids-Kommentar in Phase 1: bei Cancel bleiben nicht
        # versuchte Profile "pending" und werden beim nächsten Lauf erneut erfasst)
        db = SessionLocal()
        for pid in attempted_pids:
            if pid in sparql_failed_pids:
                continue  # bereits als "failed" committed (SPARQL-Batch-Fehler)
            p = db.query(models.CompanyProfile).get(pid)
            if not p:
                continue

            if pid in qid_map:
                qid = qid_map[pid]
                data = sparql_data.get(qid, {})
                source = f"wikidata:{qid}" if data else "wikidata"
                error = None if data else "Kein Wikidata-Datensatz (nur Basistreffer)"

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
                if not p.logo_data:
                    logo_b64 = await _fetch_logo_with_clearbit_fallback(None, p.website)
                    if logo_b64:
                        p.logo_data = logo_b64

                new_type = _classify_company_type(data.get("employee_count"), data.get("founded_year"))
                if new_type:
                    p.company_type = new_type

                p.sync_source = source
                p.sync_status = "done"
                p.sync_error = error
                p.last_synced_at = now

            elif pid in fallback_data:
                data = fallback_data[pid]
                if data.get("hq_city") and not p.hq_city:
                    p.hq_city = data["hq_city"]
                if data.get("industry"):
                    p.industry = data["industry"]
                if data.get("employee_count"):
                    p.employee_count = data["employee_count"]
                    p.employee_range = _employee_range(data["employee_count"])
                if data.get("founded_year"):
                    p.founded_year = data["founded_year"]
                if data.get("website") and not p.website:
                    p.website = data["website"]
                if data.get("linkedin_company_url") and not p.linkedin_company_url:
                    p.linkedin_company_url = data["linkedin_company_url"]

                if not p.logo_data:
                    logo_b64 = await _fetch_logo_with_clearbit_fallback(None, p.website)
                    if logo_b64:
                        p.logo_data = logo_b64

                new_type = _classify_company_type(data.get("employee_count"), data.get("founded_year"))
                if new_type:
                    p.company_type = new_type

                p.sync_source = "linkedin"
                p.sync_status = "done"
                p.sync_error = None
                p.last_synced_at = now

            else:
                p.sync_source = "wikidata"
                p.sync_status = "done"
                p.sync_error = "Kein Wikidata-/LinkedIn-Treffer gefunden"
                p.last_synced_at = now

            log.info("Synced '{}' ({}): hq={} industry={} emp={}",
                     p.name_display, p.sync_source, p.hq_city, p.industry, p.employee_count)

        db.commit()
        db.close()

        log.info("Firmensync abgeschlossen: {} Firmen{}", len(profile_ids),
                 " (abgebrochen)" if _SYNC_CANCEL else "")

    except Exception as e:
        log.opt(exception=True).error("Firmensync Fehler: {} ({})", e, type(e).__name__)
    finally:
        _SYNC_RUNNING = False
        _SYNC_CANCEL = False
        _CURRENT_COMPANY = None
