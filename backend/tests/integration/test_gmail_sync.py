"""L3 Integration — _do_gmail() in sync_google.py end-to-end.

Mockt an der Netzwerkgrenze (googleapiclient.discovery.build, siehe
tests/integration/conftest.py::fake_gmail), nicht die eigene Sync-Logik.
Anders als bei Calendar läuft hier eine zweiphasige Batch-Abholung
(Metadata dann Volltext) über new_batch_http_request() — die komplexere
Mocking-Fläche gegenüber Google Calendar. Klassifikation ist rein
keyword-basiert (_classify_type_from_text), keine AI im Spiel.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from app.routers.sync_google import _do_gmail
from tests.factories import application_factory, contact_factory
from tests.integration.conftest import gmail_message

pytestmark = pytest.mark.integration


def _now_rfc2822() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


class TestDoGmailNichtVerbunden:
    async def test_negativ_keine_google_konfiguration_liefert_klaren_fehler(self, db_session):
        # Bewusst kein google_sync-Fixture — es existiert keine GoogleSync-Zeile.
        result = await _do_gmail(1)

        assert result["errors"] == ["Nicht mit Google verbunden."]
        assert result["created"] == 0

    async def test_corner_case_konfiguration_ohne_refresh_token_gilt_als_nicht_verbunden(self, db_session):
        db_session.add(models.GoogleSync(client_id="x", client_secret_enc="y", refresh_token_enc=None))
        db_session.commit()

        result = await _do_gmail(1)

        assert result["errors"] == ["Nicht mit Google verbunden."]


class TestDoGmailNeueNachrichten:
    async def test_positiv_einladung_mit_bekanntem_kontakt_wird_als_gespraech_angelegt(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        meta, full = gmail_message(
            "msg-1", "Recruiterin <recruiterin@contoso.com>", "Einladung zum Interview",
            "Wir würden Sie gerne zu einem Interview einladen.", _now_rfc2822(),
        )
        fake_gmail([{"messages": [{"id": "msg-1"}]}], metadata={"msg-1": meta}, full={"msg-1": full})

        result = await _do_gmail(1)

        assert result["errors"] == []
        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="gmail", external_id="msg-1").one()
        assert event.typ == "gespräch"
        assert event.application_id == app.id

    async def test_positiv_absage_erzeugt_statusvorschlag_statt_direkter_aenderung(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Contoso AG", main_status="applied", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="hr@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        meta, full = gmail_message(
            "msg-2", "HR <hr@contoso.com>", "Ihre Bewerbung",
            "Leider müssen wir Ihnen mitteilen, dass wir uns für einen anderen Kandidaten entschieden haben.",
            _now_rfc2822(),
        )
        fake_gmail([{"messages": [{"id": "msg-2"}]}], metadata={"msg-2": meta}, full={"msg-2": full})

        result = await _do_gmail(1)

        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="gmail", external_id="msg-2").one()
        assert event.typ == "status"
        pm = db_session.query(models.PendingMatch).filter_by(suggested_app_id=app.id).one()
        assert pm.suggested_main_status == "rejected"
        db_session.refresh(app)
        assert app.main_status == "applied"  # Änderung geht über Review, nicht direkt

    async def test_negativ_mail_ohne_kontakt_match_wird_uebersprungen(self, db_session, google_sync, fake_gmail):
        application_factory(db_session)
        db_session.commit()

        meta, full = gmail_message(
            "msg-3", "Newsletter <news@irgendwas.de>", "Wochenrückblick",
            "Diese Woche bei uns: ...", _now_rfc2822(),
        )
        fake_gmail([{"messages": [{"id": "msg-3"}]}], metadata={"msg-3": meta}, full={"msg-3": full})

        result = await _do_gmail(1)

        assert result["created"] == 0
        assert result["skipped"] == 1
        assert db_session.query(models.Event).filter_by(source="gmail", external_id="msg-3").first() is None

    async def test_positiv_firmenname_im_betreff_ohne_bekannten_kontakt_wird_gefunden(
        self, db_session, google_sync, fake_gmail
    ):
        # No contact saved for this app at all — before this, Gmail sync
        # only matched by address (find_apps_from_addresses), so a mail from
        # an address it had never seen could never match, even mentioning
        # the company by name. It now also matches via company-name text
        # (build_firm_index/find_matching_apps), same as iCloud Mail always did.
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()

        meta, full = gmail_message(
            "msg-firmname", "Recruiting Team <talent@some-ats-vendor.example>",
            "Ihre Bewerbung bei Contoso AG", "Wir würden Sie gerne zu einem Interview einladen.",
            _now_rfc2822(),
        )
        fake_gmail([{"messages": [{"id": "msg-firmname"}]}], metadata={"msg-firmname": meta}, full={"msg-firmname": full})

        result = await _do_gmail(1)

        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="gmail", external_id="msg-firmname").one()
        assert event.application_id == app.id

    async def test_positiv_rolle_im_betreff_ohne_bekannten_kontakt_wird_gefunden(
        self, db_session, google_sync, fake_gmail
    ):
        # Company name doesn't appear anywhere — only the role title, and
        # only that (no address/domain match) justifies fetching the body.
        app = application_factory(
            db_session, firma="Contoso AG", rolle="Senior Backend Engineer",
            datum_bewerbung=date.today() - timedelta(days=30),
        )
        db_session.commit()

        meta, full = gmail_message(
            "msg-role", "Recruiting Team <talent@some-ats-vendor.example>",
            "Regarding your application for Senior Backend Engineer",
            "We'd love to schedule an interview.",
            _now_rfc2822(),
        )
        fake_gmail([{"messages": [{"id": "msg-role"}]}], metadata={"msg-role": meta}, full={"msg-role": full})

        result = await _do_gmail(1)

        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="gmail", external_id="msg-role").one()
        assert event.application_id == app.id

    async def test_positiv_phase2_erkennt_firmenname_der_nur_im_mailbody_steht(
        self, db_session, google_sync, fake_gmail
    ):
        # Phase 1 (subject/sender/to/cc only) matches via the known contact's
        # address — the company name only appears in the body, which phase 1
        # never sees. This proves phase 2 actually re-checks with the full
        # text rather than reusing the phase-1 hint_apps unchanged — before
        # this, a second application matching only via the body text (not
        # the contact) would never have been picked up.
        app1 = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app1.contacts.append(contact)
        app2 = application_factory(db_session, firma="Globex Corp", datum_bewerbung=date.today() - timedelta(days=30))
        db_session.commit()

        meta, full = gmail_message(
            "msg-body-firm", "Recruiterin <recruiterin@contoso.com>", "Following up",
            "Also — we passed your profile along to our partners at Globex Corp, they may reach out.",
            _now_rfc2822(),
        )
        fake_gmail([{"messages": [{"id": "msg-body-firm"}]}], metadata={"msg-body-firm": meta}, full={"msg-body-firm": full})

        result = await _do_gmail(1)

        assert result["created"] == 1
        event = db_session.query(models.Event).filter_by(source="gmail", external_id="msg-body-firm").one()
        # Both apps matched; _classify_deterministic() picks the first
        # (app1, the phase-1 contact-address match) — proving app2's
        # body-only match was found too (not just app1's) via the
        # "(from N matches)" note in the audit reason, which only appears
        # when hint_apps has 2+ entries.
        assert event.application_id == app1.id
        audit = db_session.query(models.AuditLog).filter_by(event_id=event.id).one()
        assert "2 matches" in audit.reason or "2 Matches" in audit.reason
        _ = app2

    async def test_negativ_mail_vor_globalem_cutoff_wird_uebersprungen(self, db_session, google_sync, fake_gmail):
        app = application_factory(db_session, firma="Contoso AG")
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        # Well outside the loose fallback window (see effective_bewerbung_floor/
        # earliest_bewerbung_date) — the app has no events yet, so its floor
        # defaults to "365 days ago"; comfortably clearing that margin here
        # avoids a same-day boundary flake.
        old_date = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        meta, full = gmail_message(
            "msg-4", "Recruiterin <recruiterin@contoso.com>", "Altes Interview",
            "Einladung zum Interview letztes Jahr.", old_date,
        )
        fake_gmail([{"messages": [{"id": "msg-4"}]}], metadata={"msg-4": meta}, full={"msg-4": full})

        result = await _do_gmail(1)

        assert result["created"] == 0
        assert result["skipped"] == 1


class TestDoGmailPaginationUndFehler:
    async def test_positiv_pagination_ueber_mehrere_seiten_wird_vollstaendig_abgeholt(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        meta1, full1 = gmail_message("msg-p1", "Recruiterin <recruiterin@contoso.com>", "Interview 1", "Einladung zum Interview.", _now_rfc2822())
        meta2, full2 = gmail_message("msg-p2", "Recruiterin <recruiterin@contoso.com>", "Interview 2", "Einladung zum Interview.", _now_rfc2822())
        service = fake_gmail(
            [
                {"messages": [{"id": "msg-p1"}], "nextPageToken": "page2"},
                {"messages": [{"id": "msg-p2"}]},
            ],
            metadata={"msg-p1": meta1, "msg-p2": meta2},
            full={"msg-p1": full1, "msg-p2": full2},
        )

        result = await _do_gmail(1)

        assert result["created"] == 2
        assert len(service.list_calls) == 2
        assert "pageToken" not in service.list_calls[0]
        assert service.list_calls[1]["pageToken"] == "page2"

    async def test_negativ_gmail_api_fehler_bei_list_liefert_sauberen_fehler(self, db_session, google_sync, fake_gmail):
        # An active application must exist so the query-building step
        # actually reaches the (deliberately failing) list() call below —
        # with zero applications and zero contact domains there is nothing
        # to search for, and _do_gmail() now returns early before ever
        # calling the Gmail API (see the "nothing to search for yet" guard).
        application_factory(db_session, firma="Contoso AG")
        db_session.commit()
        service = fake_gmail([])

        def _raise(**kwargs):
            raise RuntimeError("500 Internal Server Error")

        service.execute = _raise

        result = await _do_gmail(1)

        assert result["created"] == 0
        assert any("Gmail API Fehler" in e for e in result["errors"])

    async def test_negativ_einzelner_batch_fehler_stoppt_nicht_den_gesamten_sync(
        self, db_session, google_sync, fake_gmail
    ):
        app = application_factory(db_session, firma="Contoso AG", datum_bewerbung=date.today() - timedelta(days=30))
        contact = contact_factory(db_session, email="recruiterin@contoso.com")
        app.contacts.append(contact)
        db_session.commit()

        meta_ok, full_ok = gmail_message("msg-ok", "Recruiterin <recruiterin@contoso.com>", "Interview", "Einladung zum Interview.", _now_rfc2822())
        fake_gmail(
            [{"messages": [{"id": "msg-fail"}, {"id": "msg-ok"}]}],
            metadata={"msg-ok": meta_ok},
            full={"msg-ok": full_ok},
            batch_errors={"msg-fail": RuntimeError("boom")},
        )

        result = await _do_gmail(1)

        assert result["created"] == 1
        assert any("msg-fail" in e for e in result["errors"])
