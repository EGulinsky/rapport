"""L3 Integration — app/routers/applications.py's score_application():
end-to-end orchestration of the two new AI calls (match_score,
success_probability) against a real DB session and the FakeAIProvider
double, incl. the terminal-status shortcut, the no-JD-text skip, and that a
provider error doesn't leave a half-written record behind."""
import pytest

from app import models
from app.ai.provider import AINotConfigured, AIRateLimited
from app.routers.applications import score_application
from app.routers.attachments import store_attachment
from tests.factories import application_factory, event_factory
from tests.integration.conftest import load_fixture

pytestmark = pytest.mark.integration


def _user(db, **overrides) -> models.User:
    defaults = dict(id=1, email="test@example.com", password_hash="x", email_verified=True)
    defaults.update(overrides)
    user = db.query(models.User).get(defaults["id"])
    if user:
        for k, v in overrides.items():
            setattr(user, k, v)
        return user
    user = models.User(**defaults)
    db.add(user)
    db.flush()
    return user


class TestScoreApplicationNormalStatus:
    async def test_positiv_beide_scores_werden_berechnet_und_persistiert(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session, cv_extracted_text="5 Jahre Python-Erfahrung")
        app = application_factory(db_session, main_status="hr", sub_status="1_done")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Python Backend Engineer gesucht", user_id=app.user_id)
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await score_application(db_session, app, user, "de")

        db_session.refresh(app)
        assert app.match_score == 78
        assert app.match_score_reasoning
        assert app.success_probability == 55
        assert app.success_probability_reasoning
        assert app.ai_score_computed_at is not None
        assert len(fake_ai_provider.calls) == 2

    async def test_positiv_zweiter_call_bekommt_timeline_und_ghosting(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session)
        app = application_factory(db_session, main_status="hr")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await score_application(db_session, app, user, "de")

        second_prompt = fake_ai_provider.calls[1]["messages"][1]["content"]
        assert "MATCH-SCORE" in second_prompt
        assert "78" in second_prompt

    async def test_positiv_zweiter_call_bekommt_kontakthaeufigkeit_und_bewerberzahl(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session)
        app = application_factory(db_session, main_status="hr", bewerberzahl=87)
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        event_factory(db_session, app, typ="mail", mail_direction="received")
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await score_application(db_session, app, user, "de")

        second_prompt = fake_ai_provider.calls[1]["messages"][1]["content"]
        assert "KONTAKTHÄUFIGKEIT" in second_prompt
        assert "Bekannte Bewerberzahl" in second_prompt
        assert "87" in second_prompt

    async def test_positiv_beide_calls_bekommen_gespeichertes_feedback(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session)
        app = application_factory(db_session, main_status="hr")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.add(models.ApplicationFeedback(application_id=app.id, user_id=user.id, text="Die Rolle braucht 10 Jahre Java."))
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await score_application(db_session, app, user, "de")

        first_prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        second_prompt = fake_ai_provider.calls[1]["messages"][1]["content"]
        assert "10 Jahre Java" in first_prompt
        assert "10 Jahre Java" in second_prompt

    async def test_positiv_historische_vergleichsdaten_werden_eingebettet(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session)
        app = application_factory(db_session, main_status="hr")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        application_factory(db_session, main_status="rejected", pre_rejection_status="hr")
        application_factory(db_session, main_status="signed")
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await score_application(db_session, app, user, "de")

        second_prompt = fake_ai_provider.calls[1]["messages"][1]["content"]
        assert "HISTORISCHE VERGLEICHSDATEN" in second_prompt


class TestScoreApplicationTerminalStatus:
    async def test_positiv_rejected_nur_match_score_call_success_probability_0(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session)
        app = application_factory(db_session, main_status="rejected")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        await score_application(db_session, app, user, "de")

        db_session.refresh(app)
        assert app.match_score == 78
        assert app.success_probability == 0
        assert app.success_probability_reasoning
        assert len(fake_ai_provider.calls) == 1

    async def test_positiv_signed_nur_match_score_call_success_probability_100(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session)
        app = application_factory(db_session, main_status="signed")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        await score_application(db_session, app, user, "de")

        db_session.refresh(app)
        assert app.success_probability == 100
        assert len(fake_ai_provider.calls) == 1


class TestScoreApplicationNoJdText:
    async def test_negativ_ohne_jd_text_bleiben_scores_null_kein_ai_call(self, db_session, ai_settings, fake_ai_provider):
        user = _user(db_session)
        app = application_factory(db_session, stellenanzeige_url=None)
        db_session.commit()

        await score_application(db_session, app, user, "de")

        db_session.refresh(app)
        assert app.match_score is None
        assert app.success_probability is None
        assert app.ai_score_computed_at is None
        assert fake_ai_provider.calls == []


class TestScoreApplicationProviderErrors:
    async def test_negativ_ainotconfigured_propagiert_ohne_persistierung(self, db_session):
        user = _user(db_session)
        app = application_factory(db_session, main_status="hr")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        with pytest.raises(AINotConfigured):
            await score_application(db_session, app, user, "de")

        db_session.rollback()
        db_session.refresh(app)
        assert app.match_score is None
        assert app.ai_score_computed_at is None

    async def test_negativ_airatelimited_beim_zweiten_call_lässt_match_score_ungespeichert(self, db_session, ai_settings, fake_ai_provider):
        import litellm

        user = _user(db_session)
        app = application_factory(db_session, main_status="hr")
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "jd.txt", b"Anforderungen...", user_id=app.user_id)
        db_session.commit()

        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))
        fake_ai_provider.queue_error(
            litellm.RateLimitError(message="rate limited", llm_provider="groq", model=ai_settings.model)
        )

        with pytest.raises(AIRateLimited):
            await score_application(db_session, app, user, "de")

        db_session.rollback()
        db_session.refresh(app)
        assert app.match_score is None
        assert app.ai_score_computed_at is None
