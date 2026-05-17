import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from mobile_app.backend.desktop_runtime import DesktopRuntimeConfig, DesktopRuntimeStatus
import deploy.windows.release_backend as release_backend


def test_ensure_runtime_manual_start_ignores_auto_start(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    statuses = iter(
        [
            SimpleNamespace(ok=False, detail="offline"),
            SimpleNamespace(ok=True, detail=None),
        ]
    )
    launched = []
    clock = iter([0.0, 0.0, 0.5, 0.5])

    monkeypatch.setattr(release_backend, "get_runtime_status", lambda: next(statuses))
    monkeypatch.setattr(release_backend, "_launch_detached_daemon", lambda cfg, home: launched.append((cfg, home)))
    monkeypatch.setattr(release_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(release_backend.time, "monotonic", lambda: next(clock))

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
        workspace=str(tmp_path),
    )
    monkeypatch.setattr(
        release_backend,
        "get_runtime_status",
        lambda: SimpleNamespace(ok=False, detail="offline"),
    )

    with pytest.raises(RuntimeError, match="auto-start is disabled"):
        release_backend._ensure_runtime(config, tmp_path, require_auto_start=True)


def test_stop_runtime_kills_detected_runtime_pids_without_pid_file(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    live_pids = {222, 333}
    terminated: list[int] = []
    clock = iter([0.0, 0.0, 0.25, 0.25])

    monkeypatch.setattr(release_backend, "_read_pid_record", lambda _home: None)
    monkeypatch.setattr(
        release_backend,
        "get_runtime_status",
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
        workspace=str(tmp_path),
    )
    recorded = {}

    monkeypatch.setattr(
        release_backend,
        "_prepare_environment",
        lambda: (tmp_path, tmp_path, tmp_path / ".env", {"TELEGRAM_BOT_TOKEN": "token", "ALLOWED_USER_IDS": "42"}),
    )
    monkeypatch.setattr(release_backend, "load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "configure_channels_enabled", lambda channel_name: channel_name == "telegram")
    monkeypatch.setattr(release_backend, "_write_pid_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(release_backend.atexit, "register", lambda *args, **kwargs: None)

    import telegram_bot.telegram_agent as telegram_agent

    def _fake_main() -> None:
        recorded["force_flag"] = os.getenv("EMPLOAI_DESKTOP_FORCE_APP_SERVER")

    monkeypatch.setattr(telegram_agent, "main", _fake_main)

    result = release_backend._run_daemon(None, None)

    assert result == 0
    assert recorded["force_flag"] == "1"


def test_bootstrap_marks_app_only_runtime_incompatible_when_telegram_is_configured(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
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

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {
        "TELEGRAM_BOT_TOKEN": "token",
        "ALLOWED_USER_IDS": "42",
    }))
    monkeypatch.setattr(release_backend, "build_setup_state", lambda **_kwargs: {"required": False})
    monkeypatch.setattr(release_backend, "load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "get_runtime_status", lambda: status)
    monkeypatch.setattr(release_backend, "configure_channels_enabled", lambda channel_name: channel_name == "telegram")
    monkeypatch.setattr(release_backend, "_read_pid_record", lambda _home: None)
    monkeypatch.setattr(release_backend, "_managed_runtime_pids", lambda _home, _config, status=None: [6132])
    monkeypatch.setattr(
        release_backend,
        "_process_command_line",
        lambda pid: "C:\\Python313\\python.exe -m mobile_app.backend.desktop_runtime run --host 127.0.0.1 --port 8787" if pid == 6132 else "",
    )

    called = {"token": False}

    def _unexpected_token():
        called["token"] = True
        return {"access_token": "bad", "device_id": "device"}

    monkeypatch.setattr(release_backend, "_ensure_desktop_token", _unexpected_token)
    monkeypatch.setattr(release_backend, "_ensure_current_session_id", lambda _workspace: "session-1")
    monkeypatch.setattr(release_backend, "current_release_version", lambda _root: "0.0.0-test")

    payload = release_backend._bootstrap_payload(launch_if_needed=False)

    assert payload["runtimeStatus"]["ok"] is False
    assert payload["runtimeStatus"]["state"] == "incompatible"
    assert "Telegram and desktop share one live session" in payload["runtimeStatus"]["detail"]
    assert payload["accessToken"] == ""
    assert called["token"] is False


def test_launch_detached_daemon_uses_source_root_in_unfrozen_mode(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
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
    monkeypatch.setattr(release_backend, "load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "get_runtime_status", lambda: status)
    monkeypatch.setattr(release_backend, "configure_channels_enabled", lambda _channel_name: False)
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
        workspace=str(tmp_path),
    )
    installed: list[str] = []
    preferences: list[tuple[str, bool, str | None]] = []

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(release_backend, "load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "get_runtime_status", lambda: SimpleNamespace(ok=False))
    monkeypatch.setattr(release_backend, "_runtime_is_managed", lambda _home, _config=None: False)
    monkeypatch.setattr(release_backend.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(release_backend, "install_voice_pack", lambda pack_id: installed.append(pack_id))
    monkeypatch.setattr(
        release_backend,
        "update_voice_pack_preferences",
        lambda *, home, pack_id, requested, default_engine=None: preferences.append((pack_id, requested, default_engine)),
    )
    monkeypatch.setattr(release_backend, "_bootstrap_payload", lambda **_kwargs: {"ok": True, "setupState": {"required": False}})

    payload = release_backend._voice_pack_action("hebrew_local", install=True)

    assert payload["ok"] is True
    assert installed == ["hebrew_local"]
    assert preferences == [("hebrew_local", True, None)]


def test_voice_pack_action_removes_pack_and_falls_back_default_engine(monkeypatch, tmp_path: Path):
    config = DesktopRuntimeConfig(
        enabled=True,
        host="127.0.0.1",
        port=8787,
        auto_start=False,
        attach_timeout_seconds=3,
        workspace=str(tmp_path),
    )
    removed: list[str] = []
    preferences: list[tuple[str, bool, str | None]] = []

    monkeypatch.setattr(release_backend, "_prepare_environment", lambda: (tmp_path, tmp_path, tmp_path / ".env", {}))
    monkeypatch.setattr(release_backend, "load_desktop_runtime_config", lambda: config)
    monkeypatch.setattr(release_backend, "get_runtime_status", lambda: SimpleNamespace(ok=False))
    monkeypatch.setattr(release_backend, "_runtime_is_managed", lambda _home, _config=None: False)
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
