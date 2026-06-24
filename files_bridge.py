#!/usr/bin/env python3
"""
files_bridge.py — serves local documents to JobTracker
Run on your Mac: python3 files_bridge.py

Endpoints:
  GET /health
  GET /files?folder=/path/to/folder[&since=unix_timestamp]
      Returns: [{name, path, text, modified}]

Supported formats: .pdf, .docx, .txt, .md, .rtf
Text extraction requires: pip install pdfplumber python-docx
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 9998
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
        # Plain text fallbacks
        with open(path, "r", errors="ignore", encoding="utf-8") as f:
            return f.read()[:MAX_TEXT_CHARS]
    except Exception as e:
        return f"[Fehler beim Lesen: {e}]"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._json({"status": "ok"})
            return

        if parsed.path == "/files":
            params = parse_qs(parsed.query)
            folder = params.get("folder", [""])[0]
            since_raw = params.get("since", [""])[0]

            if not folder or not os.path.isdir(folder):
                self._json({"error": f"Ordner nicht gefunden: {folder}"}, 400)
                return

            since: float | None = None
            try:
                since = float(since_raw) if since_raw else None
            except ValueError:
                pass

            results = []
            for root, _dirs, files in os.walk(folder):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    ext = pathlib.Path(fname).suffix.lower()
                    if ext not in SUPPORTED_EXTS:
                        continue
                    try:
                        mtime = os.path.getmtime(fpath)
                    except OSError:
                        continue
                    if since is not None and mtime <= since:
                        continue
                    text = extract_text(fpath)
                    results.append({
                        "name": fname,
                        "path": fpath,
                        "text": text,
                        "modified": mtime,
                    })
            self._json(results)
            return

        self._json({"error": "not found"}, 404)

    def _json(self, data, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress per-request logs


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"Files Bridge läuft auf http://localhost:{port}")
    print(f"Unterstützte Formate: {', '.join(sorted(SUPPORTED_EXTS))}")
    print("Für PDF/DOCX-Unterstützung: pip install pdfplumber python-docx")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
