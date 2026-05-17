from __future__ import annotations

import argparse
import asyncio
import atexit
import importlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mobile_app.backend.auth_store import AppAuthStore
from mobile_app.backend.desktop_runtime import (
    DEFAULT_ATTACH_TIMEOUT_SECONDS,
    DEFAULT_DESKTOP_HOST,
    DEFAULT_DESKTOP_PORT,
    DEFAULT_DEVICE_KEY,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DEVICE_PLATFORM,
    DesktopRuntimeConfig,
    get_runtime_status,
    load_desktop_runtime_config,
    run_desktop_runtime_server,
)
from mobile_app.backend.session_bridge import AppSessionBridge
from mobile_app.backend.voice_pack_manager import (
    VOICE_ENGINE_ENGLISH,
    VOICE_ENGINE_HEBREW,
    VOICE_PACK_IDS,
    ensure_requested_voice_packs,
    install_voice_pack,
    remove_voice_pack,
)
from mobile_app.backend.app_server import TOKEN_TTL_SECONDS

from deploy.windows.release_runtime import (
    build_setup_state,
    bundle_root,
    configure_process_environment,
    current_release_version,
    ensure_runtime_files,
    env_path,
    load_existing_env_values,
    load_runtime_config,
    runtime_home,
    save_setup_values,
    update_voice_pack_preferences,
)
from deploy.windows.release_update import check_for_updates, install_latest_update


RUNTIME_PID_FILENAME = "desktop_runtime.pid.json"
RUNTIME_LOG_FILENAME = "desktop_runtime.log"


def _json_print(payload: dict[str, Any]) -> int:
    print(json.dumps(payload))
    return 0


def _runtime_paths() -> tuple[Path, Path, Path]:
    root = bundle_root()
    home = runtime_home()
    env_file = env_path(home)
    ensure_runtime_files(home, root)
    return root, home, env_file


def _prepare_environment() -> tuple[Path, Path, Path, dict[str, str]]:
    root, home, env_file = _runtime_paths()
    existing = load_existing_env_values(env_file)
    configure_process_environment(home, env_file)
    return root, home, env_file, existing


def _runtime_pid_path(home: Path) -> Path:
    return home / RUNTIME_PID_FILENAME


def _runtime_log_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / RUNTIME_LOG_FILENAME


def _default_user_id() -> int:
    allowed = os.getenv("ALLOWED_USER_IDS", "").split(",")
    for item in allowed:
        value = item.strip()
        if not value:
            continue
        try:
            return int(value)
        except ValueError:
            continue
    return 0


def _ensure_current_session_id(workspace: Path) -> str:
    bridge = AppSessionBridge(user_id=_default_user_id(), workspace=workspace)
    current = bridge.get_current_session()
    if current:
        return current.id
    created = bridge.create_session(None)
    return created.id


def _ensure_desktop_token() -> dict[str, Any]:
    store = AppAuthStore()
    return store.ensure_device_token(
        user_id=_default_user_id(),
        device_name=DEFAULT_DEVICE_NAME,
        device_platform=DEFAULT_DEVICE_PLATFORM,
        token_ttl_seconds=TOKEN_TTL_SECONDS,
        device_key=DEFAULT_DEVICE_KEY,
    )


def _self_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [sys.executable, "-m", "deploy.windows.release_backend"]


