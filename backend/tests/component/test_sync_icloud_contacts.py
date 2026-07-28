"""L1 Component — _sync_contacts_from_vcards() in sync_icloud.py.

Contact *discovery* is now unconditional — every address-book entry gets
imported, full stop, no company-name/app-relevance gating (see the plan doc
for the "ERA Group" false-positive-linking incident this replaced: a bare
"ERA" substring, left over after stripping the corporate suffix "Group",
matched unrelated words like "Beratung"/"Cooperation" and silently linked
those contacts to the wrong application).

Contact-to-application *linking* is now much narrower: only a contact
explicitly mentioned in that application's own mail/calendar/event text
still gets linked on import. A company-name match alone — the exact
mechanism that used to gate import (and that produced this file's original
regression tests, "592 imported contacts, 272 with the same company name")
— no longer creates a link at all.
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


class TestSyncContactsFromVcards:
    async def test_positiv_reiner_namens_match_auf_companyprofile_wird_trotzdem_importiert(self, db_session):
        # Ehemaliger historischer Bug: ein reiner Textmatch des ORG-Feldes gegen
        # eine bekannte CompanyProfile durfte NICHT genügen, um zu importieren
        # (592 importierte Kontakte, 272 allein mit Firma "Contoso GmbH"). Die
        # Lösung ist jetzt eine andere: Import ist unconditional — jeder
        # Adressbuch-Kontakt wird importiert — aber ohne jede Bewerbungs-Verknüpfung.
        company_profile_factory(db_session, name_display="Contoso GmbH", name_norm="contoso", website="https://www.contoso-gmbh.de/")
        vcards = [_vcard("Ehemaliger Kollege", email="kollege@web.de", org="Contoso GmbH")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors, touched_ids = await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

        assert created == 1
        contact = db_session.query(sync_icloud.models.Contact).one()
        assert contact.applications == []

    async def test_positiv_email_domain_matcht_firmen_website_mit_echter_bewerbung_wird_importiert(self, db_session):
        cp = company_profile_factory(db_session, name_display="Contoso GmbH", name_norm="contoso", website="https://www.contoso-gmbh.de/")
        application_factory(db_session, firma="Contoso GmbH", company_profile_id=cp.id)
        vcards = [_vcard("Recruiterin Muster", email="muster@contoso-gmbh.de", org="Contoso GmbH")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors, touched_ids = await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

        assert created == 1
        contact = db_session.query(sync_icloud.models.Contact).one()
        assert contact.company_profile_id is not None

    async def test_positiv_erwaehnung_in_event_wird_importiert_und_verknuepft(self, db_session):
        app = application_factory(db_session, firma="Andere Firma GmbH")
        event_factory(db_session, app, typ="notiz", notiz="Telefonat mit Anna Beispiel vereinbart")
        vcards = [_vcard("Anna Beispiel", email="anna.beispiel@web.de", org=None)]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors, touched_ids = await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

        assert created == 1
        contact = db_session.query(sync_icloud.models.Contact).one()
        assert app in contact.applications

    async def test_negativ_firma_textmatch_allein_verknuepft_nicht_mehr(self, db_session):
        # Kernverhalten der Umstellung: ein reiner Firmennamen-Match des ORG-
        # Feldes gegen eine echte Bewerbung importiert weiterhin (unconditional),
        # aber verknüpft NICHT mehr automatisch — nur eine echte Erwähnung im
        # Bewerbungs-/E-Mail-Text (oder Kalender) tut das noch.
        app = application_factory(db_session, firma="Contoso AG")
        vcards = [_vcard("Herr Beispiel", email="beispiel@web.de", org="Contoso AG")]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors, touched_ids = await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

        assert created == 1
        contact = db_session.query(sync_icloud.models.Contact).one()
        assert app not in contact.applications

    async def test_positiv_ohne_org_und_ohne_erwaehnung_wird_trotzdem_importiert(self, db_session):
        vcards = [_vcard("Unbekannt Niemand", email="niemand@web.de", org=None)]

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)):
            created, errors, touched_ids = await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

        assert created == 1
        assert db_session.query(sync_icloud.models.Contact).one().applications == []

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
            created, errors, touched_ids = await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

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
            await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

        db_session.commit()
        db_session.refresh(legacy)
        assert legacy.vorname == "Schon Gesetzt"

    async def test_positiv_ein_fehlerhafter_kontakt_blockiert_die_uebrigen_nicht(self, db_session):
        # Regression (2026-07-28 "0 synced" incident): a flush failure for
        # one contact — live cause was a UNIQUE-constraint collision against
        # an orphaned contact_application row left behind by a since-fixed
        # bulk-delete bug — used to leave the whole SQLAlchemy session in a
        # broken "PendingRollbackError" state for every later contact too,
        # so the caller's own db.commit() then raised uncaught, discarding
        # the entire batch's already-processed contacts even though most of
        # them had imported correctly. Each contact now runs inside its own
        # SAVEPOINT (db.begin_nested()), so one bad entry only fails itself.
        vcards = [
            _vcard("Kaputter Kontakt", email="kaputt@example.com"),
            _vcard("Guter Kontakt", email="gut@example.com"),
        ]
        real_find = sync_icloud._find_apps_where_contact_mentioned

        def _boom_for_kaputt(name, email, db):
            if email == "kaputt@example.com":
                raise RuntimeError("simulated flush failure")
            return real_find(name, email, db)

        with patch.object(sync_icloud, "fetch_all_vcards", new=AsyncMock(return_value=vcards)), \
             patch.object(sync_icloud, "_find_apps_where_contact_mentioned", side_effect=_boom_for_kaputt):
            created, errors, touched_ids = await sync_icloud._sync_contacts_from_vcards(_cfg(), db_session)

        assert created == 1
        assert len(errors) == 1
        assert db_session.query(sync_icloud.models.Contact).filter_by(email="kaputt@example.com").first() is None
        good = db_session.query(sync_icloud.models.Contact).filter_by(email="gut@example.com").first()
        assert good is not None
        assert len(touched_ids) == 1
        assert touched_ids == [good.id]
        db_session.commit()  # must not raise — the failed contact's savepoint didn't poison the session
