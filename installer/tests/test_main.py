"""L1 — main.py: the end-to-end bootstrap orchestration (Docker check ->
install if missing -> compose pull/up -> health poll -> open browser),
with every collaborator mocked at the installer.main module level (all
imported via `from X import Y`, so patches must target the local binding
in main.py's own namespace, not the original definition module)."""
from unittest.mock import MagicMock, patch

from installer import main as main_module


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


def _run_main(m):
    subprocess_results = [
        MagicMock(returncode=m["pull_returncode"]),
        MagicMock(returncode=m["up_returncode"]),
    ]
    with patch.object(main_module, "docker_daemon_running", return_value=m["docker_daemon_running"]), \
         patch.object(main_module, "docker_cli_available", return_value=m["docker_cli_available"]), \
         patch.object(main_module, "install_docker", return_value=m["install_docker"]), \
         patch.object(main_module, "docker_cmd_prefix", return_value=m["docker_cmd_prefix"]), \
         patch.object(main_module, "write_compose_file", return_value=m["compose_path"]), \
         patch("subprocess.run", side_effect=subprocess_results) as mock_run, \
         patch.object(main_module, "wait_for_healthy", return_value=m["wait_for_healthy"]), \
         patch.object(main_module, "open_app", return_value=m["open_app"]) as mock_open_app:
        result = main_module.main()
    return result, mock_run, mock_open_app


class TestMainHappyPath:
    def test_positiv_docker_bereits_aktiv_alles_erfolgreich(self):
        result, mock_run, mock_open_app = _run_main(_mocks())

        assert result == 0
        mock_open_app.assert_called_once()
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0].args[0] == ["docker", "compose", "-f", "/fake/docker-compose.yml", "pull"]
        assert mock_run.call_args_list[1].args[0] == ["docker", "compose", "-f", "/fake/docker-compose.yml", "up", "-d"]

    def test_positiv_verwendet_sudo_praefix_wenn_docker_cmd_prefix_es_liefert(self):
        result, mock_run, _ = _run_main(_mocks(docker_cmd_prefix=["sudo", "docker"]))

        assert result == 0
        assert mock_run.call_args_list[0].args[0][:2] == ["sudo", "docker"]


class TestMainDockerInstall:
    def test_positiv_docker_fehlt_aber_installation_gelingt(self):
        result, mock_run, mock_open_app = _run_main(_mocks(docker_daemon_running=False, docker_cli_available=False))

        assert result == 0
        mock_open_app.assert_called_once()

    def test_negativ_docker_installation_schlaegt_fehl_bricht_sofort_ab(self):
        result, mock_run, mock_open_app = _run_main(_mocks(docker_daemon_running=False, install_docker=False))

        assert result == 1
        mock_run.assert_not_called()
        mock_open_app.assert_not_called()


class TestMainFailureModes:
    def test_negativ_pull_fehlschlag_bricht_vor_up_ab(self):
        result, mock_run, mock_open_app = _run_main(_mocks(pull_returncode=1))

        assert result == 1
        assert mock_run.call_count == 1
        mock_open_app.assert_not_called()

    def test_negativ_up_fehlschlag_bricht_vor_health_poll_ab(self):
        result, mock_run, mock_open_app = _run_main(_mocks(up_returncode=1))

        assert result == 1
        assert mock_run.call_count == 2
        mock_open_app.assert_not_called()

    def test_negativ_health_poll_timeout_bricht_vor_browser_ab(self):
        result, mock_run, mock_open_app = _run_main(_mocks(wait_for_healthy=False))

        assert result == 1
        mock_open_app.assert_not_called()