def _read_pid_record(home: Path) -> dict[str, Any] | None:
    path = _runtime_pid_path(home)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_pid_record(home: Path, *, mode: str, host: str, port: int) -> None:
    _runtime_pid_path(home).write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "mode": mode,
                "host": host,
                "port": port,
                "startedAt": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _clear_pid_record(home: Path) -> None:
    path = _runtime_pid_path(home)
    record = _read_pid_record(home)
    if not record:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return
    if int(record.get("pid") or 0) != os.getpid():
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _launch_detached_daemon(config: DesktopRuntimeConfig, home: Path) -> None:
    command = [
        *_self_command(),
        "run-daemon",
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    env = os.environ.copy()
    env.setdefault("EMPLOAI_DESKTOP_RUNTIME", "1")
    env.setdefault("EMPLOAI_HOME", str(home))

    launch_cwd = str(home)
    if not getattr(sys, "frozen", False):
        source_root = bundle_root()
        launch_cwd = str(source_root)
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        source_root_text = str(source_root)
        if existing_pythonpath:
            env["PYTHONPATH"] = os.pathsep.join([source_root_text, existing_pythonpath])
        else:
            env["PYTHONPATH"] = source_root_text

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    log_path = _runtime_log_path(home)
    with log_path.open("a", encoding="utf-8") as handle:
        subprocess.Popen(
            command,
            cwd=launch_cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creationflags,
        )


def _ensure_runtime(config: DesktopRuntimeConfig, home: Path, *, require_auto_start: bool = True) -> tuple[Any, str]:
    status = get_runtime_status()
    if status.ok:
        return status, "attached"

    if not config.enabled:
        raise RuntimeError(status.detail or "Desktop runtime is disabled in config.json")
    if require_auto_start and not config.auto_start:
        raise RuntimeError("Desktop runtime is offline and auto-start is disabled")

    _launch_detached_daemon(config, home)
    deadline = time.monotonic() + max(2, config.attach_timeout_seconds or DEFAULT_ATTACH_TIMEOUT_SECONDS)
    while time.monotonic() < deadline:
        time.sleep(0.75)
        status = get_runtime_status()
        if status.ok:
            return status, "launched"

    raise RuntimeError(
        f"Desktop runtime did not become ready within {config.attach_timeout_seconds} seconds. "
        f"See {_runtime_log_path(home)} for startup logs."
    )


def _runtime_health_process_id(status: Any) -> int:
    try:
        return int(getattr(status, "process_id", 0) or 0)
    except Exception:
        return 0


def _process_command_line(pid: int) -> str:
    if pid <= 0:
        return ""

    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f'$process = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" '
                        '-ErrorAction SilentlyContinue; '
                        'if ($null -ne $process) { [string]$process.CommandLine }'
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip()

        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _is_runtime_process(pid: int) -> bool:
    command_line = _process_command_line(pid).lower()
    if not command_line:
        return False

    marker_groups = (
        ("deploy.windows.release_backend", "run-daemon"),
        ("mobile_app.backend.desktop_runtime", " run"),
        ("emploaibackend.exe", "run-daemon"),
    )
    return any(all(marker in command_line for marker in markers) for markers in marker_groups)


def _is_telegram_capable_runtime_command_line(command_line: str) -> bool:
    normalized = str(command_line or "").lower()
    if not normalized:
        return False

    marker_groups = (
        ("telegram_bot.telegram_agent",),
        ("telegram_agent.py",),
        ("deploy.windows.release_backend", "run-daemon"),
        ("emploaibackend.exe", "run-daemon"),
    )
    return any(all(marker in normalized for marker in markers) for markers in marker_groups)


def _process_ids_for_port(port: int) -> set[int]:
    if port <= 0:
        return set()

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids: set[int] = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5 or parts[0].upper() != "TCP":
                    continue
                local_address = parts[1]
                state = parts[3].upper()
                pid_text = parts[4]
                if state != "LISTENING":
                    continue
                if local_address.rsplit(":", 1)[-1] != str(port):
                    continue
                try:
                    pids.add(int(pid_text))
                except ValueError:
                    continue
            return pids

        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            int(line.strip())
            for line in result.stdout.splitlines()
            if line.strip().isdigit()
        }
    except Exception:
        return set()


def _managed_runtime_pids(home: Path, config: DesktopRuntimeConfig, *, status: Any | None = None) -> list[int]:
    record = _read_pid_record(home)
    status = status or get_runtime_status()
    pids: set[int] = set()

    recorded_pid = int(record.get("pid") or 0) if record else 0
    if recorded_pid and _process_exists(recorded_pid):
        pids.add(recorded_pid)

    health_pid = _runtime_health_process_id(status)
    if health_pid and _process_exists(health_pid):
        pids.add(health_pid)

    for port_pid in _process_ids_for_port(int(config.port or 0)):
        if not _process_exists(port_pid):
            continue
        if port_pid in pids or _is_runtime_process(port_pid):
            pids.add(port_pid)

    return sorted(pids)


def _runtime_compatibility_issue(
    home: Path,
    config: DesktopRuntimeConfig,
    status: Any,
    *,
    telegram_enabled: bool,
    telegram_configured: bool,
) -> str | None:
    if not getattr(status, "ok", False):
        return None
    if not (telegram_enabled and telegram_configured):
        return None

    record = _read_pid_record(home)
    if record:
        mode = str(record.get("mode") or "").strip()
        if mode == "telegram+app":
            return None
        if mode == "desktop-app-only":
            return (
                "Local runtime is running in desktop-app-only mode. Stop it and start the managed "
                "local runtime so Telegram and desktop share one live session."
            )

    active_pids = _managed_runtime_pids(home, config, status=status)
    for pid in active_pids:
        if _is_telegram_capable_runtime_command_line(_process_command_line(pid)):
            return None

    return (
        "Local runtime is attached to an app-only server. Stop it and start the managed local "
        "runtime so Telegram and desktop share one live session."
    )


