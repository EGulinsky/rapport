"""L3 Integration — _sync_contacts_for_app() in sync_targeted.py.

Nutzt dieselbe fetch_all_vcards()-Mocking-Grenze wie test_icloud_contacts_sync.py.
Einfachere Gate-Logik als der globale Sync: Firmenbegriffs-Text-Match ODER
Erwähnung im Bewerbungstext (_contact_mentioned_in_app), kein CompanyProfile-
Domain-Abgleich.
"""
import pytest

from app import models
from app.routers.sync_targeted import _sync_contacts_for_app
from tests.factories import application_factory, icloud_vcard

pytestmark = pytest.mark.integration


class TestSyncContactsForApp:
    async def test_positiv_kontakt_mit_suchbegriff_im_org_feld_wird_importiert(self, db_session, icloud_sync, monkeypatch):
        # Der Org-Match allein importiert den Kontakt (erscheint im Firmen-Kontakte-
        # Tab), verlinkt ihn aber NICHT automatisch mit dieser Bewerbung — das
        # passiert nur bei expliziter Erwähnung im Bewerbungstext (siehe Test unten).
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        raw = icloud_vcard("Erika Musterfrau", email="erika@contoso.com", org="Contoso AG")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, total, errors = await _sync_contacts_for_app(app, ["Contoso AG", "Contoso"], db_session)

        assert errors == []
        assert created == 1
        contact = db_session.query(models.Contact).filter_by(email="erika@contoso.com").one()
        assert contact.firma == "Contoso AG"

    async def test_positiv_kontakt_ohne_org_match_aber_im_kommentar_erwaehnt_wird_verlinkt(self, db_session, icloud_sync, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG", kommentar="Telefonat mit Erika Musterfrau.")
        db_session.commit()
        raw = icloud_vcard("Erika Musterfrau", email="erika@privat.de", org="Privatperson")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, total, errors = await _sync_contacts_for_app(app, ["Contoso AG", "Contoso"], db_session)

        assert created == 1
        contact = db_session.query(models.Contact).filter_by(email="erika@privat.de").one()
        assert app in contact.applications

    async def test_negativ_ohne_treffer_wird_uebersprungen(self, db_session, icloud_sync, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        raw = icloud_vcard("Irgendwer Anders", email="irgendwer@irgendwas.de", org="Ganz andere Firma")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, total, errors = await _sync_contacts_for_app(app, ["Contoso AG", "Contoso"], db_session)

        assert created == 0
        assert db_session.query(models.Contact).filter_by(email="irgendwer@irgendwas.de").first() is None

    async def test_negativ_kontakt_ohne_email_wird_uebersprungen(self, db_session, icloud_sync, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        raw = icloud_vcard("Erika Musterfrau", org="Contoso AG")  # keine E-Mail

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, total, errors = await _sync_contacts_for_app(app, ["Contoso AG"], db_session)

        assert created == 0

    async def test_negativ_icloud_nicht_verbunden_liefert_leeres_ergebnis(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        created, total, errors = await _sync_contacts_for_app(app, ["Contoso AG"], db_session)

        assert (created, total, errors) == (0, 0, [])

    async def test_negativ_carddav_fehler_liefert_sauberen_fehler(self, db_session, icloud_sync, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        async def fake_fetch(cfg_arg):
            raise RuntimeError("401 Unauthorized")

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, total, errors = await _sync_contacts_for_app(app, ["Contoso AG"], db_session)

        assert created == 0
        assert any("CardDAV" in e for e in errors)
