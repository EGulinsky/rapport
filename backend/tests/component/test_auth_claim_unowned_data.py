"""L1 Component — claim_unowned_data() in app/database.py: der einmalige
Übergang von der Ein-Personen-Installation (Daten ohne user_id) zu echten
Benutzerkonten. Wird über verify_email() nur für das allererste je
bestätigte Konto ausgelöst.
"""
import pytest

from app import models
from app.database import claim_unowned_data
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.component


class TestClaimUnownedData:
    def test_positiv_unbesessene_bewerbung_wird_dem_konto_zugewiesen(self, db_session):
        app = application_factory(db_session, user_id=None)
        db_session.commit()

        claim_unowned_data(db_session, user_id=42)

        db_session.refresh(app)
        assert app.user_id == 42

    def test_negativ_bereits_zugewiesene_zeile_wird_nicht_ueberschrieben(self, db_session):
        app = application_factory(db_session, user_id=7)
        db_session.commit()

        claim_unowned_data(db_session, user_id=42)

        db_session.refresh(app)
        assert app.user_id == 7

    def test_positiv_mehrere_tabellen_werden_gemeinsam_geclaimt(self, db_session):
        app = application_factory(db_session, user_id=None)
        contact = contact_factory(db_session, user_id=None)
        db_session.add(models.AiSettings(provider="groq", model="groq/llama-3.3-70b-versatile", user_id=None))
        db_session.commit()

        claim_unowned_data(db_session, user_id=99)

        db_session.refresh(app)
        db_session.refresh(contact)
        ai_settings = db_session.query(models.AiSettings).one()
        assert app.user_id == 99
        assert contact.user_id == 99
        assert ai_settings.user_id == 99

    def test_corner_case_leere_datenbank_wirft_keinen_fehler(self, db_session):
        claim_unowned_data(db_session, user_id=1)  # keine Zeilen vorhanden — darf nicht crashen


class TestCompanyProfileUniquePerUser:
    def test_positiv_gleicher_name_norm_fuer_verschiedene_nutzer_erlaubt(self, db_session):
        db_session.add(models.CompanyProfile(name_norm="contoso ag", name_display="Contoso AG", user_id=1))
        db_session.add(models.CompanyProfile(name_norm="contoso ag", name_display="Contoso AG", user_id=2))
        db_session.commit()  # darf keinen IntegrityError werfen

        assert db_session.query(models.CompanyProfile).count() == 2

    def test_negativ_gleicher_name_norm_fuer_denselben_nutzer_verboten(self, db_session):
        from sqlalchemy.exc import IntegrityError

        db_session.add(models.CompanyProfile(name_norm="contoso ag", name_display="Contoso AG", user_id=1))
        db_session.commit()

        db_session.add(models.CompanyProfile(name_norm="contoso ag", name_display="Contoso AG Dup", user_id=1))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
