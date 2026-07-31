"""L0 Unit — app/ai/timeline_text.py's build_timeline_text(), the shared
chronological formatter used by both rapportGPT's get_application_detail tool
and the match-score/success-probability prompts. Uses plain (unpersisted)
Event instances since the function only reads attributes, no DB needed."""
from datetime import date, timedelta

import pytest

from app import models
from app.ai.timeline_text import build_timeline_text

pytestmark = pytest.mark.unit


def _event(**overrides) -> models.Event:
    defaults = dict(typ="mail", datum=date.today(), autor=None, titel=None, notiz=None)
    defaults.update(overrides)
    return models.Event(**defaults)


class TestBuildTimelineText:
    def test_positiv_leere_liste_liefert_platzhalter(self):
        assert build_timeline_text([]) == "(keine Ereignisse)"

    def test_positiv_events_ohne_datum_werden_ausgeschlossen(self):
        result = build_timeline_text([_event(datum=None)])
        assert result == "(keine Ereignisse)"

    def test_positiv_sortiert_chronologisch(self):
        older = _event(datum=date.today() - timedelta(days=10), titel="Erstes")
        newer = _event(datum=date.today() - timedelta(days=1), titel="Zweites")

        result = build_timeline_text([newer, older])

        assert result.index("Erstes") < result.index("Zweites")

    def test_positiv_zeigt_alter_in_tagen(self):
        result = build_timeline_text([_event(datum=date.today() - timedelta(days=5))])
        assert "(vor 5d)" in result

    def test_positiv_autor_wird_gekuerzt_auf_namen(self):
        result = build_timeline_text([_event(autor='"Jane Doe" <jane@example.com>')])
        assert "von: Jane Doe" in result
        assert "jane@example.com" not in result

    def test_positiv_titel_und_notiz_werden_eingebettet(self):
        result = build_timeline_text([_event(titel="Interview Einladung", notiz="Termin nächste Woche")])
        assert "Betreff: Interview Einladung" in result
        assert "Inhalt: Termin nächste Woche" in result

    def test_negativ_leere_notiz_wird_nicht_angezeigt(self):
        result = build_timeline_text([_event(notiz="   ")])
        assert "Inhalt:" not in result
