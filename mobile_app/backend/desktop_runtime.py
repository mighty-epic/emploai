from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

from mobile_app.backend.auth_store import AppAuthStore
from shared.live_config import get_live_config
from shared.runtime_paths import log_root, runtime_home

if TYPE_CHECKING:
    from mobile_app.backend.session_bridge import AppSessionBridge


DEFAULT_DESKTOP_HOST = "127.0.0.1"
DEFAULT_DESKTOP_PORT = 8787
DEFAULT_ATTACH_TIMEOUT_SECONDS = 25
DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS = 10
READINESS_POLL_INTERVAL_SECONDS = 0.25
DEFAULT_DEVICE_NAME = "EmploAI Desktop"
DEFAULT_DEVICE_PLATFORM = "desktop-electron"
DEFAULT_DEVICE_KEY = "desktop-local"
DEFAULT_APP_USER_ID = 0
REMOTE_ACCOUNT_SESSION_FILENAME = "remote-account-session.json"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 180
logger = logging.getLogger(__name__)


@dataclass
class DesktopRuntimeConfig:
    enabled: bool
    host: str
    port: int
    auto_start: bool
    attach_timeout_seconds: int
    restart_attach_timeout_seconds: int
    workspace: str

    @property
    def api_base_url(self) -> str:
        host = self.host.strip() or DEFAULT_DESKTOP_HOST
        if host in {"0.0.0.0", "::", "[::]"}:
            host = "127.0.0.1"
        return f"http://{host}:{self.port}"


@dataclass
class DesktopRuntimeStatus:
    ok: bool
    state: str
    mode: str
    api_base_url: str
    runtime_home: Optional[str] = None
    startup_state: Optional[str] = None
    degraded: bool = False
    issues: list[str] | None = None
    detail: Optional[str] = None
    process_id: Optional[int] = None


def _load_workspace() -> Path:
    workspace = _workspace_root()
    load_dotenv(workspace / ".env", override=False)
    load_dotenv(override=False)
    return workspace


def _workspace_root() -> Path:
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _remote_account_user_id() -> int | None:
    home = runtime_home() or _runtime_home()
    path = home / REMOTE_ACCOUNT_SESSION_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    raw_user_id = user.get("user_id") or payload.get("user_id")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None


def _default_user_id() -> int:
    return _remote_account_user_id() or DEFAULT_APP_USER_ID


def load_desktop_runtime_config() -> DesktopRuntimeConfig:
    workspace = _load_workspace()
    config = get_live_config(workspace / "config.json")
    desktop_enabled = bool(config.get("channels.desktop.enabled", True))
    host = str(config.get("channels.desktop.host", DEFAULT_DESKTOP_HOST) or DEFAULT_DESKTOP_HOST)
    port = int(config.get("channels.desktop.port", config.get("channels.app.port", DEFAULT_DESKTOP_PORT) or DEFAULT_DESKTOP_PORT))
    auto_start = bool(config.get("channels.desktop.auto_start", False))
    attach_timeout_seconds = int(
        config.get("channels.desktop.attach_timeout_seconds", DEFAULT_ATTACH_TIMEOUT_SECONDS)
        or DEFAULT_ATTACH_TIMEOUT_SECONDS
    )
    restart_attach_timeout_seconds = int(
        config.get(
            "channels.desktop.restart_attach_timeout_seconds",
            min(DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS, attach_timeout_seconds),
        )
        or min(DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS, attach_timeout_seconds)
    )
    return DesktopRuntimeConfig(
        enabled=desktop_enabled,
        host=host,
        port=port,
        auto_start=auto_start,
        attach_timeout_seconds=max(2, attach_timeout_seconds),
        restart_attach_timeout_seconds=max(2, restart_attach_timeout_seconds),
        workspace=str(workspace),
    )


def _port_accepts_connections(url: str, *, timeout_seconds: float = 0.25) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=max(0.05, timeout_seconds)):
            return True
    except OSError:
        return False


