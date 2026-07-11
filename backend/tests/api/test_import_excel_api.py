"""L2 API — POST /api/import/excel. Baut echte .xlsx-Bytes über openpyxl
(keine Hand-Mocks) und lädt sie über die client-Fixture hoch."""
import io

import openpyxl
import pytest

from app import models
from tests.factories import application_factory

pytestmark = pytest.mark.api


def _build_workbook(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tracking"
    ws.append([
        "Firma", "HH?", "Zielfirma", "Rolle", "BesetztvonHH", "Quelle",
        "DatumBewerbung", "LetztesUpdate", "Status", "Ghosting", "Abgesagt",
        "Kommentar", "Gespräch1", "Gespräch2", "Gespräch3", "Gespräch4", "Gespräch5",
    ])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _upload(client, content: bytes, filename="import.xlsx", skip_duplicates=None):
    params = {} if skip_duplicates is None else {"skip_duplicates": skip_duplicates}
    return client.post(
        "/api/import/excel",
        files={"file": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        params=params,
    )


class TestImportExcel:
    def test_negativ_falsche_dateiendung_liefert_400(self, client):
        resp = client.post("/api/import/excel", files={"file": ("import.txt", b"nicht relevant", "text/plain")})
        assert resp.status_code == 400

    def test_negativ_kaputte_datei_liefert_422(self, client):
        resp = _upload(client, b"das ist keine excel datei")
        assert resp.status_code == 422

    def test_positiv_importiert_zeile_mit_allen_feldern(self, client, db_session):
        content = _build_workbook([[
            "Contoso AG", "x", "Globex AG", "Backend Engineer", "Andere Firma", "LinkedIn",
            "01.06.2026", "05.06.2026", "02 1. Gespräch HR/HH terminiert", None, None,
            "Kommentar", "G1", "G2", "G3", "G4", "G5",
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        body = resp.json()
        assert body["imported"] == 1
        assert body["skipped"] == 0
        app = db_session.query(models.Application).filter_by(firma="Contoso AG").one()
        assert app.is_headhunter is True
        assert app.zielfirma_bei_hh == "Globex AG"
        assert app.main_status == "hr"
        assert app.sub_status == "1_scheduled"

    def test_positiv_leere_zeile_wird_uebersprungen(self, client):
        content = _build_workbook([[None] * 17])

        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["imported"] == 0

    def test_positiv_duplikat_wird_uebersprungen(self, client, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        db_session.commit()
        content = _build_workbook([[
            "Contoso AG", None, None, "Backend Engineer", None, None,
            None, None, None, None, None, None, None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["imported"] == 0
        assert resp.json()["skipped"] == 1

    def test_positiv_skip_duplicates_false_importiert_trotzdem(self, client, db_session):
        application_factory(db_session, firma="Contoso AG", rolle="Backend Engineer")
        db_session.commit()
        content = _build_workbook([[
            "Contoso AG", None, None, "Backend Engineer", None, None,
            None, None, None, None, None, None, None, None, None, None, None,
        ]])

        resp = _upload(client, content, skip_duplicates=False)

        assert resp.status_code == 200
        assert resp.json()["imported"] == 1

    def test_positiv_fehlende_rolle_wird_zu_gedankenstrich(self, client, db_session):
        content = _build_workbook([[
            "Contoso AG", None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        app = db_session.query(models.Application).filter_by(firma="Contoso AG").one()
        assert app.rolle == "—"

    def test_positiv_abgesagt_flag_setzt_rejected_status(self, client, db_session):
        content = _build_workbook([[
            "Contoso AG", None, None, "Rolle", None, None,
            None, None, None, None, "x", None, None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        app = db_session.query(models.Application).filter_by(firma="Contoso AG").one()
        assert app.main_status == "rejected"

    def test_positiv_unbekannter_status_faellt_auf_applied_zurueck(self, client, db_session):
        content = _build_workbook([[
            "Contoso AG", None, None, "Rolle", None, None,
            None, None, "Unbekannter Status", None, None, None, None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        app = db_session.query(models.Application).filter_by(firma="Contoso AG").one()
        assert app.main_status == "applied"

    def test_positiv_kommentar_erzeugt_notiz_event(self, client, db_session):
        content = _build_workbook([[
            "Contoso AG", None, None, "Rolle", None, None,
            None, None, None, None, None, "Ein Kommentar", None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        app = db_session.query(models.Application).filter_by(firma="Contoso AG").one()
        notiz_event = db_session.query(models.Event).filter_by(application_id=app.id, typ="notiz").first()
        assert notiz_event is not None
        assert notiz_event.notiz == "Ein Kommentar"

    def test_positiv_nicht_applied_status_erzeugt_status_event(self, client, db_session):
        content = _build_workbook([[
            "Contoso AG", None, None, "Rolle", None, None,
            None, None, "12 Warten auf finale Entscheidung", None, None, None, None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        app = db_session.query(models.Application).filter_by(firma="Contoso AG").one()
        status_event = db_session.query(models.Event).filter_by(application_id=app.id, typ="status").first()
        assert status_event is not None

    def test_positiv_deutsches_datumsformat_wird_geparst(self, client, db_session):
        content = _build_workbook([[
            "Contoso AG", None, None, "Rolle", None, None,
            "15.03.2026", None, None, None, None, None, None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        from datetime import date
        assert resp.status_code == 200
        app = db_session.query(models.Application).filter_by(firma="Contoso AG").one()
        assert app.datum_bewerbung == date(2026, 3, 15)

    def test_negativ_zeile_mit_fehler_wird_uebersprungen_ohne_gesamtabbruch(self, client, db_session, monkeypatch):
        import app.routers.import_excel as import_excel_module

        original = import_excel_module.cell_str

        def _broken(val):
            if val == "KAPUTT":
                raise ValueError("absichtlicher Testfehler")
            return original(val)

        monkeypatch.setattr(import_excel_module, "cell_str", _broken)

        content = _build_workbook([[
            "KAPUTT", None, None, "Rolle", None, None,
            None, None, None, None, None, None, None, None, None, None, None,
        ]])

        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["imported"] == 0
        assert len(resp.json()["errors"]) == 1
        assert "Zeile 2" in resp.json()["errors"][0]

    def test_positiv_zwei_zeilen_gemischt_import_und_duplikat(self, client, db_session):
        content = _build_workbook([
            ["Firma A", None, None, "Rolle A", None, None, None, None, None, None, None, None, None, None, None, None, None],
            ["Firma B", None, None, "Rolle B", None, None, None, None, None, None, None, None, None, None, None, None, None],
        ])

        resp = _upload(client, content)

        assert resp.status_code == 200
        assert resp.json()["imported"] == 2
        assert "2 Bewerbungen importiert" in resp.json()["message"]
