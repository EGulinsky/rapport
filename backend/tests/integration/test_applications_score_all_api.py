"""L3 Integration — POST /api/applications/score-all (applications.py's
score_all()/_run_score_all()): kicks off best-effort AI (re-)scoring for
every one of the user's applications as a background task, using the same
sync_common.py progress/batch-result mechanism as the other global sync
sources. Placed in tests/integration/ rather than tests/api/ so it can use
the fake_ai_provider fixture from this directory's conftest.py alongside
the root client fixture (FastAPI's TestClient runs a request's
BackgroundTasks synchronously before returning, so the background function
has already completed by the time client.post() returns)."""
import pytest

from app import models
from app.routers.applications import PROGRESS_KEY_AI_SCORING, _run_score_all
from app.routers.attachments import store_attachment
from app.routers.sync_common import get_all_progress, get_batch_results
from tests.factories import application_factory, event_factory
from tests.integration.conftest import load_fixture

pytestmark = pytest.mark.integration


def _persist_current_user(db_session, **overrides) -> models.User:
    """The `client` fixture's get_current_user() override returns a
    transient (unpersisted) fake_user object with id=1 -- score_all()'s
    background task opens its OWN SessionLocal() and needs a real, committed
    User row with that same id to find CV/LinkedIn profile text."""
    defaults = dict(id=1, email="test-client@example.com", password_hash="x", email_verified=True)
    defaults.update(overrides)
    user = models.User(**defaults)
    db_session.add(user)
    db_session.commit()
    return user


def _ai_settings_for_user(db_session, user_id: int = 1, **overrides) -> models.AiSettings:
    """_run_score_all() calls set_session_user(), which activates the
    per-request tenant filter on every scoped model incl. AiSettings (see
    database.py's _SCOPED_MODEL_NAMES/_apply_tenant_filter) -- unlike the
    shared `ai_settings` fixture in this directory's conftest.py (used by
    tests that never scope the session), a config row visible to
    _run_score_all's scoring calls MUST carry the matching user_id or the
    tenant filter hides it, surfacing as a spurious AINotConfigured."""
    defaults = dict(provider="groq", model="groq/llama-3.3-70b-versatile", enabled=True, user_id=user_id)
    defaults.update(overrides)
    cfg = models.AiSettings(**defaults)
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestScoreAllEndpoint:
    def test_positiv_startet_und_initialisiert_progress(self, client, db_session, monkeypatch):
        _persist_current_user(db_session)
        # _run_score_all itself is exercised separately below (real AI calls,
        # real DB state) -- here we only check the endpoint's own contract.
        monkeypatch.setattr("app.routers.applications._run_score_all", lambda user_id: None)

        resp = client.post("/api/applications/score-all")

        assert resp.status_code == 200
        assert resp.json()["started"] is True
        progress = get_all_progress()
        assert PROGRESS_KEY_AI_SCORING in progress


class TestRunScoreAllEndToEnd:
    async def test_positiv_scored_zaehlt_alle_erfolgreich_bewerteten_apps(
        self, db_session, fake_ai_provider
    ):
        _persist_current_user(db_session)
        _ai_settings_for_user(db_session)
        for _ in range(2):
            app = application_factory(db_session, main_status="hr")
            ev = event_factory(db_session, app, typ="file")
            store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        for _ in range(2):
            fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
            fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await _run_score_all(1)

        result = get_batch_results()[PROGRESS_KEY_AI_SCORING]
        assert result["done"] is True
        assert result["scored"] == 2
        assert result["errors"] == []

    async def test_negativ_apps_ohne_jd_text_zaehlen_nicht_als_gescort(
        self, db_session, fake_ai_provider
    ):
        _persist_current_user(db_session)
        _ai_settings_for_user(db_session)
        application_factory(db_session, stellenanzeige_url=None)
        db_session.commit()

        await _run_score_all(1)

        result = get_batch_results()[PROGRESS_KEY_AI_SCORING]
        # score_application() returns early (no JD text resolvable) --
        # counted as neither scored nor an error, just a silent no-op.
        assert result["scored"] == 0
        assert result["errors"] == []
        assert fake_ai_provider.calls == []


class TestRunScoreAllThrottle:
    async def test_positiv_5s_pause_zwischen_apps_fuer_groq(self, db_session, fake_ai_provider, monkeypatch):
        _persist_current_user(db_session)
        _ai_settings_for_user(db_session)
        for _ in range(3):
            app = application_factory(db_session, main_status="hr")
            ev = event_factory(db_session, app, typ="file")
            store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        for _ in range(3):
            fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
            fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        sleeps: list[float] = []

        async def _fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("asyncio.sleep", _fake_sleep)

        await _run_score_all(1)

        # provider="groq" -> 5s throttle, called once between each pair of
        # consecutive apps (total-1 times), never before the first.
        assert sleeps == [5.0, 5.0]

    async def test_positiv_1s_pause_fuer_nicht_gedrosselten_provider(self, db_session, fake_ai_provider, monkeypatch):
        _persist_current_user(db_session)
        _ai_settings_for_user(db_session, provider="anthropic", model="claude-haiku-4-5")
        for _ in range(2):
            app = application_factory(db_session, main_status="hr")
            ev = event_factory(db_session, app, typ="file")
            store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        for _ in range(2):
            fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
            fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        sleeps: list[float] = []

        async def _fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr("asyncio.sleep", _fake_sleep)

        await _run_score_all(1)

        assert sleeps == [1.0]


class TestRunScoreAllRateLimitStopsBatch:
    async def test_negativ_airatelimited_bricht_batch_ab_ohne_weitere_apps_anzufassen(
        self, db_session, fake_ai_provider
    ):
        import litellm

        _persist_current_user(db_session)
        cfg = _ai_settings_for_user(db_session)
        apps = []
        for _ in range(2):
            app = application_factory(db_session, main_status="hr")
            ev = event_factory(db_session, app, typ="file")
            store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
            apps.append(app)
        db_session.commit()

        fake_ai_provider.queue_error(
            litellm.RateLimitError(message="rate limited", llm_provider="groq", model=cfg.model)
        )

        await _run_score_all(1)

        result = get_batch_results()[PROGRESS_KEY_AI_SCORING]
        assert result["scored"] == 0
        assert len(fake_ai_provider.calls) == 1
        for app in apps:
            db_session.refresh(app)
            assert app.match_score is None
