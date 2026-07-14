"""CV document text extraction for the AI assessment prompt (ai/tasks.py).

Backend-side counterpart to agent/text_extract.py — kept separate since the
CV file lives in backend-managed storage (routers/auth.py's CV_ROOT), not
agent-managed paths, and only needs the two extensions CV upload accepts
that have an extraction library available (.pdf, .docx — legacy .doc has no
extraction path anywhere in this repo, agent included)."""
from __future__ import annotations

import pathlib

MAX_TEXT_CHARS = 4000


def extract_cv_text(path: str) -> str | None:
    """Returns extracted text, or None if the file is missing/unreadable/
    unsupported. Callers should treat None as "skip this section" — CV
    extraction failing must never break the AI assessment it feeds into."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            text = " ".join(pages).strip()
        elif ext == ".docx":
            import docx
            doc = docx.Document(path)
            text = " ".join(paragraph.text for paragraph in doc.paragraphs).strip()
        else:
            return None
        return text[:MAX_TEXT_CHARS] or None
    except Exception:
        return None
