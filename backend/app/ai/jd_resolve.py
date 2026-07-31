"""Resolves the job-description text fed into ai/tasks.py's
compute_match_score() prompt.

Source priority (see docs/ARCHITECTURE.md's AI-scoring section for the
rationale): an application's own file-type-Event attachments (the existing
generic Attachments tab — no dedicated "upload job description" field exists
or is planned; there's no way to know which attachment, if several, is
actually the JD, so ALL extractable ones are passed to the LLM labeled by
filename and it judges relevance itself from context). Only when there are
zero attachments with extractable text does this fall back to scraping
stellenanzeige_url (LinkedIn postings only) — a genuinely expensive
Playwright browser launch, so the scraped text is cached on the Application
row and only re-fetched once the cache is empty (see
routers/applications.py's update_application(), which clears the cache when
stellenanzeige_url itself changes)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.cv_extract import extract_text_from_file

MAX_JD_ATTACHMENTS = 3
MAX_JD_TEXT_CHARS = 3000


async def resolve_jd_texts(db: Session, app: models.Application) -> list[dict]:
    """Returns up to MAX_JD_ATTACHMENTS {"filename": str, "text": str}
    entries, newest first. Falls back to a cached/live LinkedIn
    job-posting scrape of stellenanzeige_url if no attachment yielded
    text. Returns [] if neither source has anything usable."""
    events = (
        db.query(models.Event)
        .filter(models.Event.application_id == app.id, models.Event.typ == "file")
        .order_by(models.Event.datum_zeit.desc().nullslast(), models.Event.datum.desc())
        .all()
    )

    from app.routers.attachments import ATTACHMENTS_ROOT

    jd_texts: list[dict] = []
    for ev in events:
        for att in ev.attachments:
            if len(jd_texts) >= MAX_JD_ATTACHMENTS:
                break
            full_path = os.path.join(ATTACHMENTS_ROOT, att.storage_path)
            text = extract_text_from_file(full_path, max_chars=MAX_JD_TEXT_CHARS)
            if text:
                jd_texts.append({"filename": att.filename, "text": text})
        if len(jd_texts) >= MAX_JD_ATTACHMENTS:
            break

    if jd_texts:
        return jd_texts

    url = app.stellenanzeige_url
    if not url or "linkedin.com" not in url:
        return []

    if app.jd_link_text_cache:
        return [{"filename": "LinkedIn-Stellenanzeige", "text": app.jd_link_text_cache}]

    from app.linkedin_job_description import load_job_description

    try:
        page_data = await load_job_description(url, db)
    except ValueError:
        return []

    text = (page_data.get("description") or "").strip()
    if not text:
        return []

    app.jd_link_text_cache = text
    app.jd_link_text_fetched_at = datetime.now(timezone.utc)
    db.commit()
    return [{"filename": "LinkedIn-Stellenanzeige", "text": text}]
