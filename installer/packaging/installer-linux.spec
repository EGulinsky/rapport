# PyInstaller spec — builds the Linux "rapport-installer" onedir bundle.
#
# Must be run ON Linux (PyInstaller does not cross-compile):
#   pyinstaller installer/packaging/installer-linux.spec --distpath installer/packaging/dist --workpath installer/packaging/build
#
# console=True — this is a one-shot bootstrap the user watches run (Docker
# check/install, image pull, health poll), not a background service, so a
# visible terminal with progress messages is the point.
import os

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
INSTALLER_DIR = os.path.join(REPO_ROOT, "installer")

block_cipher = None

a = Analysis(
    [os.path.join(INSTALLER_DIR, "main.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[
        (os.path.join(INSTALLER_DIR, "compose_template.yml"), "."),
    ],
    hiddenimports=[
        "installer.docker_install.linux",
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
    name="rapport-installer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="rapport-installer",
)
