"""
LinkedIn Playwright scraper — scrapes the user's own "Applied Jobs" page.
Credentials are stored encrypted; session cookies are persisted so re-login is rare.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.provider import decrypt_api_key, encrypt_api_key
from app.database import get_db
from app import models

router = APIRouter(prefix="/api/sync/linkedin", tags=["sync"])

# ── In-memory task state ──────────────────────────────────────────────────────

_state: dict = {
    "status": "idle",      # idle | running | done | error | needs_login
    "step": "",
    "processed": 0,
    "created": 0,
    "updated": 0,
    "skipped": 0,
    "errors": [],
    "log": [],             # per-application action log
    "started_at": None,
    "finished_at": None,
}


def _reset_state():
    _state.update({
        "status": "idle",
        "step": "",
        "processed": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "log": [],
        "started_at": None,
        "finished_at": None,
    })


# ── Schemas ───────────────────────────────────────────────────────────────────

class LinkedInConfigWrite(BaseModel):
    email: str
    password: str


class LinkedInConfigStatus(BaseModel):
    configured: bool
    email: Optional[str] = None
    has_session: bool = False
    last_sync: Optional[str] = None


# ── Config endpoints ──────────────────────────────────────────────────────────

@router.get("/config", response_model=LinkedInConfigStatus)
def get_config(db: Session = Depends(get_db)):
    cfg = db.query(models.LinkedInSync).first()
    if not cfg:
        return LinkedInConfigStatus(configured=False)
    return LinkedInConfigStatus(
        configured=True,
        email=cfg.email,
        has_session=bool(cfg.session_cookies),
        last_sync=cfg.last_sync.isoformat() if cfg.last_sync else None,
    )


@router.post("/config", response_model=LinkedInConfigStatus)
def save_config(payload: LinkedInConfigWrite, db: Session = Depends(get_db)):
    cfg = db.query(models.LinkedInSync).first()
    if cfg:
        cfg.email = payload.email.strip()
        cfg.password_enc = encrypt_api_key(payload.password)
        cfg.session_cookies = None  # force re-login with new credentials
    else:
        cfg = models.LinkedInSync(
            email=payload.email.strip(),
            password_enc=encrypt_api_key(payload.password),
        )
        db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return LinkedInConfigStatus(
        configured=True,
        email=cfg.email,
        has_session=False,
        last_sync=cfg.last_sync.isoformat() if cfg.last_sync else None,
    )


@router.delete("/config")
def delete_config(db: Session = Depends(get_db)):
    db.query(models.LinkedInSync).delete()
    db.commit()
    _reset_state()
    return {"ok": True}


# ── Status / run endpoints ────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    return dict(_state)


@router.post("/run")
def run_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    cfg = db.query(models.LinkedInSync).first()
    if not cfg:
        raise HTTPException(400, "LinkedIn not configured")
    if _state["status"] == "running":
        raise HTTPException(409, "Sync already running")

    _reset_state()
    _state["status"] = "running"
    _state["started_at"] = datetime.now(timezone.utc).isoformat()
    background_tasks.add_task(_run_sync_task, cfg.id)
    return dict(_state)


@router.post("/clear-session")
def clear_session(db: Session = Depends(get_db)):
    cfg = db.query(models.LinkedInSync).first()
    if cfg:
        cfg.session_cookies = None
        db.commit()
    return {"ok": True}


# ── Playwright scraper ────────────────────────────────────────────────────────

LOGIN_URL = "https://www.linkedin.com/login"
BASE_JOBS_URL = "https://www.linkedin.com/my-items/saved-jobs/?cardType="

# All LinkedIn job categories → (cardType param, default main_status)
CATEGORIES: list[tuple[str, str, str]] = [
    ("SAVED",       "Gespeichert",   "prospecting"),
    ("IN_PROGRESS", "In Bearbeitung","applied"),
    ("APPLIED",     "Beworben",      "applied"),
    ("INTERVIEWS",  "Interviews",    "hr"),
    ("ARCHIVED",    "Archiviert",    "rejected"),
]

# LinkedIn status footer text → override main_status
_STATUS_MAP = {
    "application viewed":          ("hr",           None),
    "bewerbung gesehen":           ("hr",           None),
    "no longer accepting":         ("rejected",     None),
    "stelle nicht mehr verfügbar": ("rejected",     None),
    "offer":                       ("negotiating",  None),
    "angebot":                     ("negotiating",  None),
    "interview":                   ("hr",           "1_scheduled"),
}


def _parse_date(text: str) -> Optional[str]:
    """Parse 'Applied X days ago' or 'Applied on MM/DD/YYYY' → YYYY-MM-DD."""
    text = text.lower().strip()
    # "applied 3 days ago"
    m = re.search(r"(\d+)\s+day", text)
    if m:
        from datetime import timedelta
        d = datetime.now() - timedelta(days=int(m.group(1)))
        return d.strftime("%Y-%m-%d")
    # "applied 2 weeks ago"
    m = re.search(r"(\d+)\s+week", text)
    if m:
        from datetime import timedelta
        d = datetime.now() - timedelta(weeks=int(m.group(1)))
        return d.strftime("%Y-%m-%d")
    # "applied 1 month ago"
    m = re.search(r"(\d+)\s+month", text)
    if m:
        from datetime import timedelta
        d = datetime.now() - timedelta(days=int(m.group(1)) * 30)
        return d.strftime("%Y-%m-%d")
    # "applied on 1/15/2025" or "01/15/2025"
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


async def _login(page, email: str, password: str) -> bool:
    """Attempt email/password login. Returns True if successful."""
    try:
        # domcontentloaded fires quickly; wait_for_selector below waits for React to mount the form
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        # Wait up to 10 s for the username field; catch gracefully if bot-detection hides it
        try:
            await page.wait_for_selector("#username", state="visible", timeout=10000)
        except Exception:
            current_url = page.url
            title = await page.title()
            _state["errors"].append(
                f"Login-Seite nicht geladen — URL: {current_url} | Titel: {title}"
            )
            _state["status"] = "needs_login"
            _state["step"] = "LinkedIn zeigt keine Login-Maske (Bot-Detection?) — Session-Cookies zurücksetzen und erneut versuchen"
            return False

        await page.fill("#username", email)
        await page.fill("#password", password)
        submit = page.locator('[data-litms-control-urn="login-submit"], button[type="submit"]').first
        await submit.click()
        await page.wait_for_url(
            re.compile(r"linkedin\.com/(feed|checkpoint|jobs|my-items|uas/login)"),
            timeout=20000,
        )
        if "checkpoint" in page.url or "challenge" in page.url:
            _state["status"] = "needs_login"
            _state["step"] = "LinkedIn verlangt 2FA/Verification — bitte erneut anmelden"
            return False
        return True
    except Exception as e:
        _state["errors"].append(f"Login-Fehler: {e}")
        return False


async def _scrape_category(page, card_type: str, default_status: str, seen_ids: set[str]) -> list[dict]:
    """Scroll through one LinkedIn job category and collect all job cards."""
    url = f"{BASE_JOBS_URL}{card_type}"
    jobs: list[dict] = []

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return []
    await asyncio.sleep(2)

    if "login" in page.url or "authwall" in page.url:
        return []  # session expired mid-scrape

    prev_count = -1
    stale_rounds = 0
    while True:
        cards = await page.query_selector_all(
            "div.job-card-container, li.reusable-search__result-container, "
            "div[data-view-name='job-card'], li.occludable-update"
        )

        for card in cards:
            job_id = (
                await card.get_attribute("data-job-id")
                or await card.get_attribute("data-entity-urn")
                or ""
            )
            if not job_id:
                link = await card.query_selector("a[href*='/jobs/view/']")
                if link:
                    href = await link.get_attribute("href") or ""
                    m = re.search(r"/jobs/view/(\d+)", href)
                    if m:
                        job_id = m.group(1)
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title_el = await card.query_selector(
                ".job-card-list__title, .job-card-container__link, a[data-control-name='jobcard_title']"
            )
            title = (await title_el.inner_text()).strip() if title_el else ""

            company_el = await card.query_selector(
                ".job-card-container__primary-description, .artdeco-entity-lockup__subtitle span"
            )
            company = (await company_el.inner_text()).strip() if company_el else ""

            date_el = await card.query_selector(
                ".job-card-container__footer-item, .job-card-list__footer-wrapper span"
            )
            date_text = (await date_el.inner_text()).strip() if date_el else ""
            applied_date = _parse_date(date_text)

            # Footer text may override the default status
            status_text = date_text.lower()
            mapped_status: Optional[tuple] = None
            for keyword, mapping in _STATUS_MAP.items():
                if keyword in status_text:
                    mapped_status = mapping
                    break

            if title and company:
                jobs.append({
                    "id": job_id,
                    "title": title,
                    "company": company,
                    "applied_date": applied_date,
                    "default_status": default_status,
                    "status_hint": mapped_status,
                })

        if len(jobs) == prev_count:
            stale_rounds += 1
            if stale_rounds >= 3:
                break
        else:
            stale_rounds = 0
        prev_count = len(jobs)

        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(1.5)

    return jobs


def _find_or_create_application(db: Session, job: dict) -> tuple[models.Application, bool]:
    """Match job to existing application or create new. Returns (app, created)."""
    company_lower = job["company"].lower()
    role_lower = job["title"].lower()

    apps = db.query(models.Application).all()
    for app in apps:
        firma_lower = (app.firma or "").lower()
        company_match = (
            company_lower in firma_lower
            or firma_lower in company_lower
            or (app.zielfirma_bei_hh or "").lower() in company_lower
        )
        role_match = (
            role_lower in (app.rolle or "").lower()
            or (app.rolle or "").lower() in role_lower
        )
        if company_match and role_match:
            return app, False

    # Determine status for new application
    initial_status = job.get("default_status", "applied")
    if job.get("status_hint"):
        initial_status = job["status_hint"][0]

    new_app = models.Application(
        firma=job["company"],
        rolle=job["title"],
        datum_bewerbung=job["applied_date"],
        letztes_update=job["applied_date"],
        quelle="LinkedIn",
        main_status=initial_status,
        abgesagt=(initial_status == "rejected"),
    )
    db.add(new_app)
    db.flush()

    event_typ = "bewerbung" if initial_status not in ("prospecting", "rejected") else "notiz"
    event_titel = {
        "prospecting": "Gespeichert auf LinkedIn",
        "applied":     "Bewerbung eingereicht",
        "hr":          "Interview",
        "rejected":    "Archiviert / Abgelehnt",
    }.get(initial_status, "Bewerbung eingereicht")

    db.add(models.Event(
        application_id=new_app.id,
        typ=event_typ,
        datum=job["applied_date"],
        titel=event_titel,
        source="linkedin",
    ))
    return new_app, True


def _run_sync_task(cfg_id: int):
    """Blocking wrapper — runs the async scraper from a sync background task."""
    asyncio.run(_async_sync(cfg_id))


async def _async_sync(cfg_id: int):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        cfg = db.query(models.LinkedInSync).get(cfg_id)
        if not cfg:
            _state["status"] = "error"
            _state["step"] = "Konfiguration nicht gefunden"
            return

        email = cfg.email
        password = decrypt_api_key(cfg.password_enc)

        _state["step"] = "Browser starten…"

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            _state["status"] = "error"
            _state["step"] = "Playwright nicht installiert (docker compose build erforderlich)"
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1280,800",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="de-DE",
                extra_http_headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
            )
            # Remove webdriver fingerprint
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # Restore saved session
            if cfg.session_cookies:
                try:
                    cookies = json.loads(cfg.session_cookies)
                    await context.add_cookies(cookies)
                except Exception:
                    pass

            page = await context.new_page()

            # Check session validity
            _state["step"] = "Session prüfen…"
            check_url = f"{BASE_JOBS_URL}APPLIED"
            try:
                await page.goto(check_url, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                await page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=20000)

            if "login" in page.url or "authwall" in page.url or "uas/login" in page.url:
                _state["step"] = "Anmelden…"
                logged_in = await _login(page, email, password)
                if not logged_in:
                    await browser.close()
                    if _state["status"] != "needs_login":
                        _state["status"] = "error"
                    return

            # Save fresh session cookies
            cookies = await context.cookies()
            cfg.session_cookies = json.dumps(cookies)
            db.commit()

            # Scrape all categories; seen_ids is shared to avoid duplicates across categories
            all_jobs: list[dict] = []
            seen_ids: set[str] = set()
            for card_type, label, default_status in CATEGORIES:
                _state["step"] = f"Lade {label}…"
                cat_jobs = await _scrape_category(page, card_type, default_status, seen_ids)
                all_jobs.extend(cat_jobs)

            await browser.close()

        if not all_jobs and _state["status"] != "needs_login":
            _state["step"] = "Keine Jobs gefunden — LinkedIn-Layout evtl. geändert"

        _state["step"] = f"Verarbeite {len(all_jobs)} Einträge…"
        created = updated = skipped = 0
        errors: list[str] = []
        action_log: list[dict] = []
        STATUS_ORDER = ["prospecting", "applied", "hr", "fb", "waiting", "negotiating", "signed", "rejected"]
        # Early stages where LinkedIn "archived" reliably means no active process
        EARLY_STAGES = {"prospecting", "applied"}

        for i, job in enumerate(all_jobs):
            _state["processed"] = i + 1
            try:
                app, was_created = _find_or_create_application(db, job)
                company = job.get("company", "?")
                role = job.get("title", "?")
                if was_created:
                    created += 1
                    action_log.append({
                        "aktion": "neu",
                        "firma": company,
                        "rolle": role,
                        "status": app.main_status,
                    })
                else:
                    target_status = job.get("default_status", "applied")
                    if job.get("status_hint"):
                        target_status = job["status_hint"][0]

                    old_status = app.main_status
                    cur_idx = STATUS_ORDER.index(old_status) if old_status in STATUS_ORDER else 0
                    new_idx = STATUS_ORDER.index(target_status) if target_status in STATUS_ORDER else 0

                    # Archived → abgesagt: only for early-stage apps (not ongoing interviews)
                    if target_status == "rejected" and old_status in EARLY_STAGES:
                        app.main_status = "rejected"
                        app.abgesagt = True
                        updated += 1
                        action_log.append({
                            "aktion": "abgesagt",
                            "firma": company,
                            "rolle": role,
                            "von": old_status,
                        })
                    elif target_status != "rejected" and new_idx > cur_idx:
                        app.main_status = target_status
                        if job.get("status_hint") and job["status_hint"][1]:
                            app.sub_status = job["status_hint"][1]
                        updated += 1
                        action_log.append({
                            "aktion": "aktualisiert",
                            "firma": company,
                            "rolle": role,
                            "von": old_status,
                            "zu": target_status,
                        })
                    else:
                        skipped += 1
                        action_log.append({
                            "aktion": "unverändert",
                            "firma": company,
                            "rolle": role,
                            "status": old_status,
                        })
            except Exception as e:
                errors.append(f"{job.get('company', '?')}: {e}")

        cfg.last_sync = datetime.now(timezone.utc)
        db.commit()

        _state.update({
            "status": "done",
            "step": "Fertig",
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "log": action_log,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as e:
        _state["status"] = "error"
        _state["step"] = f"Fehler: {e}"
        _state["errors"] = [str(e)]
    finally:
        db.close()
