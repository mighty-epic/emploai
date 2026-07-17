import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from app_backend.local_runtime_server import DesktopRuntimeConfig, DesktopRuntimeStatus
import desktop_runtime.backend as desktop_backend


_MUTABLE_RUNTIME_ENV_KEYS = (
    "ALLOWED_USER_IDS",
    "ANTHROPIC_API_KEY",
    "DEFAULT_WORKSPACE",
    "EMPLOAI_CLOUD_BACKEND_ENABLED",
    "EMPLOAI_CLOUD_TELEGRAM_BOT_COUNT",
    "EMPLOAI_HOME",
    "EMPLOAI_REMOTE_CONTROL_BASE_URL",
    "EMPLOAI_REMOTE_CONTROL_DESKTOP_ID",
    "EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN",
    "EMPLOAI_REMOTE_CONTROL_USER_ID",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "NVIDIA_API_KEY",
    "OPENAI_API_KEY",
    "PLANNER_MODEL",
    "TELEGRAM_BOT_TOKEN",
)


@pytest.fixture(autouse=True)
def isolate_runtime_env(monkeypatch):
    original = {key: os.environ.get(key) for key in _MUTABLE_RUNTIME_ENV_KEYS}
    monkeypatch.setenv("EMPLOAI_CLOUD_BACKEND_ENABLED", "1")
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _stub_port_conflicts(monkeypatch) -> None:
    monkeypatch.setattr(desktop_backend, "_port_conflict_pids", lambda *_args, **_kwargs: [])


def test_installer_backend_cleanup_uses_quoted_cmd():
    wxs_path = Path(__file__).resolve().parents[1] / "deploy" / "windows" / "EmploAI.wxs"
    payload = wxs_path.read_text(encoding="utf-8")
    assert '&quot;[SystemFolder]cmd.exe&quot; /d /c if exist &quot;[INSTALLDIR]resources\\app\\backend&quot;' in payload


def test_default_app_user_id_ignores_allowed_user_ids(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "8562474049,42")

    assert desktop_backend._default_user_id() == desktop_backend.DEFAULT_APP_USER_ID


