import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from mobile_app.backend.desktop_runtime import DesktopRuntimeConfig, DesktopRuntimeStatus
import deploy.windows.release_backend as release_backend


def _stub_port_conflicts(monkeypatch) -> None:
    monkeypatch.setattr(release_backend, "_port_conflict_pids", lambda *_args, **_kwargs: [])


def test_installer_backend_cleanup_uses_quoted_cmd():
    wxs_path = Path(__file__).resolve().parents[1] / "deploy" / "windows" / "EmploAI.wxs"
    payload = wxs_path.read_text(encoding="utf-8")
    assert '&quot;[SystemFolder]cmd.exe&quot; /d /c if exist &quot;[INSTALLDIR]resources\\app\\backend&quot;' in payload


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

    monkeypatch.setattr(release_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=False, detail="offline"))
    monkeypatch.setattr(release_backend, "_launch_detached_daemon", lambda cfg, home: launched.append((cfg, home)))
    monkeypatch.setattr(release_backend, "_wait_for_runtime", lambda *_args, **_kwargs: SimpleNamespace(ok=True, detail=None))
    _stub_port_conflicts(monkeypatch)

    status, mode = release_backend._ensure_runtime(config, tmp_path, require_auto_start=False)

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
        release_backend,
        "_get_runtime_status",
        lambda: SimpleNamespace(ok=False, detail="offline"),
    )
    _stub_port_conflicts(monkeypatch)

    with pytest.raises(RuntimeError, match="auto-start is disabled"):
        release_backend._ensure_runtime(config, tmp_path, require_auto_start=True)


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

    monkeypatch.setattr(release_backend, "_get_runtime_status", lambda: next(status_iter))
    monkeypatch.setattr(
        release_backend,
        "_attached_runtime_requires_restart",
        lambda status: getattr(status, "process_id", 0) == 4321,
    )
    monkeypatch.setattr(release_backend, "_managed_runtime_pids", lambda *_args, **_kwargs: [4321])
    monkeypatch.setattr(release_backend, "_runtime_health_process_id", lambda status: int(getattr(status, "process_id", 0) or 0))
    monkeypatch.setattr(release_backend, "_is_runtime_process", lambda pid: pid == 4321)
    monkeypatch.setattr(release_backend, "_terminate_pid", lambda pid: terminated.append(pid))
    monkeypatch.setattr(release_backend, "_process_exists", lambda pid: False)

    status, mode = release_backend._ensure_runtime(config, tmp_path, require_auto_start=False)

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

    monkeypatch.setattr(release_backend, "_read_pid_record", lambda _home: None)
    monkeypatch.setattr(
        release_backend,
        "_get_runtime_status",
        lambda: SimpleNamespace(ok=True, process_id=222),
    )
    monkeypatch.setattr(release_backend, "_process_ids_for_port", lambda _port: {222, 333, 444})
    monkeypatch.setattr(release_backend, "_is_runtime_process", lambda pid: pid == 333)
    monkeypatch.setattr(release_backend, "_process_exists", lambda pid: pid in live_pids)
    monkeypatch.setattr(release_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(release_backend.time, "monotonic", lambda: next(clock))

    def _fake_terminate(pid: int) -> None:
        terminated.append(pid)
        live_pids.discard(pid)

    monkeypatch.setattr(release_backend, "_terminate_pid", _fake_terminate)

    result = release_backend._stop_runtime(tmp_path, config)

    assert result["stopped"] is True
    assert result["remainingPids"] == []
    assert result["pids"] == [222, 333]
    assert terminated == [222, 333]


def test_daemon_mode_runs_telegram_when_configured_even_if_app_channel_disabled(monkeypatch, tmp_path: Path):
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
        release_backend,
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

    monkeypatch.setattr(release_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "configure_channels_enabled", lambda channel_name: channel_name == "telegram")
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(release_backend, "_write_pid_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(release_backend.atexit, "register", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        release_backend,
        "_ensure_telegram_worker",
        lambda _home, enabled, configured, config_fingerprint="": recorded.update({"telegram_worker": (enabled, configured, config_fingerprint)}) or SimpleNamespace(ok=True),
    )
    monkeypatch.setattr(
        release_backend,
        "_ensure_remote_control_worker",
        lambda _home, configured, config_fingerprint="": recorded.update({"remote_worker": (configured, config_fingerprint)}) or SimpleNamespace(ok=True),
    )
    monkeypatch.setattr(
        release_backend,
        "_stop_remote_control_worker",
        lambda _home: recorded.update({"remote_worker_stopped": True}),
    )
    async def _fake_run_server(*, host: str, port: int) -> None:
        recorded["server"] = (host, port)
        return None

    monkeypatch.setattr(release_backend, "_run_desktop_runtime_server", _fake_run_server)

    result = release_backend._run_daemon(None, None)

    assert result == 0
    assert recorded["telegram_worker"][0:2] == (True, True)
    assert "remote_worker" not in recorded
    assert recorded["remote_worker_stopped"] is True
    assert recorded["server"] == ("127.0.0.1", 8787)


def test_daemon_mode_runs_remote_control_worker_when_configured(monkeypatch, tmp_path: Path):
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
        release_backend,
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

    monkeypatch.setattr(release_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "configure_channels_enabled", lambda channel_name: channel_name == "telegram")
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(release_backend, "_write_pid_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(release_backend.atexit, "register", lambda *args, **kwargs: None)
    monkeypatch.setattr(release_backend, "_stop_telegram_worker", lambda *_args, **_kwargs: recorded.setdefault("stopped_telegram", True))
    monkeypatch.setattr(
        release_backend,
        "_ensure_remote_control_worker",
        lambda _home, configured, config_fingerprint="": recorded.update({"remote_worker": (configured, config_fingerprint)}) or SimpleNamespace(ok=True),
    )

    async def _fake_run_server(*, host: str, port: int) -> None:
        recorded["server"] = (host, port)
        return None

    monkeypatch.setattr(release_backend, "_run_desktop_runtime_server", _fake_run_server)

    result = release_backend._run_daemon(None, None)

    assert result == 0
    assert recorded["remote_worker"][0] is True
    assert recorded["server"] == ("127.0.0.1", 8787)


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

    monkeypatch.setattr(release_backend, "_read_pid_record", lambda _home: None)
    monkeypatch.setattr(release_backend, "_managed_runtime_pids", lambda _home, _config, status=None: [6132])
    monkeypatch.setattr(
        release_backend,
        "_process_command_line",
        lambda pid: "C:\\Python313\\python.exe -m mobile_app.backend.desktop_runtime run --host 127.0.0.1 --port 8787" if pid == 6132 else "",
    )

    issue = release_backend._runtime_compatibility_issue(
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

    monkeypatch.setattr(release_backend, "bundle_root", lambda: source_root)
    monkeypatch.setattr(release_backend.sys, "frozen", False, raising=False)
    monkeypatch.setattr(release_backend, "_self_command", lambda: ["python", "-m", "deploy.windows.release_backend"])
    monkeypatch.setattr(release_backend, "_runtime_log_path", lambda _home: tmp_path / "desktop_runtime.log")
    monkeypatch.setattr(release_backend.subprocess, "Popen", lambda command, **kwargs: spawned.update({"command": command, **kwargs}))
    monkeypatch.setattr(Path, "open", lambda self, *args, **kwargs: _DummyHandle())

    release_backend._launch_detached_daemon(config, tmp_path)

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

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(release_backend, "build_setup_state", lambda **_kwargs: {"required": False})
    monkeypatch.setattr(release_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "_get_runtime_status", lambda: status)
    monkeypatch.setattr(release_backend, "configure_channels_enabled", lambda _channel_name: False)
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(release_backend, "_managed_runtime_pids", lambda _home, _config, status=None: [])
    monkeypatch.setattr(release_backend, "_ensure_runtime", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Synthetic launch failure")))
    monkeypatch.setattr(release_backend, "current_release_version", lambda _root: "0.0.0-test")

    payload = release_backend._bootstrap_payload(force_launch=True)

    assert payload["runtimeStatus"]["ok"] is False
    assert payload["runtimeStatus"]["state"] == "failed"
    assert payload["runtimeStatus"]["degraded"] is True
    assert payload["runtimeStatus"]["detail"] == "Synthetic launch failure"


def test_forward_voice_bridge_prepares_runtime_environment(monkeypatch, tmp_path: Path):
    recorded: dict[str, object] = {}

    monkeypatch.setattr(release_backend, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(release_backend, "env_path", lambda home: home / ".env")

    def _fake_configure(home: Path, env_file: Path) -> None:
        recorded["configure"] = (home, env_file)
        os.environ["EMPLOAI_HOME"] = str(home)

    monkeypatch.setattr(release_backend, "configure_process_environment", _fake_configure)

    class _FakeWhisperLive:
        @staticmethod
        def main() -> int:
            recorded["argv"] = list(sys.argv)
            recorded["home"] = os.environ.get("EMPLOAI_HOME")
            return 17

    monkeypatch.setitem(sys.modules, "mobile_app.backend.whisper_cpp_live", _FakeWhisperLive)

    result = release_backend._forward_voice_bridge(["--engine", "voice-engine"])

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

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(release_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=False))
    monkeypatch.setattr(release_backend, "_runtime_is_managed", lambda _home, _config=None: False)
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(release_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        release_backend,
        "install_voice_pack",
        lambda pack_id, **_kwargs: installed.append(pack_id),
    )
    monkeypatch.setattr(release_backend, "_warm_installed_voice_pack", lambda pack_id, **_kwargs: installed.append(f"warm:{pack_id}"))
    monkeypatch.setattr(
        release_backend,
        "update_voice_pack_preferences",
        lambda *, home, pack_id, requested, default_engine=None: preferences.append((pack_id, requested, default_engine)),
    )
    monkeypatch.setattr(release_backend, "_bootstrap_payload", lambda **_kwargs: {"ok": True, "setupState": {"required": False}})

    payload = release_backend._voice_pack_action("hebrew_local", install=True)

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

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(release_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=False))
    monkeypatch.setattr(release_backend, "_runtime_is_managed", lambda _home, _config=None: False)
    _stub_port_conflicts(monkeypatch)
    monkeypatch.setattr(release_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        release_backend,
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
        release_backend,
        "update_voice_pack_preferences",
        lambda *, home, pack_id, requested, default_engine=None: preferences.append((pack_id, requested, default_engine)),
    )
    monkeypatch.setattr(release_backend, "remove_voice_pack", lambda pack_id: removed.append(pack_id))
    monkeypatch.setattr(release_backend, "_bootstrap_payload", lambda **_kwargs: {"ok": True, "setupState": {"required": False}})

    payload = release_backend._voice_pack_action("hebrew_local", install=False)

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

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(release_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "_get_runtime_status", lambda: SimpleNamespace(ok=True))
    monkeypatch.setattr(release_backend, "_runtime_is_managed", lambda _home, _config=None: True)
    monkeypatch.setattr(release_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(release_backend, "_stop_runtime", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        release_backend,
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
    monkeypatch.setattr(release_backend, "save_runtime_config", lambda _home, payload: restored_payloads.append(payload))
    monkeypatch.setattr(
        release_backend,
        "install_voice_pack",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Synthetic Hebrew warmup failure")),
    )
    removed: list[str] = []
    monkeypatch.setattr(release_backend, "remove_voice_pack", lambda pack_id: removed.append(pack_id))
    monkeypatch.setattr(
        release_backend,
        "_bootstrap_payload",
        lambda **_kwargs: {"ok": True, "setupState": {"required": False}, "runtimeStatus": {"ok": True}},
    )

    with pytest.raises(RuntimeError, match="Synthetic Hebrew warmup failure"):
        release_backend._voice_pack_action("hebrew_local", install=True)

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

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, runtime_home, runtime_home / ".env", {}))
    monkeypatch.setattr(release_backend, "_load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "_stop_runtime", lambda _home, _config: {"stopped": True})

    result = release_backend._cleanup_runtime_home(voice_packs_only=False)

    assert result["ok"] is True
    assert not runtime_home.exists()
