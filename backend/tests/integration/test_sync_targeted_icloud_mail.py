"""L3 Integration — _sync_icloud_mail_for_app() in sync_targeted.py.

Wie bei Gmail (siehe test_sync_targeted_domains.py) matcht der gezielte Sync
über die Firmen-Domain, nicht wie der globale iCloud-Mail-Sync über Kontakt-
/Firmennamen-Text-Matching. Nutzt dieselbe IMAP-Fake wie test_icloud_mail_sync.py.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_targeted import _sync_icloud_mail_for_app
from tests.factories import application_factory, company_profile_factory
from tests.integration.conftest import icloud_email

pytestmark = pytest.mark.integration


def _now_rfc2822() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


class TestSyncIcloudMailForApp:
    async def test_positiv_treffer_von_firmendomain_wird_angelegt(self, db_session, icloud_sync, fake_icloud_imap):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(
            db_session, firma="Contoso AG", company_profile_id=profile.id,
            datum_bewerbung=date.today() - timedelta(days=30),
        )
        db_session.commit()

        msg_id, msg = icloud_email(
            "1", "Recruiterin <recruiterin@contoso.de>", "Einladung zum Interview",
            "Wir würden Sie gerne zu einem Interview einladen.", _now_rfc2822(),
        )
        conn = fake_icloud_imap(["1"], {msg_id: msg})

        created, total, errors = await _sync_icloud_mail_for_app(
            app, {"id": app.id, "firma": app.firma}, [], db_session,
        )

        assert errors == []
        assert created == 1
        assert total == 1
        assert any("contoso.de" in c for c in conn.search_calls)
        event = db_session.query(models.Event).filter_by(source="icloud_mail", external_id="1").one()
        assert event.application_id == app.id

    async def test_negativ_ohne_firmendomain_und_ohne_suchbegriffe_wird_uebersprungen(self, db_session, icloud_sync, fake_icloud_imap):
        # rolle="" (not the factory's random fake.job() default) so there's
        # truly nothing to search for — see the positive counterpart below,
        # which confirms company-name/role text alone (no domain) now DOES
        # trigger a search.
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=None, rolle="")
        db_session.commit()
        conn = fake_icloud_imap([])

        created, total, errors = await _sync_icloud_mail_for_app(app, {"id": app.id, "firma": app.firma}, [], db_session)

        assert (created, total, errors) == (0, 0, [])
        assert conn.search_calls == []

    async def test_positiv_ohne_domain_aber_mit_suchbegriffen_wird_trotzdem_gesucht(self, db_session, icloud_sync, fake_icloud_imap):
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=None, rolle="Backend Engineer")
        db_session.commit()
        conn = fake_icloud_imap([])

        created, total, errors = await _sync_icloud_mail_for_app(
            app, {"id": app.id, "firma": app.firma}, ["Contoso AG", "Contoso"], db_session,
        )

        assert (created, total, errors) == (0, 0, [])
        assert len(conn.search_calls) == 1
        query = conn.search_calls[0]
        assert '"Contoso AG"' in query
        assert '"Contoso"' in query
        assert '"Backend"' in query
        assert '"Engineer"' in query

    async def test_negativ_icloud_nicht_verbunden_liefert_leeres_ergebnis(self, db_session):
        app = application_factory(db_session, firma="Contoso AG")
        db_session.commit()

        created, total, errors = await _sync_icloud_mail_for_app(app, {"id": app.id, "firma": app.firma}, [], db_session)

        assert (created, total, errors) == (0, 0, [])

    async def test_negativ_imap_fehler_liefert_sauberen_fehler(self, db_session, icloud_sync, monkeypatch):
        profile = company_profile_factory(db_session, website="https://www.contoso.de/")
        app = application_factory(db_session, firma="Contoso AG", company_profile_id=profile.id)
        db_session.commit()

        def _raise(host, port):
            raise ConnectionError("Verbindung fehlgeschlagen")

        monkeypatch.setattr("imaplib.IMAP4_SSL", _raise)

        created, total, errors = await _sync_icloud_mail_for_app(app, {"id": app.id, "firma": app.firma}, [], db_session)

        assert created == 0
        assert any("IMAP" in e for e in errors)
