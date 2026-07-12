"""L2 API — attachments.py: store_attachment() sowie Upload/Download/Delete-
Endpunkte. ATTACHMENTS_ROOT liegt dank tests/conftest.py's DATABASE_URL-
Override bereits unter einem temporären Testverzeichnis — echte Datei-I/O
ist hier also unbedenklich. Jeder Test nutzt einen EIGENEN Dateinamen: die
Event-IDs starten (wegen der autouse _reset_db-Fixture) in jedem Test wieder
bei 1, aber das Anhänge-Verzeichnis auf der Platte wird zwischen Tests NICHT
geleert — gleiche Dateinamen würden sich sonst testübergreifend die
Kollisions-Umbenennung ("_1", "_2", …) teilen."""
import pytest

from app import models
from app.routers.attachments import ATTACHMENTS_ROOT, store_attachment
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.api


class TestStoreAttachment:
    def test_positiv_speichert_datei_und_legt_datensatz_an(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()

        att = store_attachment(db_session, ev.id, "store-basic.pdf", b"%PDF-1.4 Inhalt", user_id=1)
        db_session.commit()

        assert att.filename == "store-basic.pdf"
        assert att.size_bytes == len(b"%PDF-1.4 Inhalt")
        import os
        assert os.path.exists(os.path.join(ATTACHMENTS_ROOT, att.storage_path))

    def test_corner_case_gleicher_dateiname_wird_durchnummeriert(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()

        att1 = store_attachment(db_session, ev.id, "store-dupe.pdf", b"Version 1", user_id=1)
        db_session.commit()
        att2 = store_attachment(db_session, ev.id, "store-dupe.pdf", b"Version 2", user_id=1)
        db_session.commit()

        assert att1.filename == "store-dupe.pdf"
        assert att2.filename == "store-dupe_1.pdf"

    def test_negativ_zu_grosse_datei_erzeugt_pendingmatch_statt_speicherung(self, db_session, monkeypatch):
        import app.routers.attachments as attachments_module

        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()

        monkeypatch.setattr(attachments_module, "MAX_INLINE_BYTES", 10)

        with pytest.raises(ValueError, match="größer als"):
            store_attachment(db_session, ev.id, "store-riesig.zip", b"x" * 20, user_id=1)
        db_session.flush()

        pm = db_session.query(models.PendingMatch).filter_by(event_type="large_attachment").first()
        assert pm is not None
        assert pm.suggested_app_id == app.id


class TestDownloadAttachment:
    def test_negativ_nicht_gefunden_liefert_404(self, client):
        resp = client.get("/api/attachments/999/download")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "attachment.not_found"

    def test_positiv_laedt_datei_herunter(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()
        att = store_attachment(db_session, ev.id, "download-ok.pdf", b"Inhalt der Datei", user_id=1)
        db_session.commit()

        resp = client.get(f"/api/attachments/{att.id}/download")

        assert resp.status_code == 200
        assert resp.content == b"Inhalt der Datei"

    def test_negativ_datei_auf_platte_fehlt_liefert_404(self, client, db_session):
        import os

        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()
        att = store_attachment(db_session, ev.id, "download-missing.pdf", b"Inhalt", user_id=1)
        db_session.commit()
        os.remove(os.path.join(ATTACHMENTS_ROOT, att.storage_path))

        resp = client.get(f"/api/attachments/{att.id}/download")

        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "attachment.file_missing"


class TestUploadAttachment:
    def test_negativ_event_nicht_gefunden(self, client):
        resp = client.post("/api/attachments/999/upload", files={"file": ("upload-missing-event.pdf", b"Inhalt", "application/pdf")})
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "event.not_found"

    def test_positiv_datei_wird_hochgeladen(self, client, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()

        resp = client.post(f"/api/attachments/{ev.id}/upload", files={"file": ("upload-ok.pdf", b"Inhalt", "application/pdf")})

        assert resp.status_code == 201
        body = resp.json()
        assert body["filename"] == "upload-ok.pdf"
        assert body["content_type"] == "application/pdf"

    def test_negativ_zu_grosse_datei_liefert_413(self, client, db_session, monkeypatch):
        import app.routers.attachments as attachments_module

        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()
        monkeypatch.setattr(attachments_module, "MAX_INLINE_BYTES", 10)

        resp = client.post(f"/api/attachments/{ev.id}/upload", files={"file": ("upload-riesig.zip", b"x" * 20, "application/zip")})

        assert resp.status_code == 413


class TestDeleteAttachment:
    def test_negativ_nicht_gefunden(self, client):
        resp = client.delete("/api/attachments/999")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_key"] == "attachment.not_found"

    def test_positiv_loescht_datei_und_datensatz(self, client, db_session):
        import os

        app = application_factory(db_session)
        ev = event_factory(db_session, app)
        db_session.commit()
        att = store_attachment(db_session, ev.id, "delete-ok.pdf", b"Inhalt", user_id=1)
        db_session.commit()
        full_path = os.path.join(ATTACHMENTS_ROOT, att.storage_path)
        assert os.path.exists(full_path)

        resp = client.delete(f"/api/attachments/{att.id}")

        assert resp.status_code == 204
        assert not os.path.exists(full_path)
        assert db_session.query(models.Attachment).filter_by(id=att.id).first() is None
