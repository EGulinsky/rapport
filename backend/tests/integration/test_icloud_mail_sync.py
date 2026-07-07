"""L3 Integration — _do_icloud_mail() in sync_icloud.py end-to-end.

Mockt an der Netzwerkgrenze (imaplib.IMAP4_SSL, siehe
tests/integration/conftest.py::fake_icloud_imap), nicht die eigene Sync-
Logik. Zweiphasige Abholung wie beim globalen Gmail-Sync: erst nur Header
(RFC822.HEADER) für den schnellen Firmen-Check, dann volle Nachricht
(RFC822) nur für Treffer.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_icloud import _do_icloud_mail
from tests.factories import application_factory, contact_factory
from tests.integration.conftest import icloud_email

pytestmark = pytest.mark.integration


def _now_rfc2822() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


class TestDoIcloudMailNichtVerbunden:
    async def test_negativ_keine_icloud_konfiguration_liefert_klaren_fehler(self, db_session):
        result = await _do_icloud_mail(1)
        assert result["errors"] == ["Keine iCloud-Credentials gespeichert."]
        assert result["created"] == 0


class TestDoIcloudMailNeueNachrichten:
    async def test_positiv_einladung_mit_bekanntem_kontakt_wird_als_gespraech_angelegt(
        self, db_session, icloud_sync, fake_icloud_imap
    ):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        msg_id, msg = icloud_email(
            "1", "Recruiterin <recruiterin@contoso.com>", "Einladung zum Interview",
            "Wir würden Sie gerne zu einem Interview einladen.", _now_rfc2822(),
        )
        fake_icloud_imap(["1"], {msg_id: msg})

        result = await _do_icloud_mail(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_mail", external_id="1").one()
        assert event.typ == "gespräch"
        assert event.application_id == app.id

    async def test_negativ_mail_ohne_kontakt_match_wird_uebersprungen(self, db_session, icloud_sync, fake_icloud_imap):
        application_factory(db_session)
        db_session.commit()

        msg_id, msg = icloud_email(
            "2", "Newsletter <news@irgendwas.de>", "Wochenrückblick", "Diese Woche bei uns: ...", _now_rfc2822(),
        )
        fake_icloud_imap(["2"], {msg_id: msg})

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert result["skipped"] == 1
        assert db_session.query(models.Event).filter_by(source="icloud_mail", external_id="2").first() is None

    async def test_negativ_mail_vor_globalem_cutoff_wird_uebersprungen(self, db_session, icloud_sync, fake_icloud_imap):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today())
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        old_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        msg_id, msg = icloud_email(
            "3", "Recruiterin <recruiterin@contoso.com>", "Altes Interview", "Einladung zum Interview letztes Jahr.", old_date,
        )
        fake_icloud_imap(["3"], {msg_id: msg})

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert result["skipped"] == 1


class TestDoIcloudMailFehler:
    async def test_negativ_imap_verbindungsfehler_liefert_sauberen_fehler(self, db_session, icloud_sync, monkeypatch):
        def _raise(host, port):
            raise ConnectionError("Verbindung fehlgeschlagen")

        monkeypatch.setattr("imaplib.IMAP4_SSL", _raise)

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert any("IMAP-Fehler" in e for e in result["errors"])

    async def test_negativ_einzelner_fetch_fehler_stoppt_nicht_den_gesamten_sync(
        self, db_session, icloud_sync, fake_icloud_imap
    ):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        msg_id_ok, msg_ok = icloud_email(
            "ok", "Recruiterin <recruiterin@contoso.com>", "Interview", "Einladung zum Interview.", _now_rfc2822(),
        )
        conn = fake_icloud_imap(["fail", "ok"], {msg_id_ok: msg_ok})

        real_fetch = conn.fetch

        def _flaky_fetch(msg_id_bytes, spec):
            if msg_id_bytes == b"fail":
                raise RuntimeError("boom")
            return real_fetch(msg_id_bytes, spec)

        conn.fetch = _flaky_fetch

        result = await _do_icloud_mail(1)

        assert result["created"] == 1
        assert any("fail" in e for e in result["errors"])
