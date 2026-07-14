# PyInstaller spec — builds the Linux "Rapport Agent" onedir bundle.
#
# Must be run ON Linux (PyInstaller does not cross-compile) with
# requirements-packaging-linux.txt installed:
#   pyinstaller agent/packaging/agent-linux.spec --distpath agent/packaging/dist --workpath agent/packaging/build
#
# tray.py is the entry point — self-registers via a systemd user service on
# first launch (systemd_service.py), then shows the pystray tray icon (no
# rumps on Linux, see tray.py's OS branch — pystray picks an AppIndicator/GTK
# or Xorg backend at runtime depending on the desktop environment).
# console=False means no terminal window; tray.py's own logging goes to
# app_data_dir()/logs instead.
#
# Hardware-verified (see docs/ARCHITECTURE.md's portability section): build
# succeeds, first-launch self-registration writes a working systemd user
# unit, and the packaged binary's server starts and serves /health. Also
# caught and fixed a real bug this way — on a machine with no X11 display,
# pystray's backend selection raises `Xlib.error.DisplayNameError` *during
# `import pystray`*, not ImportError, which used to crash the whole agent
# instead of falling back to headless mode (see run_tray_app() in tray.py).
#
# The systemd registration itself was re-verified against a genuine systemd
# instance (a real Ubuntu VM, not just a Docker container with no init
# system) — `systemctl --user is-enabled` reports `enabled`, the unit
# reaches `active (running)`, and killing the process gets it auto-restarted
# by `Restart=always` within seconds. Docker alone can't prove this since it
# has no systemd/session-bus to register against.
#
# Still environment-dependent, not something this spec can pin at build
# time: pystray's backend choice (appindicator vs. xorg vs. gtk) depends on
# what's installed on the target desktop environment — see agent/README.md's
# Linux system-package notes.
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
        "agent.providers.linux.files", "agent.providers.linux.notes", "agent.providers.linux.calls",
        "pystray._appindicator", "pystray._gtk", "pystray._xorg",
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
    name="rapport-agent",
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
    name="rapport-agent",
)
