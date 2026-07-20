# Rapport Installer

A one-shot bootstrap app, distinct from `agent/` (a persistent background
service): download, run once, and rapport is running locally with no
manual Docker install or terminal use. Unlike the agent, it doesn't
self-register or keep running — Docker Desktop's own "start at login" plus
`restart: unless-stopped` in the bundled compose file keep the app running
across reboots once the containers are up once.

```
installer/
  main.py                # orchestrates the flow below; console progress on macOS/Linux,
                          # dispatches to gui.py on Windows (see "Windows: graphical wizard" below)
  gui.py                  # Windows-only Tkinter wizard: status line, progress bar, log box,
                          # runs the same flow as main.py in a background thread
  docker_check.py        # docker CLI + daemon detection, the sudo-fallback command prefix
  docker_install/
    macos.py              # Docker Desktop, MDM-style silent install (mount .dmg, run install --accept-license)
    windows.py             # Docker Desktop, install --quiet --accept-license
    linux.py                # Docker Engine via the get.docker.com convenience script
  compose_template.yml    # backend+frontend only (no Seq), __VERSION__ resolved at runtime
  compose_writer.py        # resolves __VERSION__ and writes the file to app_data_dir()
  health.py                 # polls /health until ready (same shape as ci.yml's deploy-job health poll)
  browser.py                 # opens http://localhost:3000 once healthy
  version.py                  # INSTALLER_VERSION — stamped by the packaging build scripts, determines
                               # which ghcr.io/egulinsky/rapport-{backend,frontend} tag gets pulled
  packaging/
    installer.spec / build_dmg.sh                                      # macOS: PyInstaller spec → "Rapport Installer.app" + .dmg
    installer-windows.spec / installer-windows.nsi / build_windows.ps1  # Windows: PyInstaller spec + NSIS setup-wizard script + build script
    installer-linux.spec / build_linux.sh                                # Linux: PyInstaller spec + build script
```

## Flow

1. Check whether Docker is already installed and the daemon is reachable
   (`docker info`).
2. If not: download and silently install Docker for the current OS —
   Docker Desktop's documented MDM-style silent-install path on macOS/
   Windows, the official `get.docker.com` convenience script on Linux.
   Still triggers the OS's own admin/password prompt once (unavoidable for
   installing privileged virtualization software) but no further
   interactive setup-wizard clicks. If it can't get Docker running (a
   failed install, or Windows needing a restart to finish enabling WSL2),
   it prints a clear message and exits rather than hanging.
3. Write the resolved compose file (this installer's own stamped version,
   substituted into `compose_template.yml`) to a per-OS app-data
   directory.
