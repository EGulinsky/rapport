"""L3 Integration — app/ai/jd_resolve.py's resolve_jd_texts(): sourcing job-
description text for the match-score prompt from an application's file-type
Event attachments (primary source), falling back to a cached/live LinkedIn
job-posting scrape of stellenanzeige_url only when no attachment yields
text. Touches real files on disk (via the real store_attachment() helper,
same as production) and a real DB session, hence integration not unit."""
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.ai.jd_resolve import MAX_JD_ATTACHMENTS, resolve_jd_texts
from app.routers.attachments import store_attachment
from tests.factories import application_factory, event_factory

pytestmark = pytest.mark.integration


class TestResolveJdTexts:
    async def test_positiv_attachment_text_wird_gelabelt_zurueckgegeben(self, db_session):
        app = application_factory(db_session)
        ev = event_factory(db_session, app, typ="file")
        store_attachment(db_session, ev.id, "job-posting.txt", b"Senior Backend Engineer, Python", user_id=app.user_id)
        db_session.commit()

        result = await resolve_jd_texts(db_session, app)

        assert len(result) == 1
        assert result[0]["filename"] == "job-posting.txt"
        assert "Senior Backend Engineer" in result[0]["text"]

    async def test_positiv_nur_file_typ_events_werden_beruecksichtigt(self, db_session):
        app = application_factory(db_session)
        mail_ev = event_factory(db_session, app, typ="mail")
        store_attachment(db_session, mail_ev.id, "not-a-jd.txt", b"Mail attachment content", user_id=app.user_id)
        db_session.commit()

        result = await resolve_jd_texts(db_session, app)

        assert result == []

    async def test_positiv_mehr_als_max_attachments_wird_gekappt(self, db_session):
        app = application_factory(db_session)
        for i in range(MAX_JD_ATTACHMENTS + 2):
            ev = event_factory(db_session, app, typ="file", datum=date.today() - timedelta(days=i))
            store_attachment(db_session, ev.id, f"doc-{i}.txt", f"Content {i}".encode(), user_id=app.user_id)
        db_session.commit()

        result = await resolve_jd_texts(db_session, app)

        assert len(result) == MAX_JD_ATTACHMENTS

    async def test_positiv_keine_attachments_linkedin_url_wird_gescraped_und_gecacht(self, db_session):
        app = application_factory(db_session, stellenanzeige_url="https://www.linkedin.com/jobs/view/12345")
        db_session.commit()

        async def _fake_load(url, db):
            return {"description": "Wir suchen einen Backend Engineer.", "company": "Contoso AG"}

        with patch("app.linkedin_job_description.load_job_description", new=_fake_load):
            result = await resolve_jd_texts(db_session, app)

        assert len(result) == 1
        assert "Backend Engineer" in result[0]["text"]
        db_session.refresh(app)
        assert app.jd_link_text_cache == "Wir suchen einen Backend Engineer."
        assert app.jd_link_text_fetched_at is not None

    async def test_positiv_gecachter_link_text_wird_ohne_erneuten_scrape_verwendet(self, db_session):
        app = application_factory(
            db_session,
            stellenanzeige_url="https://www.linkedin.com/jobs/view/12345",
            jd_link_text_cache="Bereits gecachter Text.",
        )
        db_session.commit()

        with patch("app.linkedin_job_description.load_job_description") as mock_load:
            result = await resolve_jd_texts(db_session, app)

        mock_load.assert_not_called()
        assert result == [{"filename": "LinkedIn-Stellenanzeige", "text": "Bereits gecachter Text."}]

    async def test_negativ_keine_attachments_und_keine_url_liefert_leere_liste(self, db_session):
        app = application_factory(db_session, stellenanzeige_url=None)
        db_session.commit()

        result = await resolve_jd_texts(db_session, app)

        assert result == []

    async def test_negativ_nicht_linkedin_url_liefert_leere_liste(self, db_session):
        app = application_factory(db_session, stellenanzeige_url="https://example.com/jobs/123")
        db_session.commit()

        result = await resolve_jd_texts(db_session, app)

        assert result == []

    async def test_negativ_load_job_description_wirft_valueerror_wird_abgefangen(self, db_session):
        app = application_factory(db_session, stellenanzeige_url="https://www.linkedin.com/jobs/view/12345")
        db_session.commit()

        async def _fake_load(url, db):
            raise ValueError("Seite konnte nicht geladen werden")

        with patch("app.linkedin_job_description.load_job_description", new=_fake_load):
            result = await resolve_jd_texts(db_session, app)

        assert result == []
        db_session.refresh(app)
        assert app.jd_link_text_cache is None
