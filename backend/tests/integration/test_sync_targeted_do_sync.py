"""L3 Integration — _do_sync() in sync_targeted.py, die zentrale Hintergrundlauf-
Orchestrierung des gezielten Einzelbewerbungs-Syncs (parallele Quellen-Syncs,
Kontakte-Sync, Anrufliste-Sync).

_do_sync() öffnet intern eine EIGENE `SessionLocal()` statt die Test-`db_session`
zu nutzen (siehe tests/integration/conftest.py-Modul-Docstring) — Setup-Daten
müssen daher per `db_session.commit()` sichtbar gemacht werden, nicht nur
geflusht. Die einzelnen Quellen-Sync-Funktionen selbst (_sync_gmail_for_app
etc.) sind bereits in tests/integration/test_sync_targeted_domains.py und
Nachbardateien abgedeckt — hier geht es nur um die Orchestrierung: Ergebnisse
werden aufsummiert, Fehler pro Quelle gesammelt, und die Kontakte-/Anrufliste-
Sync-Schritte dürfen den Gesamtlauf nicht zum Absturz bringen, wenn sie
fehlschlagen.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.routers.sync_targeted import _do_sync
from tests.factories import application_factory

pytestmark = pytest.mark.integration


def _mock_agent_empty(monkeypatch) -> None:
    """iCloud Notizen ruft immer den Rapport Agenten — unabhängig von Google-/
    iCloud-Konfiguration. Ohne Mock schlägt jeder _do_sync()-Lauf mit einem
    Verbindungsfehler zum (in Tests nicht existenten) Agenten fehl."""
    async def fake_get(self, url, **kw):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        return resp

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)


class TestDoSync:
    async def test_positiv_kompletter_lauf_ohne_externe_konfiguration(self, db_session, monkeypatch):
        _mock_agent_empty(monkeypatch)
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        result = await _do_sync(app.id)

        # Ohne Google-/iCloud-Konfiguration liefert jede Quelle (0, 0, []) —
        # der Gesamtlauf muss trotzdem sauber durchlaufen und ein Ergebnis liefern.
        assert result["created"] == 0
        assert result["processed"] == 0
        assert result["errors"] == []

    async def test_negativ_app_nicht_gefunden_liefert_fehler_ohne_absturz(self, db_session):
        result = await _do_sync(999999)

        assert result["created"] == 0
        assert result["processed"] == 0
        assert any("nicht gefunden" in e for e in result["errors"])

    async def test_negativ_kontakte_sync_fehler_wird_gesammelt_ohne_absturz(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        async def _boom(app_arg, terms, db, user_id=None):
            raise RuntimeError("CardDAV kaputt")

        monkeypatch.setattr("app.routers.sync_targeted._sync_contacts_for_app", _boom)

        result = await _do_sync(app.id)

        assert any("Kontakte" in e and "CardDAV kaputt" in e for e in result["errors"])

    async def test_negativ_anrufliste_sync_fehler_wird_gesammelt_ohne_absturz(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        async def _boom(app_arg, app_dict, db, user_id=None):
            raise RuntimeError("Agent kaputt")

        monkeypatch.setattr("app.routers.sync_targeted._sync_calls_for_app", _boom)

        result = await _do_sync(app.id)

        assert any("Anrufliste" in e and "Agent kaputt" in e for e in result["errors"])

    async def test_positiv_fehler_einer_einzelnen_quelle_landet_gesammelt_im_ergebnis(
        self, db_session, monkeypatch
    ):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        async def _boom(app_arg, app_dict, terms, db, user_id=None):
            raise RuntimeError("Gmail API kaputt")

        monkeypatch.setattr("app.routers.sync_targeted._sync_gmail_for_app", _boom)

        result = await _do_sync(app.id)

        assert any("Gmail" in e and "Gmail API kaputt" in e for e in result["errors"])
