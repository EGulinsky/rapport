# PyInstaller spec — builds "Rapport Agent.app".
#
# Run from the repo root:
#   pyinstaller agent/packaging/agent.spec --distpath agent/packaging/dist --workpath agent/packaging/build
#
# LSUIElement=True means no Dock icon — the app only shows up as a menu bar
# icon (see menubar.py), matching the "installer + menu-bar-app in one"
# design (first launch self-registers as a LaunchAgent, see launchd.py).
import os

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
AGENT_DIR = os.path.join(REPO_ROOT, "agent")

block_cipher = None

a = Analysis(
    [os.path.join(AGENT_DIR, "menubar.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "agent.providers.mac.files", "agent.providers.mac.notes", "agent.providers.mac.calls",
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

app = BUNDLE(
    coll,
    name="Rapport Agent.app",
    icon=None,
    bundle_identifier="com.rapport.agent",
    info_plist={
        "LSUIElement": True,
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleVersion": "0.2.0",
        "NSHumanReadableCopyright": "",
    },
)