def _healthcheck(url: str, timeout_seconds: float = 0.75) -> Optional[dict[str, Any]]:
    if not _port_accepts_connections(url, timeout_seconds=min(timeout_seconds, 0.25)):
        return None

    request = urllib.request.Request(url=f"{url.rstrip('/')}/api/app/health?shallow=1", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                return payload
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    return None


def get_runtime_status() -> DesktopRuntimeStatus:
    config = load_desktop_runtime_config()
    if not config.enabled:
        return DesktopRuntimeStatus(
            ok=False,
            state="disabled",
            mode="disabled",
            api_base_url=config.api_base_url,
            detail="Desktop channel is disabled in config.json",
        )

    payload = _healthcheck(config.api_base_url)
    if not payload:
        return DesktopRuntimeStatus(
            ok=False,
            state="offline",
            mode="detached",
            api_base_url=config.api_base_url,
            detail="No compatible local runtime responded on the configured desktop host/port",
        )

    payload_runtime_home = str(payload.get("runtime_home") or "").strip()
    expected_runtime_home = str(runtime_home() or "").strip()
    if payload_runtime_home and expected_runtime_home:
        try:
            payload_runtime_home = str(Path(payload_runtime_home).expanduser().resolve())
            expected_runtime_home = str(Path(expected_runtime_home).expanduser().resolve())
        except Exception:
            pass
        if os.path.normcase(payload_runtime_home) != os.path.normcase(expected_runtime_home):
            return DesktopRuntimeStatus(
                ok=False,
                state="offline",
                mode="detached",
                api_base_url=config.api_base_url,
                runtime_home=payload_runtime_home,
                detail=(
                    "A local runtime responded on the configured desktop port, but it belongs to a "
                    "different runtime home. Restart the desktop runtime so this app uses the correct local state."
                ),
                process_id=int(payload.get("process_id") or 0) or None,
            )

    dependency_status = payload.get("dependency_status") or {}
    degraded = bool(dependency_status.get("degraded"))
    issues = [str(item) for item in dependency_status.get("issues", [])]
    state = "degraded" if degraded else "ready"
    return DesktopRuntimeStatus(
        ok=True,
        state=state,
        mode="attached",
        api_base_url=config.api_base_url,
        runtime_home=payload_runtime_home or None,
        startup_state=str(payload.get("startup_state") or ""),
        degraded=degraded,
        issues=issues,
        process_id=int(payload.get("process_id") or 0) or None,
    )


def _desktop_log_path() -> Path:
    home = log_root()
    home.mkdir(parents=True, exist_ok=True)
    return home / "desktop_runtime.log"


def _runtime_home() -> Path:
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _load_workspace()


def _env_file_path() -> Path:
    runtime_home = _runtime_home()
    env_path = runtime_home / ".env"
    if env_path.exists():
        return env_path
    return _load_workspace() / ".env"


def launch_detached_runtime(config: DesktopRuntimeConfig) -> None:
    workspace = Path(config.workspace)
    log_path = _desktop_log_path()
    command = [
        sys.executable,
        "-m",
        "mobile_app.backend.desktop_runtime",
        "run",
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    env = os.environ.copy()
    env.setdefault("EMPLOAI_DESKTOP_RUNTIME", "1")

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    with log_path.open("a", encoding="utf-8") as handle:
        subprocess.Popen(
            command,
            cwd=str(workspace),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creationflags,
        )


def _wait_for_runtime(config: DesktopRuntimeConfig, *, timeout_seconds: int) -> tuple[DesktopRuntimeStatus, str]:
    deadline = time.monotonic() + max(2, timeout_seconds)
    last_status = get_runtime_status()
    while time.monotonic() < deadline:
        time.sleep(READINESS_POLL_INTERVAL_SECONDS)
        last_status = get_runtime_status()
        if last_status.ok:
            return last_status, "launched"
    return last_status, "detached"


def ensure_runtime(*, require_auto_start: bool = True) -> tuple[DesktopRuntimeConfig, DesktopRuntimeStatus, str]:
    config = load_desktop_runtime_config()
    status = get_runtime_status()
    if status.ok:
        return config, status, "attached"

    if not config.enabled:
        raise RuntimeError(status.detail or "Desktop channel is disabled")
    if require_auto_start and not config.auto_start:
        raise RuntimeError("Desktop runtime is offline and auto-start is disabled")

    launch_detached_runtime(config)
    status, mode = _wait_for_runtime(config, timeout_seconds=config.attach_timeout_seconds)
    if status.ok:
        return config, status, mode

    launch_detached_runtime(config)
    status, mode = _wait_for_runtime(config, timeout_seconds=config.restart_attach_timeout_seconds)
    if status.ok:
        return config, status, "recovered"

    raise RuntimeError(
        f"Desktop runtime did not become ready within {config.attach_timeout_seconds} seconds. "
        f"See {_desktop_log_path()} for startup logs."
    )


def _bootstrap_payload(
    config: DesktopRuntimeConfig,
    status: DesktopRuntimeStatus,
    *,
    runtime_mode: str,
    access_token: str = "",
    current_session_id: Optional[str] = None,
    device_id: Optional[str] = None,
) -> dict[str, Any]:
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
        "canLaunchLocalRuntime": bool(config.enabled),
        "workspaceRoot": config.workspace,
        "runtimeHome": str(_runtime_home()),
        "envFilePath": str(_env_file_path()),
        "desktopLogPath": str(_desktop_log_path()),
    }


def _offline_bootstrap(config: DesktopRuntimeConfig, status: DesktopRuntimeStatus, *, runtime_mode: str) -> dict[str, Any]:
    return _bootstrap_payload(
        config,
        status,
        runtime_mode=runtime_mode,
        access_token="",
        current_session_id=None,
        device_id=None,
    )


def _bridge() -> AppSessionBridge:
    workspace = _load_workspace()
    from mobile_app.backend.session_bridge import AppSessionBridge

    return AppSessionBridge(user_id=_default_user_id(), workspace=workspace)


def _current_session_id(bridge: AppSessionBridge) -> Optional[str]:
    current = bridge.get_current_session()
    if current:
        return current.id
    return None


def _ensure_desktop_token() -> dict[str, Any]:
    store = AppAuthStore()
    return store.ensure_device_token(
        user_id=_default_user_id(),
        device_name=DEFAULT_DEVICE_NAME,
        device_platform=DEFAULT_DEVICE_PLATFORM,
        token_ttl_seconds=TOKEN_TTL_SECONDS,
        device_key=DEFAULT_DEVICE_KEY,
    )


def bootstrap_context(*, launch_if_needed: bool = False) -> dict[str, Any]:
    config = load_desktop_runtime_config()
    status = get_runtime_status()
    runtime_mode = status.mode

    if launch_if_needed and not status.ok and config.enabled and config.auto_start:
        try:
            config, status, runtime_mode = ensure_runtime()
        except RuntimeError as exc:
            status = get_runtime_status()
            if not status.detail:
                status.detail = str(exc)
            return _offline_bootstrap(config, status, runtime_mode="detached")
    elif not status.ok:
        return _offline_bootstrap(config, status, runtime_mode="detached")

    bridge = _bridge()
    session_id = _current_session_id(bridge)
    token_payload = _ensure_desktop_token()
    return _bootstrap_payload(
        config,
        status,
        runtime_mode=runtime_mode,
        access_token=token_payload["access_token"],
        current_session_id=session_id,
        device_id=token_payload["device_id"],
    )


def start_runtime_context() -> dict[str, Any]:
    config = load_desktop_runtime_config()
    try:
        config, status, runtime_mode = ensure_runtime(require_auto_start=False)
    except RuntimeError as exc:
        status = get_runtime_status()
        if not status.detail:
            status.detail = str(exc)
        return _offline_bootstrap(config, status, runtime_mode="detached")

    bridge = _bridge()
    session_id = _current_session_id(bridge)
    token_payload = _ensure_desktop_token()
    return _bootstrap_payload(
        config,
        status,
        runtime_mode=runtime_mode,
        access_token=token_payload["access_token"],
        current_session_id=session_id,
        device_id=token_payload["device_id"],
    )


async def run_desktop_runtime_server(host: str, port: int) -> None:
    import uvicorn
    from mobile_app.backend.app_server import create_app

    async def _start_background_services() -> None:
        try:
            from mobile_app.backend.cron_runtime import ensure_global_cron_scheduler_started

            await ensure_global_cron_scheduler_started()
        except Exception:
            logger.exception("Desktop runtime background service startup failed")

    asyncio.create_task(_start_background_services())
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            loop="asyncio",
            http="h11",
            ws="websockets",
        )
    )
    await server.serve()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop runtime helper for the Electron shell.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run the local desktop runtime")
    run_parser.add_argument("--host", default=None)
    run_parser.add_argument("--port", type=int, default=None)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="inspect desktop bootstrap state and print JSON")
    bootstrap_parser.add_argument("--launch-if-needed", action="store_true")
    subparsers.add_parser("start", help="launch the local runtime if needed and print bootstrap JSON")
    subparsers.add_parser("status", help="print the current runtime status JSON")
    subparsers.add_parser("remote-control", help="connect the local desktop runtime to the remote control plane")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        config = load_desktop_runtime_config()
        host = str(args.host or config.host)
        port = int(args.port or config.port)
        asyncio.run(run_desktop_runtime_server(host=host, port=port))
        return 0

    if args.command == "bootstrap":
        print(json.dumps(bootstrap_context(launch_if_needed=bool(args.launch_if_needed))))
        return 0

    if args.command == "start":
        print(json.dumps(start_runtime_context()))
        return 0

    if args.command == "status":
        print(json.dumps(asdict(get_runtime_status())))
        return 0

    if args.command == "remote-control":
        from mobile_app.backend.remote_desktop_client import main as remote_control_main

        return int(remote_control_main([]))

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
