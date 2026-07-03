"""Document text extraction — pure Python, identical on every OS, so it lives
outside the provider/adapter layer entirely."""
from __future__ import annotations

import pathlib

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md", ".rtf", ".odt"}
MAX_TEXT_CHARS = 4000


def extract_text(path: str) -> str:
    ext = pathlib.Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return " ".join(pages)[:MAX_TEXT_CHARS]
        if ext == ".docx":
            import docx
            doc = docx.Document(path)
            return " ".join(p.text for p in doc.paragraphs)[:MAX_TEXT_CHARS]
        with open(path, "r", errors="ignore", encoding="utf-8") as f:
            return f.read()[:MAX_TEXT_CHARS]
    except Exception as e:
        return f"[Fehler beim Lesen: {e}]"
