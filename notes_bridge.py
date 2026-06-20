#!/usr/bin/env python3
"""
Notes Bridge — reads iCloud Notes via AppleScript and serves them over HTTP.
Run this once in a terminal: python3 notes_bridge.py
The jobtracker backend will call http://localhost:9999/notes automatically.
"""
import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 9999

JXA_SCRIPT = """
const app = Application('Notes')
app.includeStandardAdditions = true
const notes = app.notes()
const result = notes.map(n => {
    try {
        return {
            id: n.id(),
            name: n.name() || '',
            body: n.plaintext() || '',
            date: n.modificationDate() ? n.modificationDate().toISOString() : '',
            creationDate: n.creationDate() ? n.creationDate().toISOString() : ''
        }
    } catch(e) {
        return {id: '', name: '', body: '', date: ''}
    }
})
JSON.stringify(result)
"""


def fetch_notes() -> list[dict]:
    result = subprocess.run(
        ['osascript', '-l', 'JavaScript', '-e', JXA_SCRIPT],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'osascript failed')
    return json.loads(result.stdout.strip())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/notes':
            self.send_response(404)
            self.end_headers()
            return
        try:
            notes = fetch_notes()
            body = json.dumps(notes).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            err = json.dumps({'error': str(e)}).encode()
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def log_message(self, fmt, *args):
        print(f'[notes_bridge] {fmt % args}')


if __name__ == '__main__':
    print(f'Notes Bridge läuft auf http://localhost:{PORT}/notes')
    print('Beende mit Ctrl+C')
    HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
