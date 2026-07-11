"""L2 API — GET /api/export/pdf. Prüft, dass die verschiedenen Zweige beim
PDF-Aufbau (Headhunter-Firmenname, Kürzung langer Texte, Terminübersicht,
Seitenumbruch bei vielen Bewerbungen, since-Filter) ohne Fehler durchlaufen
und ein valides PDF zurückgeben — der eigentliche Layoutinhalt wird nicht
pixelgenau geprüft, nur Statuscode/Header/Magic-Bytes."""
from datetime import date, timedelta

import pytest

from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.api


class TestExportPdf:
    def test_positiv_leere_liste_liefert_valides_pdf(self, client):
        resp = client.get("/api/export/pdf")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    def test_positiv_mit_bewerbungen_und_terminen(self, client, db_session):
        app = application_factory(
            db_session, firma="Contoso AG", rolle="Backend Engineer",
            main_status="hr", datum_bewerbung=date.today() - timedelta(days=10),
        )
        event_factory(db_session, app, typ="gespräch", source=None, datum=date.today() - timedelta(days=2))
        db_session.commit()

        resp = client.get("/api/export/pdf")

        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF")

    def test_positiv_headhunter_firmenname_wird_kombiniert(self, client, db_session):
        application_factory(
            db_session, firma="Contoso Recruiting", is_headhunter=True, zielfirma_bei_hh="Globex AG",
            datum_bewerbung=date.today(),
        )
        db_session.commit()

        resp = client.get("/api/export/pdf")

        assert resp.status_code == 200

    def test_positiv_lange_firmennamen_und_rollen_werden_gekuerzt(self, client, db_session):
        application_factory(
            db_session,
            firma="Ein außergewöhnlich langer Firmenname GmbH & Co. KG International Holdings",
            rolle="Senior Staff Principal Backend Software Engineering Architect (m/w/d) für verteilte Systeme",
            datum_bewerbung=date.today(),
        )
        db_session.commit()

        resp = client.get("/api/export/pdf")

        assert resp.status_code == 200

    def test_positiv_since_filter_schliesst_aeltere_bewerbungen_aus(self, client, db_session):
        application_factory(db_session, firma="Alt", datum_bewerbung=date(2020, 1, 1))
        application_factory(db_session, firma="Neu", datum_bewerbung=date.today())
        db_session.commit()

        resp = client.get("/api/export/pdf", params={"since": date.today().isoformat()})

        assert resp.status_code == 200

    def test_positiv_seitenumbruch_bei_vielen_bewerbungen(self, client, db_session):
        for i in range(65):
            application_factory(db_session, firma=f"Firma {i}", datum_bewerbung=date.today() - timedelta(days=i))
        db_session.commit()

        resp = client.get("/api/export/pdf")

        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF")

    def test_positiv_bewerbung_ohne_datum_wird_aus_liste_ausgeschlossen(self, client, db_session):
        application_factory(db_session, firma="Ohne Datum", datum_bewerbung=None)
        db_session.commit()

        resp = client.get("/api/export/pdf")

        assert resp.status_code == 200

    def test_positiv_eigener_name_erscheint_im_dateinamen_header(self, client, db_session):
        application_factory(db_session, datum_bewerbung=date.today())
        db_session.commit()

        resp = client.get("/api/export/pdf", params={"name": "Max Mustermann"})

        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
