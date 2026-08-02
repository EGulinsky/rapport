"""L2 API — /api/sync/linkedin/people/search + /import."""
import pytest

from app import models
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.api


class TestSearchPeople:
    def test_negativ_ohne_linkedin_session_liefert_400(self, client, db_session):
        resp = client.get("/api/sync/linkedin/people/search?q=Max")
        assert resp.status_code == 400


class TestImportPeople:
    def test_positiv_importiert_neuen_kontakt_mit_gesplitteter_headline(self, client, db_session):
        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{
                "name": "Max Mustermann",
                "headline": "Senior Engineer at Contoso GmbH",
                "profile_url": "https://www.linkedin.com/in/max-mustermann",
            }],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["imported"] == 1
        contact = db_session.query(models.Contact).filter_by(linkedin_url="https://www.linkedin.com/in/max-mustermann").first()
        assert contact is not None
        assert contact.rolle == "Senior Engineer"
        assert contact.firma == "Contoso GmbH"

    def test_negativ_bereits_vorhandener_kontakt_per_url_wird_uebersprungen(self, client, db_session):
        contact_factory(db_session, name="Max Mustermann", linkedin_url="https://www.linkedin.com/in/max-mustermann")
        db_session.commit()

        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{
                "name": "Max Mustermann",
                "profile_url": "https://www.linkedin.com/in/max-mustermann",
            }],
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["imported"] == 0
        assert body["skipped"] == 1

    def test_positiv_verknuepft_mit_application_id(self, client, db_session):
        app = application_factory(db_session)
        db_session.commit()

        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{"name": "Verknüpfte Person", "profile_url": "https://www.linkedin.com/in/verknuepft"}],
            "application_id": app.id,
        })

        assert resp.status_code == 200
        contact = db_session.query(models.Contact).filter_by(linkedin_url="https://www.linkedin.com/in/verknuepft").first()
        assert app in contact.applications

    def test_negativ_unbekannte_application_id_liefert_404(self, client, db_session):
        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{"name": "X", "profile_url": "https://www.linkedin.com/in/x"}],
            "application_id": 999999,
        })
        assert resp.status_code == 404

    def test_corner_case_keine_trennbare_headline_bleibt_firma_leer(self, client, db_session):
        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{
                "name": "Freiberufler Person",
                "headline": "Freiberuflich",
                "profile_url": "https://www.linkedin.com/in/freiberufler",
            }],
        })

        assert resp.status_code == 200
        contact = db_session.query(models.Contact).filter_by(linkedin_url="https://www.linkedin.com/in/freiberufler").first()
        assert contact.rolle == "Freiberuflich"
        assert contact.firma is None

    def test_positiv_name_wird_in_vorname_und_nachname_gesplittet(self, client, db_session):
        """LinkedIn's people-search only exposes one display-name string, unlike
        the CSV/iCloud/Google imports which have structured first/last-name
        fields -- import_people() must split it itself rather than dumping
        the whole string into `name` (which used to leave `vorname` NULL)."""
        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{
                "name": "Max Mustermann",
                "profile_url": "https://www.linkedin.com/in/max-mustermann",
            }],
        })

        assert resp.status_code == 200
        contact = db_session.query(models.Contact).filter_by(linkedin_url="https://www.linkedin.com/in/max-mustermann").first()
        assert contact.vorname == "Max"
        assert contact.name == "Mustermann"
        assert contact.display_name == "Max Mustermann"

    def test_positiv_bestehender_kontakt_ueber_nachname_gefunden_statt_dupliziert(self, client, db_session):
        """A contact already imported via the corrected split logic (name=
        surname only) must be matched by that surname, not re-created as a
        second row just because a fresh search result carries the full
        display string again."""
        contact_factory(db_session, name="Mustermann", vorname="Max", linkedin_url=None)
        db_session.commit()

        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{
                "name": "Max Mustermann",
                "profile_url": "https://www.linkedin.com/in/max-mustermann",
            }],
        })

        assert resp.status_code == 200
        assert resp.json() == {"imported": 0, "skipped": 1}
        assert db_session.query(models.Contact).filter_by(name="Mustermann").count() == 1

    def test_positiv_altkontakt_mit_vollem_namen_wird_nachtraeglich_gesplittet(self, client, db_session):
        """A contact imported before this split fix existed has the full
        display string in `name` and vorname=NULL -- re-importing the same
        person must find that legacy row (not create a duplicate) and heal
        it with the now-available vorname/name split."""
        contact_factory(db_session, name="Max Mustermann", vorname=None, linkedin_url=None)
        db_session.commit()

        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{
                "name": "Max Mustermann",
                "profile_url": "https://www.linkedin.com/in/max-mustermann",
            }],
        })

        assert resp.status_code == 200
        assert resp.json() == {"imported": 0, "skipped": 1}
        contact = db_session.query(models.Contact).filter_by(linkedin_url="https://www.linkedin.com/in/max-mustermann").first()
        assert contact.vorname == "Max"
        assert contact.name == "Mustermann"

    def test_corner_case_einzelnes_wort_ohne_vorname(self, client, db_session):
        resp = client.post("/api/sync/linkedin/people/import", json={
            "candidates": [{"name": "Madonna", "profile_url": "https://www.linkedin.com/in/madonna"}],
        })

        assert resp.status_code == 200
        contact = db_session.query(models.Contact).filter_by(linkedin_url="https://www.linkedin.com/in/madonna").first()
        assert contact.name == "Madonna"
        assert contact.vorname is None
