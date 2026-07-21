# PyInstaller spec — builds the Windows "Rapport Agent" onedir bundle.
#
# Must be run ON Windows (PyInstaller does not cross-compile) with
# requirements-packaging-windows.txt installed:
#   pyinstaller agent/packaging/agent-windows.spec --distpath agent/packaging/dist --workpath agent/packaging/build
#
# tray.py is the entry point — self-registers via the HKCU Run registry key
# on first launch (registry_run.py; Task Scheduler was tried first but
# schtasks /create requires an elevated token even for a task that only runs
# at the current user's own logon — confirmed on real hardware), then shows
# the pystray tray icon (no rumps on Windows, see tray.py's OS branch).
# console=False means no terminal window; tray.py's own logging goes to
# app_data_dir()/logs instead.
#
# Hardware-verified on real Windows 11 (see docs/ARCHITECTURE.md's
# portability section): build succeeds, first-launch self-registration
# works under a normal (non-elevated) user, and the packaged .exe's
# tkinter/Tcl-Tk bundling is NOT broken — WindowsFilesProvider's native
# folder-picker dialog opens correctly (real title, real Documents contents,
# folder navigation all work) when triggered via the actual /files/pick-folder
# endpoint. The PyInstaller footgun this comment used to warn about
# (`--collect-all tkinter` needed if the dialog fails to open) does not
# apply here — no extra datas= entry was needed.
#
# One piece intentionally left unconfirmed: clicking the dialog's own OK/
# Cancel buttons to complete the round-trip couldn't be driven through
# screen-automation tooling in this environment (even the native OS window-
# close button didn't respond to synthetic clicks, while the file list and
# text entry did) — isolated to be a VM input-injection limitation, not an
# app bug, by reproducing the identical symptom with a plain unfrozen
# main-thread script with no FastAPI/threadpool/PyInstaller involved at all.
import os

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
AGENT_DIR = os.path.join(REPO_ROOT, "agent")

# Passed in by build_windows.ps1 (itself given the version as a CLI arg —
# either a release git tag in CI or typed by hand for a local rebuild).
# Stamped into a bundled resource file rather than a source file so there's
# exactly one place a human sets the version (see agent/version.py).
AGENT_VERSION = os.environ.get("AGENT_VERSION", "dev")
_VERSION_STAMP = os.path.join(SPECPATH, "VERSION")
with open(_VERSION_STAMP, "w") as _f:
    _f.write(AGENT_VERSION)

block_cipher = None

a = Analysis(
    [os.path.join(AGENT_DIR, "tray.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[(_VERSION_STAMP, ".")],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "agent.providers.windows.files", "agent.providers.windows.notes", "agent.providers.windows.calls",
        "pystray._win32",
        "PIL.Image", "PIL.ImageDraw",
        "tkinter", "tkinter.filedialog",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Rapport Agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Rapport Agent",
)
