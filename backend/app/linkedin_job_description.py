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
    // LinkedIn now hashes all CSS class names (atomic/CSS-in-JS build) — class-based
    // selectors like ".jobs-unified-top-card__company-name" no longer exist in the DOM.
    // Use structural/semantic signals instead, which survive these rebuilds:

    // 1) The job header always links to the posting company's LinkedIn page —
    //    the first such link in document order is that header link.
    const bad = new Set(['linkedin', 'show more', 'mehr anzeigen']);
    const companyLinks = [...document.querySelectorAll('a[href*="linkedin.com/company/"], a[href^="/company/"]')];
    for (const a of companyLinks) {
        const t = (a.innerText || '').split('\\n')[0].trim();
        if (t && t.length > 0 && t.length < 120 && !bad.has(t.toLowerCase())) return t;
    }

    // 2) <title> follows the pattern "<Job Title> | <Company> | LinkedIn"
    const parts = document.title.split('|').map(s => s.trim()).filter(Boolean);
    if (parts.length >= 3 && /linkedin/i.test(parts[parts.length - 1])) {
        return parts[parts.length - 2];
    }

    // 3) og:title meta — usually "<Company> hiring <Title> in <Location>"
    const og = document.querySelector('meta[property="og:title"]');
    const ogContent = og && og.getAttribute('content');
    if (ogContent) {
        const m = ogContent.match(/^(.+?)\\s+hiring\\s+/i);
        if (m) return m[1].trim();
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

        # LinkedIn hashes all CSS class names per build, so there is no stable
        # selector left to wait on here — _DESCRIPTION_JS's tree-walker fallback
        # doesn't need one. A short settle delay is enough after networkidle.
        await asyncio.sleep(1.0)

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

        # Retry once after extra scroll/wait in case the header was still
        # hydrating on first evaluate.
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
