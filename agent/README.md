# Rapport Agent

Replaces `files_bridge.py`, `notes_bridge.py`, and `calls_bridge.py`: a single
background process instead of three, with Bearer-token auth instead of open
ports, and an OS-adapter boundary for the planned Windows port.

```
agent/
  main.py            # FastAPI app, create_app() factory, /health
  menubar.py          # macOS menu-bar entry point (rumps) + launchd self-registration
  launchd.py           # generate/register/remove the LaunchAgent plist
  auth.py             # Bearer-token dependency
  config.py           # token generation/persistence, per-OS app-data dir
  text_extract.py      # PDF/DOCX/TXT text extraction (OS-neutral)
  providers/
    base.py           # abstract interfaces: FilesProvider, NotesProvider, CallsProvider
    factory.py         # picks the provider set based on platform.system()
    mac/               # current implementation (ported 1:1 from the old bridges)
  routers/
    files.py           # /files, /files/browse, /files/file, /files/open, /files/pick-*
    backup.py          # /backup/backups, /backup/backup-write, /backup/backup-read
    notes.py           # /notes
    calls.py           # /calls
  packaging/
    agent.spec          # PyInstaller spec → "Rapport Agent.app"
    build_dmg.sh         # builds the app + packages it into a .dmg (hdiutil)
```

## Run locally (development, no packaging)

```bash
cd agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m agent.main   # from rapport/ (repo root), not from agent/
```

Runs on port 9996. The Bearer token is generated on first start and lives at
`~/Library/Application Support/RapportAgent/config.json` (macOS).

## Tests

```bash
cd agent
python3 -m venv .venv_test
.venv_test/bin/pip install -r requirements.txt pytest httpx
.venv_test/bin/python3 -m pytest -v
```

## Build the installer (.app + .dmg)

```bash
cd agent
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_dmg.sh 0.1.0
```

Result: `agent/packaging/dist/Rapport-Agent-0.1.0.dmg` (app + Applications
symlink to drag onto). Verified live: double-clicking the `.app` registers it
on first start as a `launchd` LaunchAgent
(`~/Library/LaunchAgents/com.rapport.agent.plist`, `RunAtLoad`+`KeepAlive`),
after which the actual instance runs permanently in the background with a
menu-bar icon — no second double-click, no open terminal needed.

## Backend integration

The Docker backend talks to the agent via `AGENT_URL`
(default `http://host.docker.internal:9996`) plus a Bearer token stored in
Settings (the "Agent" tab) (`backend/app/agent_client.py`). The token is shown
once on the agent's first start (menu bar → "Copy token") and needs to be
pasted into Settings once.

## Status

Scaffold, packaging, and backend integration are done and tested. Open: the
three old `*_bridge.py` scripts at the repo root currently still run in
parallel (as their own `launchd` jobs `com.rapport.files-bridge`,
`com.rapport.notesbridge`, `com.rapport.calls-bridge`) and will only be
removed once the new agent has been verified in daily production use.
