"""
Standalone test for LinkedIn job extraction JS.
Loads captured HTML files from /tmp/linkedin_capture_*.html and runs
the same extraction JS used in sync_linkedin.py — no LinkedIn login needed.

Usage:
    # First run a sync to capture HTML files, then:
    python test_linkedin_extraction.py
"""
import asyncio
import pathlib
import sys
import json

# Import the JS and parse logic from the scraper
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from app.routers.sync_linkedin import _EXTRACT_JOBS_JS, _parse_date, CATEGORIES


async def test_category(card_type: str, html: str):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.set_content(html, wait_until="domcontentloaded")
        await asyncio.sleep(1)

        # Run extraction JS
        raw_items = await page.evaluate(_EXTRACT_JOBS_JS)

        # Check for pagination button
        next_result = await page.evaluate("""
            () => {
                let btn = document.querySelector('.artdeco-pagination__button--next:not([disabled])');
                if (btn && btn.offsetParent !== null) return 'artdeco-class: ' + btn.outerHTML.slice(0, 200);
                const nextWords = ['next', 'nächste', 'weiter'];
                for (const el of document.querySelectorAll('button, a[role="button"]')) {
                    if (el.disabled) continue;
                    const txt = (el.innerText || '').toLowerCase().trim();
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    if (nextWords.some(w => txt === w || aria.includes(w)))
                        return 'text-match: ' + (txt || aria) + ' | ' + el.outerHTML.slice(0, 200);
                }
                const testBtn = document.querySelector('[data-test-pagination-page-btn="next"]');
                if (testBtn) return 'data-test: ' + testBtn.outerHTML.slice(0, 200);
                return null;
            }
        """)

        # All buttons on page
        buttons = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim().slice(0, 50),
                aria: b.getAttribute('aria-label') || '',
                cls: b.className.slice(0, 80),
                disabled: b.disabled
            })).filter(b => b.text || b.aria)
        """)

        # All links with job-like hrefs
        job_links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .filter(a => /\\/(view|collections|detail|interviews)\\/(\\d{6,})/.test(a.href))
                .map(a => ({href: a.href, text: (a.innerText || '').trim().slice(0, 60)}))
        """)

        await browser.close()
        return raw_items, next_result, buttons, job_links


async def main():
    capture_dir = pathlib.Path("/tmp")
    found_any = False

    for card_type, label, _, _ in CATEGORIES:
        html_file = capture_dir / f"linkedin_capture_{card_type}.html"
        if not html_file.exists():
            print(f"[{card_type}] No capture file — run a sync first")
            continue

        found_any = True
        html = html_file.read_text(encoding="utf-8")
        print(f"\n{'='*60}")
        print(f"[{card_type}] ({label}) — {html_file.stat().st_size // 1024}KB")
        print(f"{'='*60}")

        raw_items, next_result, buttons, job_links = await test_category(card_type, html)

        print(f"Jobs extracted by JS: {len(raw_items)}")
        for item in raw_items[:5]:
            print(f"  - [{item.get('id')}] {item.get('title', '')[:60]}")
            ctx = item.get('context', '')
            print(f"    context[:100]: {ctx[:100]!r}")

        print(f"\nJob-like links in DOM: {len(job_links)}")
        for lnk in job_links[:5]:
            print(f"  {lnk['href'][:80]}  →  {lnk['text'][:50]}")

        print(f"\nNext-button result: {next_result}")

        print(f"\nAll buttons ({len(buttons)}):")
        for b in buttons[:15]:
            status = " [DISABLED]" if b['disabled'] else ""
            print(f"  '{b['text'] or b['aria']}'{status}  cls={b['cls'][:60]}")

    if not found_any:
        print("\nNo capture files found in /tmp/linkedin_capture_*.html")
        print("Run a LinkedIn sync first (the sync saves HTML automatically).")


if __name__ == "__main__":
    asyncio.run(main())
