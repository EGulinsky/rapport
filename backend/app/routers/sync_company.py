"""Company profile background sync — LinkedIn scraping via Playwright."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync/company", tags=["sync_company"])

_SYNC_RUNNING = False


@router.get("/status")
def company_sync_status(db: Session = Depends(get_db)):
    profiles = db.query(models.CompanyProfile).all()
    pending = [p for p in profiles if p.sync_status == "pending"]
    done = [p for p in profiles if p.sync_status == "done"]
    failed = [p for p in profiles if p.sync_status == "failed"]
    return {
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

    count = len(pending)
    if count == 0:
        return {"started": False, "count": 0, "message": "No pending profiles"}

    ids = [p.id for p in pending]
    background_tasks.add_task(_run_sync_batch, ids)
    return {"started": True, "count": count}


@router.post("/reset-lock")
def reset_lock():
    global _SYNC_RUNNING
    _SYNC_RUNNING = False
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
    global _SYNC_RUNNING
    _SYNC_RUNNING = True
    try:
        for pid in profile_ids:
            db = SessionLocal()
            try:
                profile = db.query(models.CompanyProfile).filter(models.CompanyProfile.id == pid).first()
                if not profile:
                    continue
                await _sync_one_company(db, profile)
            except Exception as e:
                logger.error("Sync error for profile %s: %s", pid, e)
            finally:
                db.close()
            # Brief pause to avoid rate limiting
            await asyncio.sleep(3)
    finally:
        _SYNC_RUNNING = False


async def _sync_one_company(db: Session, profile: models.CompanyProfile):
    """Scrape LinkedIn company page and update profile fields."""
    try:
        from playwright.async_api import async_playwright
        from app.routers.sync_linkedin import _login, _accept_consent

        li_sync = db.query(models.LinkedInSync).first()
        if not li_sync or not li_sync.email or not li_sync.password_enc:
            profile.sync_status = "failed"
            profile.sync_error = "LinkedIn nicht konfiguriert"
            db.commit()
            return

        from app.ai.provider import decrypt_api_key
        password = decrypt_api_key(li_sync.password_enc)

        cookies = []
        if li_sync.session_cookies:
            try:
                cookies = json.loads(li_sync.session_cookies)
            except Exception:
                pass

        name = profile.name_display or profile.name_norm
        search_url = f"https://www.linkedin.com/search/results/companies/?keywords={quote(name)}"

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
            if cookies:
                await context.add_cookies(cookies)

            page = await context.new_page()

            await page.goto(search_url, wait_until="load", timeout=30000)
            await _accept_consent(page)

            if "login" in page.url or "authwall" in page.url:
                logged_in = await _login(page, li_sync.email, password)
                if not logged_in:
                    await browser.close()
                    profile.sync_status = "failed"
                    profile.sync_error = "LinkedIn Login fehlgeschlagen"
                    db.commit()
                    return
                await page.goto(search_url, wait_until="load", timeout=30000)
                await _accept_consent(page)

            await asyncio.sleep(2)

            # Find first company link in search results (structural, no class-name dependency)
            company_url = await page.evaluate(f"""() => {{
                // Look for links to /company/ pages in search results
                const links = [...document.querySelectorAll('a[href*="/company/"]')];
                // Filter out nav links (short hrefs like /company/about)
                const result = links.find(a => /\\/company\\/[\\w-]+\\/?($|\\?|#)/.test(a.href));
                return result ? result.href.split('?')[0] : null;
            }}""")

            if not company_url:
                profile.sync_status = "failed"
                profile.sync_error = "Kein LI-Firmenprofil in Suchergebnissen gefunden"
                db.commit()
                await browser.close()
                return

            # Navigate directly to /about page
            about_url = company_url.rstrip("/") + "/about/"
            await page.goto(about_url, wait_until="load", timeout=30000)
            await asyncio.sleep(2)

            linkedin_url = about_url

            # Extract data via JS — LI uses hashed class names, use dt/dd structure
            extracted = await page.evaluate("""
                () => {
                    // Description: find the overview text block
                    const descCandidates = [...document.querySelectorAll('p, div, section')]
                        .filter(el => {
                            const t = (el.innerText||'').trim();
                            return t.length > 80 && t.length < 3000 && !el.querySelector('nav,header,footer,ul,ol');
                        })
                        .sort((a,b) => b.innerText.trim().length - a.innerText.trim().length);
                    const desc = descCandidates.length > 0 ? descCandidates[0].innerText.trim() : null;

                    // Structured data: LI /about uses dt/dd pairs
                    const pairs = {};
                    document.querySelectorAll('dt').forEach(dt => {
                        const dd = dt.nextElementSibling;
                        if (dd && dd.tagName === 'DD') {
                            pairs[dt.innerText.trim().toLowerCase()] = dd.innerText.trim();
                        }
                    });

                    // Fallback: scan body text for labelled lines
                    const findInText = (...labels) => {
                        for (const label of labels) {
                            const key = Object.keys(pairs).find(k => k.includes(label.toLowerCase()));
                            if (key) return pairs[key];
                        }
                        const text = document.body.innerText;
                        for (const label of labels) {
                            const m = text.match(new RegExp(label + '[:\\\\s]+([^\\\\n]{2,80})', 'i'));
                            if (m) return m[1].trim();
                        }
                        return null;
                    };

                    return {
                        description: desc,
                        employee_range: findInText('employees', 'Mitarbeiter'),
                        hq: findInText('Headquarters', 'Hauptsitz'),
                        industry: findInText('Industry', 'Branche'),
                        founded_year: findInText('Founded', 'Gegründet'),
                        website: findInText('Website'),
                        company_type: findInText('Company type', 'Unternehmensform', 'Unternehmenstyp'),
                    };
                }
            """)

            await browser.close()

        # Update profile fields
        if extracted.get("description"):
            profile.description = extracted["description"][:2000]

        if extracted.get("hq"):
            hq = extracted["hq"].strip()
            parts = [p.strip() for p in hq.split(",")]
            if len(parts) >= 2:
                profile.hq_city = parts[0]
                profile.hq_country = parts[-1]
            else:
                profile.hq_city = hq

        if extracted.get("industry"):
            profile.industry = extracted["industry"].strip()[:200]

        if extracted.get("company_type"):
            profile.company_type = extracted["company_type"].strip()[:100]

        if extracted.get("website"):
            profile.website = extracted["website"].strip()[:500]

        if extracted.get("founded_year"):
            try:
                year_str = extracted["founded_year"].strip()
                year = int("".join(c for c in year_str if c.isdigit())[:4])
                if 1800 <= year <= 2100:
                    profile.founded_year = year
            except Exception:
                pass

        if extracted.get("employee_range"):
            emp = extracted["employee_range"].strip()
            profile.employee_range = emp[:100]

        profile.linkedin_company_url = linkedin_url
        profile.sync_source = "linkedin"
        profile.sync_status = "done"
        profile.sync_error = None
        profile.last_synced_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Synced company profile %s: %s", profile.id, profile.name_display)

    except Exception as e:
        logger.error("Failed to sync company %s: %s", profile.id, e)
        profile.sync_status = "failed"
        profile.sync_error = str(e)[:500]
        db.commit()
