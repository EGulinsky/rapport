"""L2 API -- POST /api/sync/linkedin/connections/import.

Replaces the removed live connections-list scraper: the user uploads
LinkedIn's official Connections.csv export instead. Same shape as
test_sync_linkedin_messages_api.py — real CSV bytes built from LinkedIn's
actual export columns, uploaded via the client fixture.
"""
import csv
import io

import pytest

from app import models

pytestmark = pytest.mark.api

_COLUMNS = ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"]


def _build_csv(rows: list[dict], columns: list[str] | None = None) -> bytes:
    columns = columns or _COLUMNS
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def _connection_row(vorname, nachname, url, email="", firma="", rolle="", connected="01 Jan 2026"):
    return {
        "First Name": vorname, "Last Name": nachname, "URL": url,
        "Email Address": email, "Company": firma, "Position": rolle,
        "Connected On": connected,
    }


def _upload(client, content: bytes, filename="Connections.csv"):
    return client.post(
        "/api/sync/linkedin/connections/import",
        files={"file": (filename, content, "text/csv")},
    )


class TestImportConnectionsValidation:
    def test_negativ_falsche_dateiendung_wird_abgelehnt(self, client):
        resp = _upload(client, b"anything", filename="connections.txt")
        assert resp.status_code == 400

    def test_negativ_falsche_spalten_werden_abgelehnt(self, client):
        # e.g. messages.csv uploaded by mistake
        content = _build_csv(
            [{"CONVERSATION ID": "1", "FROM": "Max"}],
            columns=["CONVERSATION ID", "FROM"],
        )
        resp = _upload(client, content)
        assert resp.status_code == 422

    def test_negativ_leere_datei_wird_abgelehnt(self, client):
        content = _build_csv([])
        resp = _upload(client, content)
        assert resp.status_code == 422


class TestImportConnectionsCreatesContacts:
    def test_positiv_neue_kontakte_werden_angelegt(self, client, db_session):
        content = _build_csv([
            _connection_row("Anna", "Muster", "https://www.linkedin.com/in/anna-muster", firma="Beispiel AG", rolle="CTO"),
            _connection_row("Max", "Mustermann", "https://www.linkedin.com/in/max-mustermann", email="max@example.com"),
        ])

        resp = _upload(client, content)

        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 2
        assert body["errors"] == []

        anna = db_session.query(models.Contact).filter_by(name="Muster").first()
        assert anna is not None
        assert anna.vorname == "Anna"
        assert anna.firma == "Beispiel AG"
        assert anna.rolle == "CTO"
        assert anna.linkedin_url == "https://www.linkedin.com/in/anna-muster"

        max_c = db_session.query(models.Contact).filter_by(name="Mustermann").first()
        assert max_c.email == "max@example.com"

    def test_positiv_erneuter_upload_dupliziert_nicht(self, client, db_session):
        content = _build_csv([
            _connection_row("Anna", "Muster", "https://www.linkedin.com/in/anna-muster"),
        ])

        first = _upload(client, content)
        second = _upload(client, content)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["created"] == 1
        assert second.json()["created"] == 0
        assert db_session.query(models.Contact).filter_by(name="Muster").count() == 1

    def test_positiv_bestehender_kontakt_wird_per_linkedin_url_verlinkt(self, client, db_session):
        from tests.factories import contact_factory

        existing = contact_factory(db_session, name="Muster", vorname="Anna", linkedin_url=None, firma=None)
        db_session.commit()

        content = _build_csv([
            _connection_row("Anna", "Muster", "https://www.linkedin.com/in/anna-muster", firma="Beispiel AG"),
        ])

        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["created"] == 0
        db_session.refresh(existing)
        # _merge_parsed_contact (force=False) only fills previously-empty
        # fields — linkedin_url was None so it gets filled in from the CSV.
        assert existing.linkedin_url == "https://www.linkedin.com/in/anna-muster"
        assert existing.firma == "Beispiel AG"
