# JobTracker Agent

Ersetzt `files_bridge.py`, `notes_bridge.py` und `calls_bridge.py`: ein
einzelner Hintergrund-Prozess statt drei, mit Bearer-Token-Auth statt offener
Ports, und einer OS-Adapter-Grenze für den geplanten Windows-Port.

Architektur-Details: siehe die Session-Notizen / Chat-Verlauf zum
Architektur-Vorschlag. Kurzfassung:

```
agent/
  main.py            # FastAPI-App, create_app()-Factory, /health
  auth.py            # Bearer-Token-Dependency
  config.py          # Token-Generierung/-Persistenz, per-OS App-Data-Dir
  text_extract.py     # PDF/DOCX/TXT-Textextraktion (OS-neutral)
  providers/
    base.py          # abstrakte Interfaces: FilesProvider, NotesProvider, CallsProvider
    factory.py        # wählt Provider-Set nach platform.system()
    mac/              # heutige Implementierung (1:1 aus den alten Bridges portiert)
  routers/
    files.py          # /files, /files/browse, /files/file, /files/open, /files/pick-*
    backup.py         # /backup/backups, /backup/backup-write, /backup/backup-read
    notes.py          # /notes
    calls.py          # /calls
```

## Lokal starten (Entwicklung)

```bash
cd agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m agent.main   # von jobtracker/ (Repo-Root) aus, nicht von agent/
```

Läuft auf Port 9996. Der Bearer-Token wird beim ersten Start generiert und
liegt unter `~/Library/Application Support/JobTrackerAgent/config.json`
(macOS).

## Tests

```bash
cd agent
python3 -m venv .venv_test
.venv_test/bin/pip install -r requirements.txt pytest httpx
.venv_test/bin/python3 -m pytest -v
```

## Noch offen (nächste Schritte, nicht Teil dieses Grundgerüsts)

- Packaging: PyInstaller → `.app` → `.dmg`, Menüleisten-Icon (`rumps`),
  Selbstregistrierung als `launchd`-LaunchAgent beim ersten Start.
- Backend-Integration: `FILES_BRIDGE_URL`/`CALLS_BRIDGE_URL`/hartkodierte
  Notes-URL durch `AGENT_URL`+`AGENT_TOKEN` ersetzen, `startup_check.py` auf
  einen einzelnen `/health`-Call umstellen.
- Settings-UI: neuer "Agent"-Tab zum Einfügen des Tokens (verschlüsselt
  gespeichert, gleiches Muster wie AI-/Maps-Key).
- Die drei alten `*_bridge.py`-Skripte am Repo-Root erst entfernen, wenn der
  Agent produktiv im Einsatz ist und die Backend-Integration steht.