def _bootstrap_payload(*, launch_if_needed: bool = False, force_launch: bool = False) -> dict[str, Any]:
    root, home, env_file, existing = _prepare_environment()
    try:
        ensure_requested_voice_packs(config_path=home / "config.json")
    except Exception:
        pass
    setup_state = build_setup_state(
        home=home,
        env_file=env_file,
        source_root=root,
        existing=existing,
    )
    config = load_desktop_runtime_config()
    status = get_runtime_status()
    runtime_mode = status.mode
    telegram_enabled = bool(configure_channels_enabled("telegram"))
    telegram_configured = bool(existing.get("TELEGRAM_BOT_TOKEN") and existing.get("ALLOWED_USER_IDS"))
    compatibility_issue = _runtime_compatibility_issue(
        home,
        config,
        status,
        telegram_enabled=telegram_enabled,
        telegram_configured=telegram_configured,
    )

    should_try_launch = not setup_state["required"] and config.enabled and (
        not status.ok or bool(compatibility_issue)
    ) and (
        force_launch or launch_if_needed
    )
    if should_try_launch:
        try:
            if compatibility_issue:
                _stop_runtime(home, config)
                time.sleep(0.6)
            status, runtime_mode = _ensure_runtime(config, home, require_auto_start=not force_launch)
            compatibility_issue = _runtime_compatibility_issue(
                home,
                config,
                status,
                telegram_enabled=telegram_enabled,
                telegram_configured=telegram_configured,
            )
        except RuntimeError as exc:
            status = get_runtime_status()
            status.detail = str(exc)
            try:
                status.state = "failed"
            except Exception:
                pass
            try:
                status.degraded = True
            except Exception:
                pass
            runtime_mode = "detached"
            compatibility_issue = _runtime_compatibility_issue(
                home,
                config,
                status,
                telegram_enabled=telegram_enabled,
                telegram_configured=telegram_configured,
            )

    managed_runtime_pids = _managed_runtime_pids(home, config, status=status)

    if compatibility_issue:
        try:
            status.ok = False
        except Exception:
            pass
        try:
            status.state = "incompatible"
        except Exception:
            pass
        try:
            status.degraded = True
        except Exception:
            pass
        try:
            status.detail = compatibility_issue
        except Exception:
            pass

    access_token = ""
    current_session_id: str | None = None
    device_id: str | None = None
    if status.ok:
        workspace = Path(config.workspace)
        current_session_id = _ensure_current_session_id(workspace)
        token_payload = _ensure_desktop_token()
        access_token = str(token_payload["access_token"])
        device_id = str(token_payload["device_id"])

    return {
        "ok": True,
        "apiBaseUrl": config.api_base_url,
        "accessToken": access_token,
        "currentSessionId": current_session_id,
        "runtimeMode": runtime_mode,
        "runtimeStatus": asdict(status),
        "deviceId": device_id,
        "userId": _default_user_id(),
        "runtimeAvailable": bool(status.ok),
        "canLaunchLocalRuntime": bool(config.enabled and not setup_state["required"]),
        "runtimeProcessDetected": bool(managed_runtime_pids),
        "workspaceRoot": config.workspace,
        "runtimeHome": str(home),
        "envFilePath": str(env_file),
        "desktopLogPath": str(_runtime_log_path(home)),
        "releaseVersion": current_release_version(root),
        "setupState": setup_state,
    }


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in result.stdout
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return


def _stop_runtime(home: Path, config: DesktopRuntimeConfig | None = None) -> dict[str, Any]:
    config = config or load_desktop_runtime_config()
    managed_pids = _managed_runtime_pids(home, config)
    remaining = set(managed_pids)

    for pid in managed_pids:
        _terminate_pid(pid)

    deadline = time.monotonic() + 10
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if _process_exists(pid)}
        if not remaining:
            break
        time.sleep(0.25)

    _runtime_pid_path(home).unlink(missing_ok=True)
    return {
        "ok": True,
        "stopped": not remaining,
        "pid": managed_pids[0] if len(managed_pids) == 1 else None,
        "pids": managed_pids,
        "remainingPids": sorted(remaining),
    }