4. `docker compose pull && up -d` — pulls the prebuilt
   `ghcr.io/egulinsky/rapport-{backend,frontend}` images (published by
   `.github/workflows/release.yml`'s `publish-images` job) instead of
   building Chromium locally.
5. Poll `/health` until ready, then open `http://localhost:3000` in the
   default browser.

Deliberately **not** a persistent service — no launchd/systemd/registry
self-registration like the agent has. Once the containers are up, Docker's
own restart policy plus Docker Desktop's own login-item setting handle
everything else.

## Windows: graphical wizard

On Windows the packaged executable runs `gui.py` instead of `main.py`'s
console flow (dispatched from `main.py`'s `__main__` block based on
`platform.system()` — `main()` itself is untouched, so it's still what
runs on macOS/Linux and what `tests/test_main.py` exercises). `gui.py` is
a self-contained Tkinter window — not a refactor of `main()`, a parallel
implementation of the same step sequence — showing a live status line, a
progress bar, and a scrollable log (existing `print()` output from
`docker_install/windows.py` is captured via a small `sys.stdout`
redirection, `_QueueWriter`, so that module didn't need to change). The
bootstrap work runs on a background thread and reports back to the GUI
thread through a `queue.Queue` drained on a `root.after()` timer, since
Tkinter itself isn't thread-safe. On failure the window stays open with a
Retry button rather than a console that might flash-close; on success, an
"Open rapport" button re-opens the browser. `packaging/installer-windows.spec`
builds with `console=False` for this reason — macOS/Linux specs are
unaffected and keep `console=True`.

## Run locally (development, no packaging)

```bash
cd installer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m installer.main   # from the repo root, not from installer/
```

An unpackaged dev checkout has no stamped version — `compose_writer.py`
falls back to pulling the `:latest` image tags.

## Tests

```bash
cd installer
python3 -m venv .venv_test
.venv_test/bin/pip install pytest -r requirements.txt
.venv_test/bin/python3 -m pytest -v
```

All Docker/network interaction is mocked — no real installs or containers
touched by the test suite. `tests/test_gui.py` needs a Tk-enabled Python
(the stock python.org builds Windows CI uses have this; some Homebrew
Python formulas on macOS don't and need the sibling `python-tk` formula,
e.g. `brew install python-tk@3.14`) — it skips itself via
`pytest.importorskip` rather than failing if Tk isn't available.

## Build the installer

**macOS** (`.app` + `.dmg`):
```bash
cd installer
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_dmg.sh 4.3.6
```

**Windows** (run on Windows — PyInstaller doesn't cross-compile; also
requires `makensis` on `PATH` — `choco install nsis`, or download from
https://nsis.sourceforge.io/Download):
```powershell
cd installer
python -m venv .venv_build
.venv_build\Scripts\pip install -r packaging\requirements-packaging-windows.txt
$env:PATH = "$PWD\.venv_build\Scripts;$env:PATH"
packaging\build_windows.ps1 4.3.6
```

**Linux** (run on Linux — PyInstaller doesn't cross-compile):
```bash
cd installer
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging-linux.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_linux.sh 4.3.6
```

Each build script stamps the given version into `installer/version.py`
right before invoking PyInstaller, then reverts it afterward (even on
failure, via a shell trap) — the working tree is never left dirty by a
local build.

Result: `installer/packaging/dist/Rapport-Installer-4.3.6.dmg` (macOS),
`Rapport-Setup-4.3.6.exe` (Windows — a real NSIS setup wizard: license page,
install-directory picker, progress, Start Menu shortcut, and an uninstaller
registered in Add/Remove Programs, not just an unzip-and-run bundle), or
`rapport-installer-4.3.6-linux.tar.gz` (Linux). Build mechanics (PyInstaller
onedir → .dmg/.tar.gz, `installer-windows.nsi` → NSIS setup wizard) verified
locally on this machine — see `docs/ARCHITECTURE.md` for the full picture.
The `.nsi` script itself was verified by compiling it with Linux `makensis`
against a stand-in bundle directory (this Mac can't run the Windows
PyInstaller step); the full Windows pipeline (PyInstaller onedir →
`makensis`) is only exercised for real by `release.yml`'s `windows-latest`
runner. The Docker-install path itself
(steps 1–2 above) needs a real run on a machine with no prior Docker install
to fully verify, the same "hardware-verified" bar `agent/README.md`
documents for its own portability work — CI can only prove the packaging
succeeds, not that the silent-install path works on a genuinely clean
machine (GH-hosted runners already have Docker pre-installed).

## Image publishing

Backend/frontend images are built and pushed to GHCR by
`.github/workflows/release.yml`'s `publish-images` job whenever a GitHub
release is published — `ghcr.io/egulinsky/rapport-backend:<version>` and
`...-frontend:<version>` (plus `:latest`), `linux/amd64` only for now
(multi-arch would need slow QEMU-emulated builds for the Chromium-laden
backend image on GH's x86-only free runners; Apple Silicon Docker Desktop
still runs amd64 images fine via its built-in Rosetta emulation). The
workflow also sets both packages to public visibility — required for an
end user's `docker pull` to succeed without any GHCR credentials.
