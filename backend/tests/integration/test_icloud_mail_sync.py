"""L3 Integration — _do_icloud_mail() in sync_icloud.py end-to-end.

Mockt an der Netzwerkgrenze (imaplib.IMAP4_SSL, siehe
tests/integration/conftest.py::fake_icloud_imap), nicht die eigene Sync-
Logik. Zweiphasige Abholung wie beim globalen Gmail-Sync: erst nur Header
(RFC822.HEADER) für den schnellen Firmen-Check, dann volle Nachricht
(RFC822) nur für Treffer.
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app import models
from app.ai.provider import AINotConfigured, AIRateLimited
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

    async def test_positiv_rolle_im_betreff_ohne_bekannten_kontakt_wird_gefunden(
        self, db_session, icloud_sync, fake_icloud_imap
    ):
        # Role titles weren't indexed at all before this — only company name
        # and domain. Company name doesn't appear anywhere here.
        app = application_factory(
            db_session, firma="Contoso AG", rolle="Senior Backend Engineer",
            datum_bewerbung=date.today() - timedelta(days=30),
        )
        db_session.commit()

        msg_id, msg = icloud_email(
            "role-1", "Recruiting Team <talent@some-ats-vendor.example>",
            "Regarding your application for Senior Backend Engineer",
            "We'd love to schedule an interview.", _now_rfc2822(),
        )
        fake_icloud_imap(["role-1"], {msg_id: msg})

        result = await _do_icloud_mail(1)

        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="icloud_mail", external_id="role-1").one()
        assert event.application_id == app.id

    async def test_negativ_mail_vor_globalem_cutoff_wird_uebersprungen(self, db_session, icloud_sync, fake_icloud_imap):
        app = application_factory(db_session, firma="Contoso AG")
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        # Well outside the loose fallback window (see effective_bewerbung_floor/
        # earliest_bewerbung_date) — the app has no events yet, so its floor
        # defaults to "365 days ago"; comfortably clearing that margin here
        # avoids a same-day boundary flake.
        old_date = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        msg_id, msg = icloud_email(
            "3", "Recruiterin <recruiterin@contoso.com>", "Altes Interview", "Einladung zum Interview letztes Jahr.", old_date,
        )
        fake_icloud_imap(["3"], {msg_id: msg})

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_negativ_bereits_synctes_liefert_skip_ohne_erneute_verarbeitung(
        self, db_session, icloud_sync, fake_icloud_imap
    ):
        application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.add(models.SyncedItem(source="icloud_mail", external_id="4", user_id=1))
        db_session.commit()

        msg_id, msg = icloud_email(
            "4", "Recruiterin <recruiterin@contoso.com>", "Interview bei Contoso AG",
            "Einladung zum Interview.", _now_rfc2822(),
        )
        fake_icloud_imap(["4"], {msg_id: msg})

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert result["skipped"] == 1

    async def test_corner_case_kaputtes_date_header_wird_ignoriert_statt_absturz(
        self, db_session, icloud_sync, fake_icloud_imap
    ):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        msg_id, msg = icloud_email(
            "5", "Recruiterin <recruiterin@contoso.com>", "Einladung zum Interview",
            "Wir würden Sie gerne zu einem Interview einladen.", "kein-gueltiges-datum",
        )
        fake_icloud_imap(["5"], {msg_id: msg})

        result = await _do_icloud_mail(1)

        assert result["errors"] == []
        assert result["created"] == 1


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

    async def test_negativ_fehler_beim_vollstaendigen_fetch_stoppt_nicht_den_gesamten_sync(
        self, db_session, icloud_sync, fake_icloud_imap
    ):
        # Der zweiphasige Fetch holt Header + volle Nachricht getrennt — ein
        # Fehler in der zweiten Phase (RFC822, nicht RFC822.HEADER) muss
        # ebenso gesammelt werden, ohne den restlichen Sync abzubrechen.
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        msg_id, msg = icloud_email(
            "6", "Recruiterin <recruiterin@contoso.com>", "Interview bei Contoso AG",
            "Einladung zum Interview.", _now_rfc2822(),
        )
        conn = fake_icloud_imap(["6"], {msg_id: msg})

        real_fetch = conn.fetch

        def _flaky_full_fetch(msg_id_bytes, spec):
            if spec == "(RFC822)":
                raise RuntimeError("full-fetch-boom")
            return real_fetch(msg_id_bytes, spec)

        conn.fetch = _flaky_full_fetch

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert any("full-fetch-boom" in e for e in result["errors"])

    async def test_negativ_ai_not_configured_beendet_sync_sauber(self, db_session, icloud_sync, fake_icloud_imap, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        msg_id, msg = icloud_email(
            "7", "Recruiterin <recruiterin@contoso.com>", "Interview bei Contoso AG",
            "Einladung zum Interview.", _now_rfc2822(),
        )
        fake_icloud_imap(["7"], {msg_id: msg})
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AINotConfigured("kein Provider konfiguriert")),
        )

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert any("kein Provider konfiguriert" in e for e in result["errors"])

    async def test_negativ_unerwarteter_fehler_bei_process_item_stoppt_nicht_den_gesamten_sync(
        self, db_session, icloud_sync, fake_icloud_imap, monkeypatch
    ):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        msg_id, msg = icloud_email(
            "9", "Recruiterin <recruiterin@contoso.com>", "Interview bei Contoso AG",
            "Einladung zum Interview.", _now_rfc2822(),
        )
        fake_icloud_imap(["9"], {msg_id: msg})
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=RuntimeError("process-item-boom")),
        )

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert any("process-item-boom" in e for e in result["errors"])

    async def test_negativ_ai_rate_limited_beendet_sync_sauber(self, db_session, icloud_sync, fake_icloud_imap, monkeypatch):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        msg_id, msg = icloud_email(
            "8", "Recruiterin <recruiterin@contoso.com>", "Interview bei Contoso AG",
            "Einladung zum Interview.", _now_rfc2822(),
        )
        fake_icloud_imap(["8"], {msg_id: msg})
        monkeypatch.setattr(
            "app.routers.sync_icloud.process_item",
            AsyncMock(side_effect=AIRateLimited("Tageslimit erreicht")),
        )

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert any("AI-Tageslimit" in e for e in result["errors"])

    async def test_negativ_unerwarteter_fehler_ausserhalb_der_nachrichtenschleife_wird_gesammelt(
        self, db_session, icloud_sync, fake_icloud_imap, monkeypatch
    ):
        # build_firm_index() läuft VOR dem inneren IMAP-try/except — ein Fehler
        # dort landet im äußeren Except-Handler der Funktion (nicht in den
        # spezifischeren inneren Handlern).
        monkeypatch.setattr(
            "app.routers.sync_icloud.build_firm_index",
            lambda db: (_ for _ in ()).throw(RuntimeError("firm-index-boom")),
        )

        result = await _do_icloud_mail(1)

        assert result["created"] == 0
        assert any("firm-index-boom" in e for e in result["errors"])

    async def test_corner_case_logout_fehler_am_ende_wird_verschluckt(self, db_session, icloud_sync, fake_icloud_imap):
        conn = fake_icloud_imap([], {})

        def _raise_logout():
            raise RuntimeError("logout-boom")

        conn.logout = _raise_logout

        result = await _do_icloud_mail(1)

        assert result["errors"] == []