def _runtime_is_managed(home: Path, config: DesktopRuntimeConfig | None = None) -> bool:
    config = config or load_desktop_runtime_config()
    return bool(_managed_runtime_pids(home, config))


def _daemon_mode_for_desktop_runtime(*, telegram_enabled: bool, telegram_configured: bool) -> str:
    return "telegram+app" if telegram_enabled and telegram_configured else "desktop-app-only"


def _save_setup(launch_if_needed: bool) -> dict[str, Any]:
    root, home, env_file, existing = _prepare_environment()
    config = load_desktop_runtime_config()
    payload = json.loads(sys.stdin.read() or "{}")
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        values = payload if isinstance(payload, dict) else {}

    status_before_save = get_runtime_status()
    was_running = _runtime_is_managed(home, config) or bool(status_before_save.ok)
    if was_running:
        _stop_runtime(home, config)
        time.sleep(0.6)

    save_setup_values(
        home=home,
        env_file=env_file,
        source_root=root,
        existing=existing,
        updates={key: str(value or "") for key, value in values.items()},
    )
    return _bootstrap_payload(
        launch_if_needed=launch_if_needed,
        force_launch=was_running,
    )


def _voice_pack_action(pack_id: str, *, install: bool) -> dict[str, Any]:
    if pack_id not in VOICE_PACK_IDS:
        raise RuntimeError(f"Unsupported voice pack: {pack_id}")

    _, home, _, _ = _prepare_environment()
    config = load_desktop_runtime_config()
    status_before_action = get_runtime_status()
    was_running = _runtime_is_managed(home, config) or bool(status_before_action.ok)
    if was_running:
        _stop_runtime(home, config)
        time.sleep(0.6)

    if install:
        install_voice_pack(pack_id)
        update_voice_pack_preferences(home=home, pack_id=pack_id, requested=True)
    else:
        runtime_config = load_runtime_config(home)
        voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
        current_default = str(voice_config.get("default_engine") or "").strip().lower()
        next_default = current_default
        if current_default == pack_id:
            next_default = VOICE_ENGINE_HEBREW if pack_id == VOICE_ENGINE_ENGLISH else VOICE_ENGINE_ENGLISH
        update_voice_pack_preferences(home=home, pack_id=pack_id, requested=False, default_engine=next_default)
        remove_voice_pack(pack_id)

    return _bootstrap_payload(
        launch_if_needed=True,
        force_launch=was_running,
    )


def _forward_voice_bridge(args: list[str]) -> int:
    home = runtime_home()
    env_file = env_path(home)
    configure_process_environment(home, env_file)
    whisper_live = importlib.import_module("mobile_app.backend.whisper_cpp_live")
    previous_argv = list(sys.argv)
    try:
        sys.argv = [previous_argv[0], *args]
        return int(whisper_live.main())
    finally:
        sys.argv = previous_argv


def _run_daemon(host: str | None, port: int | None) -> int:
    root, home, env_file, existing = _prepare_environment()
    config = load_desktop_runtime_config()
    run_host = str(host or config.host or DEFAULT_DESKTOP_HOST)
    run_port = int(port or config.port or DEFAULT_DESKTOP_PORT)
    telegram_enabled = bool(configure_channels_enabled("telegram"))
    telegram_configured = bool(existing.get("TELEGRAM_BOT_TOKEN") and existing.get("ALLOWED_USER_IDS"))
    mode = _daemon_mode_for_desktop_runtime(
        telegram_enabled=telegram_enabled,
        telegram_configured=telegram_configured,
    )

    _write_pid_record(home, mode=mode, host=run_host, port=run_port)
    atexit.register(_clear_pid_record, home)

    if mode == "telegram+app":
        from telegram_bot.telegram_agent import main as telegram_main

        print("Starting EmploAI backend in telegram+app mode", flush=True)
        previous_force_flag = os.environ.get("EMPLOAI_DESKTOP_FORCE_APP_SERVER")
        os.environ["EMPLOAI_DESKTOP_FORCE_APP_SERVER"] = "1"
        try:
            telegram_main()
            return 0
        finally:
            if previous_force_flag is None:
                os.environ.pop("EMPLOAI_DESKTOP_FORCE_APP_SERVER", None)
            else:
                os.environ["EMPLOAI_DESKTOP_FORCE_APP_SERVER"] = previous_force_flag

    print("Starting EmploAI backend in desktop-app-only mode", flush=True)
    asyncio.run(run_desktop_runtime_server(host=run_host, port=run_port))
    return 0


