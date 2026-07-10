"""L1 Component — purge_source() in sync_common.py.

Risk: delete() umgeht den zentralen Mandanten-Filter, daher wird user_id
explizit gefiltert. Ohne user_id (= None) werden ALLE Nutzer getroffen.
Kein vorheriger Test deckt purge_source() ab.
"""
import pytest

from app import models
from app.routers.sync_common import purge_source, mark_synced

pytestmark = pytest.mark.component


class TestPurgeSource:
    def test_positiv_loescht_synceditems_einer_quelle(self, db_session):
        mark_synced(db_session, "gmail", "ext_1", user_id=1)
        mark_synced(db_session, "gmail", "ext_2", user_id=1)
        mark_synced(db_session, "icloud_cal", "ext_3", user_id=1)
        db_session.commit()

        purge_source(db_session, "gmail", user_id=1)

        remaining = db_session.query(models.SyncedItem).all()
        assert len(remaining) == 1
        assert remaining[0].source == "icloud_cal"

    def test_positiv_andere_quelle_bleibt_unberuehrt(self, db_session):
        mark_synced(db_session, "gmail", "ext_1", user_id=1)
        mark_synced(db_session, "linkedin", "ext_2", user_id=1)
        db_session.commit()

        purge_source(db_session, "gmail", user_id=1)

        sources = {s.source for s in db_session.query(models.SyncedItem).all()}
        assert sources == {"linkedin"}

    def test_positiv_ohne_user_id_werden_alle_user_getroffen(self, db_session):
        mark_synced(db_session, "gmail", "ext_1", user_id=1)
        mark_synced(db_session, "gmail", "ext_2", user_id=2)
        db_session.commit()

        purge_source(db_session, "gmail", user_id=None)

        assert db_session.query(models.SyncedItem).filter_by(source="gmail").count() == 0

    def test_negativ_mit_user_id_bleiben_andere_user_unberuehrt(self, db_session):
        mark_synced(db_session, "gmail", "ext_1", user_id=1)
        mark_synced(db_session, "gmail", "ext_2", user_id=2)
        db_session.commit()

        purge_source(db_session, "gmail", user_id=1)

        remaining = db_session.query(models.SyncedItem).filter_by(source="gmail").all()
        assert len(remaining) == 1
        assert remaining[0].user_id == 2

    def test_corner_case_leere_quelle_crasht_nicht(self, db_session):
        purge_source(db_session, "gmail", user_id=1)
        assert True  # kein Crash

    def test_corner_case_nicht_existente_quelle_crasht_nicht(self, db_session):
        purge_source(db_session, "unbekannte_quelle", user_id=1)
        assert True
