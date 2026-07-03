# JobTracker Agent

Ersetzt `files_bridge.py`, `notes_bridge.py` und `calls_bridge.py`: ein
einzelner Hintergrund-Prozess statt drei, mit Bearer-Token-Auth statt offener
Ports, und einer OS-Adapter-Grenze für den geplanten Windows-Port.

```
agent/
  main.py            # FastAPI-App, create_app()-Factory, /health
  menubar.py          # macOS-Menüleisten-Einstiegspunkt (rumps) + launchd-Selbstregistrierung
  launchd.py           # LaunchAgent-Plist erzeugen/registrieren/entfernen
  auth.py             # Bearer-Token-Dependency
  config.py           # Token-Generierung/-Persistenz, per-OS App-Data-Dir
  text_extract.py      # PDF/DOCX/TXT-Textextraktion (OS-neutral)
  providers/
    base.py           # abstrakte Interfaces: FilesProvider, NotesProvider, CallsProvider
    factory.py         # wählt Provider-Set nach platform.system()
    mac/               # heutige Implementierung (1:1 aus den alten Bridges portiert)
  routers/
    files.py           # /files, /files/browse, /files/file, /files/open, /files/pick-*
    backup.py          # /backup/backups, /backup/backup-write, /backup/backup-read
    notes.py           # /notes
    calls.py           # /calls
  packaging/
    agent.spec          # PyInstaller-Spec → "JobTracker Agent.app"
    build_dmg.sh         # baut App + verpackt in ein .dmg (hdiutil)
```

## Lokal starten (Entwicklung, ohne Packaging)

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

## Installer bauen (.app + .dmg)

```bash
cd agent
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_dmg.sh 0.1.0
```

Ergebnis: `agent/packaging/dist/JobTracker-Agent-0.1.0.dmg` (App +
Applications-Symlink zum Draufziehen). Live verifiziert: Doppelklick auf die
`.app` registriert sie beim ersten Start selbst als `launchd`-LaunchAgent
(`~/Library/LaunchAgents/com.jobtracker.agent.plist`, `RunAtLoad`+
`KeepAlive`), die eigentliche Instanz läuft danach dauerhaft im Hintergrund
mit Menüleisten-Icon — kein zweiter Doppelklick, kein offenes Terminal nötig.

## Backend-Integration

Das Docker-Backend spricht den Agenten über `AGENT_URL`
(Default `http://host.docker.internal:9996`) + einen in den Einstellungen
(„Agent“-Tab) hinterlegten Bearer-Token an (`backend/app/agent_client.py`).
Der Token wird beim ersten Start des Agenten einmalig angezeigt (Menüleiste →
„Token kopieren“) und muss einmalig in die Einstellungen eingefügt werden.

## Status

Grundgerüst, Packaging und Backend-Integration sind fertig und getestet.
Offen: die drei alten `*_bridge.py`-Skripte am Repo-Root laufen aktuell noch
parallel (als eigene `launchd`-Jobs `com.jobtracker.files-bridge`,
`com.jobtracker.notesbridge`, `com.jobtracker.calls-bridge`) und werden erst
entfernt, nachdem der neue Agent im Alltag produktiv verifiziert wurde.
