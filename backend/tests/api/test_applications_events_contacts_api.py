"""L2 API — Events/Kontakte-Unterrouten, Stats, AI-Assessment und Löschen in
applications.py, die tests/api/test_applications_api.py nicht abdeckt."""
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app import models
from tests.factories import application_factory, contact_factory, event_factory

pytestmark = pytest.mark.api


def _make_verbose(db):
    db.add(models.SyncSettings(user_id=1, audit_log_level="verbose"))
    db.commit()


class TestDeleteApplication:
    def test_positiv_loescht_bewerbung_und_schreibt_audit(self, client, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        resp = client.delete(f"/api/applications/{app.id}")

        assert resp.status_code == 204
        assert db_session.query(models.Application).filter_by(id=app.id).first() is None
        assert db_session.query(models.AuditLog).filter_by(app_id=app.id, action="delete").first() is not None

    def test_negativ_nicht_gefunden_liefert_404(self, client):
        resp = client.delete("/api/applications/999")
        assert resp.status_code == 404


class TestStats:
    def test_positiv_liefert_aggregierte_statistik(self, client, db_session):
        application_factory(db_session, main_status="applied")
        application_factory(db_session, main_status="applied")
        application_factory(db_session, main_status="rejected")
        db_session.commit()

        resp = client.get("/api/applications/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["rejected"] == 1
        assert body["active"] == 2
        assert body["by_status"]["applied"] == 2


class TestAiAssessAll:
    def test_positiv_streamt_start_und_done_events(self, client, db_session):
        application_factory(db_session, main_status="applied")
        db_session.commit()

        async def _fake_assess(db, app, lang="de"):
            return {"color": "green", "reasoning": "gut", "next_step": "abwarten"}

        with patch("app.ai.tasks.assess_application", new=_fake_assess):
            resp = client.get("/api/applications/ai-assess-all")

        assert resp.status_code == 200
        assert '"status": "start"' in resp.text
        assert '"status": "done"' in resp.text

    def test_negativ_ai_not_configured_stoppt_stream_mit_fehler(self, client, db_session):
        from app.ai.provider import AINotConfigured

        application_factory(db_session, main_status="applied")
        db_session.commit()

        async def _fake_assess(db, app, lang="de"):
            raise AINotConfigured("kein Provider konfiguriert")

        with patch("app.ai.tasks.assess_application", new=_fake_assess):
            resp = client.get("/api/applications/ai-assess-all")

        assert resp.status_code == 200
        assert "error" in resp.text


class TestExtractFromLinkedinUrl:
    def test_negativ_kein_linkedin_link_liefert_400(self, client):
        resp = client.post("/api/applications/extract-from-linkedin-url", json={"url": "https://example.com/job/1"})
        assert resp.status_code == 400

    def test_positiv_extrahiert_und_legt_firmenprofil_an(self, client, db_session):
        async def _fake_load(url, db):
            return {"description": "Wir suchen einen Backend Engineer.", "company": "Contoso AG"}

        async def _fake_extract(db, text):
            return {
                "firma": "Anderer Name", "rolle": "Backend Engineer", "quelle": "LinkedIn",
                "is_headhunter": False, "zielfirma_bei_hh": None, "kommentar": None,
            }

        with patch("app.linkedin_job_description.load_job_description", new=_fake_load), \
             patch("app.ai.tasks.extract_application_from_text", new=_fake_extract), \
             patch("app.routers.sync_company._run_sync_batch"):
            resp = client.post("/api/applications/extract-from-linkedin-url", json={"url": "https://linkedin.com/jobs/view/1"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["firma"] == "Contoso AG"  # gescrapter Firmenname überschreibt den KI-Wert
        assert body["company_profile_id"] is not None
        assert db_session.query(models.CompanyProfile).filter_by(name_display="Contoso AG").count() == 1

    def test_negativ_ungueltige_url_liefert_400(self, client):
        async def _fake_load(url, db):
            raise ValueError("Seite konnte nicht geladen werden")

        with patch("app.linkedin_job_description.load_job_description", new=_fake_load):
            resp = client.post("/api/applications/extract-from-linkedin-url", json={"url": "https://linkedin.com/jobs/view/1"})

        assert resp.status_code == 400

    def test_negativ_ai_rate_limit_liefert_429(self, client):
        from app.ai.provider import AIRateLimited

        async def _fake_load(url, db):
            return {"description": "Text", "company": ""}

        async def _fake_extract(db, text):
            raise AIRateLimited("Rate-Limit erreicht")

        with patch("app.linkedin_job_description.load_job_description", new=_fake_load), \
             patch("app.ai.tasks.extract_application_from_text", new=_fake_extract):
            resp = client.post("/api/applications/extract-from-linkedin-url", json={"url": "https://linkedin.com/jobs/view/1"})

        assert resp.status_code == 429


class TestAiAssessSingle:
    def test_negativ_nicht_gefunden_liefert_404(self, client):
        resp = client.post("/api/applications/999/ai-assess")
        assert resp.status_code == 404

    def test_positiv_normale_bewerbung_nutzt_assess_application(self, client, db_session):
        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        async def _fake_assess(db, a, lang="de"):
            return {"color": "green", "reasoning": "gut", "next_step": "abwarten"}

        with patch("app.ai.tasks.assess_application", new=_fake_assess):
            resp = client.post(f"/api/applications/{app.id}/ai-assess")

        assert resp.status_code == 200
        assert resp.json()["color"] == "green"
        db_session.refresh(app)
        assert app.ai_color == "green"

    def test_positiv_abgesagte_bewerbung_nutzt_assess_rejected_application(self, client, db_session):
        app = application_factory(db_session, main_status="rejected")
        db_session.commit()

        async def _fake_assess_rejected(db, a, lang="de"):
            return {"color": "red", "reasoning": "abgesagt", "next_step": "weiter bewerben"}

        with patch("app.ai.tasks.assess_rejected_application", new=_fake_assess_rejected):
            resp = client.post(f"/api/applications/{app.id}/ai-assess")

        assert resp.status_code == 200
        assert resp.json()["color"] == "red"

    def test_negativ_ai_not_configured_liefert_400(self, client, db_session):
        from app.ai.provider import AINotConfigured

        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        async def _fake_assess(db, a, lang="de"):
            raise AINotConfigured("nicht konfiguriert")

        with patch("app.ai.tasks.assess_application", new=_fake_assess):
            resp = client.post(f"/api/applications/{app.id}/ai-assess")

        assert resp.status_code == 400

    def test_negativ_ai_bad_request_liefert_400(self, client, db_session):
        from app.ai.provider import AIBadRequest

        app = application_factory(db_session, main_status="applied")
        db_session.commit()

        async def _fake_assess(db, a, lang="de"):
            raise AIBadRequest("kaputte Antwort")

        with patch("app.ai.tasks.assess_application", new=_fake_assess):
            resp = client.post(f"/api/applications/{app.id}/ai-assess")

        assert resp.status_code == 400


class TestEvents:
    def test_positiv_liste_events_sortiert_absteigend(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, datum=date.today() - timedelta(days=5), titel="Alt")
        event_factory(db_session, app, datum=date.today(), titel="Neu")
        db_session.commit()

        resp = client.get(f"/api/applications/{app.id}/events")

        assert resp.status_code == 200
        assert resp.json()[0]["titel"] == "Neu"

    def test_positiv_bewerbung_event_setzt_datum_bewerbung(self, client, db_session):
        app = application_factory(db_session, datum_bewerbung=None)
        db_session.commit()

        resp = client.post(f"/api/applications/{app.id}/events", json={
            "typ": "bewerbung", "datum": "2026-06-01", "titel": "Bewerbung eingereicht",
        })

        assert resp.status_code == 201
        db_session.refresh(app)
        assert app.datum_bewerbung == date(2026, 6, 1)

    def test_negativ_event_hinzufuegen_ohne_bewerbung_liefert_404(self, client):
        resp = client.post("/api/applications/999/events", json={"typ": "notiz"})
        assert resp.status_code == 404

    def test_negativ_event_loeschen_nicht_gefunden(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.delete(f"/api/applications/{app.id}/events/999")
        assert resp.status_code == 404

    def test_positiv_event_loeschen_berechnet_datum_bewerbung_neu(self, client, db_session):
        app = application_factory(db_session)
        event_factory(db_session, app, typ="bewerbung", datum=date(2026, 5, 1))
        newer_ev = event_factory(db_session, app, typ="bewerbung", datum=date(2026, 6, 1))
        db_session.commit()

        resp = client.delete(f"/api/applications/{app.id}/events/{newer_ev.id}")

        assert resp.status_code == 204
        db_session.refresh(app)
        assert app.datum_bewerbung == date(2026, 5, 1)

    def test_positiv_letztes_bewerbung_event_geloescht_setzt_datum_auf_none(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="bewerbung", datum=date(2026, 5, 1))
        db_session.commit()

        resp = client.delete(f"/api/applications/{app.id}/events/{ev.id}")

        assert resp.status_code == 204
        db_session.refresh(app)
        assert app.datum_bewerbung is None

    def test_negativ_event_update_nicht_gefunden(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}/events/999", json={"titel": "x"})
        assert resp.status_code == 404

    def test_positiv_event_update_bewerbungsdatum_wird_synchronisiert(self, client, db_session):
        app = application_factory(db_session, datum_bewerbung=date(2026, 1, 1))
        ev = event_factory(db_session, app, typ="bewerbung", datum=date(2026, 1, 1))
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}/events/{ev.id}", json={"datum": "2026-02-01"})

        assert resp.status_code == 200
        db_session.refresh(app)
        assert app.datum_bewerbung == date(2026, 2, 1)


class TestContacts:
    def test_positiv_liste_kontakte(self, client, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session)
        app.contacts.append(contact)
        db_session.commit()

        resp = client.get(f"/api/applications/{app.id}/contacts")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_negativ_liste_kontakte_ohne_bewerbung(self, client):
        resp = client.get("/api/applications/999/contacts")
        assert resp.status_code == 404

    def test_negativ_update_kontakt_nicht_gefunden(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}/contacts/999", json={"name": "x"})
        assert resp.status_code == 404

    def test_positiv_update_kontakt_schreibt_audit(self, client, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session, name="Alt")
        app.contacts.append(contact)
        _make_verbose(db_session)
        db_session.commit()

        resp = client.patch(f"/api/applications/{app.id}/contacts/{contact.id}", json={"name": "Neu"})

        assert resp.status_code == 200
        assert resp.json()["name"] == "Neu"
        assert db_session.query(models.AuditLog).filter_by(contact_id=contact.id, field="name").first() is not None

    def test_positiv_link_contact_verknuepft_bestehenden_kontakt(self, client, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session)
        db_session.commit()

        resp = client.put(f"/api/applications/{app.id}/contacts/{contact.id}")

        assert resp.status_code == 200
        db_session.refresh(app)
        assert contact in app.contacts

    def test_corner_case_link_contact_bereits_verknuepft_ist_no_op(self, client, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session)
        app.contacts.append(contact)
        db_session.commit()

        resp = client.put(f"/api/applications/{app.id}/contacts/{contact.id}")

        assert resp.status_code == 200
        db_session.refresh(app)
        assert len(app.contacts) == 1

    def test_negativ_link_contact_bewerbung_nicht_gefunden(self, client, db_session):
        contact = contact_factory(db_session)
        db_session.commit()

        resp = client.put(f"/api/applications/999/contacts/{contact.id}")
        assert resp.status_code == 404

    def test_negativ_link_contact_kontakt_nicht_gefunden(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.put(f"/api/applications/{app.id}/contacts/999")
        assert resp.status_code == 404

    def test_negativ_delete_contact_bewerbung_nicht_gefunden(self, client):
        resp = client.delete("/api/applications/999/contacts/1")
        assert resp.status_code == 404

    def test_negativ_delete_contact_kontakt_nicht_gefunden(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.delete(f"/api/applications/{app.id}/contacts/999")
        assert resp.status_code == 404

    def test_positiv_delete_contact_entfernt_kontakt_komplett_ohne_weitere_links(self, client, db_session):
        app = application_factory(db_session)
        contact = contact_factory(db_session)
        app.contacts.append(contact)
        db_session.commit()

        resp = client.delete(f"/api/applications/{app.id}/contacts/{contact.id}")

        assert resp.status_code == 204
        assert db_session.query(models.Contact).filter_by(id=contact.id).first() is None


class TestGetApplicationCompanyAttach:
    def test_positiv_haengt_firmenname_und_website_an(self, client, db_session):
        from tests.factories import company_profile_factory

        profile = company_profile_factory(db_session, name_display="Contoso AG", website="https://contoso.example")
        app = application_factory(db_session, company_profile_id=profile.id)
        db_session.commit()

        resp = client.get(f"/api/applications/{app.id}")

        assert resp.status_code == 200
        assert resp.json()["company_name_display"] == "Contoso AG"
        assert resp.json()["company_website"] == "https://contoso.example"


class TestListApplicationsMainStatusFilter:
    def test_positiv_filtert_nach_main_status(self, client, db_session):
        application_factory(db_session, main_status="applied")
        application_factory(db_session, main_status="hr")
        db_session.commit()

        resp = client.get("/api/applications/", params={"main_status": "hr"})

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["main_status"] == "hr"

    def test_positiv_zeigt_firmen_logo_website_aus_profil(self, client, db_session):
        from tests.factories import company_profile_factory

        profile = company_profile_factory(db_session, name_display="Contoso AG", website="https://contoso.example")
        application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id, datum_bewerbung=date.today())
        db_session.commit()

        resp = client.get("/api/applications/")

        assert resp.status_code == 200
        assert resp.json()[0]["company_website"] == "https://contoso.example"
