"""L1 Component — queue_orphaned_calendar_event() in sync_common.py.

Replaces the old immediate, unconditional auto-delete that used to run
inside sync_google.py's/sync_icloud.py's calendar-orphan cleanup — a sync
process silently deleting real timeline history with no confirmation step
was the same class of bug as the contacts bulk-delete incident this whole
change set fixes. Now it only queues a PendingMatch for review.py's
approve/reject flow to act on.
"""
import json

import pytest

from app import models
from app.routers.sync_common import queue_orphaned_calendar_event
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.component


class TestQueueOrphanedCalendarEvent:
    def test_positiv_legt_pending_match_an_statt_zu_loeschen(self, db_session):
        app = application_factory(db_session)
        orphan = event_factory(db_session, app, typ="gespräch", source="gcal", external_id="evt-1", titel="Interview")
        db_session.commit()

        queued = queue_orphaned_calendar_event(db_session, "gcal", orphan, user_id=1)
        db_session.commit()

        assert queued is True
        assert db_session.get(models.Event, orphan.id) is not None  # nicht gelöscht
        match = db_session.query(models.PendingMatch).filter_by(
            source="gcal", event_type="orphaned_calendar_event",
        ).first()
        assert match is not None
        assert match.review_status == "pending"
        assert match.suggested_app_id == app.id
        assert match.datum == orphan.datum
        assert json.loads(match.raw_content) == {"event_id": orphan.id}
        assert "Interview" in match.titel

    def test_negativ_wird_nicht_doppelt_angelegt(self, db_session):
        app = application_factory(db_session)
        orphan = event_factory(db_session, app, typ="gespräch", source="icloud_cal", external_id="evt-2")
        db_session.commit()

        first = queue_orphaned_calendar_event(db_session, "icloud_cal", orphan, user_id=1)
        db_session.commit()
        second = queue_orphaned_calendar_event(db_session, "icloud_cal", orphan, user_id=1)
        db_session.commit()

        assert first is True
        assert second is False
        assert db_session.query(models.PendingMatch).filter_by(
            source="icloud_cal", event_type="orphaned_calendar_event",
        ).count() == 1

    def test_negativ_bereits_abgelehnter_vorschlag_wird_nicht_erneut_angelegt(self, db_session):
        # Once rejected, a subsequent sync run must not re-suggest the same
        # event forever — matches cleanup.py's duplicate_contact dedup
        # pattern (checked regardless of review_status).
        app = application_factory(db_session)
        orphan = event_factory(db_session, app, typ="gespräch", source="gcal", external_id="evt-3")
        db_session.add(models.PendingMatch(
            source="gcal", external_id=f"orphan_event_{orphan.id}",
            confidence=90, event_type="orphaned_calendar_event",
            review_status="rejected", user_id=1,
        ))
        db_session.commit()

        queued = queue_orphaned_calendar_event(db_session, "gcal", orphan, user_id=1)

        assert queued is False
        assert db_session.query(models.PendingMatch).filter_by(
            source="gcal", event_type="orphaned_calendar_event",
        ).count() == 1

    def test_positiv_gcal_und_icloud_cal_erhalten_passendes_source_label(self, db_session):
        app = application_factory(db_session)
        gcal_orphan = event_factory(db_session, app, typ="gespräch", source="gcal", external_id="evt-4")
        icloud_orphan = event_factory(db_session, app, typ="gespräch", source="icloud_cal", external_id="evt-5")
        db_session.commit()

        queue_orphaned_calendar_event(db_session, "gcal", gcal_orphan, user_id=1)
        queue_orphaned_calendar_event(db_session, "icloud_cal", icloud_orphan, user_id=1)
        db_session.commit()

        gcal_match = db_session.query(models.PendingMatch).filter_by(source="gcal").first()
        icloud_match = db_session.query(models.PendingMatch).filter_by(source="icloud_cal").first()
        assert "Kalender" in gcal_match.extract or "Calendar" in gcal_match.extract
        assert "Kalender" in icloud_match.extract or "Calendar" in icloud_match.extract
