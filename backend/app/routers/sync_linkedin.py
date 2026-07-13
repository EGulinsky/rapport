"""
LinkedIn Playwright scraper — scrapes the user's own "Applied Jobs" page.
Credentials are stored encrypted; session cookies are persisted so re-login is rare.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.provider import decrypt_api_key, encrypt_api_key
from app.audit import add_audit
from app.i18n_strings import resolve_ui_language, t
from app.database import get_db
from app import models
from app.routers.applications import _ensure_company_profile
from app.auth.dependencies import get_current_user
from app.logger import get_logger

log = get_logger("sync", source="linkedin")

router = APIRouter(prefix="/api/sync/linkedin", tags=["sync"])


def _audit_backfill(db: Session, app: "models.Application", field: str, old_value, new_value, user_id, match_reason: str | None = None) -> None:
    """Protokolliert eine stille Feld-Ergänzung an einer bestehenden Bewerbung durch den LinkedIn-Sync."""
    add_audit(db, "update", "linkedin", app_id=app.id,
              field=field, old_value=old_value, new_value=new_value,
              reason_key="auto_filled_from_linkedin_with_reason" if match_reason else "auto_filled_from_linkedin",
              reason_params={"match_reason": match_reason} if match_reason else None,
              user_id=user_id)


def _commit_with_retry(db, retries: int = 5, delay: float = 2.0) -> None:
    """Commit with retry on SQLite 'database is locked' errors."""
    for attempt in range(retries):
        try:
            db.commit()
            return
        except Exception as exc:
            if attempt < retries - 1 and "locked" in str(exc).lower():
                db.rollback()
                time.sleep(delay * (attempt + 1))
            else:
                raise

# ── In-memory task state ──────────────────────────────────────────────────────

_state: dict = {
    "status": "idle",      # idle | running | done | error | needs_login | needs_2fa
    "step": "",
    "processed": 0,
    "total": 0,
    "created": 0,
    "updated": 0,
    "skipped": 0,
    "errors": [],
    "raw_jobs": [],        # all scraped jobs (for status endpoint)
    "msg_processed": 0,    # conversations scanned for messages
    "msg_created": 0,      # message events created
    "started_at": None,
    "finished_at": None,
}

# 2FA handoff: background task polls this; submit-2fa endpoint sets it
_2fa_code_input: Optional[str] = None


def _reset_state():
    global _2fa_code_input
    _2fa_code_input = None
    _state.update({
        "status": "idle",
        "step": "",
        "processed": 0,
        "total": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "msg_processed": 0,
        "msg_created": 0,
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
def get_config(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
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
def save_config(
    payload: LinkedInConfigWrite,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cfg = db.query(models.LinkedInSync).first()
    if cfg:
        cfg.email = payload.email.strip()
        cfg.password_enc = encrypt_api_key(payload.password)
        cfg.session_cookies = None  # force re-login with new credentials
    else:
        cfg = models.LinkedInSync(
            email=payload.email.strip(),
            password_enc=encrypt_api_key(payload.password),
            user_id=current_user.id,
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
def delete_config(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Bulk .delete() umgeht den zentralen Mandanten-Filter — daher explizit gefiltert.
    db.query(models.LinkedInSync).filter(models.LinkedInSync.user_id == current_user.id).delete()
    db.commit()
    _reset_state()
    return {"ok": True}


# ── Status / run endpoints ────────────────────────────────────────────────────

@router.get("/status")
def get_status(current_user: models.User = Depends(get_current_user)):
    return dict(_state)


class RunSyncRequest(BaseModel):
    target_app_id: int | None = None


@router.post("/run")
def run_sync(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    body: RunSyncRequest = Body(default=RunSyncRequest()),
    current_user: models.User = Depends(get_current_user),
):
    cfg = db.query(models.LinkedInSync).first()
    if not cfg:
        raise HTTPException(400, "LinkedIn not configured")
    if _state["status"] == "running":
        raise HTTPException(409, "Sync already running")

    _reset_state()
    _state["status"] = "running"
    _state["started_at"] = datetime.now(timezone.utc).isoformat()
    background_tasks.add_task(_run_sync_task, cfg.id, body.target_app_id)
    return dict(_state)


@router.post("/clear-session")
def clear_session(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cfg = db.query(models.LinkedInSync).first()
    if cfg:
        cfg.session_cookies = None
        db.commit()
    return {"ok": True}


class TwoFaPayload(BaseModel):
    code: str


@router.post("/submit-2fa")
def submit_two_fa(payload: TwoFaPayload, current_user: models.User = Depends(get_current_user)):
    global _2fa_code_input
    if _state["status"] != "needs_2fa":
        raise HTTPException(409, "No 2FA pending")
    _2fa_code_input = payload.code.strip()
    return {"ok": True}


# ── Playwright scraper ────────────────────────────────────────────────────────

LOGIN_URL = "https://www.linkedin.com/login"
_TRACKER  = "https://www.linkedin.com/jobs-tracker/?stage="

# (card_type, label, default_status, max_pages, url)
#
# LinkedIn's "In Progress" tab is a combined view of two distinct sub-stages that
# are NOT reachable via a single URL (?stage=in-progress renders an empty page —
# the tab is a client-side-only aggregate). Each sub-stage has its own working
# ?stage= slug and must be scraped separately:
#   - "draft":         job saved but application not started → not yet applied
#   - "clicked_apply":  applicant clicked "Apply" on LinkedIn but hasn't confirmed
#                       finishing it (LinkedIn itself asks "Did you finish applying?")
# Both represent a not-yet-confirmed application, so both map to "prospecting"
# ("Anbahnung") rather than "applied".
CATEGORIES: list[tuple[str, str, str, int, str]] = [
    ("SAVED",         "Gespeichert",    "prospecting", 99, _TRACKER + "saved"),
    ("DRAFT",         "Entwurf",        "prospecting", 99, _TRACKER + "draft"),
    ("CLICKED_APPLY", "Beworben (unbestätigt)", "prospecting", 99, _TRACKER + "clicked_apply"),
    ("APPLIED",       "Beworben",       "applied",     99, _TRACKER + "applied"),
    ("INTERVIEWS",    "Interviews",     "hr",          99, _TRACKER + "interview"),
    ("ARCHIVED",      "Archiviert",     "rejected",    99, _TRACKER + "archived"),
]

# LinkedIn status footer text → override main_status
# Note: "no longer accepting applications" is intentionally excluded —
# it reflects the job posting status, not the applicant's tracker status.
_STATUS_MAP = {
    "application viewed":          ("hr",           None),
    "bewerbung gesehen":           ("hr",           None),
    "offer":                       ("negotiating",  None),
    "angebot":                     ("negotiating",  None),
    "interview":                   ("hr",           "1_scheduled"),
}


def _parse_date(text: str) -> Optional[str]:
    """Parse LinkedIn date strings → YYYY-MM-DD."""
    from datetime import timedelta
    t = text.lower().strip()
    # short form: "6d ago", "2w ago", "3mo ago"
    m = re.search(r"(\d+)\s*d\b", t)
    if m:
        return (datetime.now() - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*w\b", t)
    if m:
        return (datetime.now() - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*mo\b", t)
    if m:
        return (datetime.now() - timedelta(days=int(m.group(1)) * 30)).strftime("%Y-%m-%d")
    # "2m ago" — bare 'm' for months (word boundary ensures 'mo' above takes priority)
    m = re.search(r"(\d+)\s*m\b", t)
    if m:
        return (datetime.now() - timedelta(days=int(m.group(1)) * 30)).strftime("%Y-%m-%d")
    # long form: "3 days ago", "2 weeks ago", "1 month ago"
    m = re.search(r"(\d+)\s+day", t)
    if m:
        return (datetime.now() - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s+week", t)
    if m:
        return (datetime.now() - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s+month", t)
    if m:
        return (datetime.now() - timedelta(days=int(m.group(1)) * 30)).strftime("%Y-%m-%d")
    # absolute: "1/15/2025"
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


# LinkedIn uses these selectors depending on version/locale
_EMAIL_SELECTORS = ["input[autocomplete='username']", "#username", "input[name='session_key']", "input[type='email']"]
_PASS_SELECTORS  = ["input[autocomplete='current-password']", "#password", "input[name='session_password']", "input[type='password']"]


async def _find_visible_locator(page, selectors: list[str], timeout_total: int = 10000):
    """Find the first *visible* element among all candidate selectors and their matches."""
    import time
    deadline = time.monotonic() + timeout_total / 1000
    while time.monotonic() < deadline:
        for sel in selectors:
            loc = page.locator(sel)
            try:
                count = await loc.count()
            except Exception:
                continue
            for i in range(count):
                try:
                    if await loc.nth(i).is_visible():
                        return loc.nth(i)
                except Exception:
                    continue
        await asyncio.sleep(0.3)
    return None


_PIN_SELECTORS = [
    "input[name='pin']",
    "input[id*='pin']",
    "input[id*='verification']",
    "input[autocomplete='one-time-code']",
    "input[inputmode='numeric']",
    "input[type='number']",
    "input[type='tel']",
]

_REMEMBER_SELECTORS = [
    "#remember-me-prompt__confirm-btn",
    "button[aria-label*='remember' i]",
    "button[aria-label*='erinnern' i]",
    "button[data-litms-control-urn*='remember']",
]


async def _wait_for_2fa_code(timeout: float = 300.0) -> Optional[str]:
    """Poll the global until the submit-2fa endpoint sets a code."""
    global _2fa_code_input
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _2fa_code_input is not None:
            code = _2fa_code_input
            _2fa_code_input = None
            return code
        await asyncio.sleep(0.5)
    return None


def _is_checkpoint_url(url: str) -> bool:
    return "checkpoint" in url or "challenge" in url or "uas/login" in url


async def _handle_2fa_checkpoint(page, lang: str = "de") -> bool:
    """Wait for 2FA: either push-approval (auto page redirect) or manual code entry."""
    global _2fa_code_input
    _2fa_code_input = None
    _state["status"] = "needs_2fa"
    _state["step"] = t("li_2fa_prompt", lang)

    import time
    deadline = time.monotonic() + 300  # 5 min total

    while time.monotonic() < deadline:
        # ── Option A: push-notification approved → page auto-redirected ──
        current_url = page.url
        if not _is_checkpoint_url(current_url):
            _state["status"] = "running"
            _state["step"] = t("li_login_success_push", lang)
            # Accept "Remember this device" if shown
            try:
                remember_loc = await _find_visible_locator(page, _REMEMBER_SELECTORS, timeout_total=2000)
                if remember_loc:
                    await remember_loc.click()
            except Exception:
                pass
            return True

        # ── Option B: user typed a code in the app ──
        if _2fa_code_input is not None:
            code = _2fa_code_input
            _2fa_code_input = None
            _state["status"] = "running"
            _state["step"] = t("li_2fa_enter_code", lang)

            pin_loc = await _find_visible_locator(page, _PIN_SELECTORS, timeout_total=5000)
            if pin_loc:
                await pin_loc.fill(code)
            else:
                await page.keyboard.type(code)
            await page.keyboard.press("Enter")

            _state["step"] = t("li_2fa_waiting_redirect", lang)
            try:
                await page.wait_for_url(
                    re.compile(r"linkedin\.com/(feed|checkpoint|jobs|my-items|uas/login)"),
                    timeout=20000,
                )
            except Exception:
                pass

            if _is_checkpoint_url(page.url):
                _state["status"] = "error"
                _state["step"] = t("li_2fa_failed", lang)
                return False

            try:
                remember_loc = await _find_visible_locator(page, _REMEMBER_SELECTORS, timeout_total=2000)
                if remember_loc:
                    await remember_loc.click()
            except Exception:
                pass

            _state["step"] = t("li_login_success_code", lang)
            return True

        await asyncio.sleep(1)

    _state["status"] = "error"
    _state["step"] = t("li_2fa_timeout", lang)
    return False


async def _login(page, email: str, password: str, lang: str = "de") -> bool:
    """Attempt email/password login. Returns True if successful."""
    try:
        _state["step"] = t("li_login_loading_page", lang)
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        # Give JS a moment to hydrate before checking selectors
        await asyncio.sleep(2)

        _state["step"] = t("li_login_waiting_form", lang)
        email_loc = await _find_visible_locator(page, _EMAIL_SELECTORS, timeout_total=10000)
        if not email_loc:
            current_url = page.url
            title = await page.title()
            try:
                snippet = await page.evaluate("document.body.innerText.slice(0, 300)")
            except Exception:
                snippet = t("no_text_placeholder", lang)
            _state["errors"].append(
                t("li_login_form_not_found", lang, url=current_url, title=title, snippet=snippet)
            )
            _state["status"] = "needs_login"
            _state["step"] = t("li_login_no_mask", lang)
            return False

        pass_loc = await _find_visible_locator(page, _PASS_SELECTORS, timeout_total=5000)

        _state["step"] = t("li_login_entering_credentials", lang)
        await email_loc.fill(email)
        if pass_loc:
            await pass_loc.fill(password)
        else:
            await page.keyboard.press("Tab")
            await page.keyboard.type(password)
        # Submit via Enter (confirmed working; button selectors are unreliable across LI versions)
        _state["step"] = t("li_login_submit", lang)
        await page.keyboard.press("Enter")
        _state["step"] = t("li_login_waiting_redirect", lang)
        await page.wait_for_url(
            re.compile(r"linkedin\.com/(feed|checkpoint|jobs|my-items|uas/login)"),
            timeout=20000,
        )
        if "checkpoint" in page.url or "challenge" in page.url:
            return await _handle_2fa_checkpoint(page, lang)
        _state["step"] = t("li_login_success", lang)
        return True
    except Exception as e:
        _state["errors"].append(t("li_login_error", lang, error=e))
        _state["step"] = t("li_login_failed", lang, error=e)
        return False


_CONSENT_SELECTORS = [
    "button[action-type=ACCEPT]",
    "button[data-test-modal-close-btn]",
]


_HINT_KW = [
    "not moving forward", "application viewed", "resume downloaded",
    "offer", "interview scheduled",
]


async def _accept_consent(page) -> None:
    """Dismiss LinkedIn cookie consent banner if present."""
    for sel in _CONSENT_SELECTORS:
        loc = page.locator(sel)
        try:
            if await loc.count() > 0:
                await loc.first.click()
                await asyncio.sleep(2)
                return
        except Exception:
            continue


def _extract_jobs_from_text(text: str, seen_keys: set[str], default_status: str, job_urls: list[str] | None = None) -> tuple[list[dict], int]:
    """Parse all job entries from page inner_text using 'Firma · Ort' anchor scanning.

    Each line containing '·' is treated as a potential Firma · Ort anchor. Navigation
    tab pills (e.g. 'Applied · 10') are skipped. The title is the line immediately
    before the anchor; beworben/hinweis are scanned between consecutive anchors.
    This approach handles entries with and without notes uniformly.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # Collect indices of valid "Firma · Ort" anchor lines
    anchor_indices: list[int] = []
    for i, line in enumerate(lines):
        if "·" not in line or len(line) >= 300:
            continue
        parts = line.split("·", 1)
        firma = parts[0].strip()
        ort = parts[1].strip() if len(parts) > 1 else ""
        # Skip nav tab pills like "Applied · 10"
        if not firma or len(firma) < 3 or ort.strip().isdigit():
            continue
        # Title must be the preceding line and be meaningful
        if i == 0 or len(lines[i - 1]) < 4:
            continue
        anchor_indices.append(i)

    new_jobs: list[dict] = []

    for pos, dot_idx in enumerate(anchor_indices):
        parts = lines[dot_idx].split("·", 1)
        firma = parts[0].strip()
        ort = parts[1].strip() if len(parts) > 1 else ""
        title = lines[dot_idx - 1]

        next_anchor = anchor_indices[pos + 1] if pos + 1 < len(anchor_indices) else len(lines)
        following = lines[dot_idx + 1:next_anchor]

        beworben_text = ""
        for line in following:
            if re.match(r"Applied\b", line, re.IGNORECASE):
                beworben_text = line
                break

        hinweis = ""
        for line in following:
            if any(kw in line.lower() for kw in _HINT_KW):
                hinweis = line
                break

        from app.dedup import dedup_key as _dk
        dedup_key = _dk(firma, title)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        applied_date = _parse_date(beworben_text) if beworben_text else None

        status_text = (beworben_text + " " + hinweis).lower()
        mapped_status: Optional[tuple] = None
        for keyword, mapping in _STATUS_MAP.items():
            if keyword in status_text:
                mapped_status = mapping
                break

        # Assign job URL by position within the deduplicated entries seen so far
        job_url = job_urls[len(new_jobs)] if job_urls and len(new_jobs) < len(job_urls) else None

        new_jobs.append({
            "id": "",
            "title": title,
            "company": firma,
            "ort": ort,
            "applied_date": applied_date,
            "default_status": default_status,
            "status_hint": mapped_status,
            "hinweis": hinweis,
            "stellenanzeige_url": job_url,
            "_raw_context": f"{firma} · {ort} | {beworben_text} | {hinweis}",
        })

    return new_jobs, len(anchor_indices)


