"""L3 Integration — app/ai/tasks.py end-to-end über app/ai/provider.py::complete().

Mockt an der Netzwerkgrenze (litellm.acompletion, siehe tests/integration/conftest.py),
nicht an der eigenen Businesslogik — testet damit Prompt-Aufruf, JSON-Parsing,
Fehler-Mapping (AINotConfigured/AIRateLimited/AIBadRequest) und die
Batch-Fallback-Logik als vollständigen Fluss.
"""
import litellm
import pytest

from app import models
from app.ai.provider import AIBadRequest, AINotConfigured, AIRateLimited
from app.ai.tasks import assess_application, classify_batch_for_app, match_and_classify
from tests.factories import application_factory, event_factory
from tests.integration.conftest import load_fixture

pytestmark = pytest.mark.integration


class TestCompleteErrorMapping:
    """Deckt die Fehlerzweige von app/ai/provider.py::complete() ab, die die
    bisherigen assess_application()-Tests nicht erreichen — insbesondere die
    drei unterschiedlichen BadRequestError-Nachrichten und die beiden
    AINotConfigured-Auslöser (keine/deaktivierte Konfiguration)."""

    async def test_negativ_keine_ai_konfiguration_wirft_ainotconfigured(self, db_session):
        app = application_factory(db_session)
        # bewusst KEIN ai_settings-Fixture — es existiert keine Zeile in der Tabelle
        with pytest.raises(AINotConfigured):
            await assess_application(db_session, app)

    async def test_negativ_deaktivierter_ai_provider_wirft_ainotconfigured(self, db_session):
        app = application_factory(db_session)
        db_session.add(models.AiSettings(provider="groq", model="groq/llama-3.3-70b-versatile", enabled=False))
        db_session.commit()

        with pytest.raises(AINotConfigured):
            await assess_application(db_session, app)

    async def test_negativ_authentication_error_wirft_aibadrequest(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_error(
            litellm.AuthenticationError(message="invalid api key", llm_provider="groq", model=ai_settings.model)
        )

        with pytest.raises(AIBadRequest, match="API-Key ungültig"):
            await assess_application(db_session, app)

    async def test_negativ_json_modus_nicht_unterstuetzt_wirft_hilfreiche_meldung(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_error(
            litellm.BadRequestError(message="json_validate_failed: model refused", model=ai_settings.model, llm_provider="groq")
        )

        with pytest.raises(AIBadRequest, match="unterstützt keinen JSON-Modus"):
            await assess_application(db_session, app)

    async def test_negativ_modell_nicht_gefunden_wirft_hilfreiche_meldung(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_error(
            litellm.BadRequestError(message="The model does not exist", model=ai_settings.model, llm_provider="groq")
        )

        with pytest.raises(AIBadRequest, match="nicht gefunden beim Anbieter"):
            await assess_application(db_session, app)

    async def test_negativ_sonstiger_bad_request_wird_gekuerzt_durchgereicht(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_error(
            litellm.BadRequestError(message="context_length_exceeded: too many tokens", model=ai_settings.model, llm_provider="groq")
        )

        with pytest.raises(AIBadRequest, match="Ungültige Anfrage"):
            await assess_application(db_session, app)


class TestAssessApplication:
    async def test_positiv_gruene_bewertung_wird_durchgereicht(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        event_factory(db_session, app, typ="gespräch", titel="Erstgespräch HR")
        fake_ai_provider.queue_content(load_fixture("assess_green.json"))

        result = await assess_application(db_session, app)

        assert result["color"] == "green"
        assert "Gespräche" in result["reasoning"] or "Feedback" in result["reasoning"]
        assert len(fake_ai_provider.calls) == 1

    async def test_positiv_rote_bewertung_wird_durchgereicht(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        fake_ai_provider.queue_content(load_fixture("assess_red.json"))

        result = await assess_application(db_session, app)

        assert result["color"] == "red"
        assert result["next_step"]

    async def test_negativ_ungueltige_farbe_faellt_auf_yellow_zurueck(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_content('{"color": "blau", "reasoning": "x", "next_step": "y"}')

        result = await assess_application(db_session, app)

        assert result["color"] == "yellow"

    async def test_negativ_rate_limit_propagiert_als_airatelimited(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_error(
            litellm.RateLimitError(message="rate limited", llm_provider="groq", model=ai_settings.model)
        )

        with pytest.raises(AIRateLimited):
            await assess_application(db_session, app)

    async def test_negativ_kaputtes_json_wirft_aibadrequest(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_content(load_fixture("malformed.txt"))

        with pytest.raises(AIBadRequest):
            await assess_application(db_session, app)

    async def test_negativ_leere_antwort_wirft_aibadrequest(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session)
        fake_ai_provider.queue_content("")

        with pytest.raises(AIBadRequest):
            await assess_application(db_session, app)


class TestMatchAndClassify:
    async def test_positiv_liefert_alle_erwarteten_felder(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        fake_ai_provider.queue_content(load_fixture("match_classify_valid.json"))

        result = await match_and_classify(
            db_session,
            source="gmail",
            raw_text="Ihr Interviewtermin am 10.07. um 14 Uhr ist bestätigt.",
            applications=[{"id": app.id, "firma": app.firma, "rolle": app.rolle}],
        )

        assert result["application_id"] == 1
        assert result["confidence"] == 0.9
        assert result["event_type"] == "interview_scheduled"
        assert result["suggested_main_status"] == "hr"


class TestClassifyBatchForApp:
    async def test_positiv_korrekte_anzahl_wird_direkt_uebernommen(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        items = [{"id": "1", "raw": "Interview-Einladung"}, {"id": "2", "raw": "Newsletter, irrelevant"}]
        fake_ai_provider.queue_content(load_fixture("batch_classify_valid.json"))

        results = await classify_batch_for_app(db_session, "gmail", items, {"id": app.id, "firma": app.firma, "rolle": app.rolle})

        assert len(results) == 2
        assert results[0]["relevant"] is True
        assert results[0]["application_id"] == app.id
        assert results[1]["relevant"] is False
        assert results[1]["application_id"] is None
        assert len(fake_ai_provider.calls) == 1  # ein einziger Batch-Call, kein Fallback

    async def test_corner_case_falsche_anzahl_loest_einzelfallback_aus(self, db_session, ai_settings, fake_ai_provider):
        # Regressionsfall aus Abschnitt 3 des Testkonzepts: das Modell ignoriert
        # gelegentlich die geforderte Batch-Größe. classify_batch_for_app muss
        # dann automatisch auf einzelne classify_for_app-Aufrufe zurückfallen.
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        items = [{"id": "1", "raw": "Interview-Einladung"}, {"id": "2", "raw": "Newsletter, irrelevant"}]

        fake_ai_provider.queue_content(load_fixture("batch_classify_wrong_count.json"))  # Batch-Versuch (verworfen)
        fake_ai_provider.queue_content(load_fixture("match_classify_valid.json"))  # Fallback Item 1
        fake_ai_provider.queue_content('{"relevant": false, "confidence": 0.05, "event_type": "note", "datum": null, "titel": "Newsletter", "extract": null, "suggested_main_status": null, "suggested_sub_status": null}')  # Fallback Item 2

        results = await classify_batch_for_app(db_session, "gmail", items, {"id": app.id, "firma": app.firma, "rolle": app.rolle})

        assert len(results) == 2
        assert len(fake_ai_provider.calls) == 3  # 1 Batch-Versuch + 2 Einzel-Fallbacks
        assert results[1]["relevant"] is False

    async def test_negativ_rate_limit_im_batch_wird_nicht_abgefangen(self, db_session, ai_settings, fake_ai_provider):
        # AIRateLimited muss auch aus dem Batch-Pfad durchgereicht werden, statt
        # fälschlich in den Fallback zu laufen (sonst würde bei Rate-Limits pro
        # Item erneut angefragt und das Limit weiter verschärft).
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        items = [{"id": "1", "raw": "a"}, {"id": "2", "raw": "b"}]
        fake_ai_provider.queue_error(
            litellm.RateLimitError(message="rate limited", llm_provider="groq", model=ai_settings.model)
        )

        with pytest.raises(AIRateLimited):
            await classify_batch_for_app(db_session, "gmail", items, {"id": app.id, "firma": app.firma, "rolle": app.rolle})
