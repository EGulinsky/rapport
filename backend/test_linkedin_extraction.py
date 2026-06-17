"""
Standalone LinkedIn extraction test — no Django/FastAPI imports needed.
Loads captured HTML from /tmp/linkedin_capture_*.html and runs the
extraction + pagination JS against them in headless Playwright.

Usage:
    python3 test_linkedin_extraction.py [INTERVIEWS|ARCHIVED|APPLIED|all]
"""
import asyncio
import pathlib
import re
import sys

# ─── Inline JS (copy from sync_linkedin.py) ────────────────────────────────
EXTRACT_JOBS_JS = r"""
() => {
    const jobIdRe = /\/(?:view|collections|search|detail)\/([\d]{6,})/;
    const allLinks = Array.from(document.querySelectorAll('a[href]')).filter(a => {
        const txt = (a.innerText || '').trim();
        return txt.length > 5 && jobIdRe.test(a.href || '');
    });
    const cardEls = Array.from(document.querySelectorAll('[data-job-id], [data-entity-urn*="jobPosting"]'));
    for (const card of cardEls) {
        let jobId2 = card.getAttribute('data-job-id') || '';
        if (!jobId2) {
            const urn = card.getAttribute('data-entity-urn') || '';
            const um = urn.match(/:(\d{6,})$/);
            if (um) jobId2 = um[1];
        }
        if (!jobId2) continue;
        const titleLink = card.querySelector('a[href]');
        if (titleLink && !(titleLink.href || '').includes(jobId2)) {
            if (!(titleLink.href || '').includes('/jobs/')) allLinks.push(titleLink);
        }
    }
    const seenIds = new Set();
    const titleLinks = allLinks.filter(a => {
        const m = (a.href || '').match(jobIdRe);
        const id = m ? m[1] : '';
        if (!id || seenIds.has(id)) return false;
        seenIds.add(id);
        return true;
    });
    return titleLinks.map(link => {
        const href = link.href || '';
        const m = href.match(jobIdRe);
        const jobId = m ? m[1] : '';
        const title = (link.innerText || '').trim();
        const MAX_CARD = 500;
        let el = link;
        let contextText = '';
        let dateHint = '';
        for (let i = 0; i < 15; i++) {
            el = el.parentElement;
            if (!el) break;
            const t = (el.innerText || '').trim();
            if (t.length > title.length + 10 && t.length <= MAX_CARD) {
                if (!contextText) contextText = t;
                if (t.length > title.length + 30) { contextText = t; break; }
            }
        }
        const card = link.closest('li, [data-job-id], article, [class*="job-card"]') || link.parentElement;
        if (card) {
            const full = (card.innerText || '').trim();
            if (full.length > contextText.length && full.length <= MAX_CARD) contextText = full;
            card.querySelectorAll('[aria-label]').forEach(el => {
                const lbl = el.getAttribute('aria-label') || '';
                if (/applied|ago|\d+[dwm]/i.test(lbl)) dateHint = lbl;
            });
        }
        return {id: jobId, title, context: contextText.slice(0, 800), dateHint};
    });
}
"""

NEXT_BUTTON_JS = r"""
() => {
    let btn = document.querySelector('.artdeco-pagination__button--next:not([disabled])');
    if (btn && btn.offsetParent !== null) return 'artdeco-class: ' + btn.outerHTML.slice(0, 300);
    const nextWords = ['next', 'nächste', 'weiter'];
    for (const el of document.querySelectorAll('button, a[role="button"]')) {
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
        const txt = (el.innerText || '').toLowerCase().trim();
        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
        if (nextWords.some(w => txt === w || aria.includes(w)))
            return 'text-match: ' + (txt || aria) + ' | html: ' + el.outerHTML.slice(0, 300);
    }
    const testBtn = document.querySelector('[data-test-pagination-page-btn="next"]');
    if (testBtn) return 'data-test: ' + testBtn.outerHTML.slice(0, 300);
    // Last resort: find any pagination-like button
    const allPag = Array.from(document.querySelectorAll('[class*="pagination"]'));
    return 'pagination elements: ' + allPag.map(e => e.tagName + '.' + e.className.slice(0,60)).join(', ');
}
"""

ALL_LINKS_JS = r"""
() => {
    // Show ALL hrefs that contain a long number (potential job ID)
    const jobRe = /\/([\d]{6,})/;
    return Array.from(document.querySelectorAll('a[href]'))
        .filter(a => jobRe.test(a.href))
        .map(a => ({
            href: a.href.slice(0, 120),
            text: (a.innerText || '').trim().slice(0, 60),
            cls: a.className.slice(0, 60)
        }))
        .slice(0, 30);
}
"""


async def test_html(card_type: str, html_path: pathlib.Path):
    from playwright.async_api import async_playwright

    print(f"\n{'='*70}")
    print(f"[{card_type}]  {html_path.name}  ({html_path.stat().st_size // 1024} KB)")
    print(f"{'='*70}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.set_content(html_path.read_text(encoding="utf-8"), wait_until="domcontentloaded")
        await asyncio.sleep(1)

        # 1. Run extraction JS
        raw_items = await page.evaluate(EXTRACT_JOBS_JS)
        print(f"\nExtracted jobs: {len(raw_items)}")
        for item in raw_items:
            print(f"  [{item.get('id','?')}] {item.get('title','')[:70]}")
            ctx = item.get('context', '')
            print(f"    context: {ctx[:120]!r}")

        # 2. All links with numeric ID
        all_links = await page.evaluate(ALL_LINKS_JS)
        print(f"\nAll job-numeric links in DOM ({len(all_links)}):")
        for lnk in all_links:
            print(f"  {lnk['href']}  →  {lnk['text'][:50]!r}")

        # 3. Next button detection
        next_result = await page.evaluate(NEXT_BUTTON_JS)
        print(f"\nNext-button detection:\n  {next_result}")

        # 4. All buttons
        buttons = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim().slice(0, 60),
                aria: b.getAttribute('aria-label') || '',
                cls: b.className.slice(0, 80),
                disabled: b.disabled,
                ariaDisabled: b.getAttribute('aria-disabled')
            })).filter(b => b.text || b.aria).slice(0, 30)
        """)
        print(f"\nButtons ({len(buttons)}):")
        for b in buttons:
            dis = " [DISABLED]" if b['disabled'] or b.get('ariaDisabled') == 'true' else ""
            label = b['text'] or b['aria']
            print(f"  '{label}'{dis}  aria='{b['aria']}'  cls={b['cls'][:60]}")

        await browser.close()


async def main():
    target = sys.argv[1].upper() if len(sys.argv) > 1 else "ALL"
    categories = ["SAVED", "IN_PROGRESS", "APPLIED", "INTERVIEWS", "ARCHIVED"]
    if target != "ALL":
        categories = [target]

    found = False
    for cat in categories:
        html_path = pathlib.Path(f"/tmp/linkedin_capture_{cat}.html")
        if not html_path.exists():
            print(f"[{cat}] No capture file at {html_path} — run a sync first")
            continue
        found = True
        await test_html(cat, html_path)

    if not found:
        print("No HTML capture files found. Run a LinkedIn sync with v2.0.35+ first.")


if __name__ == "__main__":
    asyncio.run(main())
