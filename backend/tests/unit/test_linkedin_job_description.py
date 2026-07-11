from __future__ import annotations

import asyncio
import json

import pytest

from app.linkedin_job_description import load_job_description, _DESCRIPTION_JS, _COMPANY_NAME_JS


# ---------------------------------------------------------------------------
# Playwright-Fake
# ---------------------------------------------------------------------------

class FakeLocator:
    def __init__(self, visible: bool = True):
        self._vis = visible

    @property
    def first(self):
        return self

    async def is_visible(self, **kw):
        return self._vis

    async def click(self):
        pass


DEFAULT_HTML = "<div>Senior Software Engineer position requiring 5+ years experience in Python.</div>"


class FakePage:
    def __init__(self, *, description: str = DEFAULT_HTML,
                 company: str = "Acme Corp",
                 goto_fail: bool = False,
                 login_url: bool = False):
        self._description = description
        self._company = company
        self._goto_fail = goto_fail
        self._login_url = login_url
        self.url = ""
        self.evaluate_calls: list[str] = []

    async def goto(self, url: str, **kw):
        self.url = url
        if self._goto_fail:
            raise Exception("failed to load page")
        if self._login_url:
            self.url = url + "/login"
            self._login_url = False  # only on first nav
        return None

    async def evaluate(self, js: str):
        self.evaluate_calls.append(js)
        if js == _DESCRIPTION_JS:
            return self._description
        if js == _COMPANY_NAME_JS:
            return self._company
        return None

    async def wait_for_load_state(self, *args, **kw):
        pass

    def locator(self, selector: str):
        return FakeLocator()

    async def close(self):
        pass


class FakeBrowserContext:
    def __init__(self, page: FakePage):
        self._page = page

    async def new_page(self):
        return self._page

    async def add_cookies(self, cookies: list):
        pass

    async def add_init_script(self, js: str):
        pass


class FakeBrowser:
    def __init__(self, page: FakePage):
        self._page = page

    async def new_context(self, **kw):
        return FakeBrowserContext(self._page)

    async def close(self):
        pass


class FakePlaywright:
    def __init__(self, page: FakePage):
        self._page = page

    @property
    def chromium(self):
        return self

    async def launch(self, **kw):
        return FakeBrowser(self._page)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def fake_sleep(_secs: float):
    pass


async def fake_login(_page, _email: str, _password: str) -> bool:
    return True


async def fake_accept_consent(_page):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_linkedin(db_session) -> None:
    from app import models
    from app.ai.provider import encrypt_api_key

    cfg = models.LinkedInSync(
        email="test@linkedin.com",
        password_enc=encrypt_api_key("secret"),
        session_cookies=json.dumps([{"name": "li_at", "value": "token", "domain": ".linkedin.com"}]),
    )
    db_session.add(cfg)
    db_session.flush()


def _patch_playwright(monkeypatch, page: FakePage):
    import playwright.async_api as pw_mod
    monkeypatch.setattr(pw_mod, "async_playwright", lambda: FakePlaywright(page))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

class TestLoadJobDescription:

    @pytest.fixture(autouse=True)
    def _patches(self, monkeypatch):
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        from app.routers import sync_linkedin
        monkeypatch.setattr(sync_linkedin, "_login", fake_login)
        monkeypatch.setattr(sync_linkedin, "_accept_consent", fake_accept_consent)

    async def test_no_linkedin_config(self, db_session):
        with pytest.raises(ValueError, match="LinkedIn nicht konfiguriert"):
            await load_job_description("https://linkedin.com/jobs/1", db_session)

    async def test_happy_path(self, db_session, monkeypatch):
        _setup_linkedin(db_session)
        page = FakePage()
        _patch_playwright(monkeypatch, page)

        result = await load_job_description("https://linkedin.com/jobs/1", db_session)

        assert result["description"] == DEFAULT_HTML
        assert result["company"] == "Acme Corp"
        assert _DESCRIPTION_JS in page.evaluate_calls
        assert _COMPANY_NAME_JS in page.evaluate_calls

    async def test_page_unreachable(self, db_session, monkeypatch):
        _setup_linkedin(db_session)
        _patch_playwright(monkeypatch, FakePage(goto_fail=True))

        with pytest.raises(ValueError, match="Seite nicht erreichbar"):
            await load_job_description("https://linkedin.com/jobs/1", db_session)

    async def test_login_required_success(self, db_session, monkeypatch):
        _setup_linkedin(db_session)
        _patch_playwright(monkeypatch, FakePage(
            login_url=True,
            description="<div>Job description after login</div>",
            company="PostLogin Inc",
        ))

        result = await load_job_description("https://linkedin.com/jobs/1", db_session)

        assert result["description"] == "<div>Job description after login</div>"
        assert result["company"] == "PostLogin Inc"

    async def test_login_fails(self, db_session, monkeypatch):
        _setup_linkedin(db_session)
        _patch_playwright(monkeypatch, FakePage(login_url=True, description="", company=""))
        from app.routers import sync_linkedin

        async def fake_login_fail(_p, _e, _pw):
            return False
        monkeypatch.setattr(sync_linkedin, "_login", fake_login_fail)

        with pytest.raises(ValueError, match="LinkedIn-Login fehlgeschlagen"):
            await load_job_description("https://linkedin.com/jobs/1", db_session)

    async def test_empty_description(self, db_session, monkeypatch):
        _setup_linkedin(db_session)
        _patch_playwright(monkeypatch, FakePage(description="", company=""))

        with pytest.raises(ValueError, match="Stellenbeschreibung konnte nicht extrahiert werden"):
            await load_job_description("https://linkedin.com/jobs/1", db_session)

    async def test_company_retry(self, db_session, monkeypatch):
        _setup_linkedin(db_session)

        class RetryPage(FakePage):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                self._company_calls = 0

            async def evaluate(self, js: str):
                self.evaluate_calls.append(js)
                if js == _DESCRIPTION_JS:
                    return "<div>Job description</div>"
                if js == _COMPANY_NAME_JS:
                    self._company_calls += 1
                    return "" if self._company_calls == 1 else "Retrieved Corp"
                return None

        page = RetryPage()
        _patch_playwright(monkeypatch, page)

        result = await load_job_description("https://linkedin.com/jobs/1", db_session)

        assert result["company"] == "Retrieved Corp"
        assert page._company_calls == 2


# ---------------------------------------------------------------------------
# JS-Struktur-Prüfung
# ---------------------------------------------------------------------------

class TestExtractionJs:

    def test_description_js_contains_expected_selectors(self):
        assert "insideNavOrChrome" in _DESCRIPTION_JS
        assert "document.querySelector" in _DESCRIPTION_JS
        assert "createTreeWalker" in _DESCRIPTION_JS
        assert "about the job" in _DESCRIPTION_JS.lower()

    def test_company_name_js_contains_expected_selectors(self):
        assert "linkedin.com/company/" in _COMPANY_NAME_JS
        assert "og:title" in _COMPANY_NAME_JS
        assert "split" in _COMPANY_NAME_JS

    def test_company_name_js_has_hiring_pattern(self):
        assert "hiring" in _COMPANY_NAME_JS.lower()
