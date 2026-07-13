# Rapport Agent

Replaces `files_bridge.py`, `notes_bridge.py`, and `calls_bridge.py`: a single
background process instead of three, with Bearer-token auth instead of open
ports. Runs on macOS, Windows, and Linux — hardware-verified on all three
(see "Build the installer" below).

```
agent/
  main.py            # FastAPI app, create_app() factory, /health
  tray.py             # single cross-platform entry point: service self-registration,
                       # HTTP server thread, dispatch to the right tray/menu-bar UI
  menubar.py          # macOS menu-bar UI (rumps) — pure UI, tray.py owns the bootstrap
  service.py           # dispatches is_registered()/register()/unregister() by OS
  launchd.py           # macOS: generate/register/remove the LaunchAgent plist
  registry_run.py       # Windows: HKCU Run registry key (no elevation needed)
  systemd_service.py    # Linux: systemd user service (systemctl --user, no elevation needed)
  auth.py             # Bearer-token dependency
  config.py           # token generation/persistence, ui_language, per-OS app-data dir
  strings.py            # i18n table + t(key, ui_language) for menubar/notification text
  text_extract.py      # PDF/DOCX/TXT text extraction (OS-neutral)
  providers/
    base.py           # abstract interfaces: FilesProvider, NotesProvider, CallsProvider
    factory.py         # picks the provider set based on platform.system()
    mac/               # full implementation (ported 1:1 from the old bridges)
    windows/            # files via tkinter/os.startfile; notes/calls are platform_limited stubs
    linux/              # files via zenity/kdialog/tkinter + xdg-open; notes/calls are stubs
  routers/
    files.py           # /files, /files/browse, /files/file, /files/open, /files/pick-*
    backup.py          # /backup/backups, /backup/backup-write, /backup/backup-read
    notes.py           # /notes
    calls.py           # /calls
    config.py           # PATCH /agent-api/config {ui_language} — pushed by the backend on profile/language save
  packaging/
    agent.spec / build_dmg.sh              # macOS: PyInstaller spec → "Rapport Agent.app" + .dmg
    agent-windows.spec / build_windows.ps1  # Windows: PyInstaller spec + build script
    agent-linux.spec / build_linux.sh       # Linux: PyInstaller spec + build script
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

> Windows and Linux packaging (`packaging/agent-windows.spec`/`build_windows.ps1`
> and `packaging/agent-linux.spec`/`build_linux.sh`) is hardware-verified as of
> 2026-07-13 — build, first-launch self-registration, server startup, and
> `/health` were all walked end-to-end on real Windows 11 and on Linux. Two
> real bugs only showed up on that real hardware and are now fixed: Windows'
> service registration used to silently fail under a normal (non-elevated)
> user token (`schtasks /create` returns Access Denied even for a task that
> only runs at the current user's own logon — replaced with the HKCU `Run`
> key, see `registry_run.py`), and the packaged windowed Windows build used
> to crash its server thread silently because a `console=False` build has no
> usable `sys.stdout`/`sys.stderr` (fixed by redirecting stdio to a log file,
> see `tray.py`'s `_redirect_stdio_if_headless()`). On Linux, a machine with
> no X11 display used to crash the whole agent instead of falling back to
> headless mode (pystray's backend selection raises during `import pystray`
> itself on a missing display, not with `ImportError` — see `tray.py`'s
> `run_tray_app()`).
>
> Follow-up same night: drove the packaged Windows build's `tkinter` folder
> picker interactively (via the VM's own screen, triggering the real
> `/files/pick-folder` endpoint). The dialog opens correctly — real title,
> real Documents contents, folder navigation all work — so PyInstaller's
> Tcl/Tk-data-bundling footgun this file used to warn about does not apply;
> no `--collect-all tkinter` was needed. Completing the click-through (OK/
> Cancel) couldn't be driven through screen-automation tooling in this
> particular VM setup — isolated to be a synthetic-input-delivery limitation
> of the automation, not an app bug, by reproducing the identical
> unresponsive-button symptom with a bare unfrozen main-thread script that
> has no FastAPI/threadpool/PyInstaller involved at all (even the native OS
> window-close button failed to respond, while the file list and text entry
> both worked normally) — a real end user clicking with a real mouse isn't
> expected to hit this.

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
bundle — hardware-verified, see the note above.

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
