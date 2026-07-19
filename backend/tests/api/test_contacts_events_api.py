"""L2 API -- GET /api/contacts/{id}/events: calls/mails/messages connected to
a specific contact, categorized and sorted newest-first (ContactModal.tsx
tabs). None of these event types has a direct FK to Contact, so each is
matched the same way the rest of the codebase already does: calls/messages by
contact name embedded in Event.titel, mails by sender address in Event.autor.
"""
from datetime import date, timedelta

import pytest

from tests.factories import application_factory, company_profile_factory, contact_factory, event_factory

pytestmark = pytest.mark.api


class TestContactEventsMatching:
    def test_positiv_anruf_wird_ueber_titel_gematcht(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Anna Berg", vorname=None)
        app.contacts.append(contact)
        event_factory(db_session, app, source="icloud_calls", titel="Anruf mit Anna Berg", datum=date.today())
        # Unrelated call for a different person -- must not show up here.
        event_factory(db_session, app, source="icloud_calls", titel="Anruf mit Someone Else", datum=date.today())
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["calls"]) == 1
        assert body["calls"][0]["titel"] == "Anruf mit Anna Berg"
        assert body["mails"] == []
        assert body["messages"] == []

    def test_positiv_nachricht_wird_ueber_titel_gematcht(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Grünwald", vorname="Hans-Peter")
        app.contacts.append(contact)
        event_factory(
            db_session, app, source="linkedin_msg", typ="mail",
            titel="LinkedIn-Nachricht: Hans-Peter Grünwald", datum=date.today(),
        )
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["messages"]) == 1
        assert body["messages"][0]["source"] == "linkedin_msg"

    def test_positiv_mail_wird_ueber_autor_gematcht(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Fuchs", vorname="Carla", email="carla@contoso.example")
        app.contacts.append(contact)
        event = event_factory(db_session, app, source="gmail", typ="mail", titel="Terminvorschlag", datum=date.today())
        event.autor = "Carla Fuchs <carla@contoso.example>"
        # Mail from someone else at the same application -- must not match.
        other = event_factory(db_session, app, source="gmail", typ="mail", titel="Andere Mail", datum=date.today())
        other.autor = "Jemand Anders <jemand@contoso.example>"
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["mails"]) == 1
        assert body["mails"][0]["titel"] == "Terminvorschlag"

    def test_negativ_kontakt_ohne_email_bekommt_keine_mails(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Fuchs", vorname="Carla", email=None)
        app.contacts.append(contact)
        event = event_factory(db_session, app, source="gmail", typ="mail", titel="Irrelevant", datum=date.today())
        event.autor = "Irgendwer <irgendwer@contoso.example>"
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        assert resp.json()["mails"] == []

    def test_positiv_kalendertermin_wird_ueber_autor_gematcht(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Fuchs", vorname="Carla", email="carla@contoso.example")
        app.contacts.append(contact)
        event = event_factory(db_session, app, source="gcal", typ="gespräch", titel="Interview", datum=date.today())
        event.autor = "Carla Fuchs <carla@contoso.example>"
        # Termin mit jemand anderem -- darf nicht matchen.
        other = event_factory(db_session, app, source="icloud_cal", typ="gespräch", titel="Anderer Termin", datum=date.today())
        other.autor = "Jemand Anders <jemand@contoso.example>"
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["calendar"]) == 1
        assert body["calendar"][0]["titel"] == "Interview"

    def test_positiv_external_url_wird_mitgeliefert(self, client, db_session):
        # ContactModal's Mails/Calendar tabs need external_url to offer the
        # same "open in app" link as the application timeline's SourceBadge.
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Fuchs", vorname="Carla", email="carla@contoso.example")
        app.contacts.append(contact)
        event = event_factory(db_session, app, source="gcal", typ="gespräch", titel="Interview", datum=date.today())
        event.autor = "Carla Fuchs <carla@contoso.example>"
        event.external_url = "https://www.google.com/calendar/event?eid=abc123"
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        assert resp.json()["calendar"][0]["external_url"] == "https://www.google.com/calendar/event?eid=abc123"

    def test_negativ_kontakt_ohne_email_bekommt_keine_kalendertermine(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Fuchs", vorname="Carla", email=None)
        app.contacts.append(contact)
        event = event_factory(db_session, app, source="gcal", typ="gespräch", titel="Irrelevant", datum=date.today())
        event.autor = "Irgendwer <irgendwer@contoso.example>"
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        assert resp.json()["calendar"] == []

    def test_negativ_events_anderer_bewerbung_werden_nicht_einbezogen(self, client, db_session):
        app_a = application_factory(db_session, firma="Contoso")
        app_b = application_factory(db_session, firma="Other Inc")
        contact = contact_factory(db_session, name="Berg", vorname="Anna")
        app_a.contacts.append(contact)
        # Same-named call on an application this contact is NOT linked to.
        event_factory(db_session, app_b, source="icloud_calls", titel="Anruf mit Anna Berg", datum=date.today())
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        assert resp.json()["calls"] == []

    def test_positiv_sortierung_neueste_zuerst(self, client, db_session):
        app = application_factory(db_session, firma="Contoso")
        contact = contact_factory(db_session, name="Berg", vorname="Anna")
        app.contacts.append(contact)
        event_factory(db_session, app, source="icloud_calls", titel="Anruf mit Anna Berg #1", datum=date.today() - timedelta(days=10))
        event_factory(db_session, app, source="icloud_calls", titel="Anruf mit Anna Berg #2", datum=date.today() - timedelta(days=1))
        event_factory(db_session, app, source="icloud_calls", titel="Anruf mit Anna Berg #3", datum=date.today() - timedelta(days=5))
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        titles = [c["titel"] for c in resp.json()["calls"]]
        assert titles == ["Anruf mit Anna Berg #2", "Anruf mit Anna Berg #3", "Anruf mit Anna Berg #1"]

    def test_positiv_company_name_und_rolle_werden_angereichert(self, client, db_session):
        profile = company_profile_factory(db_session, name_display="Contoso Corp")
        app = application_factory(db_session, firma="Contoso", rolle="Senior Engineer", company_profile_id=profile.id)
        contact = contact_factory(db_session, name="Berg", vorname="Anna")
        app.contacts.append(contact)
        event_factory(db_session, app, source="icloud_calls", titel="Anruf mit Anna Berg", datum=date.today())
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        item = resp.json()["calls"][0]
        assert item["company_name"] == "Contoso Corp"
        assert item["rolle"] == "Senior Engineer"

    def test_corner_case_kontakt_ohne_bewerbungen_liefert_leere_listen(self, client, db_session):
        contact = contact_factory(db_session, name="Ohne Bewerbung")
        db_session.commit()

        resp = client.get(f"/api/contacts/{contact.id}/events")

        assert resp.status_code == 200
        assert resp.json() == {"calls": [], "mails": [], "messages": [], "calendar": []}

    def test_negativ_unbekannter_kontakt_liefert_404(self, client):
        resp = client.get("/api/contacts/999999/events")

        assert resp.status_code == 404
