"""L3 Integration — _sync_contacts_http() in sync_icloud.py end-to-end.

fetch_all_vcards() ist die pragmatische Mocking-Grenze: es ist reines CardDAV-
Wire-Protokoll (mehrstufiges PROPFIND/REPORT über rohes XML, keine SDK-
Bibliothek wie bei Gmail/Calendar) ohne eigene Businesslogik — analog zu
googleapiclient.discovery.build() bei Google.

Die "Skip contacts with no real connection"-Gate in _sync_contacts_http()
(siehe Kommentar dort) hat in der Vergangenheit zwei live verifizierte
Massenimport-Bugs verursacht (592 Kontakte, 272 aus einer Firma; danach 32
Contoso-Domain-Kontakte trotz 0 Bewerbungen) — die Regressionstests unten
decken beide Szenarien gezielt ab.
"""
import pytest

from app import models
from app.dedup import norm_firma
from app.routers.sync_icloud import _sync_contacts_http
from tests.factories import application_factory, company_profile_factory, icloud_vcard

pytestmark = pytest.mark.integration


def _cfg(db_session) -> models.ICloudSync:
    from app.ai.provider import encrypt_api_key
    cfg = models.ICloudSync(apple_id="test@example.com", app_password_enc=encrypt_api_key("pw"))
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestSyncContactsHttp:
    async def test_positiv_firmenname_matcht_bewerbung_direkt(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard("Erika Musterfrau", family="Musterfrau", given="Erika", email="erika@contoso.com", org="Contoso AG")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert errors == []
        assert created == 1
        contact = db_session.query(models.Contact).filter_by(email="erika@contoso.com").one()
        assert app in contact.applications

    async def test_positiv_erwaehnung_im_bewerbungstext_matcht_ohne_firmenname(self, db_session, monkeypatch):
        app = application_factory(db_session, firma="Fremdfirma GmbH", kommentar="Gespräch mit Erika Musterfrau war gut.")
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard("Erika Musterfrau", family="Musterfrau", given="Erika", email="erika@privat.de", org="Privatperson")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 1
        contact = db_session.query(models.Contact).filter_by(email="erika@privat.de").one()
        assert app in contact.applications

    async def test_negativ_ohne_jede_verbindung_wird_kontakt_nicht_importiert(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard("Irgendwer Anders", email="irgendwer@irgendwas.de", org="Ganz Andere Firma")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 0
        assert db_session.query(models.Contact).filter_by(email="irgendwer@irgendwas.de").first() is None

    async def test_negativ_verwaistes_company_profile_ohne_bewerbung_importiert_nicht(self, db_session, monkeypatch):
        # Regression: CompanyProfile existiert (z.B. Altlast), ist aber an KEINE
        # Bewerbung angebunden — ein Domain-Match allein darf nicht importieren.
        company_profile_factory(
            db_session, name_norm=norm_firma("Orphaned Corp"), name_display="Orphaned Corp",
            website="https://www.orphaned-corp.de/",
        )
        application_factory(db_session, firma="Ganz andere Bewerbung GmbH")
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard("Jemand Fremdes", email="jemand@orphaned-corp.de", org="Orphaned Corp")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 0
        assert db_session.query(models.Contact).filter_by(email="jemand@orphaned-corp.de").first() is None

    async def test_negativ_company_profile_ohne_domain_match_importiert_nicht(self, db_session, monkeypatch):
        # Regression: Profil ist zwar an eine Bewerbung angebunden, aber die
        # Kontakt-E-Mail-Domain stimmt nicht mit der Firmen-Website überein —
        # reiner Namens-Match über CompanyProfile darf allein nicht importieren.
        profile = company_profile_factory(
            db_session, name_norm=norm_firma("Linked Corp"), name_display="Linked Corp",
            website="https://www.linked-corp.de/",
        )
        application_factory(db_session, firma="Ganz andere Bewerbung GmbH", company_profile_id=profile.id)
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard("Jemand Fremdes", email="jemand@fremde-domain.de", org="Linked Corp")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 0
        assert db_session.query(models.Contact).filter_by(email="jemand@fremde-domain.de").first() is None

    async def test_positiv_bestehender_kontakt_wird_angereichert_statt_dupliziert(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        existing = models.Contact(name="Musterfrau", vorname="Erika", email="erika@contoso.com", firma="Contoso AG")
        db_session.add(existing)
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard(
            "Erika Musterfrau", family="Musterfrau", given="Erika", email="erika@contoso.com",
            org="Contoso AG", linkedin_url="https://linkedin.com/in/erika",
        )

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 0  # kein neuer Kontakt
        assert db_session.query(models.Contact).filter_by(email="erika@contoso.com").count() == 1
        # Kein refresh() hier: _sync_contacts_http() committet nicht selbst (das
        # macht erst der aufrufende sync_contacts()-Endpoint) — refresh() würde
        # die noch ungecommittete Anreicherung aus der DB überschreiben.
        assert existing.linkedin_url == "https://linkedin.com/in/erika"

    async def test_negativ_carddav_fehler_liefert_sauberen_fehler(self, db_session, monkeypatch):
        cfg = _cfg(db_session)

        async def fake_fetch(cfg_arg):
            raise RuntimeError("401 Unauthorized")

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 0
        assert any("CardDAV HTTP-Fehler" in e for e in errors)

    async def test_negativ_keine_vcards_gefunden_liefert_hinweis(self, db_session, monkeypatch):
        cfg = _cfg(db_session)

        async def fake_fetch(cfg_arg):
            return []

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 0
        assert any("Keine vCards" in e for e in errors)

    async def test_negativ_unparsbare_vcard_wird_uebersprungen_rest_wird_verarbeitet(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        cfg = _cfg(db_session)
        good = icloud_vcard("Erika Musterfrau", family="Musterfrau", given="Erika", email="erika@contoso.com", org="Contoso AG")
        broken = "BEGIN:VCARD\nVERSION:3.0\nEND:VCARD"  # kein FN -> _parse_vcard() liefert None

        async def fake_fetch(cfg_arg):
            return [broken, good]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert errors == []
        assert created == 1

    async def test_positiv_bestehender_kontakt_wird_um_telefon_firma_und_rolle_angereichert(self, db_session, monkeypatch):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        existing = models.Contact(name="Musterfrau", vorname="Erika", email="erika@contoso.com")
        db_session.add(existing)
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard(
            "Erika Musterfrau", family="Musterfrau", given="Erika", email="erika@contoso.com",
            org="Contoso AG", title="Recruiterin", tel="+49 30 1234567",
        )

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 0
        assert existing.telefon == "+49 30 1234567"
        assert existing.firma == "Contoso AG"
        assert existing.rolle == "Recruiterin"

    async def test_positiv_reiner_domain_match_ohne_erwaehnung_oder_firma_textmatch_importiert(self, db_session, monkeypatch):
        # Regressionsfall (dritte Variante): CompanyProfile ist an eine echte
        # Bewerbung angebunden UND die E-Mail-Domain matcht — aber der
        # Firmenname im vCard-ORG-Feld matcht KEINE Bewerbung per Text
        # (unterschiedliche Namen), und der Kontakt wird auch nirgends erwähnt.
        # Der Domain-Match allein muss hier ausreichen (match_reason "E-Mail-
        # Domain passt zu Firma").
        cp = company_profile_factory(
            db_session, name_display="Contoso Holding", name_norm=norm_firma("Contoso Holding"),
            website="https://www.contoso-holding.de/",
        )
        application_factory(db_session, firma="Ganz anderer Bewerbungsname GmbH", company_profile_id=cp.id)
        db_session.commit()
        cfg = _cfg(db_session)
        raw = icloud_vcard("Neue Person", email="neu@contoso-holding.de", org="Contoso Holding")

        async def fake_fetch(cfg_arg):
            return [raw]

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 1
        contact = db_session.query(models.Contact).filter_by(email="neu@contoso-holding.de").one()
        assert contact.company_profile_id == cp.id

    async def test_negativ_unerwarteter_fehler_bei_einem_kontakt_stoppt_nicht_den_gesamten_sync(
        self, db_session, monkeypatch
    ):
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        cfg = _cfg(db_session)
        broken_org_vcard = icloud_vcard("Kaputte Person", email="kaputt@contoso.com", org="Contoso AG")
        good_vcard = icloud_vcard("Gute Person", email="gut@web.de", org="Contoso AG")

        async def fake_fetch(cfg_arg):
            return [broken_org_vcard, good_vcard]

        real_norm_firma = __import__("app.dedup", fromlist=["norm_firma"]).norm_firma

        def _flaky_norm_firma(name):
            if name == "Contoso AG" and not getattr(_flaky_norm_firma, "_called", False):
                _flaky_norm_firma._called = True
                raise RuntimeError("norm-firma-boom")
            return real_norm_firma(name)

        monkeypatch.setattr("app.routers.sync_icloud.fetch_all_vcards", fake_fetch)
        monkeypatch.setattr("app.dedup.norm_firma", _flaky_norm_firma)

        created, errors = await _sync_contacts_http(cfg, db_session)

        assert created == 1
        assert any("norm-firma-boom" in e for e in errors)