def configure_channels_enabled(channel_name: str) -> bool:
    config = load_desktop_runtime_config()
    if channel_name == "telegram":
        workspace = Path(config.workspace)
        config_path = workspace / "config.json"
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return channel_name in {"desktop", "app"}
        channels = payload.get("channels") or {}
        channel = channels.get(channel_name) or {}
        return bool(channel.get("enabled", channel_name in {"desktop", "app"}))
    if channel_name == "desktop":
        return bool(config.enabled)
    if channel_name == "app":
        workspace = Path(config.workspace)
        config_path = workspace / "config.json"
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return True
        channels = payload.get("channels") or {}
        channel = channels.get("app") or {}
        return bool(channel.get("enabled", True))
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows release backend helper for the EmploAI desktop app.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="prepare desktop bootstrap state")
    bootstrap_parser.add_argument("--launch-if-needed", action="store_true")

    subparsers.add_parser("start", help="launch the local runtime if needed and print bootstrap JSON")
    subparsers.add_parser("stop", help="stop the managed local runtime and print bootstrap JSON")
    subparsers.add_parser("status", help="print the current runtime status JSON")
    subparsers.add_parser("setup-state", help="print the current setup state JSON")

    save_setup_parser = subparsers.add_parser("save-setup", help="save setup JSON from stdin and print bootstrap JSON")
    save_setup_parser.add_argument("--launch-if-needed", action="store_true")

    voice_pack_install_parser = subparsers.add_parser("install-voice-pack", help="install a managed voice pack and print bootstrap JSON")
    voice_pack_install_parser.add_argument("--pack", required=True, choices=VOICE_PACK_IDS)

    voice_pack_remove_parser = subparsers.add_parser("remove-voice-pack", help="remove a managed voice pack and print bootstrap JSON")
    voice_pack_remove_parser.add_argument("--pack", required=True, choices=VOICE_PACK_IDS)

    updates_parser = subparsers.add_parser("check-updates", help="check for release updates and print JSON")
    updates_parser.add_argument("--force", action="store_true")

    subparsers.add_parser("install-update", help="download and launch the latest MSI update")

    voice_bridge_parser = subparsers.add_parser("voice-bridge", help="forward commands into the standalone whisper live bridge")
    voice_bridge_parser.add_argument("voice_args", nargs=argparse.REMAINDER)

    run_parser = subparsers.add_parser("run-daemon", help="run the managed local runtime daemon")
    run_parser.add_argument("--host", default=None)
    run_parser.add_argument("--port", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv if argv is not None else sys.argv[1:])
    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    if args.command == "bootstrap":
        return _json_print(_bootstrap_payload(launch_if_needed=bool(args.launch_if_needed)))

    if args.command == "start":
        return _json_print(_bootstrap_payload(force_launch=True))

    if args.command == "stop":
        _prepare_environment()
        _, home, _ = _runtime_paths()
        _stop_runtime(home)
        return _json_print(_bootstrap_payload(launch_if_needed=False))

    if args.command == "status":
        _prepare_environment()
        return _json_print(asdict(get_runtime_status()))

    if args.command == "setup-state":
        root, home, env_file, existing = _prepare_environment()
        return _json_print(
            build_setup_state(
                home=home,
                env_file=env_file,
                source_root=root,
                existing=existing,
            )
        )

    if args.command == "save-setup":
        return _json_print(_save_setup(launch_if_needed=bool(args.launch_if_needed)))

    if args.command == "install-voice-pack":
        return _json_print(_voice_pack_action(str(args.pack), install=True))

    if args.command == "remove-voice-pack":
        return _json_print(_voice_pack_action(str(args.pack), install=False))

    if args.command == "check-updates":
        root, home, _ = _runtime_paths()
        return _json_print(check_for_updates(home, root, force=bool(args.force)))

    if args.command == "install-update":
        root, home, _ = _runtime_paths()
        return _json_print(install_latest_update(home, root))

    if args.command == "voice-bridge":
        return _forward_voice_bridge(list(args.voice_args or []))

    if args.command == "run-daemon":
        return _run_daemon(args.host, args.port)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
