#!/usr/bin/env python3
"""
files_bridge.py — serves local documents to JobTracker
Run on your Mac: python3 files_bridge.py

Endpoints:
  GET  /health
  GET  /files?folder=/path/to/folder[&since=unix_timestamp]
       Returns: [{name, path, text, modified, subfolder}]
  GET  /browse?folder=/path/to/folder[&subfolder=Name]
       Returns: [{name, path, type, modified}]  (no text extraction)
  GET  /file?path=/absolute/path/to/file
       Returns: {name, path, text, modified}
  GET  /backups?folder=/path/to/backups
       Returns: [{name, path, modified, size}]  (only .db files)
  POST /backup-write   body: {folder, filename, data_b64, keep_count}
       Writes backup file; deletes oldest if count exceeds keep_count
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
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
        with open(path, "r", errors="ignore", encoding="utf-8") as f:
            return f.read()[:MAX_TEXT_CHARS]
    except Exception as e:
        return f"[Fehler beim Lesen: {e}]"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/backup-write":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            folder = body.get("folder", "")
            filename = body.get("filename", "")
            data_b64 = body.get("data_b64", "")
            keep_count = int(body.get("keep_count", 7))

            if not folder or not filename or not data_b64:
                self._json({"error": "folder, filename und data_b64 erforderlich"}, 400)
                return

            target_dir = pathlib.Path(folder)
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                data = base64.b64decode(data_b64)
                (target_dir / filename).write_bytes(data)

                # Cleanup: keep only the newest keep_count .db files
                backups = sorted(
                    [f for f in target_dir.iterdir() if f.suffix == ".db" and f.is_file()],
                    key=lambda f: f.stat().st_mtime,
                )
                for old in backups[:-keep_count]:
                    old.unlink(missing_ok=True)

                self._json({"success": True, "filename": filename})
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        self._json({"error": "not found"}, 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._json({"status": "ok"})
            return

        if parsed.path == "/files":
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

            root = pathlib.Path(folder).resolve()
            results = []
            for fpath_obj in root.rglob("*"):
                if not fpath_obj.is_file():
                    continue
                if fpath_obj.suffix.lower() not in SUPPORTED_EXTS:
                    continue
                fpath = str(fpath_obj)
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue
                if since is not None and mtime <= since:
                    continue

                # First-level subfolder relative to root (for firm matching)
                rel = fpath_obj.relative_to(root)
                subfolder = rel.parts[0] if len(rel.parts) > 1 else ""

                text = extract_text(fpath)
                results.append({
                    "name": fpath_obj.name,
                    "path": fpath,
                    "text": text,
                    "modified": mtime,
                    "subfolder": subfolder,
                })
            self._json(results)
            return

        if parsed.path == "/browse":
            folder = params.get("folder", [""])[0]
            subfolder = params.get("subfolder", [""])[0]

            if not folder or not os.path.isdir(folder):
                self._json({"error": f"Ordner nicht gefunden: {folder}"}, 400)
                return

            root = pathlib.Path(folder).resolve()
            search_root = (root / subfolder) if subfolder else root

            if not search_root.exists():
                self._json({"error": f"Unterordner nicht gefunden: {subfolder}"}, 400)
                return

            results = []
            try:
                for item in sorted(search_root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                    try:
                        mtime = item.stat().st_mtime
                    except OSError:
                        mtime = 0
                    if item.is_dir():
                        results.append({"name": item.name, "path": str(item), "type": "folder", "modified": mtime})
                    elif item.is_file() and item.suffix.lower() in SUPPORTED_EXTS:
                        results.append({"name": item.name, "path": str(item), "type": "file", "modified": mtime})
            except PermissionError as e:
                self._json({"error": str(e)}, 403)
                return
            self._json(results)
            return

        if parsed.path == "/file":
            path = params.get("path", [""])[0]
            if not path or not os.path.isfile(path):
                self._json({"error": f"Datei nicht gefunden: {path}"}, 404)
                return
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0
            text = extract_text(path)
            self._json({"name": os.path.basename(path), "path": path, "text": text, "modified": mtime})
            return

        if parsed.path == "/open":
            path = params.get("path", [""])[0]
            if not path or not os.path.isfile(path):
                self._json({"error": f"Datei nicht gefunden: {path}"}, 404)
                return
            try:
                subprocess.Popen(["open", path])
                self._json({"success": True})
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        if parsed.path == "/pick-folder":
            try:
                result = subprocess.run(
                    ['osascript', '-e', 'POSIX path of (choose folder with prompt "Backup-Ordner wählen:")'],
                    capture_output=True, text=True, timeout=60,
                )
                path = result.stdout.strip().rstrip('/')
                if path:
                    self._json({"path": path})
                else:
                    self._json({"error": "Kein Ordner ausgewählt"}, 400)
            except subprocess.TimeoutExpired:
                self._json({"error": "Timeout — kein Ordner ausgewählt"}, 400)
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        if parsed.path == "/backup-read":
            path = params.get("path", [""])[0]
            if not path or not os.path.isfile(path):
                self._json({"error": f"Datei nicht gefunden: {path}"}, 404)
                return
            try:
                data = pathlib.Path(path).read_bytes()
                self._json({"data_b64": base64.b64encode(data).decode(), "name": os.path.basename(path)})
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        if parsed.path == "/backups":
            folder = params.get("folder", [""])[0]
            if not folder or not os.path.isdir(folder):
                self._json([])
                return
            target_dir = pathlib.Path(folder)
            backups = []
            for f in sorted(target_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.is_file() and f.suffix == ".db":
                    st = f.stat()
                    backups.append({
                        "name": f.name,
                        "path": str(f),
                        "modified": st.st_mtime,
                        "size": st.st_size,
                    })
            self._json(backups)
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
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"Files Bridge läuft auf http://localhost:{port}")
    print(f"Unterstützte Formate: {', '.join(sorted(SUPPORTED_EXTS))}")
    print("Für PDF/DOCX-Unterstützung: pip install pdfplumber python-docx")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
