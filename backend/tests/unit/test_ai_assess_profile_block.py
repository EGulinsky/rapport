"""L0/L1 — _build_profile_block() and its wiring into assess_application()/
assess_rejected_application()'s prompt. Patches app.ai.tasks.complete
directly (lighter boundary than the litellm-level integration tests in
tests/integration/test_ai_provider_flow.py) since this only needs to inspect
the prompt text that gets built, not exercise the real LLM error mapping."""
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.tasks import _build_profile_block, assess_application, assess_rejected_application
from tests.factories import application_factory


@pytest.mark.unit
class TestBuildProfileBlock:
    def test_negativ_ohne_daten_liefert_leeren_string(self):
        assert _build_profile_block(None, None) == ""

    def test_positiv_nur_cv(self):
        result = _build_profile_block("Senior Engineer, 10 Jahre Erfahrung", None)
        assert result.startswith("=== BEWERBERPROFIL ===\n")
        assert "Lebenslauf (Auszug):\nSenior Engineer, 10 Jahre Erfahrung" in result
        assert "LinkedIn" not in result

    def test_positiv_nur_linkedin(self):
        result = _build_profile_block(None, "Headline: Senior Engineer at Contoso")
        assert result.startswith("=== BEWERBERPROFIL ===\n")
        assert "LinkedIn-Profil (Auszug):\nHeadline: Senior Engineer at Contoso" in result
        assert "Lebenslauf" not in result

    def test_positiv_beide_vorhanden(self):
        result = _build_profile_block("CV-Text", "LinkedIn-Text")
        assert "CV-Text" in result
        assert "LinkedIn-Text" in result

    def test_positiv_endet_mit_leerzeile(self):
        """Damit die Formatierung an der Einfügestelle im f-string-Template
        sauber bleibt, egal ob der Block leer oder gefüllt ist."""
        result = _build_profile_block("CV-Text", None)
        assert result.endswith("\n\n")


@pytest.mark.component
class TestAssessApplicationProfileWiring:
    async def test_positiv_cv_und_linkedin_landen_im_prompt(self, db_session):
        app = application_factory(db_session)
        db_session.commit()
        captured = {}

        async def _fake_complete(db, messages, **kw):
            captured["prompt"] = messages[1]["content"]
            return {"color": "green", "reasoning": "ok", "next_step": "abwarten"}

        with patch("app.ai.tasks.complete", new=AsyncMock(side_effect=_fake_complete)):
            await assess_application(db_session, app, cv_text="Meine CV-Erfahrung", linkedin_text="Mein LinkedIn-Profil")

        assert "=== BEWERBERPROFIL ===" in captured["prompt"]
        assert "Meine CV-Erfahrung" in captured["prompt"]
        assert "Mein LinkedIn-Profil" in captured["prompt"]

    async def test_negativ_ohne_profildaten_kein_block_im_prompt(self, db_session):
        app = application_factory(db_session)
        db_session.commit()
        captured = {}

        async def _fake_complete(db, messages, **kw):
            captured["prompt"] = messages[1]["content"]
            return {"color": "green", "reasoning": "ok", "next_step": "abwarten"}

        with patch("app.ai.tasks.complete", new=AsyncMock(side_effect=_fake_complete)):
            await assess_application(db_session, app)

        assert "=== BEWERBERPROFIL ===" not in captured["prompt"]

    async def test_positiv_rejected_application_bekommt_profilblock_ebenfalls(self, db_session):
        app = application_factory(db_session, main_status="rejected")
        db_session.commit()
        captured = {}

        async def _fake_complete(db, messages, **kw):
            captured["prompt"] = messages[1]["content"]
            return {"color": "red", "reasoning": "ok", "next_step": "verbessern"}

        with patch("app.ai.tasks.complete", new=AsyncMock(side_effect=_fake_complete)):
            await assess_rejected_application(db_session, app, cv_text="Meine CV-Erfahrung")

        assert "=== BEWERBERPROFIL ===" in captured["prompt"]
        assert "Meine CV-Erfahrung" in captured["prompt"]
