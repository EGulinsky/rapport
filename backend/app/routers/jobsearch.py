"""
Jobsuche: search configured job portals for vacancies.

GET  /api/jobsearch/portals              → list portals
POST /api/jobsearch/portals              → add custom portal
PATCH /api/jobsearch/portals/{id}        → update portal
DELETE /api/jobsearch/portals/{id}       → delete portal
GET  /api/jobsearch/search?q=&location=  → search via LinkedIn playwright
POST /api/jobsearch/import               → import jobs as prospecting applications
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

router = APIRouter(prefix="/api/jobsearch", tags=["jobsearch"])

# ── Default portals seeded on first use ──────────────────────────────────────

_DEFAULT_PORTALS = [
    dict(name="LinkedIn",    portal_type="linkedin", url_template=None,                                                                                   color="#0a66c2", is_builtin=True,  sort_order=0),
    dict(name="StepStone",   portal_type="link",     url_template="https://www.stepstone.de/jobs/{q}/?what={q}&where={location}",                         color="#E8000D", is_builtin=True,  sort_order=1),
    dict(name="Indeed",      portal_type="link",     url_template="https://de.indeed.com/jobs?q={q}&l={location}",                                        color="#003A9B", is_builtin=True,  sort_order=2),
    dict(name="Xing Jobs",   portal_type="link",     url_template="https://www.xing.com/jobs/search?keywords={q}&location={location}",                    color="#026466", is_builtin=True,  sort_order=3),
    dict(name="Experteer",   portal_type="link",     url_template="https://www.experteer.de/jobs?query={q}&location={location}",                          color="#FF6900", is_builtin=True,  sort_order=4),
    dict(name="Headhunter24",portal_type="link",     url_template="https://www.headhunter24.de/jobs/?q={q}",                                              color="#7c3aed", is_builtin=True,  sort_order=5),
    dict(name="Jobware",     portal_type="link",     url_template="https://www.jobware.de/suche/?suchbegriff={q}&einsatzort={location}",                  color="#f59e0b", is_builtin=True,  sort_order=6),
]


def _seed_portals(db: Session) -> None:
    """Insert default portals if table is empty."""
    if db.query(models.JobPortal).count() == 0:
        for p in _DEFAULT_PORTALS:
            db.add(models.JobPortal(**p))
        db.commit()


def _get_portals(db: Session) -> list[models.JobPortal]:
    _seed_portals(db)
    return db.query(models.JobPortal).order_by(models.JobPortal.sort_order, models.JobPortal.id).all()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class PortalCreate(BaseModel):
    name: str
    portal_type: str = "link"
    url_template: str | None = None
    color: str | None = None
    enabled: bool = True

class PortalUpdate(BaseModel):
    name: str | None = None
    url_template: str | None = None
    color: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None

class ImportRequest(BaseModel):
    jobs: list[dict]   # each: {title, company, location, url, source}


# ── Portals CRUD ─────────────────────────────────────────────────────────────

@router.get("/portals")
def list_portals(db: Session = Depends(get_db)):
    return [_portal_out(p) for p in _get_portals(db)]


@router.post("/portals")
def add_portal(body: PortalCreate, db: Session = Depends(get_db)):
    _seed_portals(db)
    p = models.JobPortal(
        name=body.name,
        portal_type=body.portal_type,
        url_template=body.url_template,
        color=body.color,
        enabled=body.enabled,
        is_builtin=False,
        sort_order=100,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _portal_out(p)


@router.patch("/portals/{portal_id}")
def update_portal(portal_id: int, body: PortalUpdate, db: Session = Depends(get_db)):
    p = db.query(models.JobPortal).get(portal_id)
    if not p:
        raise HTTPException(404, "Portal nicht gefunden")
    if body.name is not None:
        p.name = body.name
    if body.url_template is not None:
        p.url_template = body.url_template
    if body.color is not None:
        p.color = body.color
    if body.enabled is not None:
        p.enabled = body.enabled
    if body.sort_order is not None:
        p.sort_order = body.sort_order
    db.commit()
    db.refresh(p)
    return _portal_out(p)


@router.delete("/portals/{portal_id}")
def delete_portal(portal_id: int, db: Session = Depends(get_db)):
    p = db.query(models.JobPortal).get(portal_id)
    if not p:
        raise HTTPException(404, "Portal nicht gefunden")
    if p.is_builtin:
        raise HTTPException(400, "Eingebaute Portale können nicht gelöscht werden")
    db.delete(p)
    db.commit()
    return {"deleted": portal_id}


def _portal_out(p: models.JobPortal) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "portal_type": p.portal_type,
        "url_template": p.url_template,
        "color": p.color,
        "enabled": p.enabled,
        "is_builtin": p.is_builtin,
        "sort_order": p.sort_order,
    }


# ── LinkedIn job search ───────────────────────────────────────────────────────

def _build_search_url(query: str, location: str) -> str:
    # No date filter (f_TPR removed) so we match LI's default behaviour
    return (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={quote(query)}"
        f"&location={quote(location)}"
        f"&sortBy=DD"
    )


# Extract job cards from LI search results list (left panel).
# Targets list items with data-occludable-job-id or href-based job IDs.
# Falls back through multiple selector strategies for different LI UI versions.
_EXTRACT_JS = """() => {
    const seen = new Set();
    const results = [];

    // Strategy 1: cards with data-occludable-job-id (2024-2025 LI UI)
    document.querySelectorAll('[data-occludable-job-id]').forEach(card => {
        const jobId = card.getAttribute('data-occludable-job-id') || '';
        if (!jobId || seen.has(jobId)) return;
        seen.add(jobId);
        const url = 'https://www.linkedin.com/jobs/view/' + jobId + '/';

        const titleEl = card.querySelector(
            'a[aria-label], .job-card-list__title--link, [class*="job-card-list__title"], h3 a, h2 a'
        );
        const title = (titleEl?.getAttribute('aria-label') || titleEl?.innerText || '').replace(/\\n/g, ' ').trim();

        const companyEl = card.querySelector(
            '.artdeco-entity-lockup__subtitle span, .job-card-container__primary-description, [class*="subtitle"] span, h4'
        );
        const company = (companyEl?.innerText || '').trim();

        const locationEl = card.querySelector(
            '.job-card-container__metadata-item, [class*="metadata-item"], li[class*="caption"]'
        );
        const location = (locationEl?.innerText || '').trim();

        const easyApply = !!(card.querySelector('[class*="easy-apply"]') ||
            card.querySelector('[aria-label*="Easy Apply"]'));

        if (title) results.push({ id: jobId, title, company, location, url, easy_apply: easyApply });
    });

    if (results.length > 0) return results.slice(0, 30);

    // Strategy 2: fallback via href-based dedup
    const links = [...document.querySelectorAll('a[href*="/jobs/view/"]')]
        .map(a => ({ a, url: a.href.split('?')[0].replace(/\\/$/, '') }))
        .filter(({ url }) => {
            const m = url.match(/\\/jobs\\/view\\/(\\d+)/);
            if (!m) return false;
            if (seen.has(m[1])) return false;
            seen.add(m[1]);
            return true;
        });

    links.slice(0, 30).forEach(({ a, url }) => {
        const id = (url.match(/\\/jobs\\/view\\/(\\d+)/) || [])[1] || '';
        const card = a.closest('li') || a.closest('[data-job-id]') || a.parentElement?.parentElement;
        const titleEl = card?.querySelector('h3, h2, [class*="title"]');
        const title = (titleEl?.innerText || a.innerText || '').replace(/\\n/g, ' ').trim();
        const companyEl = card?.querySelector('h4, [class*="subtitle"], [class*="company"], [class*="primary-description"]');
        const company = (companyEl?.innerText || '').trim();
        const locationEl = card?.querySelector('[class*="metadata-item"], [class*="location"]');
        const location = (locationEl?.innerText || '').trim();
        if (id && title) results.push({ id, title, company, location, url, easy_apply: false });
    });

    return results.slice(0, 30);
}"""


# Extract full job description from a LI job detail page
_DESCRIPTION_JS = """() => {
    function isNavJunk(el) {
        const t = (el.innerText || '').trim();
        return /skip to (search|main|content|footer|aside)/i.test(t);
    }
    const selectors = [
        '#job-details',
        '.jobs-description__content',
        '.jobs-description-content__text',
        'article.jobs-description',
        '[class*="jobs-description__container"]',
        '.description__text',
        '[data-view-name="job-view-description"]',
        'div[class*="show-more-less-html"]',
        'div[class*="jobs-box__html-content"]',
        'section.jobs-view-layout__job-details',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.innerText.trim().length > 100 && !isNavJunk(el)) return el.innerHTML;
    }
    // Heading-based fallback: look for "About the job" section
    const headings = [...document.querySelectorAll('h2, h3')];
    const about = headings.find(h => /about the job|über die stelle|über die position|job description/i.test(h.innerText));
    if (about) {
        let html = '';
        let el = about.nextElementSibling;
        while (el && !/^H[23]$/.test(el.tagName)) { html += el.outerHTML; el = el.nextElementSibling; }
        if (html.trim().length > 50) return html;
    }
    return '';
}"""


async def _linkedin_search(query: str, location: str, db: Session) -> list[dict]:
    cfg = db.query(models.LinkedInSync).first()
    if not cfg or not cfg.email or not cfg.password_enc:
        raise ValueError("LinkedIn nicht konfiguriert — bitte unter Einstellungen einrichten")

    from app.ai.provider import decrypt_api_key
    from app.routers.sync_linkedin import _login, _accept_consent

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ValueError("Playwright nicht installiert")

    password = decrypt_api_key(cfg.password_enc)
    search_url = _build_search_url(query, location)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="de-DE",
            extra_http_headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        if cfg.session_cookies:
            try:
                await context.add_cookies(json.loads(cfg.session_cookies))
            except Exception:
                pass

        page = await context.new_page()

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            await browser.close()
            raise ValueError(f"Seite konnte nicht geladen werden: {e}")

        await _accept_consent(page)

        if "login" in page.url or "authwall" in page.url or "uas/login" in page.url:
            logged_in = await _login(page, cfg.email, password)
            if not logged_in:
                await browser.close()
                raise ValueError("LinkedIn Login fehlgeschlagen")
            cookies = await context.cookies()
            cfg.session_cookies = json.dumps(cookies)
            db.commit()
            # Navigate to search after login
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await _accept_consent(page)

        # Wait for the job list cards to appear (up to 10 s)
        try:
            await page.wait_for_selector(
                '[data-occludable-job-id], a[href*="/jobs/view/"]',
                timeout=10000,
            )
        except Exception:
            pass
        # Extra scroll to trigger lazy-load
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)

        try:
            jobs = await page.evaluate(_EXTRACT_JS)
        except Exception:
            jobs = []

        await browser.close()

    return [
        {
            "id": j["id"],
            "source": "linkedin",
            "title": j.get("title", "").strip(),
            "company": j.get("company", "").strip(),
            "location": j.get("location", "").strip(),
            "url": j.get("url", ""),
            "easy_apply": j.get("easy_apply", False),
        }
        for j in jobs
        if j.get("id")
    ]


# ── Search endpoint ───────────────────────────────────────────────────────────

@router.get("/search")
async def search_jobs(
    q: str = "",
    location: str = "Deutschland",
    db: Session = Depends(get_db),
):
    if not q.strip():
        return {"results": [], "portals": []}

    portals = [p for p in _get_portals(db) if p.enabled]

    # LinkedIn results (live scrape)
    li_results: list[dict] = []
    li_error: str | None = None
    li_portal = next((p for p in portals if p.portal_type == "linkedin"), None)
    if li_portal:
        try:
            li_results = await _linkedin_search(q.strip(), location.strip(), db)
        except ValueError as e:
            li_error = str(e)

    # Link portals: generate search URLs
    link_portals = []
    for p in portals:
        if p.portal_type != "link" or not p.url_template:
            continue
        url = p.url_template.replace("{q}", quote(q.strip())).replace("{location}", quote(location.strip()))
        link_portals.append({
            "id": p.id,
            "name": p.name,
            "color": p.color,
            "url": url,
        })

    return {
        "results": li_results,
        "portals": link_portals,
        "linkedin_error": li_error,
    }


# ── Description endpoint ──────────────────────────────────────────────────────

async def _load_description(job_url: str, db: Session) -> str:
    """Load full job description from a LinkedIn job page."""
    cfg = db.query(models.LinkedInSync).first()
    if not cfg or not cfg.email or not cfg.password_enc:
        raise ValueError("LinkedIn nicht konfiguriert")

    from app.ai.provider import decrypt_api_key
    from app.routers.sync_linkedin import _login, _accept_consent

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ValueError("Playwright nicht installiert")

    password = decrypt_api_key(cfg.password_enc)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="de-DE",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        if cfg.session_cookies:
            try:
                await context.add_cookies(json.loads(cfg.session_cookies))
            except Exception:
                pass

        page = await context.new_page()
        try:
            await page.goto(job_url, wait_until="load", timeout=30000)
        except Exception as e:
            await browser.close()
            raise ValueError(f"Seite nicht erreichbar: {e}")

        await _accept_consent(page)

        if "login" in page.url or "authwall" in page.url:
            logged_in = await _login(page, cfg.email, password)
            if not logged_in:
                await browser.close()
                raise ValueError("LinkedIn Login fehlgeschlagen")
            await page.goto(job_url, wait_until="load", timeout=30000)
            await _accept_consent(page)

        # Let JS finish rendering
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollBy(0, 600)")
        await asyncio.sleep(0.5)

        # Try "See more" / "Mehr anzeigen" to expand truncated description
        try:
            btn = page.locator('button:has-text("See more"), button:has-text("Mehr anzeigen"), button[aria-label*="description"]').first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # Wait for any known description container
        try:
            await page.wait_for_selector(
                '#job-details, .jobs-description__content, .description__text, [data-view-name="job-view-description"], div[class*="show-more-less-html"]',
                timeout=8000,
            )
        except Exception:
            pass
        await asyncio.sleep(0.5)

        # Debug: dump classes of all divs with substantial text
        debug_info = ""
        try:
            debug_info = await page.evaluate("""() => {
                const items = [...document.querySelectorAll('div, article, section')]
                    .filter(el => (el.innerText||'').trim().length > 200 && (el.innerText||'').trim().length < 5000)
                    .map(el => ({
                        tag: el.tagName,
                        cls: el.className?.toString().slice(0,120) || '',
                        id: el.id || '',
                        len: (el.innerText||'').trim().length,
                        dataView: el.getAttribute('data-view-name') || '',
                    }));
                return JSON.stringify(items.slice(0, 30));
            }""")
        except Exception as e:
            debug_info = str(e)
        import logging
        logging.getLogger("jobsearch").warning("DOM DUMP url=%s\n%s", job_url, debug_info)

        description = ""
        try:
            description = await page.evaluate(_DESCRIPTION_JS)
        except Exception:
            pass

        await browser.close()

    return description or ""


@router.get("/description")
async def get_description(url: str, db: Session = Depends(get_db)):
    if not url or "/jobs/view/" not in url:
        raise HTTPException(400, "Ungültige Job-URL")
    try:
        text = await _load_description(url, db)
        return {"description": text}
    except ValueError as e:
        raise HTTPException(500, str(e))


# ── Import endpoint ───────────────────────────────────────────────────────────

@router.post("/import")
def import_jobs(body: ImportRequest, db: Session = Depends(get_db)):
    from datetime import date
    created_ids = []
    skipped = 0

    for job in body.jobs:
        firma = (job.get("company") or "").strip()
        rolle = (job.get("title") or "").strip()
        url   = job.get("url") or None

        if not firma or not rolle:
            skipped += 1
            continue

        # Check if already exists (loose match)
        from app.dedup import norm_firma, norm_rolle
        exists = any(
            norm_firma(a.firma or "") == norm_firma(firma)
            and norm_rolle(a.rolle or "") == norm_rolle(rolle)
            for a in db.query(models.Application).all()
        )
        if exists:
            skipped += 1
            continue

        app = models.Application(
            firma=firma,
            rolle=rolle,
            quelle=job.get("source", "Jobsuche").capitalize(),
            main_status="prospecting",
            datum_bewerbung=date.today(),
            letztes_update=date.today(),
            stellenanzeige_url=url,
            linkedin_job_id=job.get("id") if job.get("source") == "linkedin" else None,
        )
        db.add(app)
        db.flush()

        db.add(models.Event(
            application_id=app.id,
            typ="notiz",
            datum=date.today(),
            titel="Aus Jobsuche übernommen",
            source="jobsearch",
        ))

        from app.audit import add_audit
        add_audit(db, "create", "jobsearch", app_id=app.id, new_value=f"{firma} – {rolle}")

        created_ids.append(app.id)

    db.commit()
    return {"created": len(created_ids), "skipped": skipped, "ids": created_ids}
