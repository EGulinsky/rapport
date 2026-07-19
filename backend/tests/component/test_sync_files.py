"""L1 Component — sync_files.py: _do_local_files() und die HTTP-Endpunkte.

Der Rapport Agent wird nicht direkt angesprochen, sondern über
app.agent_client.agent_get/agent_post (die selbst httpx.AsyncClient nutzen) —
Mocking-Grenze ist daher httpx.AsyncClient.get/post direkt, wie in
tests/component/test_sync_targeted_agent_sources.py etabliert.
"""
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app import models
from app.routers.sync_files import _do_local_files, _rolle_in_name
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.component


def _mock_response(json_data, status=200, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.text = text
    resp.headers = {"content-type": "application/json"}
    return resp


def _cfg(db_session, **overrides) -> models.FilesConfig:
    defaults = dict(enabled=True, folder_path="/Users/x/Bewerbungen", user_id=1)
    defaults.update(overrides)
    cfg = models.FilesConfig(**defaults)
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestRolleInName:
    def test_positiv_rolle_im_namen_enthalten(self):
        assert _rolle_in_name("Backend Engineer", "contoso backend engineer 2026") is True

    def test_negativ_rolle_nicht_enthalten(self):
        assert _rolle_in_name("Backend Engineer", "contoso frontend developer") is False

    def test_corner_case_m_w_d_suffix_wird_entfernt(self):
        assert _rolle_in_name("Backend Engineer (m/w/d)", "contoso backend engineer ordner") is True

    def test_negativ_leere_rolle_liefert_false(self):
        assert _rolle_in_name("", "irgendein ordner") is False


class TestDoLocalFiles:
    async def test_negativ_kein_ordner_konfiguriert_liefert_fehler(self, db_session):
        _cfg(db_session, folder_path=None)

        result = await _do_local_files(1)

        assert result["errors"] == ["Kein Ordner konfiguriert."]

    async def test_negativ_deaktiviert_liefert_leeres_ergebnis(self, db_session):
        _cfg(db_session, enabled=False)

        result = await _do_local_files(1)

        assert result == {"processed": 0, "created": 0, "skipped": 0, "errors": []}

    async def test_negativ_ohne_bekannte_firmen_liefert_leeres_ergebnis(self, db_session):
        _cfg(db_session)

        result = await _do_local_files(1)

        assert result == {"processed": 0, "created": 0, "skipped": 0, "errors": []}

    async def test_positiv_datei_im_passenden_ordner_wird_als_event_angelegt(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=10))
        contact_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        files = [{"path": "/root/Contoso AG/cv.pdf", "name": "cv.pdf", "subfolder": "Contoso AG", "modified": None}]

        async def fake_get(self, url, **kw):
            return _mock_response(files)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_local_files(1)

        assert result["created"] == 1
        assert result["errors"] == []
        event = db_session.query(models.Event).filter_by(source="local_files").one()
        assert event.application_id == app.id
        assert event.titel == "cv.pdf"

    async def test_positiv_datum_zeit_wird_aus_datei_mtime_gesetzt(self, db_session, monkeypatch):
        from datetime import datetime, timezone

        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=10))
        contact_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        mtime = datetime(2026, 7, 18, 11, 15, 0, tzinfo=timezone.utc)
        files = [{"path": "/root/Contoso AG/cv.pdf", "name": "cv.pdf", "subfolder": "Contoso AG", "modified": mtime.timestamp()}]

        async def fake_get(self, url, **kw):
            return _mock_response(files)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        await _do_local_files(1)

        event = db_session.query(models.Event).filter_by(source="local_files").one()
        assert event.datum == date(2026, 7, 18)
        assert event.datum_zeit == datetime(2026, 7, 18, 11, 15, 0)

    async def test_negativ_agent_nicht_erreichbar_liefert_fehler(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        async def fake_get(self, url, **kw):
            raise RuntimeError("connection refused")

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_local_files(1)

        assert result["created"] == 0
        assert any("nicht erreichbar" in e for e in result["errors"])

    async def test_negativ_agent_fehlerstatus_liefert_fehler(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        async def fake_get(self, url, **kw):
            return _mock_response({"error": "Ordner nicht gefunden"}, status=404)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_local_files(1)

        assert result["created"] == 0
        assert any("Agent-Fehler" in e for e in result["errors"])

    async def test_negativ_ordner_ohne_firmenmatch_wird_uebersprungen(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        files = [{"path": "/root/Unbekannt/cv.pdf", "name": "cv.pdf", "subfolder": "Unbekannte Firma", "modified": None}]

        async def fake_get(self, url, **kw):
            return _mock_response(files)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_local_files(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_positiv_mehrdeutiger_ordner_wird_ueber_rolle_disambiguiert(self, db_session, monkeypatch):
        app1 = application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer", datum_bewerbung=date.today() - timedelta(days=5))
        application_factory(db_session, firma="Contoso AG", rolle="Frontend Engineer", datum_bewerbung=date.today() - timedelta(days=5))
        contact_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        files = [{"path": "/root/Contoso AG Backend Engineer/cv.pdf", "name": "cv.pdf", "subfolder": "Contoso AG Backend Engineer", "modified": None}]

        async def fake_get(self, url, **kw):
            return _mock_response(files)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_local_files(1)

        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="local_files").one()
        assert event.application_id == app1.id

    async def test_negativ_mehrdeutiger_ordner_ohne_eindeutige_rolle_wird_uebersprungen(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        application_factory(db_session, firma="Contoso AG", rolle="Frontend Engineer")
        contact_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        files = [{"path": "/root/Contoso AG/cv.pdf", "name": "cv.pdf", "subfolder": "Contoso AG", "modified": None}]

        async def fake_get(self, url, **kw):
            return _mock_response(files)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_local_files(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_positiv_bereits_synchronisierte_datei_wird_uebersprungen(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=5))
        contact_factory(db_session, firma="Contoso AG")
        _cfg(db_session)

        import hashlib
        path = "/root/Contoso AG/cv.pdf"
        file_id = hashlib.md5(path.encode()).hexdigest()[:20]
        db_session.add(models.SyncedItem(source="local_files", external_id=file_id, user_id=1))
        db_session.commit()

        files = [{"path": path, "name": "cv.pdf", "subfolder": "Contoso AG", "modified": None}]

        async def fake_get(self, url, **kw):
            return _mock_response(files)

        monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

        result = await _do_local_files(1)

        assert result["created"] == 0
        assert result["skipped"] == 1
