"""L1 Unit — rapportGPT's add_assessment_feedback tool (app/ai/chat.py),
the first mutating chat tool. See test_ai_chat_tools.py for the read-only
tools' equivalent direct-executor test style."""
import pytest

from app import models
from app.ai import chat
from app.database import set_session_user
from tests.factories import application_factory

pytestmark = pytest.mark.unit


def _user(id_=1) -> models.User:
    return models.User(id=id_, email=f"user{id_}@example.com", password_hash="x")


class TestAddAssessmentFeedback:
    async def test_positiv_speichert_feedback_und_gibt_zaehler_zurueck(self, db_session):
        app = application_factory(db_session, firma="Contoso AG", stellenanzeige_url=None)
        db_session.commit()
        set_session_user(db_session, 1)

        result = await chat._tool_add_assessment_feedback(
            db_session, _user(1), {"application_id": app.id, "feedback": "Braucht 10 Jahre Java, habe keine."},
        )

        assert result["saved"] is True
        assert result["feedback_count"] == 1
        row = db_session.query(models.ApplicationFeedback).filter_by(application_id=app.id).first()
        assert row is not None
        assert row.text == "Braucht 10 Jahre Java, habe keine."
        assert row.user_id == 1
        # No JD text resolvable (no attachment/URL) -- score_application()
        # returns False without an AI call, so the tool reports this rather
        # than silently pretending scores were recomputed.
        assert "rescore_note" in result

    async def test_positiv_ist_ein_append_only_log_kein_ueberschreiben(self, db_session):
        app = application_factory(db_session, stellenanzeige_url=None)
        db_session.commit()
        set_session_user(db_session, 1)

        await chat._tool_add_assessment_feedback(db_session, _user(1), {"application_id": app.id, "feedback": "Erste Notiz."})
        result2 = await chat._tool_add_assessment_feedback(db_session, _user(1), {"application_id": app.id, "feedback": "Zweite Notiz."})

        assert result2["feedback_count"] == 2
        texts = [f.text for f in db_session.query(models.ApplicationFeedback).filter_by(application_id=app.id).order_by(models.ApplicationFeedback.created_at).all()]
        assert texts == ["Erste Notiz.", "Zweite Notiz."]

    async def test_negativ_leeres_feedback_liefert_error_ohne_zu_speichern(self, db_session):
        app = application_factory(db_session)
        db_session.commit()
        set_session_user(db_session, 1)

        result = await chat._tool_add_assessment_feedback(db_session, _user(1), {"application_id": app.id, "feedback": "   "})

        assert result["error"] == "missing_argument"
        assert db_session.query(models.ApplicationFeedback).filter_by(application_id=app.id).count() == 0

    async def test_negativ_unbekannte_id_liefert_not_found(self, db_session):
        set_session_user(db_session, 1)

        result = await chat._tool_add_assessment_feedback(db_session, _user(1), {"application_id": 99999, "feedback": "Notiz"})

        assert result["error"] == "not_found"

    async def test_negativ_andere_user_id_liefert_not_found(self, db_session):
        app = application_factory(db_session, firma="Firma A", user_id=2)
        db_session.commit()
        set_session_user(db_session, 1)

        result = await chat._tool_add_assessment_feedback(db_session, _user(1), {"application_id": app.id, "feedback": "Notiz"})

        assert result["error"] == "not_found"
        assert db_session.query(models.ApplicationFeedback).filter_by(application_id=app.id).count() == 0


class TestExecuteToolDispatch:
    async def test_positiv_dispatcht_an_add_assessment_feedback(self, db_session):
        app = application_factory(db_session, stellenanzeige_url=None)
        db_session.commit()
        set_session_user(db_session, 1)

        result = await chat._execute_tool(db_session, _user(1), "add_assessment_feedback", {"application_id": app.id, "feedback": "Notiz"})

        assert result["saved"] is True
