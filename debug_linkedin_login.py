#!/usr/bin/env python3
"""
LinkedIn login debugger — läuft im Docker-Container.

Ausführen:
    docker exec -it jobtracker-backend python3 /app/debug_linkedin_login.py
"""
import asyncio
import json
import re
import sqlite3
from pathlib import Path
from cryptography.fernet import Fernet

LOGIN_URL = "https://www.linkedin.com/login"

EMAIL_SELECTORS = [
    "input[autocomplete='username']",
    "#username",
    "input[name='session_key']",
    "input[type='email']",
    "input[type='text']",
]
PASS_SELECTORS = [
    "input[autocomplete='current-password']",
    "#password",
    "input[name='session_password']",
    "input[type='password']",
]


def get_credentials():
    data_dir = Path("/app/data")
    fernet = Fernet((data_dir / "fernet.key").read_bytes().strip())
    conn = sqlite3.connect(str(data_dir / "jobtracker.db"))
    row = conn.execute("SELECT email, password_enc FROM linkedin_sync LIMIT 1").fetchone()
    conn.close()
    return row[0], fernet.decrypt(row[1].encode()).decode()


async def inspect_inputs(page, selectors, label):
    print(f"\n--- {label} ---")
    for sel in selectors:
        loc = page.locator(sel)
        count = await loc.count()
        if count == 0:
            print(f"  '{sel}': nicht gefunden")
            continue
        print(f"  '{sel}': {count} element(s)")
        for i in range(count):
            el = loc.nth(i)
            visible = await el.is_visible()
            enabled = await el.is_enabled()
            bb = await el.bounding_box()
            val = await el.input_value() if visible else "N/A"
            print(f"    [{i}] visible={visible} enabled={enabled} bbox={bb} value='{val}'")


async def find_fillable(page, selectors, label, timeout=12):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for sel in selectors:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                el = loc.nth(i)
                try:
                    if await el.is_visible() and await el.is_enabled():
                        print(f"  ✓ {label}: '{sel}'[{i}]")
                        return el
                except Exception:
                    continue
        await asyncio.sleep(0.4)
    return None


async def main():
    email, password = get_credentials()
    print(f"Credentials: {email}")

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
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

        page = await context.new_page()
        print(f"\n→ goto {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)
        print(f"  URL: {page.url}")
        print(f"  Titel: {await page.title()}")

        # Alle Inputs inspizieren
        await inspect_inputs(page, EMAIL_SELECTORS, "E-Mail-Felder")
        await inspect_inputs(page, PASS_SELECTORS, "Passwort-Felder")

        # Seiten-Text
        snippet = await page.evaluate("document.body.innerText.slice(0, 400)")
        print(f"\n--- Seitentext ---\n{snippet}\n")

        # Screenshot
        await page.screenshot(path="/app/data/debug_login.png")
        print("Screenshot: /app/data/debug_login.png")

        # Login-Versuch
        print("\n→ Suche E-Mail-Feld…")
        email_loc = await find_fillable(page, EMAIL_SELECTORS, "email")
        if not email_loc:
            print("FEHLER: Kein E-Mail-Feld gefunden!")
            await browser.close()
            return

        await email_loc.fill(email)
        print("→ E-Mail gefüllt")

        print("→ Suche Passwort-Feld…")
        pass_loc = await find_fillable(page, PASS_SELECTORS, "password")
        if pass_loc:
            await pass_loc.fill(password)
            print("→ Passwort gefüllt")
        else:
            print("→ Passwort-Feld nicht gefunden, Tab+Type als Fallback")
            await page.keyboard.press("Tab")
            await page.keyboard.type(password)

        # Screenshot nach Eingabe
        await page.screenshot(path="/app/data/debug_login_filled.png")
        print("Screenshot nach Eingabe: /app/data/debug_login_filled.png")

        print("→ Suche Submit-Button…")
        submit_selectors = [
            '[data-litms-control-urn="login-submit"]',
            'button[type="submit"]',
            'button[aria-label*="inloggen" i]',
            'button[aria-label*="sign in" i]',
        ]
        submit_loc = await find_fillable(page, submit_selectors, "submit", timeout=5)
        if submit_loc:
            await submit_loc.click()
            print("→ Submit geklickt")
        else:
            print("→ Submit per Enter")
            await page.keyboard.press("Enter")

        print("→ Warte auf Weiterleitung…")
        try:
            await page.wait_for_url(
                re.compile(r"linkedin\.com/(feed|checkpoint|jobs|my-items|uas/login)"),
                timeout=20000,
            )
            print(f"  → {page.url}")
            if "checkpoint" in page.url or "challenge" in page.url:
                print("ACHTUNG: 2FA/Verification erforderlich!")
            else:
                print("✓ Login erfolgreich!")
        except Exception as e:
            print(f"FEHLER Weiterleitung: {e}")
            print(f"  URL: {page.url}")
            await page.screenshot(path="/app/data/debug_login_error.png")
            print("Screenshot: /app/data/debug_login_error.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
