"""Generic document text extraction, used for the CV (User.cv_extracted_text)
and, since v4.6.70, per-application job-description attachments feeding
ai/tasks.py's match-score prompt (see ai/jd_resolve.py).

Backend-side counterpart to agent/text_extract.py — kept separate since these
files live in backend-managed storage (routers/auth.py's CV_ROOT,
routers/attachments.py's ATTACHMENTS_ROOT), not agent-managed paths, and only
needs the extensions that have an extraction path available here (.pdf,
.docx, .txt, .md — legacy .doc has no extraction path anywhere in this repo,
agent included)."""
from __future__ import annotations

import multiprocessing
import pathlib

MAX_TEXT_CHARS = 4000  # CV-specific cap, used by extract_cv_text()'s wrapper

# pdfplumber/pdfminer can pathologically spin at ~100% CPU for minutes on
# certain real-world PDFs without raising or returning — this once took
# down the whole app via _migrate_cv_extracted_text_cache()'s startup
# backfill (production incident, 2026-07-16). That's CPU-bound work, so a
# thread-based timeout can't stop it — only killing the process can, hence
# running the actual extraction in a subprocess bounded to this timeout.
EXTRACTION_TIMEOUT_SECONDS = 20


def _extract_text_unbounded(path: str, max_chars: int) -> str | None:
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
        elif ext in (".txt", ".md"):
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
        else:
            return None
        return text[:max_chars] or None
    except Exception:
        return None


def _extract_worker(path: str, max_chars: int, out_queue: "multiprocessing.Queue[str | None]") -> None:
    out_queue.put(_extract_text_unbounded(path, max_chars))


def extract_text_from_file(
    path: str, max_chars: int = MAX_TEXT_CHARS, timeout: int = EXTRACTION_TIMEOUT_SECONDS
) -> str | None:
    """Returns extracted text, or None if the file is missing/unreadable/
    unsupported/too slow. Callers should treat None as "skip this section"
    — extraction failing must never break whatever it feeds into (an AI
    prompt, a startup migration, an upload request), nor block the caller
    beyond `timeout` seconds."""
    ctx = multiprocessing.get_context("spawn")
    queue: "multiprocessing.Queue[str | None]" = ctx.Queue()
    proc = ctx.Process(target=_extract_worker, args=(path, max_chars, queue))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join(2)
        if proc.is_alive():
            proc.kill()
            proc.join()
        return None
    try:
        return queue.get(timeout=5)
    except Exception:
        return None


def extract_cv_text(path: str, timeout: int = EXTRACTION_TIMEOUT_SECONDS) -> str | None:
    """CV-specific wrapper: same extraction, CV's own MAX_TEXT_CHARS cap."""
    return extract_text_from_file(path, max_chars=MAX_TEXT_CHARS, timeout=timeout)
