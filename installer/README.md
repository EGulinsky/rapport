# Rapport Installer

A one-shot bootstrap for the backend+frontend Docker stack, distinct from
`agent/` (a persistent background service): download, run once, and
rapport is running locally with no manual Docker install or terminal use.
Unlike the agent, it doesn't self-register or keep running — Docker
Desktop's own "start at login" plus `restart: unless-stopped` in the
bundled compose file keep the app running across reboots once the
containers are up once.

**Two independent implementations, one per platform family:**
- **macOS/Linux** — a small Python package (`main.py` and friends below),
  packaged with PyInstaller into a `.app`/`.dmg` (macOS) or `.tar.gz`
  (Linux).
- **Windows** — a real Windows Installer package built with the
  [WiX Toolset](https://wixtoolset.org/) (`packaging/windows-wix/`): a
  single MSI (`Rapport-Setup-<version>.msi`), no Python and no extra
  `.exe` wrapper. See "Windows: WiX installer" below.

```
installer/
  main.py                # macOS/Linux bootstrap: check Docker -> install if missing ->
                          # write compose file -> pull/up -> health poll -> open browser
  docker_check.py        # docker CLI + daemon detection, the sudo-fallback command prefix
  docker_install/
    macos.py              # Docker Desktop, MDM-style silent install (mount .dmg, run install --accept-license)
    linux.py                # Docker Engine via the get.docker.com convenience script
                             # (no windows.py -- Windows installs Docker from start-rapport.bat instead, see below)
  compose_template.yml    # backend+frontend only (no Seq), __VERSION__ resolved at build/run time
  compose_writer.py        # resolves __VERSION__ and writes the file to app_data_dir() (macOS/Linux only)
  health.py                 # polls /health until ready (same shape as ci.yml's deploy-job health poll)
  browser.py                 # opens http://localhost:3000 once healthy
  version.py                  # INSTALLER_VERSION -- stamped by the macOS/Linux packaging build scripts,
                               # determines which ghcr.io/egulinsky/rapport-{backend,frontend} tag gets pulled
  packaging/
    installer.spec / build_dmg.sh              # macOS: PyInstaller spec -> "Rapport Installer.app" + .dmg
    installer-linux.spec / build_linux.sh       # Linux: PyInstaller spec + build script
    windows-wix/                                # Windows: a single WiX MSI (see below)
```

## Flow (macOS/Linux)

1. Check whether Docker is already installed and the daemon is reachable
   (`docker info`).
2. If not: download and silently install Docker for the current OS —
   Docker Desktop's documented MDM-style silent-install path on macOS, the
   official `get.docker.com` convenience script on Linux. Still triggers
   the OS's own admin/password prompt once (unavoidable for installing
   privileged virtualization software) but no further interactive
   setup-wizard clicks. If it can't get Docker running, it prints a clear
   message and exits rather than hanging.
3. Write the resolved compose file (this installer's own stamped version,
   substituted into `compose_template.yml`) to a per-OS app-data
   directory.
4. `docker compose pull && up -d` — pulls the prebuilt
   `ghcr.io/egulinsky/rapport-{backend,frontend}` images (published by
   `.github/workflows/release.yml`'s `publish-images` job) instead of
   building Chromium locally.
5. Poll `/health` until ready, then open `http://localhost:3000` in the
   default browser.

Deliberately **not** a persistent service — no launchd/systemd
self-registration like the agent has. Once the containers are up, Docker's
own restart policy plus Docker Desktop's own login-item setting handle
everything else.

## Windows: WiX installer

Windows gets a real Windows Installer package instead of a Python console
app — `packaging/windows-wix/RapportPackage/`, a single MSI (WiX v5,
`WixToolset.Sdk`), deliberately **not** wrapped in an extra `.exe`
bootstrapper:

- **`Product.wxs`** — installs `docker-compose.yml` (this build's version
  already substituted for `__VERSION__`, generated at build time — never
  checked in) and `start-rapport.bat` into `Program Files\Rapport`, plus a
  "Start rapport" Start Menu shortcut. Uses `WixUI_InstallDir` for the
  standard Windows Installer wizard (license → install-directory picker →
  progress → finish) — the MSI is the whole installer here, so it needs
  its own UI. Fixed `UpgradeCode` + `MajorUpgrade` means installing a newer
  version's `Rapport-Setup.msi` replaces the old one automatically (genuine
  version-awareness the old NSIS installer never had). Windows Installer
  itself provides the Add/Remove Programs entry, the UAC elevation prompt,
  and the uninstaller — nothing to author by hand for any of that.
