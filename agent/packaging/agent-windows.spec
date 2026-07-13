# PyInstaller spec — builds the Windows "Rapport Agent" onedir bundle.
#
# Must be run ON Windows (PyInstaller does not cross-compile) with
# requirements-packaging-windows.txt installed:
#   pyinstaller agent/packaging/agent-windows.spec --distpath agent/packaging/dist --workpath agent/packaging/build
#
# tray.py is the entry point — self-registers via Task Scheduler on first
# launch (task_scheduler.py), then shows the pystray tray icon (no rumps on
# Windows, see tray.py's OS branch). console=False means no terminal window;
# tray.py's own logging goes to app_data_dir()/logs instead.
#
# NOT YET HARDWARE-VERIFIED (see docs/ARCHITECTURE.md's portability section):
# tkinter's Tcl/Tk data files are a known PyInstaller footgun on Windows — if
# WindowsFilesProvider's native dialogs fail to open in the built .exe (but
# work when run from source), add `--collect-all tkinter` to the pyinstaller
# invocation or an explicit `datas=[...]` entry here.
import os

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
AGENT_DIR = os.path.join(REPO_ROOT, "agent")

block_cipher = None

a = Analysis(
    [os.path.join(AGENT_DIR, "tray.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[],
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
