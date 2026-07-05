"""L1 Component — _sync_contacts_http() in sync_icloud.py.

Regressionstest für einen live an Produktivdaten gefundenen Bug: 592 importierte
Kontakte, davon 272 allein mit Firma "Contoso GmbH". Ursache war, dass ein reiner
Textmatch des ORG-Feldes einer vCard gegen den Namen einer bekannten CompanyProfile
(z.B. aus einer früheren Bewerbung) ausreichte, um JEDEN Kontakt mit diesem
Firmennamen zu importieren — unabhängig davon, ob eine tatsächliche Verbindung zur
Bewerbung besteht. Das importiert faktisch ein komplettes Adressbuch eines früheren
Arbeitgebers, sobald irgendeine CompanyProfile mit gleichem Namen existiert.

Fix: ein reiner Namens-Match auf die CompanyProfile reicht nicht mehr aus. Es wird
zusätzlich verlangt, dass die E-Mail-Domain des Kontakts zur Website der Firma
passt — oder dass der Kontakt anderweitig (Erwähnung in Events/Bewerbungstext,
Firma-Textmatch auf eine echte Bewerbung) mit einer Bewerbung verknüpft ist.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.routers import sync_icloud
from tests.factories import application_factory, company_profile_factory, contact_factory, event_factory

pytestmark = pytest.mark.component


def _vcard(fn: str, email: str | None = None, org: str | None = None, n: tuple[str, str] | None = None) -> str:
    """n: optionales (family, given) für das strukturierte N:-Feld."""
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{fn}"]
    if n:
        lines.append(f"N:{n[0]};{n[1]};;;")
    if email:
        lines.append(f"EMAIL:{email}")
    if org:
        lines.append(f"ORG:{org}")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def _cfg():
    return sync_icloud.models.ICloudSync(
        apple_id="test@example.com", app_password_enc="x",
    )


class TestSyncContactsHttp:
    async def test_negativ_reiner_namens_match_auf_companyprofile_importiert_nicht(self, db_session):
        # Regressionsfall: CompanyProfile "Contoso GmbH" existiert (z.B. aus einer alten
        # Bewerbung), aber der Adressbuch-Kontakt hat weder eine passende E-Mail-Domain
        # noch sonst eine Verbindung zu einer Bewerbung — darf NICHT importiert werden.
        company_profile_factory(db_session, name_display="Contoso GmbH", name_norm="contoso", website="https://www.contoso-gmbh.de/")
        vcards = [_vcard("Ehemaliger Kollege", email="kollege@web.de", org="Contoso GmbH")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors = await sync_icloud._sync_contacts_http(_cfg(), db_session)

        assert created == 0
        assert db_session.query(sync_icloud.models.Contact).count() == 0

    async def test_negativ_domain_match_ohne_bewerbung_zur_firma_importiert_nicht(self, db_session):
        # Regressionsfall (Follow-up): Contoso-Domain-Kontakte wurden weiter importiert,
        # obwohl es zu Contoso gar keine Bewerbung gibt — die CompanyProfile existierte nur
        # noch als Datenleiche. Ein Domain-Match reicht nicht, wenn die Firma nicht
        # tatsächlich mit einer Bewerbung verknüpft ist (live: 32 Contoso-Kontakte trotz 0
        # Bewerbungen zu Contoso).
        company_profile_factory(db_session, name_display="Contoso GmbH", name_norm="contoso", website="https://www.contoso-gmbh.de/")
        vcards = [_vcard("Ehemaliger Kollege", email="kollege@contoso-gmbh.de", org="Contoso GmbH")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors = await sync_icloud._sync_contacts_http(_cfg(), db_session)

        assert created == 0
        assert db_session.query(sync_icloud.models.Contact).count() == 0

    async def test_positiv_email_domain_matcht_firmen_website_mit_echter_bewerbung_wird_importiert(self, db_session):
        cp = company_profile_factory(db_session, name_display="Contoso GmbH", name_norm="contoso", website="https://www.contoso-gmbh.de/")
        application_factory(db_session, firma="Contoso GmbH", company_profile_id=cp.id)
        vcards = [_vcard("Recruiterin Muster", email="muster@contoso-gmbh.de", org="Contoso GmbH")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors = await sync_icloud._sync_contacts_http(_cfg(), db_session)

        assert created == 1
        contact = db_session.query(sync_icloud.models.Contact).one()
        assert contact.company_profile_id is not None

    async def test_positiv_erwaehnung_in_event_wird_trotz_fremder_domain_importiert(self, db_session):
        app = application_factory(db_session, firma="Andere Firma GmbH")
        event_factory(db_session, app, typ="notiz", notiz="Telefonat mit Anna Beispiel vereinbart")
        vcards = [_vcard("Anna Beispiel", email="anna.beispiel@web.de", org=None)]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors = await sync_icloud._sync_contacts_http(_cfg(), db_session)

        assert created == 1

    async def test_positiv_firma_textmatch_auf_echte_bewerbung_wird_importiert_und_verknuepft(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        vcards = [_vcard("Herr Beispiel", email="beispiel@web.de", org="Contoso AG")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors = await sync_icloud._sync_contacts_http(_cfg(), db_session)

        assert created == 1
        contact = db_session.query(sync_icloud.models.Contact).one()
        assert app in contact.applications

    async def test_corner_case_ohne_org_und_ohne_erwaehnung_kein_import(self, db_session):
        vcards = [_vcard("Unbekannt Niemand", email="niemand@web.de", org=None)]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors = await sync_icloud._sync_contacts_http(_cfg(), db_session)

        assert created == 0

    async def test_positiv_legacy_kontakt_ohne_email_wird_per_altem_vollnamen_gefunden_und_gesplittet(self, db_session):
        # Live-Regressionsfall: Alt-Kontakte (vor dem Vorname/Nachname-Split)
        # haben den vollen Anzeigenamen im name-Feld stehen und vorname=None.
        # Ohne Fallback-Match über den alten Vollnamen (fn) würde ein erneuter
        # Sync sie per E-Mail-loser Suche nicht wiederfinden und stattdessen
        # fälschlich ein Duplikat mit dem neu gesplitteten Namen anlegen.
        legacy = contact_factory(db_session, name="Max Mustermann", vorname=None, email=None, firma="Fabrikam GmbH")
        db_session.commit()
        vcards = [_vcard("Max Mustermann", n=("Mustermann", "Max"), org="Fabrikam GmbH")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors = await sync_icloud._sync_contacts_http(_cfg(), db_session)

        assert created == 0  # kein Duplikat
        assert db_session.query(sync_icloud.models.Contact).count() == 1
        db_session.commit()
        db_session.refresh(legacy)
        assert legacy.name == "Mustermann"
        assert legacy.vorname == "Max"

    async def test_negativ_legacy_kontakt_mit_bereits_gesetztem_vorname_wird_nicht_ueberschrieben(self, db_session):
        # Ein bereits (manuell oder korrekt) gesetzter vorname darf nicht von
        # einem erneuten Sync überschrieben werden.
        legacy = contact_factory(db_session, name="Anders", vorname="Schon Gesetzt", email=None, firma="Fabrikam GmbH")
        db_session.commit()
        vcards = [_vcard("Max Mustermann", n=("Mustermann", "Max"), org="Fabrikam GmbH")]

        # Kein Treffer über name/fn, da der Alt-Kontakt einen anderen Namen hat —
        # simuliert stattdessen direkt über einen Treffer mit gleichem Namen.
        legacy.name = "Mustermann"
        db_session.commit()

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            await sync_icloud._sync_contacts_http(_cfg(), db_session)

        db_session.commit()
        db_session.refresh(legacy)
        assert legacy.vorname == "Schon Gesetzt"