async def _scrape_category(page, card_type: str, default_status: str, seen_ids: set[str], max_pages: int = 99, url: str = "", label: str = "", lang: str = "de") -> list[dict]:
    """Read one LinkedIn job-tracker tab via page text and 'Add note' delimiters.

    Pagination strategy:
    1. Primary: click artdeco Next button (scroll into view first)
    2. Fallback: detect page number buttons via aria-label
    3. Stop when no new jobs found on a page or no Next button visible
    """
    base_url = url if url else _TRACKER + card_type.lower()
    jobs: list[dict] = []
    seen_keys: set[str] = set()

    try:
        await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return []

    landed_url = page.url
    if "login" in landed_url or "authwall" in landed_url or "jobs-tracker" not in landed_url:
        _state["errors"].append(f"[DEBUG] {card_type}: goto {base_url!r} → landed on {landed_url!r} — skip")
        return []

    await _accept_consent(page)
    # Extra wait for SPA to render job cards
    await asyncio.sleep(4)

    # Save first-page HTML for offline debugging
    try:
        html = await page.content()
        import pathlib
        pathlib.Path(f"/tmp/linkedin_capture_{card_type}.html").write_text(html, encoding="utf-8")
    except Exception:
        pass

    for page_num in range(max_pages):
        # Scroll to bottom: reveals lazy-loaded cards and pagination buttons
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)

        text = await page.inner_text("body")

        # Extract unique job-listing URLs (desktop+mobile renders each link twice)
        try:
            raw_links: list[str] = await page.evaluate(
                "() => [...new Set([...document.querySelectorAll('a[href*=\"/jobs/view/\"]')]"
                ".map(a => a.href.split('?')[0].replace(/\\/$/, '')))]"
            )
        except Exception:
            raw_links = []

        new_jobs, chunk_count = _extract_jobs_from_text(text, seen_keys, default_status, raw_links)
        jobs.extend(new_jobs)
        _state["step"] = t("li_page_result", lang, label=label or card_type, page=page_num + 1, count=len(jobs))

        has_next_text = bool(re.search(r'\bNext\b', text[-2000:], re.IGNORECASE))
        log.debug("[LI pag] {} p{}: {} chunks, {} neue Jobs (gesamt {}), next_in_text={}",
                  card_type, page_num + 1, chunk_count, len(new_jobs), len(jobs), has_next_text)

        if page_num >= max_pages - 1:
            break

        # Try to click Next button — try multiple selectors
        clicked_next = False
        next_selectors = [
            "[data-testid='pagination-controls-next-button-visible']",
            ".artdeco-pagination__button--next:not([disabled])",
            "button[aria-label*='Next']:not([disabled])",
            "button[aria-label*='next' i]:not([disabled])",
        ]
        for sel in next_selectors:
            loc = page.locator(sel).first
            try:
                if await loc.count() > 0 and await loc.is_visible(timeout=1000):
                    await loc.scroll_into_view_if_needed(timeout=3000)
                    await asyncio.sleep(0.5)
                    await loc.click(timeout=5000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        await asyncio.sleep(4)
                    clicked_next = True
                    log.debug("[LI pag] {} p{}→{}: Next geklickt ({})", card_type, page_num + 1, page_num + 2, sel)
                    break
            except Exception:
                pass

        if not clicked_next:
            log.debug("[LI pag] {} p{}: kein Next-Button → Ende", card_type, page_num + 1)
            break

    return jobs


async def _scrape_messages(page, db: Session, apps_list: list, user_id: Optional[int] = None, lang: str = "de") -> int:
    """Scrape LinkedIn inbox and create timeline events for application-related conversations.

    Matching strategy (two passes, no blind thread-opens):
    1. PRIMARY — contact name in sidebar: LinkedIn shows the person's name in the
       conversation list. We match known contacts (linked to applications via
       contact_application) against that name. Accurate and efficient.
    2. SECONDARY — company name in message preview: when the sidebar preview text
       itself mentions a known company ("Hi, I'm reaching out from Acme…"), we catch
       initial messages from yet-unknown recruiters without needing to open the thread.
    """
    from app.routers.sync_common import load_synced_ids, mark_synced
    from app.dedup import norm_firma

    _state["step"] = t("li_messages_loading_inbox", lang)

    # PRIMARY lookup: contact full-name (lowercased) → set of linked app_ids
    name_map: dict[str, set[int]] = {}
    try:
        contacts_with_apps = (
            db.query(models.Contact)
            .filter(models.Contact.applications.any())
            .all()
        )
        for contact in contacts_with_apps:
            normalized = (contact.name or "").lower().strip()
            if len(normalized) >= 3:
                app_ids = {app.id for app in contact.applications}
                if app_ids:
                    name_map.setdefault(normalized, set()).update(app_ids)
    except Exception:
        pass

    # SECONDARY lookup: normalized company name → set of app_ids
    # Used for preview-text matching (requires ≥ 5 chars to avoid "SAP"/"BMW" noise)
    company_map: dict[str, set[int]] = {}
    for app in apps_list:
        for raw in filter(None, [app.firma, getattr(app, "zielfirma_bei_hh", None)]):
            key = norm_firma(raw)
            if len(key) >= 5:
                company_map.setdefault(key, set()).add(app.id)

    if not name_map and not company_map:
        return 0

    synced = load_synced_ids(db, "linkedin_msg")
    created = 0

    try:
        await page.goto("https://www.linkedin.com/messaging/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        # Extract conversation thread links + sidebar text (name + last-message preview)
        try:
            conv_data: list[dict] = await page.evaluate("""
                () => {
                    const seen = new Set();
                    const results = [];
                    document.querySelectorAll('a[href*="/messaging/thread/"]').forEach(a => {
                        const href = a.href.split('?')[0];
                        if (seen.has(href)) return;
                        seen.add(href);
                        const item = a.closest('li') || a.closest('[data-control-name]') || a.parentElement;
                        results.push({ href, text: item ? item.innerText : a.innerText });
                    });
                    return results;
                }
            """)
        except Exception:
            conv_data = []

        _state["msg_processed"] = len(conv_data)

        for conv in conv_data[:50]:
            href = (conv.get("href") or "").strip()
            sidebar_text = (conv.get("text") or "").lower()
            if not href:
                continue

            m = re.search(r"/messaging/thread/([^/?#]+)", href)
            if not m:
                continue
            thread_id = m.group(1)

            if thread_id in synced:
                continue

            # ── Pass 1: contact name in sidebar (person's name shown by LinkedIn) ──
            matched_ids: set[int] = set()
            matched_participant: Optional[str] = None
            for contact_name, ids in name_map.items():
                if contact_name in sidebar_text:
                    matched_ids.update(ids)
                    if not matched_participant:
                        matched_participant = contact_name.title()

            # ── Pass 2: company name in sidebar preview text ──
            if not matched_ids:
                for company_key, ids in company_map.items():
                    if company_key in sidebar_text:
                        matched_ids.update(ids)

            if not matched_ids:
                continue

            # Open conversation only for matched threads (to get message content)
            _state["step"] = t("li_messages_opening_thread", lang, thread=thread_id[:16])
            try:
                await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                full_text = await page.inner_text("body")
            except Exception:
                continue

            # ── Pass 3 (refinement): if we only matched via company (pass 2),
            #    also try contact names in the full thread text to narrow app_ids ──
            if matched_participant is None:
                refined: set[int] = set()
                for contact_name, ids in name_map.items():
                    if contact_name in full_text.lower():
                        refined.update(ids)
                if refined:
                    matched_ids &= refined if matched_ids & refined else matched_ids

            # Extract human-readable participant name for the event title
            skip = {"LinkedIn", "Messaging", "Nachrichten", "Messages", "New message", "Send"}
            lines = [ln.strip() for ln in full_text.split("\n") if 2 < len(ln.strip()) < 80]
            participant = matched_participant or next(
                (ln for ln in lines if ln not in skip), "Unbekannt"
            )

            # Message preview: first long-ish line that looks like actual content
            preview_lines = [ln.strip() for ln in full_text.split("\n")
                             if len(ln.strip()) > 20 and ln.strip() not in skip
                             and ln.strip() != participant]
            preview = preview_lines[0][:300] if preview_lines else None

            today = date.today()

            for app_id in matched_ids:
                existing = (
                    db.query(models.Event)
                    .filter_by(application_id=app_id, source="linkedin_msg", external_id=thread_id)
                    .first()
                )
                if existing:
                    continue
                msg_titel = f"LinkedIn-Nachricht: {participant[:80]}"
                msg_event = models.Event(
                    application_id=app_id,
                    typ="mail",
                    datum=today,
                    titel=msg_titel,
                    notiz=preview,
                    source="linkedin_msg",
                    external_id=thread_id,
                    user_id=user_id,
                )
                db.add(msg_event)
                db.flush()
                add_audit(db, "create", "linkedin", app_id=app_id, event_id=msg_event.id,
                          new_value=msg_titel, user_id=user_id)
                created += 1

            mark_synced(db, "linkedin_msg", thread_id, user_id)
            try:
                db.commit()
            except Exception:
                db.rollback()

    except Exception as e:
        _state["errors"].append(f"Messages-Scraper: {e}")

    _state["msg_created"] = created
    return created


def _li_job_id_from_url(url: str) -> str | None:
    """Extract LinkedIn job ID from a stellenanzeige_url like .../jobs/view/1234567890/..."""
    if not url or "linkedin.com" not in url:
        return None
    m = re.search(r"/jobs/view/(\d+)", url)
    return m.group(1) if m else None


def _quick_match(job: dict, target_app: "models.Application") -> bool:
    """Fast no-write check: does this LI job belong to target_app?"""
    from app.dedup import norm_firma, norm_rolle
    li_job_id = job.get("id", "") or _li_job_id_from_url(job.get("stellenanzeige_url", "") or "") or ""
    if li_job_id:
        if li_job_id == (target_app.linkedin_job_id or ""):
            return True
        if li_job_id == (_li_job_id_from_url(target_app.stellenanzeige_url or "") or ""):
            return True
    job_firma = norm_firma(job.get("company", ""))
    job_rolle = norm_rolle(job.get("title", ""))
    if (norm_firma(target_app.firma or "") == job_firma
            or norm_firma(target_app.zielfirma_bei_hh or "") == job_firma):
        if norm_rolle(target_app.rolle or "") == job_rolle:
            return True
    return False


def _find_or_create_application(
    db: Session, job: dict, user_id: Optional[int] = None
) -> tuple[models.Application, bool, str | None, str]:
    """Match job to existing application or create new. Returns (app, created, pending_status).

    pending_status is set when a new app was created but the LI source implies a status
    that should go through review (currently: 'rejected'). Caller must create PendingMatch.
    """
    li_job_id = job.get("id", "") or _li_job_id_from_url(job.get("stellenanzeige_url", "") or "") or ""
    lang = resolve_ui_language(db, user_id)

    clean_title = job.get("title", "")

    def _needs_rolle_cleanup(rolle: str) -> bool:
        """True if the stored rolle still contains raw LinkedIn card noise."""
        low = rolle.lower()
        return any(s in low for s in ("applied", "posted", "notes", "add note", "(hybrid)", "(remote)"))

    # 1. Exact match by LinkedIn job ID (prevents duplicates across syncs)
    if li_job_id:
        app = db.query(models.Application).filter(
            models.Application.linkedin_job_id == li_job_id
        ).first()
        if not app:
            # Also match via stellenanzeige_url that contains the LI job ID
            candidates = db.query(models.Application).filter(
                models.Application.stellenanzeige_url.isnot(None)
            ).all()
            for c in candidates:
                if _li_job_id_from_url(c.stellenanzeige_url or "") == li_job_id:
                    app = c
                    break
        if app:
            if li_job_id and not app.linkedin_job_id:
                app.linkedin_job_id = li_job_id
            if clean_title and _needs_rolle_cleanup(app.rolle or ""):
                old_rolle = app.rolle
                app.rolle = clean_title
                _audit_backfill(db, app, "rolle", old_rolle, clean_title, user_id, match_reason=t("matched_linkedin_job_id", lang, job_id=li_job_id))
            if job.get("ort") and not app.ort:
                app.ort = job["ort"]
                _audit_backfill(db, app, "ort", None, job["ort"], user_id, match_reason=t("matched_linkedin_job_id", lang, job_id=li_job_id))
            return app, False, None, f"job_id:{li_job_id}→#{app.id}"

    # 2. Normalized-equality match: both company AND role must match after
    # stripping corporate suffixes and gender markers.
    from app.dedup import norm_firma, norm_rolle
    job_firma = norm_firma(job["company"])
    job_rolle = norm_rolle(job["title"])
    is_rejected_source = (job.get("default_status") == "rejected")
    apps = db.query(models.Application).all()
    # Sort: if the incoming job is archived, try already-rejected apps first
    if is_rejected_source:
        apps = sorted(apps, key=lambda a: 0 if a.abgesagt else 1)

    for app in apps:
        company_match = (
            norm_firma(app.firma or "") == job_firma
            or norm_firma(app.zielfirma_bei_hh or "") == job_firma
        )
        role_match = norm_rolle(app.rolle or "") == job_rolle
        if company_match and role_match:
            # Backfill the job ID so future syncs use the fast path
            if li_job_id and not app.linkedin_job_id:
                app.linkedin_job_id = li_job_id
            if clean_title and _needs_rolle_cleanup(app.rolle or ""):
                old_rolle = app.rolle
                app.rolle = clean_title
                _audit_backfill(db, app, "rolle", old_rolle, clean_title, user_id, match_reason=t("matched_company_role", lang, company=repr(job['company'])))
            if job.get("ort") and not app.ort:
                app.ort = job["ort"]
                _audit_backfill(db, app, "ort", None, job["ort"], user_id, match_reason=t("matched_company_role", lang, company=repr(job['company'])))
            return app, False, None, f"firma+rolle→#{app.id}"

    # 2.5 Check merge aliases: after a manual merge the loser's identifiers are stored here
    alias = None
    if li_job_id:
        alias = db.query(models.MergeAlias).filter(
            models.MergeAlias.entity_type == "application",
            models.MergeAlias.alias_li_job_id == li_job_id,
        ).first()
    if not alias:
        for a in db.query(models.MergeAlias).filter(
            models.MergeAlias.entity_type == "application",
            models.MergeAlias.alias_firma.isnot(None),
        ).all():
            if (norm_firma(a.alias_firma or "") == job_firma
                    and norm_rolle(a.alias_rolle or "") == job_rolle):
                alias = a
                break
    if alias:
        canonical = db.get(models.Application, alias.canonical_id)
        if canonical:
            if li_job_id and not canonical.linkedin_job_id:
                canonical.linkedin_job_id = li_job_id
            return canonical, False, None, f"alias→#{canonical.id}"

    # 3. Create new application
    intended_status = job.get("default_status", "applied")
    if job.get("status_hint"):
        intended_status = job["status_hint"][0]
    # Never create with rejected — goes through review queue instead (like existing apps)
    initial_status = "applied" if intended_status == "rejected" else intended_status

    def _to_date(val):
        if val is None:
            return None
        if isinstance(val, date):
            return val
        try:
            return date.fromisoformat(str(val))
        except Exception:
            return None

    applied_date_obj = _to_date(job["applied_date"])

    new_app = models.Application(
        firma=job["company"],
        rolle=job["title"],
        ort=job.get("ort") or None,
        datum_bewerbung=applied_date_obj,
        letztes_update=applied_date_obj,
        quelle="LinkedIn",
        main_status=initial_status,
        linkedin_job_id=li_job_id or None,
        stellenanzeige_url=job.get("stellenanzeige_url") or None,
        user_id=user_id,
    )
    db.add(new_app)
    db.flush()

    add_audit(db, "create", "linkedin", app_id=new_app.id,
              new_value=f"{job['company']} – {job['title']}", user_id=user_id)

    event_typ = "bewerbung" if initial_status not in ("prospecting", "rejected") else "notiz"
    event_titel = {
        "prospecting": "Gespeichert auf LinkedIn",
        "applied":     "Bewerbung eingereicht",
        "hr":          "Interview",
        "rejected":    "Archiviert / Abgelehnt",
    }.get(initial_status, "Bewerbung eingereicht")

    li_event = models.Event(
        application_id=new_app.id,
        typ=event_typ,
        datum=applied_date_obj,
        titel=event_titel,
        source="linkedin",
        user_id=user_id,
    )
    db.add(li_event)
    db.flush()

    # Ensure a CompanyProfile exists for the new application's firma
    _ensure_company_profile(db, new_app)

    add_audit(db, "create", "linkedin", app_id=new_app.id, event_id=li_event.id,
              new_value=event_titel, user_id=user_id)
    # pending_status (review-queue trigger) nur bei "rejected" — für jeden anderen
    # intended_status wurde initial_status bereits identisch gesetzt, ein Review-
    # Vorschlag wäre dort ein sinnloser No-op ("X → X", live in PendingMatch gefunden).
    pending_status = intended_status if intended_status == "rejected" else None
    return new_app, True, pending_status, f"neu→#{new_app.id}"


_STATUS_ORDER = ["prospecting", "applied", "hr", "fb", "waiting", "negotiating", "signed", "rejected"]


def _categories_for_individual_sync(target_app: "models.Application | None") -> list[tuple]:
    """Welche LinkedIn-Kategorien beim Einzelsync (eine bestimmte Bewerbung) durchsucht
    werden. ARCHIVED wird übersprungen, außer die Bewerbung ist selbst schon abgesagt —
    eine gezielt neu gesyncte Bewerbung liegt praktisch nie im Archiv, das Durchblättern
    (bis zu 99 Seiten) macht den Einzelsync sonst unnötig langsam."""
    if target_app and target_app.main_status == "rejected":
        return CATEGORIES
    return [c for c in CATEGORIES if c[0] != "ARCHIVED"]


def _process_linkedin_job(db: Session, job: dict, user_id: Optional[int] = None) -> dict:
    """Match/create an application from one scraped LI job and apply the
    status-progression + PendingMatch-dedup rules.

    Extracted out of the sync loop's closure so this — historically the most
    bug-prone part (repeated duplicate status proposals, see issues #9/#14) —
    is directly testable without a real Playwright session.

    Returns {"result": "created"|"updated"|"skipped", "app_id": int,
    "match_grund": str, ...}."""
    app, was_created, pending_status, match_grund = _find_or_create_application(db, job, user_id)
    pfx = f"[LI #{app.id}]"
    log.debug("{} job_id={} firma={!r} rolle={!r} kat={} hint={} raw={!r} match={}",
              pfx, job.get("id", ""), job.get("company", ""), job.get("title", ""),
              job.get("_label", ""), job.get("status_hint", ""), job.get("_raw_context", ""), match_grund)

    if was_created:
        pending_match_created = False
        if pending_status:
            li_job_id_val = job.get("id", "")
            pm_ext_id = f"linkedin_{li_job_id_val}__status__{pending_status}"
            db.add(models.PendingMatch(
                source="linkedin",
                external_id=pm_ext_id,
                confidence=90,
                event_type="status_change",
                datum=date.today(),
                titel=f"Neu (LI Archiv): applied → {pending_status}",
                suggested_app_id=app.id,
                suggested_main_status=pending_status,
                status_only=True,
                user_id=user_id,
            ))
            pending_match_created = True
            log.info("{} neu angelegt, zur Überprüfung: applied → {} | match={}", pfx, pending_status, match_grund)
        else:
            log.info("{} neu angelegt: {} | match={}", pfx, app.main_status, match_grund)
        return {
            "result": "created", "app_id": app.id, "match_grund": match_grund,
            "pending_status": pending_status, "pending_match_created": pending_match_created,
        }

    lang = resolve_ui_language(db, user_id)
    job_url = job.get("stellenanzeige_url") or None
    if job_url and not app.stellenanzeige_url:
        app.stellenanzeige_url = job_url
        _audit_backfill(db, app, "stellenanzeige_url", None, job_url, user_id, match_reason=t("matches_linkedin_match", lang, match_reason=match_grund))
    if not app.datum_bewerbung and job.get("applied_date"):
        try:
            new_datum = date.fromisoformat(str(job["applied_date"]))
            app.datum_bewerbung = new_datum
            _audit_backfill(db, app, "datum_bewerbung", None, str(new_datum), user_id, match_reason=t("matches_linkedin_match", lang, match_reason=match_grund))
        except Exception:
            pass
    db.flush()

    target_status = job.get("default_status", "applied")
    if job.get("status_hint"):
        target_status = job["status_hint"][0]

    old_status = app.main_status
    cur_idx = _STATUS_ORDER.index(old_status) if old_status in _STATUS_ORDER else 0
    new_idx = _STATUS_ORDER.index(target_status) if target_status in _STATUS_ORDER else 0

    status_changed = (
        (target_status == "rejected" and old_status != "rejected")
        or (target_status != "rejected" and new_idx > cur_idx)
    )

    if not status_changed:
        log.debug("{} unverändert: {} | match={}", pfx, old_status, match_grund)
        return {"result": "skipped", "app_id": app.id, "match_grund": match_grund, "old_status": old_status}

    li_job_id_val = job.get("id", "")
    pm_ext_id = f"linkedin_{li_job_id_val}__status__{target_status}"
    already_pending = db.query(models.PendingMatch).filter(
        models.PendingMatch.source == "linkedin",
        models.PendingMatch.external_id == pm_ext_id,
        models.PendingMatch.review_status == "pending",
    ).first()
    already_reviewed = db.query(models.PendingMatch).filter(
        models.PendingMatch.suggested_app_id == app.id,
        models.PendingMatch.suggested_main_status == target_status,
        models.PendingMatch.review_status.in_(["approved", "rejected"]),
    ).first()
    pending_match_created = False
    if not already_pending and not already_reviewed:
        sub_hint = job["status_hint"][1] if job.get("status_hint") else None
        db.add(models.PendingMatch(
            source="linkedin",
            external_id=pm_ext_id,
            confidence=90,
            event_type="status_change",
            datum=date.today(),
            titel=f"Status: {old_status} → {target_status}",
            suggested_app_id=app.id,
            suggested_main_status=target_status,
            suggested_sub_status=sub_hint,
            status_only=True,
            user_id=user_id,
        ))
        pending_match_created = True
        log.info("{} Status-Vorschlag erstellt: {} → {} | match={}", pfx, old_status, target_status, match_grund)
    elif already_pending:
        log.info("{} Status-Vorschlag übersprungen (bereits ausstehend): {} → {} | match={}", pfx, old_status, target_status, match_grund)
    else:
        log.info("{} Status-Vorschlag übersprungen (bereits überprüft: {}): {} → {} | match={}", pfx, already_reviewed.review_status, old_status, target_status, match_grund)

    return {
        "result": "updated", "app_id": app.id, "match_grund": match_grund,
        "old_status": old_status, "target_status": target_status,
        "pending_match_created": pending_match_created,
    }


def _run_sync_task(cfg_id: int, target_app_id: int | None = None):
    """Blocking wrapper — runs the async scraper from a sync background task."""
    asyncio.run(_async_sync(cfg_id, target_app_id))


async def _async_sync(cfg_id: int, target_app_id: int | None = None):
    from app.database import SessionLocal, set_session_user

    db = SessionLocal()
    lang = "de"
    try:
        cfg = db.query(models.LinkedInSync).get(cfg_id)
        if not cfg:
            _state["status"] = "error"
            _state["step"] = t("li_config_not_found", "de")
            return
        user_id = cfg.user_id
        if user_id is not None:
            set_session_user(db, user_id)
        lang = resolve_ui_language(db, user_id)

        email = cfg.email
        password = decrypt_api_key(cfg.password_enc)

        _state["step"] = t("li_starting_browser", lang)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            _state["status"] = "error"
            _state["step"] = t("li_playwright_missing", lang)
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

            # Check session validity — /feed redirects to uas/login when session expired
            _state["step"] = t("li_session_check", lang)
            check_url = "https://www.linkedin.com/feed/"
            try:
                await page.goto(check_url, wait_until="domcontentloaded", timeout=20000)
                _state["step"] = t("li_session_loaded", lang, url=page.url[:60])
            except Exception as nav_err:
                _state["step"] = t("li_session_fallback", lang, error=nav_err)
                await page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=20000)

            # Session invalid if redirected away from feed (to login/authwall)
            _not_on_feed = "linkedin.com/feed" not in page.url
            if "login" in page.url or "authwall" in page.url or "uas/login" in page.url or _not_on_feed:
                if _not_on_feed:
                    _state["step"] = t("li_session_expired", lang, url=page.url[:60])
                logged_in = await _login(page, email, password, lang)
                if not logged_in:
                    await browser.close()
                    if _state["status"] != "needs_login":
                        _state["status"] = "error"
                    return
            # Save fresh session cookies
            cookies = await context.cookies()
            cfg.session_cookies = json.dumps(cookies)
            _commit_with_retry(db)

            created = updated = skipped = 0
            errors: list[str] = []

            def _process(job: dict) -> None:
                nonlocal created, updated, skipped
                try:
                    outcome = _process_linkedin_job(db, job, user_id)
                    if outcome["result"] == "created":
                        created += 1
                    elif outcome["result"] == "updated":
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append(f"{job.get('company', '?')}: {e}")
                    log.error("[LI] Fehler bei {}/{}: {}", job.get("company", "?"), job.get("title", "?"), e)

            # ── Individueller Sync: Kategorie für Kategorie, sofort matchen ──────────
            if target_app_id is not None:
                target_app = db.query(models.Application).get(target_app_id)
                target_li_job_id = (target_app.linkedin_job_id if target_app else None) or (
                    _li_job_id_from_url(target_app.stellenanzeige_url or "") if target_app else None
                )
                log.info("[LI] Individueller Sync App #{} — LI-ID: {}", target_app_id, target_li_job_id or "unbekannt")

                search_categories = _categories_for_individual_sync(target_app)

                found_job: dict | None = None
                cats_searched = 0
                for card_type, label, default_status, max_pages, cat_url in search_categories:
                    _state["step"] = t("li_page_loading", lang, label=label, page=1)
                    cat_jobs = await _scrape_category(page, card_type, default_status, set(), max_pages=max_pages, url=cat_url, label=label, lang=lang)
                    for j in cat_jobs:
                        j["_card_type"] = card_type
                        j["_label"] = label
                    cats_searched += 1
                    log.info("[LI kat] {}: {} gefunden", label, len(cat_jobs))
                    _state["step"] = t("li_jobs_searching_match", lang, label=label, count=len(cat_jobs))

                    if target_app:
                        for j in cat_jobs:
                            if _quick_match(j, target_app):
                                found_job = j
                                break

                    if found_job:
                        log.info("[LI] Match in Kategorie '{}' nach {} Kategorien", label, cats_searched)
                        break

                await browser.close()

                if found_job:
                    _state["total"] = 1
                    _state["processed"] = 1
                    _state["step"] = t("li_processing_match", lang)
                    _process(found_job)
                else:
                    log.info("[LI] Ziel-App #{} nicht in LI-Daten gefunden", target_app_id)
                    _state["step"] = t("li_no_entry_found", lang)

            # ── Batch-Sync: alle Kategorien sammeln, dann verarbeiten ───────────────
            else:
                # Dedup by firma|title — later categories (higher priority) overwrite earlier
                all_jobs_by_key: dict[str, dict] = {}
                for card_type, label, default_status, max_pages, cat_url in CATEGORIES:
                    _state["step"] = t("li_page_loading", lang, label=label, page=1)
                    cat_jobs = await _scrape_category(page, card_type, default_status, set(), max_pages=max_pages, url=cat_url, label=label, lang=lang)
                    for j in cat_jobs:
                        j["_card_type"] = card_type
                        j["_label"] = label
                        dedup_key = f"{j.get('company', '').lower().strip()} | {j.get('title', '').lower().strip()}"
                        all_jobs_by_key[dedup_key] = j
                    log.info("[LI kat] {}: {} gefunden (gesamt {})", label, len(cat_jobs), len(all_jobs_by_key))
                    _state["step"] = t("li_jobs_found_total", lang, label=label, count=len(cat_jobs), total=len(all_jobs_by_key))
                all_jobs = list(all_jobs_by_key.values())

                # Scrape messages before closing the browser session
                apps_for_msg = db.query(models.Application).all()
                msg_created = await _scrape_messages(page, db, apps_for_msg, user_id, lang=lang)
                _state["msg_created"] = msg_created

                await browser.close()

                if not all_jobs and _state["status"] != "needs_login":
                    _state["step"] = t("li_no_jobs_layout_changed", lang)

                _state["raw_jobs"] = all_jobs
                _state["total"] = len(all_jobs)
                _state["step"] = t("li_processing_progress", lang, current=0, total=len(all_jobs))

                for i, job in enumerate(all_jobs):
                    _state["processed"] = i + 1
                    _state["step"] = t("li_processing_progress", lang, current=i + 1, total=len(all_jobs))
                    _process(job)

        cfg.last_sync = datetime.now(timezone.utc)
        _commit_with_retry(db)

        log.info("[LI sync] fertig: {} neu, {} aktualisiert, {} unverändert, {} fehler",
                 created, updated, skipped, len(errors))
        _state.update({
            "status": "done",
            "step": t("done", lang),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "msg_created": _state.get("msg_created", 0),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as e:
        _state["status"] = "error"
        _state["step"] = t("li_error", lang, error=e)
        _state["errors"] = [str(e)]
    finally:
        db.close()


# ── Manuelle Personensuche + Kontakt-Import ──────────────────────────────────
# Reine on-demand Suche (kein Hintergrund-Batch) — reuse _get_linkedin_context
# aus sync_company.py: nutzt nur eine bestehende, gültige Session, kein
# Login-Versuch (soll nicht in den 2FA-Flow des Job-Syncs oben eingreifen).

_PEOPLE_NOISE = {"1st", "2nd", "3rd", "connect", "follow", "message", "pending",
                 "view profile", "status is offline", "status is reachable"}
# Live beobachtet (Suche nach 'Satya Nadella'): der Verbindungsgrad steht nicht
# immer als eigene Zeile ("• 3rd+"), sondern klebt teils direkt am Namen
# ("Satya Nadella • 3rd+") — reines Zeilen-Filtern gegen _PEOPLE_NOISE reicht
# dann nicht, das Suffix muss aus jeder Zeile herausgeschnitten werden.
_DEGREE_SUFFIX_RE = re.compile(r"\s*•\s*(1st|2nd|3rd\+?)\s*$", re.IGNORECASE)
_DEGREE_MARKER_RE = re.compile(r"•\s*(1st|2nd|3rd\+?)", re.IGNORECASE)


async def _linkedin_search_people(context, query: str, limit: int = 10) -> list[dict]:
    """Sucht LinkedIn-Personen, liefert bis zu `limit` Kandidaten
    ({"name","headline","profile_url"}). Best-effort — jeder Fehler (Layout-
    Änderung, Rate-Limit, keine Treffer) liefert eine leere Liste statt den
    Aufruf abzubrechen.

    Wie beim Firmen-Suchscraper (sync_company.py) umschließt der Ergebnis-
    Link oft die ganze Karte (Name, Verbindungsgrad, Headline, Buttons) —
    deshalb wird nur die erste Zeile als Name genommen und Rauschen
    (Verbindungsgrad, Button-Beschriftungen) explizit herausgefiltert statt
    blind die zweite Zeile als Headline zu vertrauen.
    """
    candidates: list[dict] = []
    page = await context.new_page()
    try:
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        anchors = await page.locator("a[href*='/in/']").all()
        seen_urls: set[str] = set()
        for a in anchors:
            href = await a.get_attribute("href")
            if not href or "/in/" not in href:
                continue
            url = href.split("?")[0].rstrip("/")
            if url in seen_urls:
                continue

            raw_text = await a.inner_text()
            # LinkedIns Ergebnisseite verlinkt auch Personen, die nur als
            # "X, Y und 20 weitere gemeinsame Kontakte" in einer FREMDEN Karte
            # erwähnt werden — diese Erwähnungs-Links haben dieselbe /in/-URL-
            # Struktur wie echte Suchergebnisse, aber nur den nackten Namen als
            # Text (kein Verbindungsgrad). Live beobachtet (Suche nach 'Michael
            # Schmidt'): ohne Filter landeten diese Erwähnungen als Kandidaten
            # ohne Firma/Headline im Ergebnis und verbrauchten das `limit`-
            # Kontingent, bevor echte weitere Treffer gescannt wurden — wirkte
            # wie "nur die erste Trefferseite". Ein echtes Suchergebnis hat
            # immer einen Verbindungsgrad ("• 1st/2nd/3rd") im Kartentext.
            if not _DEGREE_MARKER_RE.search(raw_text):
                continue
            seen_urls.add(url)

            lines = []
            for ln in raw_text.splitlines():
                ln = _DEGREE_SUFFIX_RE.sub("", ln).strip()
                if ln and ln.lower() not in _PEOPLE_NOISE:
                    lines.append(ln)
            if not lines:
                continue
            name = lines[0]
            headline = lines[1] if len(lines) > 1 else None

            candidates.append({
                "name": name[:200],
                "headline": (headline[:300] if headline else None),
                "profile_url": url,
            })
            if len(candidates) >= limit:
                break
    except Exception as e:
        log.debug("LinkedIn-Personensuche Fehler für '{}': {}", query, e)
    finally:
        await page.close()
    return candidates


def _split_headline(headline: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """'Senior Engineer at Contoso' → (rolle, firma). Best-effort — viele
    LinkedIn-Headlines (v.a. individuell angepasste, ohne Firmenerwähnung,
    z.B. nur "Head of Customer Program Management") enthalten die Firma
    überhaupt nicht im Text; dann bleibt firma bewusst None statt geraten zu
    werden. Ein Blick auf die volle Profilseite als Fallback wurde geprüft,
    scheitert aber am LinkedIn-Suchlimit für nicht verbundene Profile
    ("Explore Premium profiles"-Wall) — kein zuverlässiger Weg mit einem
    normalen Account."""
    if not headline:
        return None, None
    for sep in (" at ", " bei ", " @ "):
        if sep in headline:
            rolle, firma = headline.split(sep, 1)
            return rolle.strip() or None, firma.strip() or None
    return headline.strip() or None, None


@router.get("/people/search")
async def search_people(q: str = Query(..., min_length=2), current_user: models.User = Depends(get_current_user)):
    from app.routers.sync_company import _get_linkedin_context

    li_ctx = None
    try:
        li_ctx = await _get_linkedin_context(current_user.id)
    except Exception as e:
        log.warning("Personensuche: LinkedIn-Browser-Start fehlgeschlagen: {}", e)
    if not li_ctx:
        raise HTTPException(status_code=400, detail="Keine gültige LinkedIn-Session konfiguriert")

    playwright, browser, context = li_ctx
    try:
        candidates = await _linkedin_search_people(context, q)
    finally:
        await browser.close()
        await playwright.stop()
    return candidates


class PeopleImportCandidate(BaseModel):
    name: str
    headline: Optional[str] = None
    profile_url: str


class PeopleImportPayload(BaseModel):
    candidates: list[PeopleImportCandidate]
    application_id: Optional[int] = None


@router.post("/people/import")
def import_people(
    body: PeopleImportPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Importiert vom User ausgewählte LinkedIn-Personen (aus /people/search)
    als echte Contact-Zeilen. Explizite User-Aktion, keine Relevanz-Prüfung."""
    app_obj = None
    if body.application_id:
        app_obj = db.query(models.Application).filter(
            models.Application.id == body.application_id
        ).first()
        if not app_obj:
            raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden")

    imported = 0
    skipped = 0
    for cand in body.candidates:
        existing = db.query(models.Contact).filter_by(linkedin_url=cand.profile_url).first()
        if not existing:
            existing = db.query(models.Contact).filter_by(name=cand.name).first()
        if existing:
            skipped += 1
            if app_obj and app_obj not in existing.applications:
                existing.applications.append(app_obj)
            continue
        rolle, firma = _split_headline(cand.headline)
        contact = models.Contact(
            name=cand.name, linkedin_url=cand.profile_url, rolle=rolle, firma=firma,
            user_id=current_user.id,
        )
        db.add(contact)
        db.flush()
        if app_obj:
            contact.applications.append(app_obj)
        add_audit(db, "create", "user", contact_id=contact.id,
                  app_id=app_obj.id if app_obj else None,
                  new_value=contact.name, reason_key="import_from_linkedin_people_search",
                  user_id=current_user.id)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}


class CompanySearchCandidate(BaseModel):
    name: str
    url: str
    snippet: Optional[str] = None


class CompanyImportCandidate(BaseModel):
    name: str
    url: str


class CompanyImportPayload(BaseModel):
    candidates: list[CompanyImportCandidate]


@router.get("/companies/search")
async def search_companies(q: str = Query(..., min_length=2), current_user: models.User = Depends(get_current_user)):
    """LinkedIn-Firmensuche: sucht LinkedIn nach Unternehmen, die `q` im Namen
    tragen. Liefert eine Liste von Kandidaten (Name, LinkedIn-URL, Snippet)
    analog zu /people/search."""
    from app.routers.sync_company import _get_linkedin_context, _linkedin_search_candidates

    li_ctx = None
    try:
        li_ctx = await _get_linkedin_context(current_user.id)
    except Exception as e:
        log.warning("Firmensuche: LinkedIn-Browser-Start fehlgeschlagen: {}", e)
    if not li_ctx:
        raise HTTPException(status_code=400, detail="Keine gültige LinkedIn-Session konfiguriert")

    playwright, browser, context = li_ctx
    try:
        candidates = await _linkedin_search_candidates(context, q)
    finally:
        await browser.close()
        await playwright.stop()
    return candidates


@router.post("/companies/import")
def import_companies(
    body: CompanyImportPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Importiert vom User ausgewählte LinkedIn-Firmenkandidaten (aus
    /companies/search) als echte CompanyProfile-Zeilen. Überspringt
    bereits existierende Profile (matched per normalized name)."""
    from app.dedup import norm_firma

    imported = 0
    skipped = 0
    for cand in body.candidates:
        name = cand.name.strip()
        if not name:
            skipped += 1
            continue
        key = norm_firma(name)
        existing = db.query(models.CompanyProfile).filter(
            models.CompanyProfile.name_norm == key,
            models.CompanyProfile.user_id == current_user.id,
        ).first()
        if existing:
            skipped += 1
            continue
        profile = models.CompanyProfile(
            name_norm=key,
            name_display=name[:200],
            linkedin_company_url=cand.url,
            sync_status="pending",
            user_id=current_user.id,
        )
        db.add(profile)
        db.flush()
        add_audit(db, "create", "user", company_profile_id=profile.id,
                  new_value=profile.name_display,
                  reason_key="import_from_linkedin_company_search",
                  user_id=current_user.id)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}
