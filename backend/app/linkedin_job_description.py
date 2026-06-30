"""
Load the full job description text from a LinkedIn job posting URL.
Reuses the Playwright login/consent helpers from sync_linkedin.py.
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy.orm import Session

from app import models

_DESCRIPTION_JS = """() => {
    // LI hashes all CSS class names — use structural heuristics instead
    function insideNavOrChrome(el) {
        let n = el;
        while (n) {
            const tag = n.tagName;
            if (tag === 'NAV' || tag === 'HEADER' || tag === 'FOOTER') return true;
            const role = n.getAttribute && n.getAttribute('role');
            if (role === 'navigation' || role === 'banner') return true;
            n = n.parentElement;
        }
        return false;
    }

    // Try known stable selectors first (future-proofing)
    const stableSelectors = [
        '#job-details',
        '[data-view-name="job-view-description"]',
        'article.jobs-description',
        'div[class*="show-more-less-html"]',
    ];
    for (const sel of stableSelectors) {
        const el = document.querySelector(sel);
        if (el && el.innerText.trim().length > 200 && !insideNavOrChrome(el)) return el.innerHTML;
    }

    // Structural fallback: find "About the job" / Stellenbeschreibung section
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let tnode;
    while (tnode = walker.nextNode()) {
        if (/^\\s*(about the job|über die stelle|stellenbeschreibung)\\s*$/i.test(tnode.textContent)) {
            let el = tnode.parentElement;
            for (let i = 0; i < 6; i++) {
                if (!el) break;
                const sib = el.nextElementSibling;
                if (sib && (sib.innerText || '').trim().length > 200) return sib.innerHTML;
                el = el.parentElement;
            }
        }
    }
    // Last resort: element with 3-40 p/li descendants, no chrome children, 400-8000 chars
    const candidates = [...document.querySelectorAll('div, article, section')]
        .filter(el => {
            if (insideNavOrChrome(el)) return false;
            if (el.querySelector('nav, header, footer, [role="navigation"]')) return false;
            const t = (el.innerText || '').trim();
            if (t.length < 400 || t.length > 8000) return false;
            if (/skip to (search|main|content)/i.test(t)) return false;
            return true;
        })
        .map(el => ({
            el,
            richness: el.querySelectorAll('p, li, ul, ol, h2, h3, strong').length,
        }))
        .filter(c => c.richness >= 3 && c.richness <= 60)
        .sort((a, b) => b.richness - a.richness);

    if (candidates.length > 0) return candidates[0].el.innerHTML;
    return '';
}"""

_COMPANY_NAME_JS = """() => {
    // Stable structural selectors for the job posting's hiring/posting company,
    // tried in order (logged-in unified top card, public top card, generic fallback).
    const selectors = [
        '.job-details-jobs-unified-top-card__company-name a',
        '.job-details-jobs-unified-top-card__company-name',
        '.jobs-unified-top-card__company-name a',
        '.jobs-unified-top-card__company-name',
        '.topcard__org-name-link',
        '.topcard__flavor--black-link',
        'a[data-tracking-control-name="public_jobs_topcard-org-name"]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        const t = el && el.innerText && el.innerText.trim();
        if (t && t.length > 0 && t.length < 120) return t;
    }

    // Fallback: parse <meta property="og:title"> — usually "<Company> hiring <Title> in <Location>"
    const og = document.querySelector('meta[property="og:title"]');
    const ogContent = og && og.getAttribute('content');
    if (ogContent) {
        const m = ogContent.match(/^(.+?)\\s+hiring\\s+/i);
        if (m) return m[1].trim();
    }

    // Fallback for anonymized/"confidential" postings: LinkedIn still shows the
    // recruiter who posted it ("hiring team" / "hirer card"), whose subtitle
    // usually reads "<Title> at <Company>" — that company is the headhunter/agency.
    const hirerSelectors = [
        '.hirer-card__hirer-information',
        '.job-details-people-who-can-help__hirer-information',
        '[data-test-id="hirer-information"]',
        '.jobs-poster__name',
    ];
    for (const sel of hirerSelectors) {
        const el = document.querySelector(sel);
        const t = el && el.innerText && el.innerText.trim();
        if (!t) continue;
        const m = t.match(/\\b(?:at|bei)\\s+(.+)$/im);
        if (m && m[1].trim().length > 0 && m[1].trim().length < 120) return m[1].trim();
    }

    return '';
}"""


async def load_job_description(job_url: str, db: Session) -> dict:
    """Load job description text and posting company name from a LinkedIn job posting page.

    Returns {"description": str, "company": str | None}.
    """
    cfg = db.query(models.LinkedInSync).first()
    if not cfg or not cfg.email or not cfg.password_enc:
        raise ValueError("LinkedIn nicht konfiguriert — bitte zuerst in den Einstellungen unter 'LinkedIn' verbinden.")

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
                raise ValueError("LinkedIn-Login fehlgeschlagen")
            await page.goto(job_url, wait_until="load", timeout=30000)
            await _accept_consent(page)

        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

        await page.evaluate("window.scrollBy(0, 600)")
        await asyncio.sleep(0.5)

        try:
            btn = page.locator('button:has-text("See more"), button:has-text("Mehr anzeigen"), button[aria-label*="description"]').first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        try:
            await page.wait_for_selector(
                '#job-details, .jobs-description__content, .description__text, [data-view-name="job-view-description"], div[class*="show-more-less-html"]',
                timeout=8000,
            )
        except Exception:
            pass
        await asyncio.sleep(0.5)

        description = ""
        try:
            description = await page.evaluate(_DESCRIPTION_JS)
        except Exception:
            pass

        company = ""
        try:
            company = await page.evaluate(_COMPANY_NAME_JS)
        except Exception:
            pass

        # Top-card selectors miss on anonymized/"confidential" postings — the
        # hiring-team/hirer-card fallback lives further down the page, so give
        # it a chance to lazy-load before giving up.
        if not company:
            try:
                await page.evaluate("window.scrollBy(0, 1200)")
                await asyncio.sleep(1.0)
                company = await page.evaluate(_COMPANY_NAME_JS)
            except Exception:
                pass

        await browser.close()

    if not description:
        raise ValueError("Stellenbeschreibung konnte nicht extrahiert werden — Seitenstruktur evtl. geändert oder Zugriff verweigert.")

    return {"description": description, "company": company or None}
