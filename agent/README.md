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
  config.py           # token generation/persistence, ui_language, per-OS app-data dir
  strings.py            # i18n table + t(key, ui_language) for menubar/notification text
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
    config.py           # PATCH /agent-api/config {ui_language} — pushed by the backend on profile/language save
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

**Linux only — non-pip system packages** (not installable via `pip`, needed
by `providers/linux/files.py`'s folder/file picker and `tray.py`'s clipboard
copy; both degrade gracefully if missing, but won't have a working file
picker / tray-menu clipboard action without at least one of these):
`zenity` or `kdialog` (folder/file picker, falls back to `tkinter` if
neither is present), `xclip` or `xsel` (clipboard).

> Note: the provider/service/tray split below is mid-port — Windows
> (`packaging/agent-windows.spec` + `build_windows.ps1`) and Linux
> (`packaging/agent-linux.spec` + `build_linux.sh`) now have PyInstaller
> specs and build scripts alongside macOS's `agent.spec` + `build_dmg.sh`,
> but **neither has been run or verified on real hardware yet** — both
> scripts must be executed on their target OS (PyInstaller doesn't
> cross-compile) and are unverified until that happens. Until then, both
> platforms effectively mean "run from source" per the section above.

## Tests

```bash
cd agent
python3 -m venv .venv_test
.venv_test/bin/pip install -r requirements.txt pytest httpx
.venv_test/bin/python3 -m pytest -v
```

## Build the installer

**macOS** (`.app` + `.dmg`):
```bash
cd agent
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_dmg.sh 0.1.0
```

**Windows** (run on Windows — PyInstaller doesn't cross-compile):
```powershell
cd agent
python -m venv .venv_build
.venv_build\Scripts\pip install -r packaging\requirements-packaging-windows.txt
$env:PATH = "$PWD\.venv_build\Scripts;$env:PATH"
packaging\build_windows.ps1 0.1.0
```

**Linux** (run on Linux — PyInstaller doesn't cross-compile):
```bash
cd agent
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging-linux.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_linux.sh 0.1.0
```

Windows/Linux results are a `.zip`/`.tar.gz` of the onedir PyInstaller
bundle — **not yet hardware-verified**, see the note above.

Result (macOS): `agent/packaging/dist/Rapport-Agent-0.1.0.dmg` (app +
Applications symlink to drag onto). Verified live: double-clicking the
`.app` registers it on first start as a `launchd` LaunchAgent
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

Scaffold, packaging, and backend integration are done and tested. The three
old `*_bridge.py` scripts have been retired — this agent is the only bridge
process now. The menu bar and its notifications follow the account's UI
language: the backend pushes `ui_language` to `PATCH /agent-api/config`
whenever the profile language changes (`config.py` persists it, `strings.py`
renders the menu text), and the agent process is restarted automatically so
the change takes effect without a manual relaunch.