- **`start-rapport.bat`** — the actual bootstrap logic, run manually from
  the "Start rapport" Start Menu shortcut after installing (there's no
  Burn bootstrapper here to auto-launch it right after Setup finishes, so
  this is a deliberate one extra click compared to macOS/Linux): check for
  Docker, download+silently install Docker Desktop if missing (`curl` +
  the documented `install --quiet --accept-license` flags, handling the
  3010 "restart required" exit code distinctly), wait for the daemon,
  `docker compose pull && up -d`, poll `/health` via `curl`, then open the
  browser — the same step sequence as the macOS/Linux Python flow, just as
  a plain batch script. Can be re-run any time from the same shortcut
  (useful if Docker needed a restart, or containers didn't come back up).
  On any failure the window stays open (`pause`) rather than flashing
  closed, so the error is actually readable.
- **`build_windows_wix.ps1`** — resolves `docker-compose.yml` and
  generates `License.rtf` (from the repo's real `LICENSE`, so it can never
  drift out of sync) at build time, then `dotnet build`s the MSI project.
  WiX itself is fetched via a NuGet `PackageReference` in the `.wixproj`
  file — no separate CLI tool install needed, unlike NSIS's `choco install
  nsis` step.

Deliberately **no** Docker-prerequisite handling at the MSI level: Docker
Desktop's own installer binary is a vendor-hosted, frequently-updated file,
awkward to model as MSI-native install logic. Handling it as plain
batch-script logic in `start-rapport.bat` keeps the MSI itself simple (just
files + a shortcut) and matches how the macOS/Linux Python flow does the
same check-and-install.

## Run locally (macOS/Linux development, no packaging)

```bash
cd installer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m installer.main   # from the repo root, not from installer/
```

An unpackaged dev checkout has no stamped version — `compose_writer.py`
falls back to pulling the `:latest` image tags. (Windows has no Python
flow to run locally this way — see "Windows: WiX installer" above.)

## Tests (macOS/Linux Python package)

```bash
cd installer
python3 -m venv .venv_test
.venv_test/bin/pip install pytest -r requirements.txt
.venv_test/bin/python3 -m pytest -v
```

All Docker/network interaction is mocked — no real installs or containers
touched by the test suite. The Windows WiX installer has no equivalent
Python test suite; its `start-rapport.bat` logic can only meaningfully be
exercised on a real Windows machine.

## Build the installer

**macOS** (`.app` + `.dmg`):
```bash
cd installer
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_dmg.sh 4.3.6
```

**Windows** (run on Windows — WiX doesn't cross-compile any more reliably
than PyInstaller does; requires the .NET SDK on `PATH`, `dotnet --version`
to check):
```powershell
cd installer/packaging/windows-wix
./build_windows_wix.ps1 4.3.6
```

**Linux** (run on Linux — PyInstaller doesn't cross-compile):
```bash
cd installer
python3 -m venv .venv_build
.venv_build/bin/pip install -r packaging/requirements-packaging-linux.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_linux.sh 4.3.6
```

The macOS/Linux build scripts stamp the given version into `installer/version.py`
right before invoking PyInstaller, then reverts it afterward (even on
failure, via a shell trap) — the working tree is never left dirty by a
local build.

Result: `installer/packaging/dist/Rapport-Installer-4.3.6.dmg` (macOS),
`installer/packaging/windows-wix/dist/Rapport-Setup-4.3.6.msi` (Windows — a
real Windows Installer package: license page, install-directory picker,
progress, finish, Start Menu shortcut, version-aware upgrades, and an
uninstaller registered in Add/Remove Programs, all provided natively by
WiX/MSI rather than hand-rolled), or `rapport-installer-4.3.6-linux.tar.gz`
(Linux). macOS/Linux build mechanics (PyInstaller onedir → .dmg/.tar.gz)
verified locally on this machine — see `docs/ARCHITECTURE.md` for the full
picture.

The Windows WiX build could only be partially verified on this Mac: WiX v5
is a cross-platform .NET tool and `dotnet build` does run here, catching
real XML-authoring mistakes (it caught and helped fix several during
development) — but the toolset explicitly warns "only supports Windows...
all behavior after this point is undefined" and a minimal, textbook-correct
`<Directory Name="...">` element fails to compile at all under this
non-Windows host (confirmed via an isolated reproduction), so the actual
MSI compilation can only be proven by `release.yml`'s `windows-latest`
runner. The Docker-install path in `start-rapport.bat` similarly needs a
real run on a machine with no prior Docker install to fully verify, the
same "hardware-verified" bar `agent/README.md` documents for its own
portability work — CI can only prove the packaging succeeds, not that the
silent-install path works on a genuinely clean machine (GH-hosted runners
already have Docker pre-installed).

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
