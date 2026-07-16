"""Version this installer was built for — determines which image tags
(ghcr.io/egulinsky/rapport-{backend,frontend}:<version>) get pulled.
Overwritten by the packaging build scripts (mirroring agent/packaging/'s
`[version]` CLI arg) right before PyInstaller bundles this file; the
placeholder below is only ever seen in an unpackaged dev checkout, where
compose_writer.py falls back to the `:latest` tag instead.
"""
INSTALLER_VERSION = "0.0.0-dev"
