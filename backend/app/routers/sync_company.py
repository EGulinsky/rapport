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

        li_sync = db.query(models.LinkedInSync).first()
        cookies = []
        if li_sync and li_sync.session_cookies:
            try:
                cookies = json.loads(li_sync.session_cookies)
            except Exception:
                cookies = []

        name = profile.name_display or profile.name_norm
        search_url = f"https://www.linkedin.com/search/results/companies/?keywords={quote(name)}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            if cookies:
                await context.add_cookies(cookies)

            page = await context.new_page()

            # Accept consent if shown
            try:
                await page.goto("https://www.linkedin.com", timeout=15000)
                consent = page.locator("button[action-type='ACCEPT']")
                if await consent.count() > 0:
                    await consent.first.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Navigate to company search
            await page.goto(search_url, timeout=20000)
            await page.wait_for_timeout(3000)

            # Find first company result
            card_selector = "[data-view-name='search-entity-result-universal-template']"
            try:
                await page.wait_for_selector(card_selector, timeout=10000)
            except Exception:
                profile.sync_status = "failed"
                profile.sync_error = "No company results found on LinkedIn"
                db.commit()
                await browser.close()
                return

            cards = page.locator(card_selector)
            if await cards.count() == 0:
                profile.sync_status = "failed"
                profile.sync_error = "No company results found"
                db.commit()
                await browser.close()
                return

            # Click first result
            await cards.first.click()
            await page.wait_for_timeout(2000)

            # Navigate to /about tab
            try:
                about_link = page.locator("a[href*='/about']").first
                if await about_link.count() > 0:
                    await about_link.click()
                    await page.wait_for_timeout(2000)
                else:
                    about_url = page.url.rstrip("/") + "/about"
                    await page.goto(about_url, timeout=15000)
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

            linkedin_url = page.url

            # Extract data via JS
            extracted = await page.evaluate("""
                () => {
                    const getText = (selector) => {
                        const el = document.querySelector(selector);
                        return el ? el.innerText.trim() : null;
                    };

                    // Description
                    const desc = getText('.org-about-us-organization-description__text')
                        || getText('[data-view-name="about-module"]');

                    // Helper: find value near a label text
                    const findNear = (labelText) => {
                        const items = document.querySelectorAll('dt, .org-page-details__definition-term, [class*="label"], [class*="detail"]');
                        for (const item of items) {
                            if (item.innerText && item.innerText.includes(labelText)) {
                                const next = item.nextElementSibling;
                                if (next) return next.innerText.trim();
                                const parent = item.parentElement;
                                if (parent) {
                                    const dd = parent.querySelector('dd');
                                    if (dd) return dd.innerText.trim();
                                }
                            }
                        }
                        // Fallback: scan all text for label pattern
                        const allText = document.body.innerText;
                        const regex = new RegExp(labelText + '[\\\\s\\\\n]+([^\\\\n]+)', 'i');
                        const m = allText.match(regex);
                        return m ? m[1].trim() : null;
                    };

                    return {
                        description: desc,
                        employee_range: findNear('employee'),
                        hq: findNear('Headquarters') || findNear('Hauptsitz'),
                        industry: findNear('Industry') || findNear('Branche'),
                        founded_year: findNear('Founded') || findNear('Gegründet'),
                        website: findNear('Website'),
                        company_type: findNear('Company type') || findNear('Unternehmensform'),
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
