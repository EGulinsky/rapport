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
import re
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
    return (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={quote(query)}"
        f"&location={quote(location)}"
        f"&f_TPR=r2592000"   # last 30 days
        f"&sortBy=DD"         # most recent
    )


_EXTRACT_JS = """() => {
    // Collect unique job view URLs
    const seen = new Set();
    const links = [...document.querySelectorAll('a[href*="/jobs/view/"]')]
        .map(a => a.href.split('?')[0].replace(/\\/$/, ''))
        .filter(h => { if (seen.has(h)) return false; seen.add(h); return true; });

    return links.slice(0, 30).map(url => {
        const id = (url.match(/jobs\\/view\\/(\\d+)/) || [])[1] || '';
        const a = document.querySelector('a[href*="' + id + '"]');
        const card = a && (a.closest('li') || a.closest('article') || a.parentElement);

        const getText = (el, ...sels) => {
            for (const s of sels) {
                const node = el && el.querySelector(s);
                if (node && node.innerText.trim()) return node.innerText.trim();
            }
            return '';
        };

        const title = getText(card,
            'h3', 'h2',
            '.job-card-list__title',
            '.artdeco-entity-lockup__title',
            '[class*="job-card-list__title"]'
        ) || (a && a.innerText.trim()) || '';

        const company = getText(card,
            'h4',
            '.job-card-container__primary-description',
            '.artdeco-entity-lockup__subtitle',
            '[class*="primary-description"]'
        );

        const location = getText(card,
            '.job-card-container__metadata-item',
            '.artdeco-entity-lockup__caption',
            '[class*="metadata-item"]',
            '[class*="location"]'
        );

        const easyApply = !!(card && card.querySelector(
            '[class*="easy-apply"], [aria-label*="Easy Apply"], [aria-label*="Easy apply"]'
        ));

        return { id, title, company, location, url, easy_apply: easyApply };
    }).filter(j => j.id && j.title);
}"""


async def _linkedin_search(query: str, location: str, db: Session) -> list[dict]:
    cfg = db.query(models.LinkedInSync).first()
    if not cfg or not cfg.email or not cfg.password_enc:
        raise ValueError("LinkedIn nicht konfiguriert — bitte unter Einstellungen einrichten")

    from app.security import decrypt_api_key
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

        # Wait for SPA to render job cards
        await asyncio.sleep(4)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)

        try:
            jobs = await page.evaluate(_EXTRACT_JS)
        except Exception:
            jobs = []

        # Fallback: if JS extraction failed, use URL-only extraction
        if not jobs:
            try:
                raw_links = await page.evaluate(
                    "() => [...new Set([...document.querySelectorAll('a[href*=\"/jobs/view/\"]')]"
                    ".map(a => a.href.split('?')[0].replace(/\\/$/, '')))]"
                )
                for url in raw_links[:30]:
                    m = re.search(r'/jobs/view/(\d+)', url)
                    if m:
                        jobs.append({"id": m.group(1), "title": "", "company": "", "location": "", "url": url, "easy_apply": False})
            except Exception:
                pass

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
