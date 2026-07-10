"""L1 Component — exec_cleanup() application auto-merge in cleanup.py.

Risk: Die automatische Zusammenführung (keeper gewinnt, loser wird gelöscht)
ist destruktiv — Events/Kontakte müssen korrekt umgehängt werden, sonst
Datenverlust. Bisher nur _find_app_groups() getestet, nicht der exec-Flow.
"""
import pytest

from app import models
from app.routers import cleanup
from tests.factories import application_factory, contact_factory, event_factory

pytestmark = pytest.mark.component


class TestCleanupExecApplications:
    async def test_positiv_duplikate_werden_zusammengefuehrt_und_verlierer_geloescht(self, db_session):
        # keeper bekommt Events+Kontakte → höherer Score → bleibt erhalten
        keeper = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer",
                                     kommentar="Hauptprofil mit Notizen")
        loser = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer")
        ev = event_factory(db_session, keeper, typ="notiz", titel="Telefonat")
        contact = contact_factory(db_session)
        keeper.contacts.append(contact)
        db_session.commit()

        await cleanup.cleanup_run(
            db=db_session, scope="applications",
            current_user=models.User(id=1, email="test@x.de", password_hash="x", email_verified=True),
        )

        # Nach db.commit() in cleanup_run Session expired — frisch laden
        db_session.expire_all()
        keeper_fresh = db_session.get(models.Application, keeper.id)
        assert keeper_fresh is not None
        ev_fresh = db_session.get(models.Event, ev.id)
        assert ev_fresh is not None
        assert ev_fresh.application_id == keeper.id
        assert contact in keeper_fresh.contacts
        assert db_session.get(models.Application, loser.id) is None

    async def test_positiv_nur_exakte_dedup_key_treffer_werden_gemeraged(self, db_session):
        a1 = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer")
        a2 = application_factory(db_session, firma="Contoso GmbH", rolle="Senior Engineer")  # andere Rolle
        db_session.commit()

        await cleanup.cleanup_run(
            db=db_session, scope="applications",
            current_user=models.User(id=1, email="test@x.de", password_hash="x", email_verified=True),
        )

        # Verschiedene dedup_keys → keine Gruppe, beide bleiben
        assert db_session.get(models.Application, a1.id) is not None
        assert db_session.get(models.Application, a2.id) is not None

    async def test_negativ_contacts_werden_nicht_dupliziert(self, db_session):
        keeper = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer")
        loser = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer")
        contact = contact_factory(db_session)
        keeper.contacts.append(contact)
        loser.contacts.append(contact)
        db_session.commit()

        await cleanup.cleanup_run(
            db=db_session, scope="applications",
            current_user=models.User(id=1, email="test@x.de", password_hash="x", email_verified=True),
        )

        db_session.refresh(keeper)
        assert keeper.contacts.count(contact) == 1

    async def test_corner_case_mehr_als_zwei_duplikate(self, db_session):
        a1 = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer",
                                  kommentar="bester Kommentar")
        a2 = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer")
        a3 = application_factory(db_session, firma="Contoso GmbH", rolle="Engineer")
        db_session.commit()

        await cleanup.cleanup_run(
            db=db_session, scope="applications",
            current_user=models.User(id=1, email="test@x.de", password_hash="x", email_verified=True),
        )

        # a1 (höchster Score durch kommentar) bleibt, a2 + a3 werden gelöscht
        assert db_session.get(models.Application, a1.id) is not None
        assert db_session.get(models.Application, a2.id) is None
        assert db_session.get(models.Application, a3.id) is None

    async def test_negativ_loeschen_ohne_duplikate_crasht_nicht(self, db_session):
        application_factory(db_session, firma="Einzigartig GmbH", rolle="Engineer")
        db_session.commit()

        await cleanup.cleanup_run(
            db=db_session, scope="applications",
            current_user=models.User(id=1, email="test@x.de", password_hash="x", email_verified=True),
        )

        assert db_session.query(models.Application).count() == 1
