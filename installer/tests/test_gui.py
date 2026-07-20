"""L1 — gui.py: the Windows-only graphical wizard. _QueueWriter is tested
as plain logic (no Tk needed); _bootstrap() is tested end-to-end against a
real (but headless-safe) InstallerWindow with every collaborator mocked at
the installer.gui module level, mirroring test_main.py's approach for the
console flow this module parallels."""
import queue
from unittest.mock import MagicMock, patch

import pytest

tk = pytest.importorskip("tkinter", reason="requires a Tk-enabled Python (not available on every dev machine)")

from installer import gui


class TestQueueWriter:
    def test_positiv_vollstaendige_zeile_wird_sofort_verschickt(self):
        q: "queue.Queue" = queue.Queue()
        writer = gui._QueueWriter(q)

        writer.write("hello world\n")

        assert q.get_nowait() == ("log", "hello world")
        assert q.empty()

    def test_positiv_teilzeilen_werden_gepuffert_bis_zeilenumbruch(self):
        q: "queue.Queue" = queue.Queue()
        writer = gui._QueueWriter(q)

        writer.write("hel")
        writer.write("lo\n")

        assert q.get_nowait() == ("log", "hello")

    def test_positiv_mehrere_zeilen_in_einem_write_aufruf(self):
        q: "queue.Queue" = queue.Queue()
        writer = gui._QueueWriter(q)

        writer.write("line1\nline2\n")

        assert q.get_nowait() == ("log", "line1")
        assert q.get_nowait() == ("log", "line2")

    def test_negativ_leere_zeilen_werden_nicht_verschickt(self):
        q: "queue.Queue" = queue.Queue()
        writer = gui._QueueWriter(q)

        writer.write("\n\n")

        assert q.empty()


@pytest.fixture
def window():
    try:
        win = gui.InstallerWindow.__new__(gui.InstallerWindow)
    except Exception as exc:  # pragma: no cover - headless CI without a display
        pytest.skip(f"no display available for Tk: {exc}")
    win.root = tk.Tk()
    win._queue = queue.Queue()
    win._build_widgets()
    yield win
    win.root.destroy()


def _mocks(**overrides):
    defaults = dict(
        docker_daemon_running=True,
        docker_cli_available=True,
        install_docker=True,
        docker_cmd_prefix=["docker"],
        compose_path="/fake/docker-compose.yml",
        pull_returncode=0,
        up_returncode=0,
        wait_for_healthy=True,
        open_app=True,
    )
    defaults.update(overrides)
    return defaults


def _run_bootstrap(win, m):
    subprocess_results = [
        MagicMock(returncode=m["pull_returncode"]),
        MagicMock(returncode=m["up_returncode"]),
    ]
    with patch.object(gui, "docker_daemon_running", return_value=m["docker_daemon_running"]), \
         patch.object(gui, "docker_cli_available", return_value=m["docker_cli_available"]), \
         patch.object(gui, "install_docker", return_value=m["install_docker"]), \
         patch.object(gui, "docker_cmd_prefix", return_value=m["docker_cmd_prefix"]), \
         patch.object(gui, "write_compose_file", return_value=m["compose_path"]), \
         patch("subprocess.run", side_effect=subprocess_results) as mock_run, \
         patch.object(gui, "wait_for_healthy", return_value=m["wait_for_healthy"]), \
         patch.object(gui, "open_app", return_value=m["open_app"]) as mock_open_app:
        result = gui.InstallerWindow._bootstrap(win)
    return result, mock_run, mock_open_app


class TestBootstrapHappyPath:
    def test_positiv_docker_bereits_aktiv_alles_erfolgreich(self, window):
        result, mock_run, mock_open_app = _run_bootstrap(window, _mocks())

        assert result is True
        mock_open_app.assert_called_once()
        assert mock_run.call_count == 2


class TestBootstrapDockerInstall:
    def test_positiv_docker_fehlt_aber_installation_gelingt(self, window):
        result, _, mock_open_app = _run_bootstrap(window, _mocks(docker_daemon_running=False, docker_cli_available=False))

        assert result is True
        mock_open_app.assert_called_once()

    def test_negativ_docker_installation_schlaegt_fehl_bricht_sofort_ab(self, window):
        result, mock_run, mock_open_app = _run_bootstrap(window, _mocks(docker_daemon_running=False, install_docker=False))

        assert result is False
        mock_run.assert_not_called()
        mock_open_app.assert_not_called()


class TestBootstrapFailureModes:
    def test_negativ_pull_fehlschlag_bricht_vor_up_ab(self, window):
        result, mock_run, mock_open_app = _run_bootstrap(window, _mocks(pull_returncode=1))

        assert result is False
        assert mock_run.call_count == 1
        mock_open_app.assert_not_called()

    def test_negativ_up_fehlschlag_bricht_vor_health_poll_ab(self, window):
        result, mock_run, mock_open_app = _run_bootstrap(window, _mocks(up_returncode=1))

        assert result is False
        assert mock_run.call_count == 2
        mock_open_app.assert_not_called()

    def test_negativ_health_poll_timeout_bricht_vor_browser_ab(self, window):
        result, _, mock_open_app = _run_bootstrap(window, _mocks(wait_for_healthy=False))

        assert result is False
        mock_open_app.assert_not_called()


class TestOnFinished:
    def test_positiv_erfolg_aktiviert_open_button(self, window):
        window._on_finished(True)

        assert str(window.open_button["state"]) == "normal"
        assert str(window.retry_button["state"]) == "disabled"

    def test_negativ_fehlschlag_aktiviert_retry_button(self, window):
        window._on_finished(False)

        assert str(window.retry_button["state"]) == "normal"
        assert str(window.open_button["state"]) == "disabled"


class TestDrainQueue:
    def test_positiv_log_eintraege_landen_im_textfeld(self, window):
        window._queue.put(("log", "hello from worker"))

        # _drain_queue reschedules itself via root.after() -- harmless here
        # since the fixture destroys the window right after the test.
        window._drain_queue()

        content = window.log_text.get("1.0", "end")
        assert "hello from worker" in content

    def test_positiv_status_update_setzt_status_var(self, window):
        window._queue.put(("status", "Doing the thing…"))

        window._drain_queue()

        assert window.status_var.get() == "Doing the thing…"