def test_install_update_cli_accepts_restart_executable(monkeypatch, tmp_path: Path, capsys):
    root = tmp_path / "bundle"
    home = tmp_path / "home"
    env_file = home / ".env"
    restart_exe = tmp_path / "Programs" / "EmploAI" / "EmploAI.exe"
    captured = {}

    monkeypatch.setattr(desktop_backend, "_runtime_paths", lambda: (root, home, env_file))

    def _fake_install_latest_update(home_arg, root_arg, *, restart_executable=None):
        captured["home"] = home_arg
        captured["root"] = root_arg
        captured["restart_executable"] = restart_executable
        return {
            "ok": True,
            "launched": True,
            "restartExecutable": str(restart_executable),
        }

    monkeypatch.setattr(desktop_backend, "install_latest_update", _fake_install_latest_update)

    assert desktop_backend.main(["install-update", "--restart-executable", str(restart_exe)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["launched"] is True
    assert captured["home"] == home
    assert captured["root"] == root
    assert captured["restart_executable"] == restart_exe.resolve()
    assert payload["restartExecutable"] == str(restart_exe.resolve())


def test_ensure_runtime_manual_start_ignores_auto_start(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    launched = []

    monkeypatch.setattr(desktop_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=False, detail="offline"))
    monkeypatch.setattr(desktop_backend, "_launch_detached_daemon", lambda cfg, home: launched.append((cfg, home)))
    monkeypatch.setattr(desktop_backend, "_wait_for_runtime", lambda *_args, **_kwargs: SimpleNamespace(ok=True, detail=None))
    _stub_port_conflicts(monkeypatch)

    status, mode = desktop_backend._ensure_runtime(config, tmp_path, require_auto_start=False)

    assert launched == [(config, tmp_path)]
    assert status.ok is True
    assert mode == "launched"


def test_ensure_runtime_bootstrap_respects_auto_start(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    monkeypatch.setattr(
        desktop_backend,
        "_get_runtime_status",
        lambda: SimpleNamespace(ok=False, detail="offline"),
    )
    _stub_port_conflicts(monkeypatch)

    with pytest.raises(RuntimeError, match="auto-start is disabled"):
        desktop_backend._ensure_runtime(config, tmp_path, require_auto_start=True)


def test_runtime_status_payload_distinguishes_busy_runtime_process_from_dead_runtime(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    status = DesktopRuntimeStatus(
        ok=False,
        state="offline",
        mode="detached",
        api_base_url="http://127.0.0.1:8787",
        detail="Health probe timed out while the runtime was busy",
    )
    monkeypatch.setattr(desktop_backend, "_prepare_environment", lambda **_kwargs: None)
    monkeypatch.setattr(desktop_backend, "_runtime_paths", lambda: (tmp_path, tmp_path, tmp_path / ".env"))
    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "_get_runtime_status", lambda: status)
    monkeypatch.setattr(
        desktop_backend,
        "_managed_runtime_pids",
        lambda _home, _config, status=None: [4321],
    )

    payload = desktop_backend._runtime_status_payload()

    assert payload["ok"] is False
    assert payload["runtimeProcessDetected"] is True


def test_ensure_runtime_restarts_incompatible_attached_runtime(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=True,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    first_status = SimpleNamespace(ok=True, detail=None, process_id=4321)
    second_status = SimpleNamespace(ok=True, detail=None, process_id=9876)
    status_iter = iter([first_status, second_status])
    terminated = []

    monkeypatch.setattr(desktop_backend, "_get_runtime_status", lambda: next(status_iter))
    monkeypatch.setattr(
        desktop_backend,
        "_attached_runtime_requires_restart",
        lambda status: getattr(status, "process_id", 0) == 4321,
    )
    monkeypatch.setattr(desktop_backend, "_managed_runtime_pids", lambda *_args, **_kwargs: [4321])
    monkeypatch.setattr(desktop_backend, "_runtime_health_process_id", lambda status: int(getattr(status, "process_id", 0) or 0))
    monkeypatch.setattr(desktop_backend, "_is_runtime_process", lambda pid: pid == 4321)
    monkeypatch.setattr(desktop_backend, "_terminate_pid", lambda pid: terminated.append(pid))
    monkeypatch.setattr(desktop_backend, "_process_exists", lambda pid: False)

    status, mode = desktop_backend._ensure_runtime(config, tmp_path, require_auto_start=False)

    assert terminated == [4321]
    assert status is second_status
    assert mode == "reattached"


def test_stop_runtime_kills_detected_runtime_pids_without_pid_file(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    live_pids = {222, 333}
    terminated: list[int] = []
    clock = iter([0.0, 0.0, 0.25, 0.25])

    monkeypatch.setattr(desktop_backend, "_read_pid_record", lambda _home: None)
    monkeypatch.setattr(
        desktop_backend,
        "_get_runtime_status",
        lambda: SimpleNamespace(ok=True, process_id=222),
    )
    monkeypatch.setattr(desktop_backend, "_process_ids_for_port", lambda _port: {222, 333, 444})
    monkeypatch.setattr(desktop_backend, "_is_runtime_process", lambda pid: pid == 333)
    monkeypatch.setattr(desktop_backend, "_process_exists", lambda pid: pid in live_pids)
    monkeypatch.setattr(desktop_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(desktop_backend.time, "monotonic", lambda: next(clock))

    def _fake_terminate(pid: int) -> None:
        terminated.append(pid)
        live_pids.discard(pid)

    monkeypatch.setattr(desktop_backend, "_terminate_pid", _fake_terminate)

    result = desktop_backend._stop_runtime(tmp_path, config)

    assert result["stopped"] is True
    assert result["remainingPids"] == []
    assert result["pids"] == [222, 333]
    assert terminated == [222, 333]


def test_stop_runtime_can_preserve_paired_computer_host(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    live_pids = {101, 202, 303}
    terminated: list[int] = []

    monkeypatch.setattr(desktop_backend, "_request_runtime_agent_stop", lambda _config: None)
    monkeypatch.setattr(desktop_backend, "_managed_runtime_pids", lambda _home, _config: [101])
    monkeypatch.setattr(desktop_backend, "_managed_telegram_worker_pids", lambda _home: [202])
    monkeypatch.setattr(desktop_backend, "_managed_remote_control_worker_pids", lambda _home: [303])
    monkeypatch.setattr(desktop_backend, "_process_exists", lambda pid: pid in live_pids)
    monkeypatch.setattr(desktop_backend.time, "sleep", lambda _seconds: None)

    def terminate(pid: int) -> None:
        terminated.append(pid)
        live_pids.discard(pid)

    monkeypatch.setattr(desktop_backend, "_terminate_pid", terminate)

    result = desktop_backend._stop_runtime(tmp_path, config, preserve_fleet_host=True)

    assert result["stopped"] is True
    assert result["fleetHostPreserved"] is True
    assert result["pids"] == [101, 202]
    assert terminated == [101, 202]
    assert 303 in live_pids


def test_daemon_mode_defers_telegram_worker_until_bootstrap_when_configured(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    recorded = {}

    monkeypatch.setattr(
        desktop_backend,
        "_prepare_environment",
        lambda: (tmp_path, tmp_path, tmp_path / ".env", {"TELEGRAM_BOT_TOKEN": "token", "ALLOWED_USER_IDS": "42"}),
    )
    release_info_dir = tmp_path / "deploy" / "windows"
    release_info_dir.mkdir(parents=True)
    (release_info_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")
    (tmp_path / "release_state.json").write_text(
        json.dumps(
            {
                "last_onboarded_version": "0.1.0-beta.2",
                "telegram_rebind_required": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "configure_channels_enabled", lambda channel_name: channel_name == "telegram")
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(desktop_backend, "_write_pid_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(desktop_backend.atexit, "register", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        desktop_backend,
        "_ensure_telegram_worker",
        lambda _home, enabled, configured, config_fingerprint="": recorded.update({"telegram_worker": (enabled, configured, config_fingerprint)}) or SimpleNamespace(ok=True),
    )
    monkeypatch.setattr(
        desktop_backend,
        "_ensure_remote_control_worker",
        lambda _home, configured, config_fingerprint="": recorded.update({"remote_worker": (configured, config_fingerprint)}) or SimpleNamespace(ok=True),
    )
    monkeypatch.setattr(
        desktop_backend,
        "_stop_remote_control_worker",
        lambda _home: recorded.update({"remote_worker_stopped": True}),
    )
    async def _fake_run_server(*, host: str, port: int) -> None:
        recorded["server"] = (host, port)
        return None

    monkeypatch.setattr(desktop_backend, "_run_desktop_runtime_server", _fake_run_server)

    result = desktop_backend._run_daemon(None, None)

    assert result == 0
    assert "telegram_worker" not in recorded
    assert "remote_worker" not in recorded
    assert recorded["remote_worker_stopped"] is True
    assert recorded["server"] == ("127.0.0.1", 8787)


def test_daemon_mode_defers_remote_control_worker_until_bootstrap_when_configured(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    recorded = {}

    monkeypatch.setattr(
        desktop_backend,
        "_prepare_environment",
        lambda: (
            tmp_path,
            tmp_path,
            tmp_path / ".env",
            {
                "OPENAI_API_KEY": "sk-test",
                "EMPLOAI_REMOTE_CONTROL_BASE_URL": "https://example.com",
                "EMPLOAI_REMOTE_CONTROL_EMAIL": "user@example.com",
                "EMPLOAI_REMOTE_CONTROL_PASSWORD": "correct horse",
            },
        ),
    )
    release_info_dir = tmp_path / "deploy" / "windows"
    release_info_dir.mkdir(parents=True)
    (release_info_dir / "release_info.json").write_text('{"version":"0.1.0-beta.2"}', encoding="utf-8")
    (tmp_path / "release_state.json").write_text(
        json.dumps({"last_onboarded_version": "0.1.0-beta.2", "telegram_rebind_required": False}, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "configure_channels_enabled", lambda channel_name: channel_name == "telegram")
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(desktop_backend, "_write_pid_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(desktop_backend.atexit, "register", lambda *args, **kwargs: None)
    monkeypatch.setattr(desktop_backend, "_stop_telegram_worker", lambda *_args, **_kwargs: recorded.setdefault("stopped_telegram", True))
    monkeypatch.setattr(
        desktop_backend,
        "_ensure_remote_control_worker",
        lambda _home, configured, config_fingerprint="": recorded.update({"remote_worker": (configured, config_fingerprint)}) or SimpleNamespace(ok=True),
    )

    async def _fake_run_server(*, host: str, port: int) -> None:
        recorded["server"] = (host, port)
        return None

    monkeypatch.setattr(desktop_backend, "_run_desktop_runtime_server", _fake_run_server)

    result = desktop_backend._run_daemon(None, None)

    assert result == 0
    assert "remote_worker" not in recorded
    assert recorded["server"] == ("127.0.0.1", 8787)


def test_bootstrap_payload_ensures_service_workers_after_runtime_ready(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    existing = {
        "TELEGRAM_BOT_TOKEN": "token",
        "ALLOWED_USER_IDS": "42",
    }
    recorded = {}

    monkeypatch.setattr(
        desktop_backend,
        "_prepare_environment",
        lambda **_kwargs: (tmp_path, tmp_path, tmp_path / ".env", dict(existing)),
    )
    monkeypatch.setattr(desktop_backend, "apply_installer_voice_pack_preferences", lambda _home: {})
    monkeypatch.setattr(
        desktop_backend,
        "build_setup_state",
        lambda **_kwargs: {"required": False, "telegramConfigured": True, "validationIssues": []},
    )
    monkeypatch.setattr(
        desktop_backend,
        "_apply_runtime_secret_overlay",
        lambda values: {**values, "NVIDIA_API_KEY": "nvidia-overlay"},
    )
    monkeypatch.setattr(
        desktop_backend,
        "_effective_release_env_values",
        lambda _root, _home, values, **_kwargs: (values, False),
    )
    monkeypatch.setattr(
        desktop_backend,
        "_refresh_setup_model_catalog",
        lambda _setup_state, values: recorded.update({"model_catalog_values": dict(values)}),
    )
    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(
        desktop_backend,
        "_get_runtime_status",
        lambda: desktop_backend.DesktopRuntimeStatus(
            ok=True,
            state="running",
            mode="attached",
            api_base_url="http://127.0.0.1:8787",
            process_id=1234,
        ),
    )
    monkeypatch.setattr(desktop_backend, "_attached_runtime_requires_restart_checked", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(desktop_backend, "configure_channels_enabled", lambda channel_name: channel_name == "telegram")
    monkeypatch.setattr(desktop_backend, "_remote_control_configured_from_values", lambda _values: True)
    monkeypatch.setattr(
        desktop_backend,
        "_ensure_telegram_worker",
        lambda _home, enabled, configured, config_fingerprint="": recorded.update({"telegram_worker": (enabled, configured, config_fingerprint)}) or desktop_backend.TelegramServiceStatus(enabled=enabled, configured=configured, state="running"),
    )
    monkeypatch.setattr(
        desktop_backend,
        "_ensure_remote_control_worker",
        lambda _home, configured, config_fingerprint="": recorded.update({"remote_worker": (configured, config_fingerprint)}) or desktop_backend.RemoteControlServiceStatus(configured=configured, state="running"),
    )
    monkeypatch.setattr(desktop_backend, "_managed_runtime_pids", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(desktop_backend, "_ensure_desktop_token", lambda: {"access_token": "token", "device_id": "device"})
    monkeypatch.setattr(desktop_backend, "current_release_version", lambda _root: "0.0.0-test")

    payload = desktop_backend._bootstrap_payload(resolve_current_session=False)

    assert payload["runtimeStatus"]["ok"] is True
    assert recorded["telegram_worker"][0:2] == (True, True)
    assert recorded["remote_worker"][0] is True
    assert recorded["model_catalog_values"]["NVIDIA_API_KEY"] == "nvidia-overlay"
    assert payload["telegramStatus"]["state"] == "running"
    assert payload["setupState"]["remoteControlStatus"]["state"] == "running"


def test_runtime_secret_overlay_restores_stripped_provider_keys(monkeypatch):
    monkeypatch.setenv(
        desktop_backend.RUNTIME_SECRET_OVERLAY_ENV,
        json.dumps(
            {
                "OPENAI_API_KEY": "sk-overlay",
                "GOOGLE_API_KEY": "gemini-overlay",
                "NVIDIA_API_KEY": "nvidia-overlay",
                "IGNORED_SECRET": "nope",
            }
        ),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    effective = desktop_backend._apply_runtime_secret_overlay({"DEFAULT_WORKSPACE": "C:/Work"})

    assert effective["OPENAI_API_KEY"] == "sk-overlay"
    assert effective["GOOGLE_API_KEY"] == "gemini-overlay"
    assert effective["GEMINI_API_KEY"] == "gemini-overlay"
    assert effective["NVIDIA_API_KEY"] == "nvidia-overlay"
    assert "IGNORED_SECRET" not in effective
    assert os.environ["OPENAI_API_KEY"] == "sk-overlay"
    assert os.environ["GEMINI_API_KEY"] == "gemini-overlay"
    assert os.environ["NVIDIA_API_KEY"] == "nvidia-overlay"


def test_ensure_telegram_worker_cleans_duplicate_local_workers(monkeypatch, tmp_path: Path):
    live_pids = {101, 202}
    terminated: list[int] = []
    launched: list[Path] = []

    monkeypatch.setattr(desktop_backend, "_managed_telegram_worker_pids", lambda _home: sorted(live_pids))
    monkeypatch.setattr(desktop_backend, "_terminate_pid", lambda pid: terminated.append(pid) or live_pids.discard(pid))
    monkeypatch.setattr(desktop_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(desktop_backend, "_read_telegram_pid_record", lambda _home: None)
    monkeypatch.setattr(desktop_backend, "_read_telegram_status_record", lambda _home: None)
    monkeypatch.setattr(desktop_backend, "_write_telegram_status_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_backend, "_clear_telegram_status_record", lambda _home: None)
    monkeypatch.setattr(desktop_backend, "_launch_detached_telegram_worker", lambda home: launched.append(home))

    desktop_backend._ensure_telegram_worker(
        tmp_path,
        enabled=True,
        configured=True,
        config_fingerprint="token:users",
    )

    assert terminated == [101, 202]
    assert launched == [tmp_path]


def test_ensure_remote_control_worker_cleans_duplicate_local_workers(monkeypatch, tmp_path: Path):
    live_pids = {303, 404}
    terminated: list[int] = []
    launched: list[Path] = []

    monkeypatch.setattr(desktop_backend, "_managed_remote_control_worker_pids", lambda _home: sorted(live_pids))
    monkeypatch.setattr(desktop_backend, "_terminate_pid", lambda pid: terminated.append(pid) or live_pids.discard(pid))
    monkeypatch.setattr(desktop_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(desktop_backend, "_read_remote_control_pid_record", lambda _home: None)
    monkeypatch.setattr(desktop_backend, "_read_remote_control_status_record", lambda _home: None)
    monkeypatch.setattr(desktop_backend, "_write_remote_control_status_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_backend, "_clear_remote_control_status_record", lambda _home: None)
    monkeypatch.setattr(desktop_backend, "_launch_detached_remote_control_worker", lambda home: launched.append(home))

    desktop_backend._ensure_remote_control_worker(
        tmp_path,
        configured=True,
        config_fingerprint="remote:account",
    )

    assert terminated == [303, 404]
    assert launched == [tmp_path]


def test_remote_control_status_rejects_stale_running_record(monkeypatch, tmp_path: Path):
    import desktop_runtime.services as runtime_services

    monkeypatch.setattr(runtime_services, "_read_remote_control_pid_record", lambda _home: None)
    monkeypatch.setattr(
        runtime_services,
        "_read_remote_control_status_record",
        lambda _home: {"state": "running", "detail": "Stale connected detail."},
    )

    status = runtime_services._remote_control_service_status(tmp_path, configured=True)

    assert status.state == "offline"
    assert status.process_id is None
    assert status.detail == "The paired-computer status record is stale because its host process is not running."


def test_fleet_host_start_registers_and_launches_paired_host(monkeypatch, tmp_path: Path, capsys):
    import desktop_runtime.fleet_host as fleet_host
    import shared.fleet_connection as fleet_connection

    calls: list[str] = []
    monkeypatch.setattr(desktop_backend, "_prepare_environment", lambda **_kwargs: None)
    monkeypatch.setattr(
        desktop_backend,
        "_runtime_paths",
        lambda: (tmp_path, tmp_path / "home", tmp_path / ".env"),
    )
    monkeypatch.setattr(fleet_connection, "fleet_connection_configured", lambda _home: True)
    monkeypatch.setattr(
        fleet_host,
        "ensure_fleet_host_autostart",
        lambda _home: calls.append("registered") or {"state": "registered", "registered": True},
    )
    monkeypatch.setattr(
        fleet_host,
        "fleet_host_autostart_status",
        lambda _home: {"state": "running", "registered": True, "processId": 4242},
    )
    monkeypatch.setattr(desktop_backend, "_fleet_connection_config_fingerprint", lambda _home: "fingerprint")
    monkeypatch.setattr(
        desktop_backend,
        "_ensure_remote_control_worker",
        lambda _home, configured, config_fingerprint: calls.append(
            f"started:{configured}:{config_fingerprint}"
        ) or desktop_backend.RemoteControlServiceStatus(
            configured=True,
            state="running",
            process_id=4242,
        ),
    )

    assert desktop_backend.main(["fleet-host-start"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls == ["registered", "started:True:fingerprint"]
    assert payload["state"] == "running"
    assert payload["relay"]["state"] == "running"
    assert payload["relay"]["process_id"] == 4242


def test_unpaired_remote_control_supervision_does_not_scan_all_processes(monkeypatch, tmp_path: Path):
    stop_calls: list[bool] = []

    monkeypatch.setattr(
        desktop_backend,
        "_stop_remote_control_worker",
        lambda _home, scan_processes=True: stop_calls.append(scan_processes),
    )
    monkeypatch.setattr(
        desktop_backend,
        "_remote_control_service_status",
        lambda _home, configured: desktop_backend.RemoteControlServiceStatus(
            configured=configured,
            state="not_configured",
        ),
    )

    status = desktop_backend._ensure_remote_control_worker(tmp_path, configured=False)

    assert stop_calls == [False]
    assert status.state == "not_configured"


def test_windows_process_scan_is_created_without_a_console(monkeypatch):
    import desktop_runtime.services as runtime_services

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(runtime_services, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        runtime_services,
        "subprocess",
        SimpleNamespace(run=fake_run, CREATE_NO_WINDOW=0x08000000),
    )
    monkeypatch.setattr(runtime_services, "hidden_subprocess_kwargs", lambda: {"creationflags": 0x08000000})

    assert runtime_services._process_ids_for_command_markers("run-remote-control-worker") == set()
    assert captured["creationflags"] == 0x08000000


def test_windows_port_scan_is_created_without_a_console(monkeypatch):
    import desktop_runtime.services as runtime_services

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(runtime_services, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(runtime_services, "subprocess", SimpleNamespace(run=fake_run))
    monkeypatch.setattr(runtime_services, "hidden_subprocess_kwargs", lambda: {"creationflags": 0x08000000})

    assert runtime_services._process_ids_for_port(8787) == set()
    assert captured["command"][0] == "netstat"
    assert captured["creationflags"] == 0x08000000


def test_windows_pid_check_is_created_without_a_console(monkeypatch):
    import desktop_runtime.bootstrap as runtime_bootstrap

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(stdout="python.exe 4242")

    monkeypatch.setattr(runtime_bootstrap, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(runtime_bootstrap, "subprocess", SimpleNamespace(run=fake_run))
    monkeypatch.setattr(runtime_bootstrap, "hidden_subprocess_kwargs", lambda: {"creationflags": 0x08000000})

    assert runtime_bootstrap._process_exists(4242) is True
    assert captured["command"][0] == "tasklist"
    assert captured["creationflags"] == 0x08000000


def test_runtime_compatibility_issue_flags_app_only_runtime_when_telegram_is_configured(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    status = DesktopRuntimeStatus(
        ok=True,
        state="ready",
        mode="attached",
        api_base_url="http://127.0.0.1:8787",
        detail=None,
        degraded=False,
        process_id=None,
    )

    monkeypatch.setattr(desktop_backend, "_read_pid_record", lambda _home: None)
    monkeypatch.setattr(desktop_backend, "_managed_runtime_pids", lambda _home, _config, status=None: [6132])
    monkeypatch.setattr(
        desktop_backend,
        "_process_command_line",
        lambda pid: "C:\\Python313\\python.exe -m app_backend.local_runtime_server run --host 127.0.0.1 --port 8787" if pid == 6132 else "",
    )

    issue = desktop_backend._runtime_compatibility_issue(
        tmp_path,
        config,
        status,
        telegram_enabled=True,
        telegram_configured=True,
    )

    assert issue is not None
    assert "Telegram and desktop share one live session" in issue


def test_launch_detached_daemon_uses_source_root_in_unfrozen_mode(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    source_root = tmp_path / "repo"
    source_root.mkdir()
    spawned: dict[str, object] = {}

    class _DummyHandle:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, _value):
            return 0

    monkeypatch.setattr(desktop_backend, "bundle_root", lambda: source_root)
    monkeypatch.setattr(desktop_backend.sys, "frozen", False, raising=False)
    monkeypatch.setattr(desktop_backend, "_self_command", lambda: ["python", "-m", "desktop_runtime.backend"])
    monkeypatch.setattr(desktop_backend, "_runtime_log_path", lambda _home: tmp_path / "desktop_runtime.log")
    monkeypatch.setattr(desktop_backend.subprocess, "Popen", lambda command, **kwargs: spawned.update({"command": command, **kwargs}))
    monkeypatch.setattr(Path, "open", lambda self, *args, **kwargs: _DummyHandle())

    desktop_backend._launch_detached_daemon(config, tmp_path)

    assert spawned["cwd"] == str(source_root)
    env = spawned["env"]
    assert env["EMPLOAI_HOME"] == str(tmp_path)
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(source_root)


def test_force_launch_reports_launch_failure_detail(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    status = DesktopRuntimeStatus(
        ok=False,
        state="offline",
        mode="detached",
        api_base_url="http://127.0.0.1:8787",
        detail="No compatible local runtime responded on the configured desktop host/port",
        degraded=False,
        process_id=None,
    )

    monkeypatch.setattr(desktop_backend, "_prepare_environment", lambda **_kwargs: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(desktop_backend, "build_setup_state", lambda **_kwargs: {"required": False})
    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "_get_runtime_status", lambda: status)
    monkeypatch.setattr(desktop_backend, "configure_channels_enabled", lambda _channel_name: False)
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(desktop_backend, "_managed_runtime_pids", lambda _home, _config, status=None: [])
    monkeypatch.setattr(desktop_backend, "_ensure_runtime", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Synthetic launch failure")))
    monkeypatch.setattr(desktop_backend, "current_release_version", lambda _root: "0.0.0-test")

    payload = desktop_backend._bootstrap_payload(force_launch=True)

    assert payload["runtimeStatus"]["ok"] is False
    assert payload["runtimeStatus"]["state"] == "failed"
    assert payload["runtimeStatus"]["degraded"] is True
    assert payload["runtimeStatus"]["detail"] == "Synthetic launch failure"


def test_forward_voice_bridge_prepares_runtime_environment(monkeypatch, tmp_path: Path):
    recorded: dict[str, object] = {}

    monkeypatch.setattr(desktop_backend, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(desktop_backend, "env_path", lambda home: home / ".env")

    def _fake_configure(home: Path, env_file: Path) -> None:
        recorded["configure"] = (home, env_file)
        monkeypatch.setenv("EMPLOAI_HOME", str(home))

    monkeypatch.setattr(desktop_backend, "configure_process_environment", _fake_configure)

    class _FakeWhisperLive:
        @staticmethod
        def main() -> int:
            recorded["argv"] = list(sys.argv)
            recorded["home"] = os.environ.get("EMPLOAI_HOME")
            return 17

    monkeypatch.setitem(sys.modules, "app_backend.whisper_cpp_live", _FakeWhisperLive)

    result = desktop_backend._forward_voice_bridge(["--engine", "voice-engine"])

    assert result == 17
    assert recorded["configure"] == (tmp_path, tmp_path / ".env")
    assert recorded["argv"][-2:] == ["--engine", "voice-engine"]
    assert recorded["home"] == str(tmp_path)


def test_voice_pack_action_installs_pack_and_marks_requested(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    installed: list[str] = []
    preferences: list[tuple[str, bool, str | None]] = []

    monkeypatch.setattr(desktop_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=False))
    monkeypatch.setattr(desktop_backend, "_runtime_is_managed", lambda _home, _config=None: False)
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(desktop_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        desktop_backend,
        "install_voice_pack",
        lambda pack_id, **_kwargs: installed.append(pack_id),
    )
    monkeypatch.setattr(desktop_backend, "_warm_installed_voice_pack", lambda pack_id, **_kwargs: installed.append(f"warm:{pack_id}"))
    monkeypatch.setattr(
        desktop_backend,
        "update_voice_pack_preferences",
        lambda *, home, pack_id, requested, default_engine=None: preferences.append((pack_id, requested, default_engine)),
    )
    monkeypatch.setattr(desktop_backend, "_bootstrap_payload", lambda **_kwargs: {"ok": True, "setupState": {"required": False}})

    payload = desktop_backend._voice_pack_action("hebrew_local", install=True)

    assert payload["ok"] is True
    assert installed == ["hebrew_local", "warm:hebrew_local"]
    assert preferences == [("hebrew_local", True, "hebrew_local")]


def test_voice_pack_action_removes_pack_and_falls_back_default_engine(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    removed: list[str] = []
    preferences: list[tuple[str, bool, str | None]] = []

    monkeypatch.setattr(desktop_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=False))
    monkeypatch.setattr(desktop_backend, "_runtime_is_managed", lambda _home, _config=None: False)
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(desktop_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        desktop_backend,
        "load_runtime_config",
        lambda _home: {
            "voice": {
                "default_engine": "hebrew_local",
                "packs": {
                    "english_local": {"requested": True},
                    "hebrew_local": {"requested": True},
                },
            }
        },
    )
    monkeypatch.setattr(
        desktop_backend,
        "update_voice_pack_preferences",
        lambda *, home, pack_id, requested, default_engine=None: preferences.append((pack_id, requested, default_engine)),
    )
    monkeypatch.setattr(desktop_backend, "remove_voice_pack", lambda pack_id: removed.append(pack_id))
    monkeypatch.setattr(desktop_backend, "_bootstrap_payload", lambda **_kwargs: {"ok": True, "setupState": {"required": False}})

    payload = desktop_backend._voice_pack_action("hebrew_local", install=False)

    assert payload["ok"] is True
    assert removed == ["hebrew_local"]
    assert preferences == [("hebrew_local", False, "english_local")]


def test_voice_pack_action_restores_runtime_after_install_failure(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    restored_payloads: list[dict[str, object]] = []

    monkeypatch.setattr(desktop_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=True))
    monkeypatch.setattr(desktop_backend, "_runtime_is_managed", lambda _home, _config=None: True)
    monkeypatch.setattr(desktop_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(desktop_backend, "_stop_runtime", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        desktop_backend,
        "load_runtime_config",
        lambda _home: {
            "voice": {
                "default_engine": "english_local",
                "packs": {
                    "english_local": {"requested": True},
                    "hebrew_local": {"requested": False},
                },
            }
        },
    )
    monkeypatch.setattr(desktop_backend, "save_runtime_config", lambda _home, payload: restored_payloads.append(payload))
    monkeypatch.setattr(
        desktop_backend,
        "install_voice_pack",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Synthetic Hebrew warmup failure")),
    )
    removed: list[str] = []
    monkeypatch.setattr(desktop_backend, "remove_voice_pack", lambda pack_id: removed.append(pack_id))
    monkeypatch.setattr(
        desktop_backend,
        "_bootstrap_payload",
        lambda **_kwargs: {"ok": True, "setupState": {"required": False}, "runtimeStatus": {"ok": True}},
    )

    with pytest.raises(RuntimeError, match="Synthetic Hebrew warmup failure"):
        desktop_backend._voice_pack_action("hebrew_local", install=True)

    assert removed == ["hebrew_local"]
    assert restored_payloads
    restored_voice = restored_payloads[-1]["voice"]
    assert restored_voice["default_engine"] == "english_local"
    assert restored_voice["packs"]["english_local"]["requested"] is True
    assert restored_voice["packs"]["hebrew_local"]["requested"] is False


def test_cleanup_runtime_home_removes_all_packaged_state_on_full_cleanup(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    (runtime_home / "config.json").write_text("{}", encoding="utf-8")
    (runtime_home / "desktop-sidebar-state.json").write_text("{}", encoding="utf-8")
    (runtime_home / "voice_packs").mkdir()
    (runtime_home / "data").mkdir()

    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        restart_attach_timeout_seconds=3,
        workspace=str(runtime_home),
    )

    monkeypatch.setattr(desktop_backend, "_prepare_environment", lambda: (tmp_path, runtime_home, runtime_home / ".env", {}))
    monkeypatch.setattr(desktop_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(desktop_backend, "_stop_runtime", lambda _home, _config: {"stopped": True})

    result = desktop_backend._cleanup_runtime_home(voice_packs_only=False)

    assert result["ok"] is True
    assert not runtime_home.exists()
