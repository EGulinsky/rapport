"""L0 — compose_writer.py: resolves __VERSION__ in the bundled compose
template to the installer's stamped build version (or :latest in an
unstamped dev checkout), and writes the result to app_data_dir()."""
from unittest.mock import patch

from installer import compose_writer


class TestResolvedComposeText:
    def test_positiv_ersetzt_version_platzhalter(self):
        text = compose_writer.resolved_compose_text(version="4.3.6")
        assert "ghcr.io/egulinsky/rapport-backend:4.3.6" in text
        assert "ghcr.io/egulinsky/rapport-frontend:4.3.6" in text
        assert "__VERSION__" not in text

    def test_positiv_dev_platzhalter_faellt_auf_latest_zurueck(self):
        text = compose_writer.resolved_compose_text(version="0.0.0-dev")
        assert "ghcr.io/egulinsky/rapport-backend:latest" in text
        assert "0.0.0-dev" not in text


class TestWriteComposeFile:
    def test_positiv_schreibt_aufgeloeste_datei_in_app_data_dir(self, tmp_path):
        with patch.object(compose_writer, "app_data_dir", return_value=tmp_path):
            path = compose_writer.write_compose_file()

        assert path == tmp_path / "docker-compose.yml"
        assert path.exists()
        assert "__VERSION__" not in path.read_text()
