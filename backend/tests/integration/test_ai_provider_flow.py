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
from app.ai.tasks import (
    classify_batch_for_app,
    classify_for_app,
    compute_match_score,
    compute_success_probability,
    extract_application_from_text,
    match_and_classify,
    test_connection as ai_test_connection,
)
from tests.factories import application_factory
from tests.integration.conftest import load_fixture

pytestmark = pytest.mark.integration


class TestCompleteErrorMapping:
    """Deckt die Fehlerzweige von app/ai/provider.py::complete() ab — insbesondere
    die drei unterschiedlichen BadRequestError-Nachrichten und die beiden
    AINotConfigured-Auslöser (keine/deaktivierte Konfiguration). Nutzt
    test_connection() als einfachsten complete()-Aufrufer, da sie kein
    Application-Objekt braucht."""

    async def test_negativ_keine_ai_konfiguration_wirft_ainotconfigured(self, db_session):
        # bewusst KEIN ai_settings-Fixture — es existiert keine Zeile in der Tabelle
        with pytest.raises(AINotConfigured):
            await ai_test_connection(db_session)

    async def test_negativ_deaktivierter_ai_provider_wirft_ainotconfigured(self, db_session):
        db_session.add(models.AiSettings(provider="groq", model="groq/llama-3.3-70b-versatile", enabled=False))
        db_session.commit()

        with pytest.raises(AINotConfigured):
            await ai_test_connection(db_session)

    async def test_negativ_authentication_error_wirft_aibadrequest(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_error(
            litellm.AuthenticationError(message="invalid api key", llm_provider="groq", model=ai_settings.model)
        )

        with pytest.raises(AIBadRequest, match="API-Key ungültig"):
            await ai_test_connection(db_session)

    async def test_negativ_json_modus_nicht_unterstuetzt_wirft_hilfreiche_meldung(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_error(
            litellm.BadRequestError(message="json_validate_failed: model refused", model=ai_settings.model, llm_provider="groq")
        )

        with pytest.raises(AIBadRequest, match="unterstützt keinen JSON-Modus"):
            await ai_test_connection(db_session)

    async def test_negativ_modell_nicht_gefunden_wirft_hilfreiche_meldung(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_error(
            litellm.BadRequestError(message="The model does not exist", model=ai_settings.model, llm_provider="groq")
        )

        with pytest.raises(AIBadRequest, match="nicht gefunden beim Anbieter"):
            await ai_test_connection(db_session)

    async def test_negativ_sonstiger_bad_request_wird_gekuerzt_durchgereicht(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_error(
            litellm.BadRequestError(message="context_length_exceeded: too many tokens", model=ai_settings.model, llm_provider="groq")
        )

        with pytest.raises(AIBadRequest, match="Ungültige Anfrage"):
            await ai_test_connection(db_session)


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

    async def test_corner_case_leere_item_liste_liefert_leeres_ergebnis(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")

        results = await classify_batch_for_app(db_session, "gmail", [], {"id": app.id, "firma": app.firma, "rolle": app.rolle})

        assert results == []
        assert fake_ai_provider.calls == []

    async def test_negativ_rate_limit_bei_einzelnem_fallback_item_wird_durchgereicht(self, db_session, ai_settings, fake_ai_provider):
        # Ein Fehler im Batch-Versuch löst den Fallback aus; tritt DANACH bei
        # einem einzelnen Fallback-Item ein Rate-Limit auf, muss dieses (anders
        # als sonstige Fehler) durchgereicht statt in einen Default umgewandelt werden.
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        items = [{"id": "1", "raw": "a"}, {"id": "2", "raw": "b"}]

        fake_ai_provider.queue_content(load_fixture("malformed.txt"))  # Batch-Versuch schlägt fehl
        fake_ai_provider.queue_error(
            litellm.RateLimitError(message="rate limited", llm_provider="groq", model=ai_settings.model)
        )  # Fallback Item 1

        with pytest.raises(AIRateLimited):
            await classify_batch_for_app(db_session, "gmail", items, {"id": app.id, "firma": app.firma, "rolle": app.rolle})

    async def test_corner_case_einzelnes_item_nutzt_direkten_klassifizierungspfad(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        fake_ai_provider.queue_content(
            '{"relevant": true, "confidence": 0.8, "event_type": "note", "datum": null, '
            '"titel": "Info", "extract": "Kurze Info", "suggested_main_status": null, "suggested_sub_status": null}'
        )

        results = await classify_batch_for_app(db_session, "gmail", [{"id": "1", "raw": "Inhalt"}], {"id": app.id, "firma": app.firma, "rolle": app.rolle})

        assert len(results) == 1
        assert results[0]["application_id"] == app.id
        assert "Zu prüfende Bewerbung" in fake_ai_provider.calls[0]["messages"][1]["content"]

    async def test_positiv_headhunter_mit_zielfirma_baut_eingeschraenkten_batch_prompt(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso Recruiting", rolle="Backend Engineer", is_headhunter=True)
        items = [{"id": "1", "raw": "Interview-Einladung"}, {"id": "2", "raw": "Newsletter, irrelevant"}]
        fake_ai_provider.queue_content(load_fixture("batch_classify_valid.json"))

        await classify_batch_for_app(
            db_session, "gmail", items,
            {"id": app.id, "firma": app.firma, "rolle": app.rolle, "zielfirma": "Globex AG"},
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "Headhunter: Contoso Recruiting" in prompt
        assert "Zielunternehmen: Globex AG" in prompt

    async def test_corner_case_fehler_bei_batch_versuch_loest_fallback_aus(self, db_session, ai_settings, fake_ai_provider):
        # Nicht nur eine falsche Item-Anzahl, sondern ein echter Fehler beim
        # Batch-Versuch selbst (z.B. kaputtes JSON) muss ebenfalls in den
        # Fallback laufen — UND ein Fehler bei einem einzelnen Fallback-Item
        # darf den Gesamtlauf nicht abbrechen, sondern liefert einen Default.
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        items = [{"id": "1", "raw": "Interview-Einladung"}, {"id": "2", "raw": "Newsletter, irrelevant"}]

        fake_ai_provider.queue_content(load_fixture("malformed.txt"))  # Batch-Versuch schlägt fehl
        fake_ai_provider.queue_content(load_fixture("match_classify_valid.json"))  # Fallback Item 1 (ok)
        fake_ai_provider.queue_content(load_fixture("malformed.txt"))  # Fallback Item 2 (schlägt auch fehl)

        results = await classify_batch_for_app(db_session, "gmail", items, {"id": app.id, "firma": app.firma, "rolle": app.rolle})

        assert len(results) == 2
        assert len(fake_ai_provider.calls) == 3
        assert results[1] == {"relevant": False, "confidence": 0.0, "application_id": None}


class TestClassifyForApp:
    async def test_positiv_relevant_setzt_application_id(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        fake_ai_provider.queue_content(
            '{"relevant": true, "confidence": 0.8, "event_type": "note", "datum": null, '
            '"titel": "Info", "extract": "Kurze Info", "suggested_main_status": null, "suggested_sub_status": null}'
        )

        result = await classify_for_app(db_session, "gmail", "Irgendein Inhalt", {"id": app.id, "firma": app.firma, "rolle": app.rolle})

        assert result["application_id"] == app.id
        assert result["relevant"] is True

    async def test_negativ_nicht_relevant_setzt_confidence_null_und_keine_id(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        fake_ai_provider.queue_content(
            '{"relevant": false, "confidence": 0.4, "event_type": "note", "datum": null, '
            '"titel": "Irrelevant", "extract": null, "suggested_main_status": null, "suggested_sub_status": null}'
        )

        result = await classify_for_app(db_session, "gmail", "Newsletter", {"id": app.id, "firma": app.firma, "rolle": app.rolle})

        assert result["application_id"] is None
        assert result["confidence"] == 0.0

    async def test_positiv_headhunter_mit_zielfirma_baut_eingeschraenkten_prompt(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso Recruiting", rolle="Backend Engineer", is_headhunter=True)
        fake_ai_provider.queue_content(
            '{"relevant": true, "confidence": 0.7, "event_type": "note", "datum": null, '
            '"titel": "Info", "extract": "Kurze Info", "suggested_main_status": null, "suggested_sub_status": null}'
        )

        await classify_for_app(
            db_session, "gmail", "Inhalt",
            {"id": app.id, "firma": app.firma, "rolle": app.rolle, "zielfirma": "Globex AG"},
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "Headhunter: Contoso Recruiting" in prompt
        assert "Zielunternehmen: Globex AG" in prompt


class TestTestConnection:
    async def test_positiv_ok_antwort_liefert_ok(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content('{"ok": true}')

        result = await ai_test_connection(db_session)

        assert result == "ok"

    async def test_negativ_unerwartete_antwort_wird_durchgereicht(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content('{"ok": false}')

        result = await ai_test_connection(db_session)

        assert "Unerwartete Antwort" in result


class TestGeminiThinkingDisabled:
    """Regression for a live-reported bug: selecting a "thinking"-enabled
    Gemini model (2.5 Flash/Pro, unlike Flash-Lite which doesn't think by
    default) caused every AI call to fail with a bare json.JSONDecodeError
    ("Unterminated string...") — the hidden reasoning pass consumed the
    entire max_tokens budget, truncating the JSON response mid-string. Fixed
    by disabling thinking (reasoning_effort="none") for any Gemini model that
    actually supports the knob (see _disable_gemini_thinking in provider.py)."""

    async def test_positiv_gemini_25_flash_erhaelt_reasoning_effort_none(self, db_session, ai_settings, fake_ai_provider):
        ai_settings.model = "gemini/gemini-2.5-flash"
        fake_ai_provider.queue_content('{"ok": true}')

        await ai_test_connection(db_session)

        assert fake_ai_provider.calls[0]["reasoning_effort"] == "none"

    async def test_negativ_aeltere_gemini_modelle_ohne_thinking_bleiben_unangetastet(self, db_session, ai_settings, fake_ai_provider):
        # gemini-1.5-flash doesn't support reasoning_effort at all -- passing
        # it would raise litellm.UnsupportedParamsError, so it must stay absent.
        ai_settings.model = "gemini/gemini-1.5-flash"
        fake_ai_provider.queue_content('{"ok": true}')

        await ai_test_connection(db_session)

        assert "reasoning_effort" not in fake_ai_provider.calls[0]

    async def test_negativ_andere_provider_bleiben_unangetastet(self, db_session, ai_settings, fake_ai_provider):
        # ai_settings already defaults to a groq model -- confirm the Gemini-only
        # gate doesn't leak into other providers.
        fake_ai_provider.queue_content('{"ok": true}')

        await ai_test_connection(db_session)

        assert "reasoning_effort" not in fake_ai_provider.calls[0]

    async def test_positiv_lehnt_gemini_alias_reasoning_effort_ab_retry_ohne_erfolgreich(
        self, db_session, ai_settings, fake_ai_provider,
    ):
        # Regression follow-up: litellm's static param table claims some
        # Gemini aliases (e.g. "-latest" aliases) support reasoning_effort,
        # but the live API rejects it outright ("Request contains an invalid
        # argument", 400 INVALID_ARGUMENT). Since we only ever add the param
        # ourselves, retry once without it instead of failing the whole call.
        ai_settings.model = "gemini/gemini-flash-lite-latest"
        fake_ai_provider.queue_error(
            litellm.BadRequestError(
                message='{"error": {"code": 400, "message": "Request contains an invalid argument.", "status": "INVALID_ARGUMENT"}}',
                llm_provider="gemini", model=ai_settings.model,
            )
        )
        fake_ai_provider.queue_content('{"ok": true}')

        await ai_test_connection(db_session)

        assert len(fake_ai_provider.calls) == 2
        assert fake_ai_provider.calls[0]["reasoning_effort"] == "none"
        assert "reasoning_effort" not in fake_ai_provider.calls[1]

    async def test_negativ_bad_request_ohne_reasoning_effort_wird_nicht_wiederholt(
        self, db_session, ai_settings, fake_ai_provider,
    ):
        # A genuine BadRequestError unrelated to our own reasoning_effort
        # addition (e.g. a groq model) must propagate immediately -- no retry.
        fake_ai_provider.queue_error(
            litellm.BadRequestError(message="context_length_exceeded", llm_provider="groq", model=ai_settings.model)
        )

        with pytest.raises(AIBadRequest, match="context_length_exceeded"):
            await ai_test_connection(db_session)

        assert len(fake_ai_provider.calls) == 1


class TestExtractApplicationFromText:
    async def test_positiv_direkter_arbeitgeber(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(
            '{"firma": "Contoso AG", "rolle": "Backend Engineer", "quelle": "LinkedIn", '
            '"is_headhunter": false, "zielfirma_bei_hh": null, "kommentar": "München, Senior-Level"}'
        )

        result = await extract_application_from_text(db_session, "Contoso AG sucht einen Backend Engineer in München.")

        assert result["firma"] == "Contoso AG"
        assert result["rolle"] == "Backend Engineer"
        assert result["is_headhunter"] is False
        assert result["zielfirma_bei_hh"] is None

    async def test_positiv_headhunter_anzeige(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(
            '{"firma": "Contoso Recruiting", "rolle": "Backend Engineer", "quelle": "LinkedIn", '
            '"is_headhunter": true, "zielfirma_bei_hh": "Börsennotierter Technologiekonzern", "kommentar": null}'
        )

        result = await extract_application_from_text(
            db_session, "Wir suchen im Auftrag unseres Kunden einen Backend Engineer."
        )

        assert result["is_headhunter"] is True
        assert result["zielfirma_bei_hh"] == "Börsennotierter Technologiekonzern"

    async def test_negativ_fehlende_felder_werden_zu_leerstring_oder_default(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content("{}")

        result = await extract_application_from_text(db_session, "Kaum Info")

        assert result["firma"] == ""
        assert result["rolle"] == ""
        assert result["quelle"] == "LinkedIn"
        assert result["is_headhunter"] is False
        assert result["zielfirma_bei_hh"] is None
        assert result["kommentar"] is None


class TestMatchAndClassifyFormatting:
    async def test_positiv_zielfirma_und_besetzt_von_werden_formatiert(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso Recruiting", rolle="Backend Engineer")
        fake_ai_provider.queue_content(load_fixture("match_classify_valid.json"))

        await match_and_classify(
            db_session, source="gmail", raw_text="Inhalt",
            applications=[{"id": app.id, "firma": app.firma, "rolle": app.rolle, "zielfirma": "Globex AG", "besetzt_von": "Contoso Recruiting"}],
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "(Zielfirma: Globex AG)" in prompt
        assert "(besetzt von: Contoso Recruiting)" in prompt

    async def test_positiv_hint_apps_werden_im_prompt_bevorzugt(self, db_session, ai_settings, fake_ai_provider):
        app = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        other = application_factory(db_session, firma="Globex AG", rolle="Frontend Engineer")
        fake_ai_provider.queue_content(load_fixture("match_classify_valid.json"))

        await match_and_classify(
            db_session, source="gmail", raw_text="Inhalt",
            applications=[
                {"id": app.id, "firma": app.firma, "rolle": app.rolle},
                {"id": other.id, "firma": other.firma, "rolle": other.rolle},
            ],
            hint_apps=[{"id": app.id, "firma": app.firma, "rolle": app.rolle}],
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "HINWEIS: Dieser Eintrag wurde durch Suche nach dem Firmennamen gefunden" in prompt


class TestComputeMatchScore:
    async def test_positiv_liefert_score_und_reasoning(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        result = await compute_match_score(
            db_session, firma="Contoso AG", rolle="Backend Engineer",
            profile_block="=== BEWERBERPROFIL ===\nLebenslauf (Auszug):\n5 Jahre Python\n\n",
            jd_texts=[{"filename": "jd.txt", "text": "Python, Kubernetes, 3+ Jahre"}],
        )

        assert result["match_score"] == 78
        assert "Python-Erfahrung" in result["reasoning"]

    async def test_positiv_jd_texte_werden_gelabelt_in_prompt_eingebettet(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        await compute_match_score(
            db_session, firma="Contoso AG", rolle="Backend Engineer",
            profile_block="",
            jd_texts=[{"filename": "stellenanzeige.pdf", "text": "Muss Python können"}],
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "=== STELLENANZEIGE(N) ===" in prompt
        assert "[stellenanzeige.pdf]" in prompt
        assert "Muss Python können" in prompt

    async def test_negativ_score_ausserhalb_bereich_wird_geklammert(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content('{"match_score": 150, "reasoning": "..."}')

        result = await compute_match_score(db_session, firma="X", rolle="Y", profile_block="", jd_texts=[])

        assert result["match_score"] == 100

    async def test_negativ_score_als_ungueltiger_typ_wird_zu_default(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content('{"match_score": "sehr gut", "reasoning": "..."}')

        result = await compute_match_score(db_session, firma="X", rolle="Y", profile_block="", jd_texts=[])

        assert result["match_score"] == 0

    async def test_positiv_englische_sprache_wird_im_prompt_angefordert(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        await compute_match_score(db_session, firma="X", rolle="Y", profile_block="", jd_texts=[], ui_language="en")

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert 'Write "reasoning" in English.' in prompt

    async def test_positiv_system_prompt_fordert_strenge_bewertung(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        await compute_match_score(db_session, firma="X", rolle="Y", profile_block="", jd_texts=[])

        system_prompt = fake_ai_provider.calls[0]["messages"][0]["content"]
        assert "anspruchsvoll" in system_prompt
        user_prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "Sei streng" in user_prompt

    async def test_positiv_feedback_entries_werden_im_prompt_eingebettet(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        await compute_match_score(
            db_session, firma="X", rolle="Y", profile_block="", jd_texts=[],
            feedback_entries=["Die Rolle braucht 10 Jahre Java, ich habe keine."],
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "HINWEISE DES BEWERBERS" in prompt
        assert "10 Jahre Java" in prompt

    async def test_negativ_ohne_feedback_kein_hinweisblock(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("match_score_valid.json"))

        await compute_match_score(db_session, firma="X", rolle="Y", profile_block="", jd_texts=[])

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "HINWEISE DES BEWERBERS" not in prompt


class TestComputeSuccessProbability:
    async def test_positiv_liefert_probability_und_reasoning(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        result = await compute_success_probability(
            db_session, firma="Contoso AG", rolle="Backend Engineer",
            main_status="hr", sub_status="1_done",
            match_score=78, match_reasoning="Guter Fit",
            timeline_text="(keine Ereignisse)", ghosting=False,
        )

        assert result["success_probability"] == 55
        assert "HR-Gespräch" in result["reasoning"]

    async def test_positiv_ghosting_hinweis_wird_in_prompt_eingebettet(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="hr", sub_status=None,
            match_score=50, match_reasoning="...", timeline_text="...", ghosting=True,
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "gilt aktuell als Ghosting" in prompt

    async def test_negativ_kein_ghosting_hinweis_ohne_ghosting(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="hr", sub_status=None,
            match_score=50, match_reasoning="...", timeline_text="...", ghosting=False,
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "gilt aktuell als Ghosting" not in prompt

    async def test_negativ_probability_ausserhalb_bereich_wird_geklammert(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content('{"success_probability": -20, "reasoning": "..."}')

        result = await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="applied", sub_status=None,
            match_score=10, match_reasoning="...", timeline_text="...", ghosting=False,
        )

        assert result["success_probability"] == 0

    async def test_positiv_match_score_und_timeline_werden_im_prompt_referenziert(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="hr", sub_status=None,
            match_score=91, match_reasoning="Exzellenter Fit", timeline_text="01.01.2026 [mail]", ghosting=False,
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "91/100" in prompt
        assert "Exzellenter Fit" in prompt
        assert "01.01.2026 [mail]" in prompt

    async def test_positiv_aufgabe_erwaehnt_kontakthaeufigkeit_und_historie_nicht_nur_aktivitaet(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="hr", sub_status=None,
            match_score=50, match_reasoning="...", timeline_text="...", ghosting=False,
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "Kontakthäufigkeit" in prompt
        assert "historischen Vergleichsdaten" in prompt
        assert "nicht nur den reinen Zeitverlauf/die Aktivität" in prompt

    async def test_positiv_activity_stats_block_wird_eingebettet(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="hr", sub_status=None,
            match_score=50, match_reasoning="...", timeline_text="...", ghosting=False,
            activity_stats_block="=== KONTAKTHÄUFIGKEIT & -RICHTUNG ===\nAnzahl Ereignisse gesamt: 3\n\n",
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "=== KONTAKTHÄUFIGKEIT & -RICHTUNG ===" in prompt
        assert "Anzahl Ereignisse gesamt: 3" in prompt

    async def test_positiv_history_block_wird_eingebettet(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="hr", sub_status=None,
            match_score=50, match_reasoning="...", timeline_text="...", ghosting=False,
            history_block="=== HISTORISCHE VERGLEICHSDATEN ===\nVon 5 bisherigen Bewerbungen...\n\n",
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "=== HISTORISCHE VERGLEICHSDATEN ===" in prompt
        assert "Von 5 bisherigen Bewerbungen" in prompt

    async def test_positiv_feedback_entries_werden_eingebettet(self, db_session, ai_settings, fake_ai_provider):
        fake_ai_provider.queue_content(load_fixture("success_probability_valid.json"))

        await compute_success_probability(
            db_session, firma="X", rolle="Y", main_status="hr", sub_status=None,
            match_score=50, match_reasoning="...", timeline_text="...", ghosting=False,
            feedback_entries=["Sie haben informell schon abgesagt."],
        )

        prompt = fake_ai_provider.calls[0]["messages"][1]["content"]
        assert "HINWEISE DES BEWERBERS" in prompt
        assert "informell schon abgesagt" in prompt
