"""L1 Component — ai/tasks.py::resolve_ui_language().

Background sync tasks (e.g. sync_targeted.py's _do_sync) only have a user_id,
not the full current_user object, so the AI-assessment language has to be
looked up from the DB by id instead.
"""
import pytest

from app import models
from app.ai.tasks import resolve_ui_language

pytestmark = pytest.mark.component


class TestResolveUiLanguage:
    def test_positiv_liefert_gespeicherte_sprache(self, db_session):
        user = models.User(email="en-user@example.com", password_hash="x", email_verified=True, ui_language="en")
        db_session.add(user)
        db_session.commit()

        assert resolve_ui_language(db_session, user.id) == "en"

    def test_negativ_unbekannte_user_id_faellt_auf_de_zurueck(self, db_session):
        assert resolve_ui_language(db_session, 999999) == "de"

    def test_negativ_kein_user_id_faellt_auf_de_zurueck(self, db_session):
        assert resolve_ui_language(db_session, None) == "de"

    def test_negativ_ungueltiger_sprachwert_faellt_auf_de_zurueck(self, db_session):
        user = models.User(email="bad-lang@example.com", password_hash="x", email_verified=True, ui_language="fr")
        db_session.add(user)
        db_session.commit()

        assert resolve_ui_language(db_session, user.id) == "de"
