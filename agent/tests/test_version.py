"""L0 — agent/version.py: reads the version PyInstaller bakes into the
frozen binary as a bundled resource file (see packaging/agent*.spec), not a
source-tracked constant. A dev run (`python -m agent.main`) is never frozen
and has no such resource."""
import sys

from agent import version as version_module


class TestReadBundledVersion:
    def test_negativ_nicht_frozen_liefert_dev_fallback(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)

        assert version_module._read_bundled_version() == "dev"

    def test_positiv_frozen_liest_meipass_version_datei(self, tmp_path, monkeypatch):
        (tmp_path / "VERSION").write_text("4.6.29")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "Rapport Agent"), raising=False)

        assert version_module._read_bundled_version() == "4.6.29"

    def test_positiv_frozen_faellt_auf_macos_resources_ordner_zurueck(self, tmp_path, monkeypatch):
        # macOS .app BUNDLE: PyInstaller 6.x moves data files out of
        # Contents/MacOS (== sys._MEIPASS) into Contents/Resources — a
        # plain _MEIPASS lookup finds nothing there (hardware-verified
        # against a real built .app).
        meipass = tmp_path / "Contents" / "MacOS"
        meipass.mkdir(parents=True)
        resources = tmp_path / "Contents" / "Resources"
        resources.mkdir(parents=True)
        (resources / "VERSION").write_text("4.6.29")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
        monkeypatch.setattr(sys, "executable", str(meipass / "Rapport Agent"), raising=False)

        assert version_module._read_bundled_version() == "4.6.29"

    def test_negativ_frozen_ohne_version_datei_liefert_dev_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "Rapport Agent"), raising=False)

        assert version_module._read_bundled_version() == "dev"

    def test_negativ_frozen_leere_version_datei_liefert_dev_fallback(self, tmp_path, monkeypatch):
        (tmp_path / "VERSION").write_text("   ")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "Rapport Agent"), raising=False)

        assert version_module._read_bundled_version() == "dev"
