from __future__ import annotations

import os
import json
import subprocess
import time
from pathlib import Path
from typing import Any


FLEET_HOST_PROTOCOL_VERSION = 2
_HOST_STARTED_AT = time.time()


def _source_root() -> Path:
    from desktop_runtime.config import bundle_root

    return Path(bundle_root()).resolve()


def _release_version() -> str:
    from desktop_runtime.config import current_release_version

    try:
        return str(current_release_version(_source_root()) or "dev")
    except Exception:
        return "dev"


def _runtime_view(*, launch: bool = False) -> dict[str, Any]:
    from app_backend.local_runtime_server import bootstrap_context, start_runtime_context

    bootstrap = start_runtime_context() if launch else bootstrap_context(launch_if_needed=False)
    status = bootstrap.get("runtimeStatus") if isinstance(bootstrap.get("runtimeStatus"), dict) else {}
    ready = bool(bootstrap.get("runtimeAvailable")) and bool(status.get("ok"))
    return {
        "state": str(status.get("state") or ("ready" if ready else "offline")),
        "ready": ready,
        "process_id": int(status.get("process_id") or 0) or None,
        "detail": str(status.get("detail") or "").strip() or None,
    }


def _electron_executable() -> Path | None:
    root = _source_root()
    if os.name == "nt":
        candidate = root / "desktop_app" / "node_modules" / "electron" / "dist" / "electron.exe"
    else:
        candidate = root / "desktop_app" / "node_modules" / "electron" / "dist" / "electron"
    return candidate if candidate.exists() else None


def _desktop_process_ids() -> list[int]:
    home = Path(os.environ.get("EMPLOAI_HOME") or _source_root()).resolve()
    record_path = home / "desktop_shell.pid.json"
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []
    if pid <= 0:
        return []
    try:
        from desktop_runtime.fleet_host import _process_exists

        return [pid] if pid != os.getpid() and _process_exists(pid) else []
    except Exception:
        return []


def _desktop_view() -> dict[str, Any]:
    executable = _electron_executable()
    process_ids = _desktop_process_ids()
    return {
        "state": "running" if process_ids else "stopped",
        "running": bool(process_ids),
        "process_ids": process_ids,
        "start_supported": bool(executable),
        "detail": (
            "The EmploAI desktop window is running."
            if process_ids
            else "The EmploAI desktop window is closed."
        ),
    }


def _update_view() -> dict[str, Any]:
    from desktop_runtime.fleet_update import fleet_update_status
    from shared.runtime_paths import runtime_home

    home = runtime_home()
    if not home:
        return {"supported": False, "state": "unavailable", "active": False}
    return fleet_update_status(home, _source_root())


def fleet_host_status() -> dict[str, Any]:
    return {
        "protocol_version": FLEET_HOST_PROTOCOL_VERSION,
        "app_version": _release_version(),
        "host": {
            "state": "running",
            "process_id": os.getpid(),
            "uptime_seconds": max(0, int(time.time() - _HOST_STARTED_AT)),
            "detail": "The persistent Yggdrasil host is available independently of the app runtime.",
        },
        "runtime": _runtime_view(),
        "desktop": _desktop_view(),
        "update": _update_view(),
    }


def fleet_host_capabilities() -> dict[str, Any]:
    status = fleet_host_status()
    return {
        "fleet_protocol_version": 2,
        "app_version": status["app_version"],
        "host_control": {
            "protocol_version": FLEET_HOST_PROTOCOL_VERSION,
            "runtime_status": True,
            "start_runtime": True,
            "start_desktop": bool(status["desktop"]["start_supported"]),
            "update_status": True,
            "check_update": bool(status["update"]["supported"]),
            "start_update": bool(status["update"]["supported"]),
            "runtime_state": status["runtime"]["state"],
            "desktop_state": status["desktop"]["state"],
            "update_state": status["update"]["state"],
        },
    }


def check_update_from_fleet_host() -> dict[str, Any]:
    from desktop_runtime.fleet_update import check_fleet_update
    from shared.runtime_paths import runtime_home

    home = runtime_home()
    if not home:
        raise RuntimeError("The EmploAI runtime home is unavailable")
    return check_fleet_update(home, _source_root())


def start_update_from_fleet_host(*, expected_commit: str) -> dict[str, Any]:
    from desktop_runtime.fleet_update import start_fleet_update
    from shared.runtime_paths import runtime_home

    home = runtime_home()
    if not home:
        raise RuntimeError("The EmploAI runtime home is unavailable")
    return start_fleet_update(
        home,
        _source_root(),
        expected_commit=expected_commit,
        host_pid=os.getpid(),
    )


def start_runtime_from_fleet_host() -> dict[str, Any]:
    runtime = _runtime_view(launch=True)
    if not runtime["ready"]:
        raise RuntimeError(runtime.get("detail") or "The EmploAI backend did not become ready")
    return fleet_host_status()


def start_desktop_from_fleet_host() -> dict[str, Any]:
    start_runtime_from_fleet_host()
    current = _desktop_view()
    if current["running"]:
        return fleet_host_status()

    root = _source_root()
    desktop_dir = root / "desktop_app"
    renderer_index = desktop_dir / "renderer_client" / "dist" / "index.html"
    executable = _electron_executable()
    if not executable:
        raise RuntimeError("Electron is not installed for this EmploAI checkout. Run npm run setup on that computer.")
    if not renderer_index.exists():
        raise RuntimeError("The desktop renderer is not built. Update EmploAI or run npm run desktop:build-renderer on that computer.")

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    log_dir = Path(os.environ.get("EMPLOAI_HOME") or root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "fleet_desktop_launch.log"
    with log_path.open("a", encoding="utf-8") as handle:
        subprocess.Popen(
            [str(executable), "."],
            cwd=str(desktop_dir),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creationflags,
        )

    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        if _desktop_process_ids():
            return fleet_host_status()
        time.sleep(0.25)
    raise RuntimeError(f"The desktop process was launched but did not become visible. See {log_path}")
