"""L1 Component — der zentrale Mandanten-Filter in app/database.py.

Statt jede Query in ~20 Router-Dateien einzeln um `.filter_by(user_id=...)`
zu ergänzen, markiert set_session_user() die aktive Session mit der Konto-ID;
ein SQLAlchemy-Session-Event (`do_orm_execute`) filtert danach automatisch
jede SELECT-Query gegen ein mandantengebundenes Modell. Diese Tests
verifizieren den Mechanismus selbst, nicht einzelne Router.
"""
import pytest

from app import models
from app.database import set_session_user
from tests.factories import application_factory, contact_factory

pytestmark = pytest.mark.component


class TestTenantScopingFilter:
    def test_positiv_ohne_session_user_sieht_alles(self, db_session):
        # Unscoped (kein set_session_user() aufgerufen) — entspricht dem
        # Verhalten von Hintergrund-Jobs ohne bekanntes Konto.
        application_factory(db_session, firma="Firma A", user_id=1)
        application_factory(db_session, firma="Firma B", user_id=2)
        db_session.commit()

        results = db_session.query(models.Application).all()

        assert {a.firma for a in results} == {"Firma A", "Firma B"}

    def test_positiv_scoped_session_sieht_nur_eigene_zeilen(self, db_session):
        application_factory(db_session, firma="Firma A", user_id=1)
        application_factory(db_session, firma="Firma B", user_id=2)
        db_session.commit()

        set_session_user(db_session, 1)
        results = db_session.query(models.Application).all()

        assert [a.firma for a in results] == ["Firma A"]

    def test_negativ_zeilen_ohne_user_id_sind_fuer_niemanden_sichtbar(self, db_session):
        # Nicht geclaimte Alt-Daten (user_id IS NULL) sind für ein gescoptes
        # Konto unsichtbar, bis claim_unowned_data() sie zuweist.
        application_factory(db_session, firma="Nicht zugeordnet", user_id=None)
        db_session.commit()

        set_session_user(db_session, 1)
        results = db_session.query(models.Application).all()

        assert results == []

    def test_positiv_wechsel_des_session_users_wechselt_sichtbarkeit(self, db_session):
        application_factory(db_session, firma="Firma A", user_id=1)
        application_factory(db_session, firma="Firma B", user_id=2)
        db_session.commit()

        set_session_user(db_session, 1)
        assert [a.firma for a in db_session.query(models.Application).all()] == ["Firma A"]

        set_session_user(db_session, 2)
        assert [a.firma for a in db_session.query(models.Application).all()] == ["Firma B"]

    def test_positiv_filter_gilt_auch_fuer_andere_mandantengebundene_modelle(self, db_session):
        contact_factory(db_session, name="Kontakt A", user_id=1)
        contact_factory(db_session, name="Kontakt B", user_id=2)
        db_session.commit()

        set_session_user(db_session, 1)
        results = db_session.query(models.Contact).all()

        assert [c.name for c in results] == ["Kontakt A"]

    def test_corner_case_filter_by_id_respektiert_scoping_auch_bei_fremder_id(self, db_session):
        # Ein gescoptes Konto darf eine fremde ID nicht per direkter
        # filter_by(id=...)-Abfrage umgehen können.
        app_b = application_factory(db_session, firma="Firma B", user_id=2)
        db_session.commit()

        set_session_user(db_session, 1)
        result = db_session.query(models.Application).filter_by(id=app_b.id).first()

        assert result is None
