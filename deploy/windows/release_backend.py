from __future__ import annotations

import argparse
import asyncio
import atexit
import hashlib
import importlib
import json
import os
import shutil
import socket
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from mobile_app.backend.auth_store import AppAuthStore
from mobile_app.backend.voice_pack_manager import (
    ALLOW_DEV_VOICE_PACK_SOURCES_ENV,
    APP_STT_ENGLISH_PACK_REPO_ENV,
    APP_STT_HEBREW_MODEL_REPO_ENV,
    ENGLISH_PACK_ARCHIVE_URL_ENV,
    ENGLISH_PACK_REVISION_ENV,
    HEBREW_PACK_ARCHIVE_URL_ENV,
    HEBREW_PACK_REVISION_ENV,
    VOICE_ENGINE_ENGLISH,
    VOICE_ENGINE_HEBREW,
    VOICE_PACK_IDS,
    get_voice_pack_status,
    install_voice_pack,
    managed_voice_packs_root,
    remove_voice_pack,
)

from deploy.windows.release_runtime import (
    RUNTIME_DATA_SCHEMA_STATE_KEY,
    RUNTIME_DATA_SCHEMA_VERSION,
    apply_telegram_rebind_gate,
    build_setup_state,
    bundle_root,
    configure_process_environment,
    current_release_version,
    ensure_runtime_files,
    env_path,
    apply_installer_voice_pack_preferences,
    load_existing_env_values,
    load_release_state,
    load_runtime_config,
    runtime_home,
    save_setup_values,
    save_runtime_config,
    should_require_telegram_rebind,
    update_voice_pack_preferences,
    VOICE_ENGINE_NONE,
)
from deploy.windows.release_update import check_for_updates, install_latest_update

if TYPE_CHECKING:
    from mobile_app.backend.session_bridge import AppSessionBridge


RUNTIME_PID_FILENAME = "desktop_runtime.pid.json"
RUNTIME_LOG_FILENAME = "desktop_runtime.log"
TELEGRAM_RUNTIME_PID_FILENAME = "desktop_telegram_runtime.pid.json"
TELEGRAM_RUNTIME_LOG_FILENAME = "desktop_telegram_runtime.log"
TELEGRAM_RUNTIME_STATUS_FILENAME = "desktop_telegram_status.json"
REMOTE_CONTROL_RUNTIME_PID_FILENAME = "desktop_remote_control.pid.json"
REMOTE_CONTROL_RUNTIME_LOG_FILENAME = "desktop_remote_control.log"
REMOTE_CONTROL_RUNTIME_STATUS_FILENAME = "desktop_remote_control_status.json"
VOICE_PACK_BOOTSTRAP_REPORT_FILENAME = "installer_voice_pack_bootstrap.json"
DEFAULT_ATTACH_TIMEOUT_SECONDS = 25
DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS = 10
READINESS_POLL_INTERVAL_SECONDS = 0.25
RUNTIME_LOG_TAIL_BYTES = 16384
DEFAULT_DESKTOP_HOST = "127.0.0.1"
DEFAULT_DESKTOP_PORT = 8787
DEFAULT_DEVICE_NAME = "EmploAI Desktop"
DEFAULT_DEVICE_PLATFORM = "desktop-electron"
DEFAULT_DEVICE_KEY = "desktop-local"
DEFAULT_APP_USER_ID = 0
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 180
TELEGRAM_STATUS_PATH_ENV = "EMPLOAI_TELEGRAM_STATUS_PATH"
TELEGRAM_NOTIFY_ON_READY_ENV = "EMPLOAI_TELEGRAM_NOTIFY_ON_READY"
REMOTE_CONTROL_STATUS_PATH_ENV = "EMPLOAI_REMOTE_CONTROL_STATUS_PATH"


def _desktop_runtime_module():
    from mobile_app.backend import desktop_runtime as module

    return module


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
    startup_state: Optional[str] = None
    readiness_scope: Optional[str] = None
    degraded: bool = False
    issues: list[str] | None = None
    detail: Optional[str] = None
    process_id: Optional[int] = None


@dataclass
class TelegramServiceStatus:
    enabled: bool
    configured: bool
    state: str
    detail: Optional[str] = None
    process_id: Optional[int] = None
    log_path: Optional[str] = None
    ready_at: Optional[str] = None


@dataclass
class RemoteControlServiceStatus:
    configured: bool
    state: str
    detail: Optional[str] = None
    process_id: Optional[int] = None
    log_path: Optional[str] = None
    desktop_id: Optional[str] = None
    desktop_name: Optional[str] = None
    ready_at: Optional[str] = None


def _load_desktop_runtime_config():
    home = runtime_home()
    runtime_config = load_runtime_config(home)
    channels = runtime_config.get("channels") if isinstance(runtime_config.get("channels"), dict) else {}
    desktop = channels.get("desktop") if isinstance(channels.get("desktop"), dict) else {}
    app = channels.get("app") if isinstance(channels.get("app"), dict) else {}
    enabled = bool(desktop.get("enabled", True))
    host = str(desktop.get("host", DEFAULT_DESKTOP_HOST) or DEFAULT_DESKTOP_HOST)
    port = int(desktop.get("port", app.get("port", DEFAULT_DESKTOP_PORT) or DEFAULT_DESKTOP_PORT))
    auto_start = bool(desktop.get("auto_start", False))
    attach_timeout_seconds = int(desktop.get("attach_timeout_seconds", DEFAULT_ATTACH_TIMEOUT_SECONDS) or DEFAULT_ATTACH_TIMEOUT_SECONDS)
    restart_attach_timeout_seconds = int(
        desktop.get(
            "restart_attach_timeout_seconds",
            min(DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS, attach_timeout_seconds),
        )
        or min(DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS, attach_timeout_seconds)
    )
    return DesktopRuntimeConfig(
        enabled=enabled,
        host=host,
        port=port,
        auto_start=auto_start,
        attach_timeout_seconds=max(2, attach_timeout_seconds),
        restart_attach_timeout_seconds=max(2, restart_attach_timeout_seconds),
        workspace=str(home),
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


def _get_runtime_status():
    config = _load_desktop_runtime_config()
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

    dependency_status = payload.get("dependency_status") or {}
    degraded = bool(dependency_status.get("degraded"))
    issues = [str(item) for item in dependency_status.get("issues", [])]
    state = "degraded" if degraded else "ready"
    return DesktopRuntimeStatus(
        ok=True,
        state=state,
        mode="attached",
        api_base_url=config.api_base_url,
        startup_state=str(payload.get("startup_state") or ""),
        readiness_scope=str(payload.get("readiness_scope") or "app_api"),
        degraded=degraded,
        issues=issues,
        process_id=int(payload.get("process_id") or 0) or None,
    )


async def _run_desktop_runtime_server(*, host: str, port: int) -> None:
    await _desktop_runtime_module().run_desktop_runtime_server(host=host, port=port)


def _json_print(payload: dict[str, Any]) -> int:
    print(json.dumps(payload))
    return 0


def _stream_print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload), flush=True)


def _emit_voice_pack_progress(
    progress_callback,
    *,
    pack_id: str,
    state: str,
    phase: str,
    message: str,
    percent: float | int | None = None,
    downloaded_bytes: int | None = None,
    total_bytes: int | None = None,
) -> None:
    if progress_callback is None:
        return
    payload: dict[str, Any] = {
        "packId": pack_id,
        "state": state,
        "phase": phase,
        "message": message,
    }
    if percent is not None:
        payload["percent"] = round(float(percent), 1)
    if downloaded_bytes is not None:
        payload["downloadedBytes"] = int(downloaded_bytes)
    if total_bytes is not None:
        payload["totalBytes"] = int(total_bytes)
    progress_callback(payload)


def _runtime_paths() -> tuple[Path, Path, Path]:
    root = bundle_root()
    home = runtime_home()
    state = load_release_state(home)
    try:
        stored_schema = int(state.get(RUNTIME_DATA_SCHEMA_STATE_KEY) or 0)
    except Exception:
        stored_schema = 0
    if stored_schema != RUNTIME_DATA_SCHEMA_VERSION:
        _terminate_stale_managed_processes(home)
    env_file = env_path(home)
    ensure_runtime_files(home, root)
    return root, home, env_file


def _pid_from_record_path(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    try:
        return int(payload.get("pid") or 0)
    except Exception:
        return 0


def _terminate_stale_managed_processes(home: Path) -> None:
    for filename in (RUNTIME_PID_FILENAME, TELEGRAM_RUNTIME_PID_FILENAME):
        path = home / filename
        pid = _pid_from_record_path(path)
        if pid and _process_exists(pid):
            _terminate_pid(pid)
            time.sleep(0.2)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    _clear_telegram_status_record(home)


def _release_info_payload(root: Path) -> dict[str, Any]:
    info_path = root / "deploy" / "windows" / "release_info.json"
    if not info_path.exists():
        return {}
    try:
        payload = json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_hebrew_pack_archive_url(root: Path) -> str:
    payload = _release_info_payload(root)
    explicit_url = str(payload.get("hebrew_voice_pack_archive_url") or "").strip()
    if explicit_url:
        return explicit_url

    github_repo = str(payload.get("github_repo") or "").strip().strip("/")
    asset_name = str(payload.get("hebrew_voice_pack_asset") or "").strip()
    release_tag = str(payload.get("hebrew_voice_pack_release_tag") or payload.get("release_tag") or "").strip()
    if not (github_repo and asset_name and release_tag):
        return ""
    return f"https://github.com/{github_repo}/releases/download/{quote(release_tag)}/{quote(asset_name)}"


def _configure_pack_source_environment(root: Path) -> None:
    payload = _release_info_payload(root)
    managed_release_voice_mode = bool(getattr(sys, "frozen", False)) and os.getenv(
        ALLOW_DEV_VOICE_PACK_SOURCES_ENV,
        "",
    ).strip().lower() not in {"1", "true", "yes", "on"}
    configured_english_repo = str(payload.get("english_voice_pack_repo") or "").strip()
    if managed_release_voice_mode:
        if configured_english_repo:
            os.environ[APP_STT_ENGLISH_PACK_REPO_ENV] = configured_english_repo
        else:
            os.environ.pop(APP_STT_ENGLISH_PACK_REPO_ENV, None)
    elif not os.getenv(APP_STT_ENGLISH_PACK_REPO_ENV, "").strip() and configured_english_repo:
        os.environ[APP_STT_ENGLISH_PACK_REPO_ENV] = configured_english_repo

    configured_english_archive_url = str(payload.get("english_voice_pack_archive_url") or "").strip()
    if managed_release_voice_mode:
        if configured_english_archive_url:
            os.environ[ENGLISH_PACK_ARCHIVE_URL_ENV] = configured_english_archive_url
        else:
            os.environ.pop(ENGLISH_PACK_ARCHIVE_URL_ENV, None)
    elif not os.getenv(ENGLISH_PACK_ARCHIVE_URL_ENV, "").strip() and configured_english_archive_url:
        os.environ[ENGLISH_PACK_ARCHIVE_URL_ENV] = configured_english_archive_url

    configured_english_revision = str(payload.get("english_voice_pack_revision") or "").strip()
    if managed_release_voice_mode:
        if configured_english_revision:
            os.environ[ENGLISH_PACK_REVISION_ENV] = configured_english_revision
        else:
            os.environ.pop(ENGLISH_PACK_REVISION_ENV, None)
    elif not os.getenv(ENGLISH_PACK_REVISION_ENV, "").strip() and configured_english_revision:
        os.environ[ENGLISH_PACK_REVISION_ENV] = configured_english_revision

    configured_hebrew_repo = str(payload.get("hebrew_voice_pack_repo") or "").strip()
    if managed_release_voice_mode:
        if configured_hebrew_repo:
            os.environ[APP_STT_HEBREW_MODEL_REPO_ENV] = configured_hebrew_repo
        else:
            os.environ.pop(APP_STT_HEBREW_MODEL_REPO_ENV, None)
    elif not os.getenv(APP_STT_HEBREW_MODEL_REPO_ENV, "").strip() and configured_hebrew_repo:
        os.environ[APP_STT_HEBREW_MODEL_REPO_ENV] = configured_hebrew_repo

    configured_hebrew_archive_url = str(payload.get("hebrew_voice_pack_archive_url") or "").strip()
    if managed_release_voice_mode:
        if configured_hebrew_archive_url:
            os.environ[HEBREW_PACK_ARCHIVE_URL_ENV] = configured_hebrew_archive_url
        else:
            os.environ.pop(HEBREW_PACK_ARCHIVE_URL_ENV, None)
    elif not os.getenv(HEBREW_PACK_ARCHIVE_URL_ENV, "").strip():
        if configured_hebrew_archive_url:
            os.environ[HEBREW_PACK_ARCHIVE_URL_ENV] = configured_hebrew_archive_url
        elif not (os.getenv(APP_STT_HEBREW_MODEL_REPO_ENV, "").strip() or str(payload.get("hebrew_voice_pack_repo") or "").strip()):
            derived = _default_hebrew_pack_archive_url(root)
            if derived:
                os.environ[HEBREW_PACK_ARCHIVE_URL_ENV] = derived

    configured_revision = str(payload.get("hebrew_voice_pack_revision") or "").strip()
    if managed_release_voice_mode:
        if configured_revision:
            os.environ[HEBREW_PACK_REVISION_ENV] = configured_revision
        else:
            os.environ.pop(HEBREW_PACK_REVISION_ENV, None)
    elif not os.getenv(HEBREW_PACK_REVISION_ENV, "").strip() and configured_revision:
        os.environ[HEBREW_PACK_REVISION_ENV] = configured_revision


def _prepare_environment() -> tuple[Path, Path, Path, dict[str, str]]:
    root, home, env_file = _runtime_paths()
    existing = load_existing_env_values(env_file)
    configure_process_environment(home, env_file)
    _configure_pack_source_environment(root)
    return root, home, env_file, existing


def _effective_release_env_values(
    root: Path,
    home: Path,
    existing: dict[str, str],
    *,
    mark_rebind_required: bool = False,
) -> tuple[dict[str, str], bool]:
    rebind_required = should_require_telegram_rebind(
        home,
        root,
        mark=mark_rebind_required,
    )
    return apply_telegram_rebind_gate(existing, rebind_required=rebind_required), rebind_required


def _runtime_pid_path(home: Path) -> Path:
    return home / RUNTIME_PID_FILENAME


def _runtime_log_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / RUNTIME_LOG_FILENAME


def _telegram_runtime_pid_path(home: Path) -> Path:
    return home / TELEGRAM_RUNTIME_PID_FILENAME


def _telegram_runtime_log_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / TELEGRAM_RUNTIME_LOG_FILENAME


def _telegram_runtime_status_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / TELEGRAM_RUNTIME_STATUS_FILENAME


def _remote_control_runtime_pid_path(home: Path) -> Path:
    return home / REMOTE_CONTROL_RUNTIME_PID_FILENAME


def _remote_control_runtime_log_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / REMOTE_CONTROL_RUNTIME_LOG_FILENAME


def _remote_control_runtime_status_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / REMOTE_CONTROL_RUNTIME_STATUS_FILENAME


def _voice_pack_bootstrap_report_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / VOICE_PACK_BOOTSTRAP_REPORT_FILENAME


def _default_user_id() -> int:
    return DEFAULT_APP_USER_ID


def _normalize_allowed_user_ids(raw_value: str) -> str:
    values = sorted({item.strip() for item in str(raw_value or "").split(",") if item.strip()})
    return ",".join(values)


def _telegram_config_fingerprint(token: str, allowed_user_ids: str) -> str:
    normalized_token = str(token or "").strip()
    normalized_allowed = _normalize_allowed_user_ids(allowed_user_ids)
    if not (normalized_token and normalized_allowed):
        return ""
    payload = f"{normalized_token}\n{normalized_allowed}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _telegram_config_fingerprint_from_values(values: dict[str, str]) -> str:
    return _telegram_config_fingerprint(
        values.get("TELEGRAM_BOT_TOKEN", ""),
        values.get("ALLOWED_USER_IDS", ""),
    )


def _remote_control_config_fingerprint_from_values(values: dict[str, str]) -> str:
    base_url = str(values.get("EMPLOAI_REMOTE_CONTROL_BASE_URL", "") or "").strip().rstrip("/")
    email = str(values.get("EMPLOAI_REMOTE_CONTROL_EMAIL", "") or "").strip().casefold()
    password = str(values.get("EMPLOAI_REMOTE_CONTROL_PASSWORD", "") or "").strip()
    desktop_name = str(values.get("EMPLOAI_REMOTE_DESKTOP_NAME", "") or "").strip() or "EmploAI Desktop"
    desktop_key = str(values.get("EMPLOAI_REMOTE_DESKTOP_KEY", "") or "").strip() or "desktop-default"
    if not (base_url and email and password):
        return ""
    payload = "\n".join([base_url, email, password, desktop_name, desktop_key]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _current_session_id(workspace: Path) -> str | None:
    from mobile_app.backend.session_bridge import AppSessionBridge

    bridge = AppSessionBridge(user_id=_default_user_id(), workspace=workspace)
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


def _read_telegram_pid_record(home: Path) -> dict[str, Any] | None:
    path = _telegram_runtime_pid_path(home)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_remote_control_pid_record(home: Path) -> dict[str, Any] | None:
    path = _remote_control_runtime_pid_path(home)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_pid_record(home: Path, *, mode: str, host: str, port: int) -> None:
    root = bundle_root()
    _runtime_pid_path(home).write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "mode": mode,
                "host": host,
                "port": port,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "releaseVersion": current_release_version(root),
                "executable": str(Path(sys.executable).resolve()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_telegram_pid_record(home: Path, *, config_fingerprint: str | None = None) -> None:
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    _telegram_runtime_pid_path(home).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _write_remote_control_pid_record(home: Path, *, config_fingerprint: str | None = None) -> None:
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    _remote_control_runtime_pid_path(home).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _read_telegram_status_record(home: Path) -> dict[str, Any] | None:
    path = _telegram_runtime_status_path(home)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_remote_control_status_record(home: Path) -> dict[str, Any] | None:
    path = _remote_control_runtime_status_path(home)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_telegram_status_record(
    home: Path,
    *,
    state: str,
    detail: str | None = None,
    ready_at: str | None = None,
    config_fingerprint: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        payload["detail"] = detail
    if ready_at:
        payload["readyAt"] = ready_at
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    _telegram_runtime_status_path(home).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_remote_control_status_record(
    home: Path,
    *,
    state: str,
    detail: str | None = None,
    ready_at: str | None = None,
    config_fingerprint: str | None = None,
    desktop_id: str | None = None,
    desktop_name: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        payload["detail"] = detail
    if ready_at:
        payload["readyAt"] = ready_at
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    if desktop_id:
        payload["desktopId"] = desktop_id
    if desktop_name:
        payload["desktopName"] = desktop_name
    _remote_control_runtime_status_path(home).write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _clear_telegram_pid_record(home: Path) -> None:
    path = _telegram_runtime_pid_path(home)
    record = _read_telegram_pid_record(home)
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


def _clear_remote_control_pid_record(home: Path) -> None:
    path = _remote_control_runtime_pid_path(home)
    record = _read_remote_control_pid_record(home)
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


def _clear_telegram_status_record(home: Path) -> None:
    try:
        _telegram_runtime_status_path(home).unlink(missing_ok=True)
    except Exception:
        pass


def _clear_remote_control_status_record(home: Path) -> None:
    try:
        _remote_control_runtime_status_path(home).unlink(missing_ok=True)
    except Exception:
        pass


def _stop_telegram_worker(home: Path) -> None:
    for pid in _managed_telegram_worker_pids(home):
        _terminate_pid(pid)
        time.sleep(0.2)
    _telegram_runtime_pid_path(home).unlink(missing_ok=True)
    _clear_telegram_status_record(home)


def _stop_remote_control_worker(home: Path) -> None:
    record = _read_remote_control_pid_record(home)
    pid = int(record.get("pid") or 0) if record else 0
    if pid and _process_exists(pid):
        _terminate_pid(pid)
        time.sleep(0.2)
    _remote_control_runtime_pid_path(home).unlink(missing_ok=True)
    _clear_remote_control_status_record(home)


def _launch_detached_daemon(config: "DesktopRuntimeConfig", home: Path) -> None:
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
    env["EMPLOAI_HOME"] = str(home)

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
    log_path.write_text("", encoding="utf-8")
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


def _launch_detached_telegram_worker(home: Path) -> None:
    command = [*_self_command(), "run-telegram-worker", "--home", str(home)]
    env = os.environ.copy()
    env["EMPLOAI_HOME"] = str(home)
    env["EMPLOAI_SKIP_EMBEDDED_APP_SERVER"] = "1"
    env["EMPLOAI_SKIP_CRON_SCHEDULER"] = "1"
    env["EMPLOAI_DESKTOP_TELEGRAM_WORKER"] = "1"
    env[TELEGRAM_STATUS_PATH_ENV] = str(_telegram_runtime_status_path(home))
    env[TELEGRAM_NOTIFY_ON_READY_ENV] = "1"

    launch_cwd = str(home)
    if not getattr(sys, "frozen", False):
        source_root = bundle_root()
        launch_cwd = str(source_root)
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        source_root_text = str(source_root)
        env["PYTHONPATH"] = os.pathsep.join([source_root_text, existing_pythonpath]) if existing_pythonpath else source_root_text

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    log_path = _telegram_runtime_log_path(home)
    log_path.write_text("", encoding="utf-8")
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


def _launch_detached_remote_control_worker(home: Path) -> None:
    command = [*_self_command(), "run-remote-control-worker"]
    env = os.environ.copy()
    env["EMPLOAI_HOME"] = str(home)
    env["EMPLOAI_DESKTOP_REMOTE_CONTROL_WORKER"] = "1"
    env[REMOTE_CONTROL_STATUS_PATH_ENV] = str(_remote_control_runtime_status_path(home))

    launch_cwd = str(home)
    if not getattr(sys, "frozen", False):
        source_root = bundle_root()
        launch_cwd = str(source_root)
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        source_root_text = str(source_root)
        env["PYTHONPATH"] = os.pathsep.join([source_root_text, existing_pythonpath]) if existing_pythonpath else source_root_text

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    log_path = _remote_control_runtime_log_path(home)
    log_path.write_text("", encoding="utf-8")
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


def _tail_text(path: Path, *, max_bytes: int = 8192) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _runtime_log_failure_detail(home: Path) -> str | None:
    tail = _tail_text(_runtime_log_path(home), max_bytes=RUNTIME_LOG_TAIL_BYTES)
    if not tail:
        return None

    text = tail.replace("\r\n", "\n")
    if "Traceback (most recent call last):" in text:
        traceback_lines = text[text.rfind("Traceback (most recent call last):") :].splitlines()
        summary_line = ""
        for line in reversed(traceback_lines):
            candidate = line.strip()
            if not candidate or candidate.startswith("File "):
                continue
            summary_line = candidate
            break
        if summary_line:
            return f"Local runtime crashed during startup: {summary_line}"

    if "Exception in callback" in text:
        exception_lines = text[text.rfind("Exception in callback") :].splitlines()
        for line in reversed(exception_lines):
            candidate = line.strip()
            if not candidate or candidate.startswith("File "):
                continue
            if ":" in candidate or candidate.startswith("Exception"):
                return f"Local runtime crashed during startup: {candidate}"
        return "Local runtime crashed during startup. Check the desktop runtime log for details."

    error_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("ERROR:")]
    if error_lines:
        return f"Local runtime reported a startup error: {error_lines[-1]}"

    return None


def _telegram_service_status(home: Path, *, enabled: bool, configured: bool) -> TelegramServiceStatus:
    log_path = _telegram_runtime_log_path(home)
    record = _read_telegram_pid_record(home)
    status_record = _read_telegram_status_record(home) or {}
    worker_pids = _managed_telegram_worker_pids(home)
    pid = worker_pids[0] if len(worker_pids) == 1 else 0
    if not pid and record:
        recorded_pid = int(record.get("pid") or 0)
        if recorded_pid and _process_exists(recorded_pid):
            pid = recorded_pid
    status_state = str(status_record.get("state") or "").strip().lower()
    status_detail = str(status_record.get("detail") or "").strip() or None
    ready_at = str(status_record.get("readyAt") or "").strip() or None

    if not enabled:
        return TelegramServiceStatus(
            enabled=False,
            configured=configured,
            state="disabled",
            detail="Telegram channel is disabled in config.json.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if not configured:
        return TelegramServiceStatus(
            enabled=True,
            configured=False,
            state="not_configured",
            detail="Telegram is enabled but TELEGRAM_BOT_TOKEN or ALLOWED_USER_IDS is missing.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    tail = _tail_text(log_path)
    if len(worker_pids) > 1:
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="degraded",
            detail=f"Multiple local Telegram workers are running ({len(worker_pids)}). Restarting the managed worker will clean them up.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if pid:
        if "telegram.error.Conflict" in tail or "terminated by other getUpdates request" in tail:
            return TelegramServiceStatus(
                enabled=True,
                configured=True,
                state="degraded",
                detail="Telegram worker is running but another bot poller is conflicting with getUpdates.",
                process_id=pid,
                log_path=str(log_path),
                ready_at=ready_at,
            )
        if status_state == "running":
            return TelegramServiceStatus(
                enabled=True,
                configured=True,
                state="running",
                detail=status_detail,
                process_id=pid,
                log_path=str(log_path),
                ready_at=ready_at,
            )
        if status_state == "degraded":
            return TelegramServiceStatus(
                enabled=True,
                configured=True,
                state="degraded",
                detail=status_detail or "Telegram worker started but reported a degraded state.",
                process_id=pid,
                log_path=str(log_path),
                ready_at=ready_at,
            )
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="starting",
            detail=status_detail or "Telegram worker is starting in the background.",
            process_id=pid,
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if "telegram.error.Conflict" in tail or "terminated by other getUpdates request" in tail:
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="degraded",
            detail="Telegram worker could not stabilize because another bot poller is active.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if status_state == "degraded":
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="degraded",
            detail=status_detail or "Telegram worker failed during startup.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    return TelegramServiceStatus(
        enabled=True,
        configured=True,
        state="offline",
        detail=status_detail or "Telegram worker is not running.",
        log_path=str(log_path),
        ready_at=ready_at,
    )


def _ensure_telegram_worker(
    home: Path,
    *,
    enabled: bool,
    configured: bool,
    config_fingerprint: str = "",
) -> TelegramServiceStatus:
    if not enabled or not configured:
        _stop_telegram_worker(home)
        return _telegram_service_status(home, enabled=enabled, configured=configured)

    record = _read_telegram_pid_record(home) or {}
    status_record = _read_telegram_status_record(home) or {}
    record_fingerprint = str(
        record.get("configFingerprint")
        or status_record.get("configFingerprint")
        or ""
    ).strip()
    if config_fingerprint and record_fingerprint != config_fingerprint:
        _stop_telegram_worker(home)

    worker_pids = _managed_telegram_worker_pids(home)
    if len(worker_pids) > 1:
        _stop_telegram_worker(home)

    status = _telegram_service_status(home, enabled=enabled, configured=configured)
    if status.process_id:
        return status
    if status.state == "degraded":
        status_record = _read_telegram_status_record(home) or {}
        updated_at = str(status_record.get("updatedAt") or "").strip()
        if updated_at:
            try:
                updated_at_epoch = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                updated_at_epoch = 0.0
            if updated_at_epoch and (time.time() - updated_at_epoch) < 15:
                return status

    _write_telegram_status_record(
        home,
        state="starting",
        detail="Telegram worker is starting in the background.",
        config_fingerprint=config_fingerprint or None,
    )
    _launch_detached_telegram_worker(home)
    time.sleep(0.2)
    return _telegram_service_status(home, enabled=enabled, configured=configured)


def _remote_control_configured_from_values(values: dict[str, str]) -> bool:
    return bool(
        str(values.get("EMPLOAI_REMOTE_CONTROL_BASE_URL", "") or "").strip()
        and str(values.get("EMPLOAI_REMOTE_CONTROL_EMAIL", "") or "").strip()
        and str(values.get("EMPLOAI_REMOTE_CONTROL_PASSWORD", "") or "").strip()
    )


def _remote_control_service_status(home: Path, *, configured: bool) -> RemoteControlServiceStatus:
    log_path = _remote_control_runtime_log_path(home)
    record = _read_remote_control_pid_record(home)
    status_record = _read_remote_control_status_record(home) or {}
    pid = int(record.get("pid") or 0) if record else 0
    if pid and not _process_exists(pid):
        pid = 0
    status_state = str(status_record.get("state") or "").strip().lower()
    status_detail = str(status_record.get("detail") or "").strip() or None
    ready_at = str(status_record.get("readyAt") or "").strip() or None
    desktop_id = str(status_record.get("desktopId") or "").strip() or None
    desktop_name = str(status_record.get("desktopName") or "").strip() or None

    if not configured:
        return RemoteControlServiceStatus(
            configured=False,
            state="not_configured",
            detail="Remote control is not configured yet.",
            log_path=str(log_path),
            desktop_id=desktop_id,
            desktop_name=desktop_name,
            ready_at=ready_at,
        )

    if pid:
        if status_state == "running":
            return RemoteControlServiceStatus(
                configured=True,
                state="running",
                detail=status_detail or "Desktop is connected to the EmploAI cloud control plane.",
                process_id=pid,
                log_path=str(log_path),
                desktop_id=desktop_id,
                desktop_name=desktop_name,
                ready_at=ready_at,
            )
        if status_state == "degraded":
            return RemoteControlServiceStatus(
                configured=True,
                state="degraded",
                detail=status_detail or "Remote control worker started but reported an error.",
                process_id=pid,
                log_path=str(log_path),
                desktop_id=desktop_id,
                desktop_name=desktop_name,
                ready_at=ready_at,
            )
        return RemoteControlServiceStatus(
            configured=True,
            state="starting",
            detail=status_detail or "Remote control worker is starting in the background.",
            process_id=pid,
            log_path=str(log_path),
            desktop_id=desktop_id,
            desktop_name=desktop_name,
            ready_at=ready_at,
        )

    if status_state == "degraded":
        return RemoteControlServiceStatus(
            configured=True,
            state="degraded",
            detail=status_detail or "Remote control worker failed during startup.",
            log_path=str(log_path),
            desktop_id=desktop_id,
            desktop_name=desktop_name,
            ready_at=ready_at,
        )

    return RemoteControlServiceStatus(
        configured=True,
        state="offline",
        detail=status_detail or "Remote control worker is not running.",
        log_path=str(log_path),
        desktop_id=desktop_id,
        desktop_name=desktop_name,
        ready_at=ready_at,
    )


def _ensure_remote_control_worker(
    home: Path,
    *,
    configured: bool,
    config_fingerprint: str = "",
) -> RemoteControlServiceStatus:
    if not configured:
        _stop_remote_control_worker(home)
        return _remote_control_service_status(home, configured=False)

    record = _read_remote_control_pid_record(home) or {}
    status_record = _read_remote_control_status_record(home) or {}
    record_fingerprint = str(
        record.get("configFingerprint")
        or status_record.get("configFingerprint")
        or ""
    ).strip()
    if config_fingerprint and record_fingerprint != config_fingerprint:
        _stop_remote_control_worker(home)

    status = _remote_control_service_status(home, configured=True)
    if status.process_id:
        return status
    if status.state == "degraded":
        status_record = _read_remote_control_status_record(home) or {}
        updated_at = str(status_record.get("updatedAt") or "").strip()
        if updated_at:
            try:
                updated_at_epoch = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                updated_at_epoch = 0.0
            if updated_at_epoch and (time.time() - updated_at_epoch) < 15:
                return status

    _write_remote_control_status_record(
        home,
        state="starting",
        detail="Remote control worker is starting in the background.",
        config_fingerprint=config_fingerprint or None,
    )
    _launch_detached_remote_control_worker(home)
    time.sleep(0.2)
    return _remote_control_service_status(home, configured=True)


def _wait_for_runtime(config: "DesktopRuntimeConfig", home: Path, *, timeout_seconds: int) -> DesktopRuntimeStatus:
    deadline = time.monotonic() + max(2, timeout_seconds)
    last_status = _get_runtime_status()
    failure_detail = _runtime_log_failure_detail(home)
    if failure_detail:
        last_status.detail = failure_detail
        last_status.state = "failed"
        last_status.degraded = True
        return last_status
    while time.monotonic() < deadline:
        time.sleep(READINESS_POLL_INTERVAL_SECONDS)
        last_status = _get_runtime_status()
        if last_status.ok:
            return last_status
        failure_detail = _runtime_log_failure_detail(home)
        if failure_detail:
            last_status.detail = failure_detail
            last_status.state = "failed"
            last_status.degraded = True
            return last_status
    return last_status


def _port_conflict_pids(config: "DesktopRuntimeConfig", home: Path, *, status: Any | None = None) -> list[int]:
    managed_pids = set(_managed_runtime_pids(home, config, status=status))
    return sorted(
        pid
        for pid in _process_ids_for_port(int(config.port or 0))
        if pid not in managed_pids and _process_exists(pid)
    )


def _ensure_runtime(
    config: "DesktopRuntimeConfig",
    home: Path,
    *,
    require_auto_start: bool = True,
    attach_timeout_override: int | None = None,
    restart_attach_timeout_override: int | None = None,
) -> tuple[Any, str]:
    status = _get_runtime_status()
    if status.ok:
        if not _attached_runtime_requires_restart(status):
            return status, "attached"

        incompatible_pids = _managed_runtime_pids(home, config, status=status)
        health_pid = _runtime_health_process_id(status)
        if health_pid and health_pid not in incompatible_pids and _is_runtime_process(health_pid):
            incompatible_pids.append(health_pid)
        for pid in sorted(set(incompatible_pids)):
            _terminate_pid(pid)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not any(_process_exists(pid) for pid in incompatible_pids):
                break
            time.sleep(0.2)
        status = _get_runtime_status()
        if status.ok and not _attached_runtime_requires_restart(status):
            return status, "reattached"

    if not config.enabled:
        raise RuntimeError(status.detail or "Desktop runtime is disabled in config.json")
    if require_auto_start and not config.auto_start:
        raise RuntimeError("Desktop runtime is offline and auto-start is disabled")

    port_conflicts = _port_conflict_pids(config, home, status=status)
    if port_conflicts:
        conflict_text = ", ".join(str(pid) for pid in port_conflicts)
        raise RuntimeError(
            f"Configured desktop port {config.port} is already in use by another process ({conflict_text})."
        )

    stale_pids = _managed_runtime_pids(home, config, status=status)
    if stale_pids:
        _stop_runtime(home, config)
        time.sleep(0.4)

    attach_timeout_seconds = max(2, int(attach_timeout_override or config.attach_timeout_seconds or DEFAULT_ATTACH_TIMEOUT_SECONDS))
    restart_attach_timeout_seconds = max(
        2,
        int(
            restart_attach_timeout_override
            or min(DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS, attach_timeout_seconds)
        ),
    )

    _launch_detached_daemon(config, home)
    status = _wait_for_runtime(config, home, timeout_seconds=attach_timeout_seconds)
    if status.ok:
        return status, "launched"

    recovered_pids = _managed_runtime_pids(home, config, status=status)
    if recovered_pids:
        _stop_runtime(home, config)
        time.sleep(0.4)
        _launch_detached_daemon(config, home)
        status = _wait_for_runtime(config, home, timeout_seconds=restart_attach_timeout_seconds)
        if status.ok:
            return status, "recovered"

    failure_detail = str(status.detail or "").strip()
    if failure_detail:
        raise RuntimeError(failure_detail)

    raise RuntimeError(
        f"Desktop runtime did not become ready within {attach_timeout_seconds} seconds. "
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


def _process_ids_for_command_markers(*markers: str) -> set[int]:
    normalized_markers = [str(marker or "").strip().lower() for marker in markers if str(marker or "").strip()]
    if not normalized_markers:
        return set()

    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Get-CimInstance Win32_Process | ForEach-Object { "
                        "if ($_.CommandLine) { \"{0}`t{1}\" -f $_.ProcessId, $_.CommandLine } "
                        "}"
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(
                ["ps", "-eo", "pid=,command="],
                capture_output=True,
                text=True,
                check=False,
            )

        pids: set[int] = set()
        for line in result.stdout.splitlines():
            if os.name == "nt":
                pid_text, separator, command_line = line.partition("\t")
            else:
                stripped = line.strip()
                pid_text, separator, command_line = stripped.partition(" ")
            if not separator:
                continue
            normalized_command_line = command_line.lower()
            if not all(marker in normalized_command_line for marker in normalized_markers):
                continue
            try:
                pids.add(int(pid_text.strip()))
            except ValueError:
                continue
        return pids
    except Exception:
        return set()


def _process_executable_path(pid: int) -> str:
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
                        'if ($null -ne $process) { [string]$process.ExecutablePath }'
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip()

        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
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


def _runtime_process_matches_current_build(pid: int) -> bool:
    if pid <= 0 or not _process_exists(pid):
        return False
    if not _is_runtime_process(pid):
        return False

    current_executable = str(Path(sys.executable).resolve()).strip().lower()
    process_executable = _process_executable_path(pid).strip().lower()
    if current_executable and process_executable:
        return process_executable == current_executable

    command_line = _process_command_line(pid).strip().lower()
    if not command_line:
        return False
    if getattr(sys, "frozen", False):
        return current_executable in command_line if current_executable else False
    return (
        "deploy.windows.release_backend" in command_line
        or "mobile_app.backend.desktop_runtime" in command_line
    ) and (current_executable in command_line if current_executable else True)


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


def _managed_runtime_pids(home: Path, config: "DesktopRuntimeConfig", *, status: Any | None = None) -> list[int]:
    record = _read_pid_record(home)
    status = status or _get_runtime_status()
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


def _managed_telegram_worker_pids(home: Path) -> list[int]:
    pids: set[int] = set()
    record = _read_telegram_pid_record(home)
    recorded_pid = int(record.get("pid") or 0) if record else 0
    if recorded_pid and _process_exists(recorded_pid):
        pids.add(recorded_pid)

    for pid in _process_ids_for_command_markers("run-telegram-worker"):
        if pid == os.getpid() or not _process_exists(pid):
            continue
        command_line = _process_command_line(pid).lower()
        if "run-telegram-worker" not in command_line:
            continue
        if (
            "deploy.windows.release_backend" not in command_line
            and "emploaibackend" not in command_line
        ):
            continue
        pids.add(pid)

    return sorted(pids)


def _managed_service_pids(home: Path, config: "DesktopRuntimeConfig", *, status: Any | None = None) -> list[int]:
    pids = set(_managed_runtime_pids(home, config, status=status))
    pids.update(_managed_telegram_worker_pids(home))
    remote_record = _read_remote_control_pid_record(home)
    remote_pid = int(remote_record.get("pid") or 0) if remote_record else 0
    if remote_pid and _process_exists(remote_pid):
        pids.add(remote_pid)
    return sorted(pids)


def _runtime_compatibility_issue(
    home: Path,
    config: "DesktopRuntimeConfig",
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


def _attached_runtime_requires_restart(status: Any) -> bool:
    if not getattr(status, "ok", False):
        return False
    health_pid = _runtime_health_process_id(status)
    if health_pid <= 0:
        return False
    return not _runtime_process_matches_current_build(health_pid)


def _bootstrap_payload(
    *,
    launch_if_needed: bool = False,
    force_launch: bool = False,
    resolve_current_session: bool = True,
    attach_timeout_override: int | None = None,
    restart_attach_timeout_override: int | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    root, home, env_file, existing = _prepare_environment()
    prepare_ms = round((time.perf_counter() - started_at) * 1000, 1)

    phase_started_at = time.perf_counter()
    apply_installer_voice_pack_preferences(home)
    setup_state = build_setup_state(
        home=home,
        env_file=env_file,
        source_root=root,
        existing=existing,
    )
    effective_existing, _ = _effective_release_env_values(root, home, existing, mark_rebind_required=False)
    setup_state_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    config = _load_desktop_runtime_config()
    if bool(setup_state.get("telegramRebindRequired")):
        _stop_telegram_worker(home)

    phase_started_at = time.perf_counter()
    status = _get_runtime_status()
    if _attached_runtime_requires_restart(status):
        try:
            status.detail = (
                "Restarting the packaged local runtime so the desktop app uses the current installed build."
            )
            status.state = "offline"
            status.ok = False
        except Exception:
            pass
    status_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)
    runtime_mode = status.mode
    telegram_enabled = bool(configure_channels_enabled("telegram"))
    telegram_configured = bool(setup_state.get("telegramConfigured"))
    telegram_config_fingerprint = _telegram_config_fingerprint_from_values(effective_existing)
    remote_control_configured = _remote_control_configured_from_values(effective_existing)
    remote_control_config_fingerprint = _remote_control_config_fingerprint_from_values(effective_existing)

    should_try_launch = not setup_state["required"] and config.enabled and not status.ok and (force_launch or launch_if_needed)
    launch_ms = 0.0
    if should_try_launch:
        phase_started_at = time.perf_counter()
        try:
            status, runtime_mode = _ensure_runtime(
                config,
                home,
                require_auto_start=not force_launch,
                attach_timeout_override=attach_timeout_override,
                restart_attach_timeout_override=restart_attach_timeout_override,
            )
        except RuntimeError as exc:
            status = _get_runtime_status()
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
        launch_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    phase_started_at = time.perf_counter()
    telegram_status = (
        _ensure_telegram_worker(
            home,
            enabled=telegram_enabled,
            configured=telegram_configured,
            config_fingerprint=telegram_config_fingerprint,
        )
        if status.ok
        else _telegram_service_status(home, enabled=telegram_enabled, configured=telegram_configured)
    )
    telegram_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    phase_started_at = time.perf_counter()
    remote_control_status = (
        _ensure_remote_control_worker(
            home,
            configured=remote_control_configured,
            config_fingerprint=remote_control_config_fingerprint,
        )
        if status.ok
        else _remote_control_service_status(home, configured=remote_control_configured)
    )
    remote_control_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    setup_state["remoteControlStatus"] = asdict(remote_control_status)

    managed_runtime_pids = _managed_runtime_pids(home, config, status=status)

    access_token = ""
    current_session_id: str | None = None
    device_id: str | None = None
    session_ms = 0.0
    if status.ok:
        phase_started_at = time.perf_counter()
        token_payload = _ensure_desktop_token()
        access_token = str(token_payload["access_token"])
        device_id = str(token_payload["device_id"])
        if resolve_current_session:
            workspace = Path(config.workspace)
            try:
                current_session_id = _current_session_id(workspace)
            except Exception as exc:
                issues = list(status.issues or [])
                issues.append(f"Shared session warm-up failed: {exc}")
                try:
                    status.issues = issues
                    status.degraded = True
                except Exception:
                    pass
        session_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    timings = {
        "prepare_environment_ms": prepare_ms,
        "setup_state_ms": setup_state_ms,
        "runtime_status_ms": status_ms,
        "runtime_launch_ms": launch_ms,
        "telegram_ms": telegram_ms,
        "remote_control_ms": remote_control_ms,
        "session_ms": session_ms,
        "total_ms": round((time.perf_counter() - started_at) * 1000, 1),
    }

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
        "telegramLogPath": str(_telegram_runtime_log_path(home)),
        "releaseVersion": current_release_version(root),
        "setupState": setup_state,
        "telegramStatus": asdict(telegram_status),
        "startupTimings": timings,
    }


def _bootstrap_installer_voice_packs() -> dict[str, Any]:
    root, home, _, _ = _prepare_environment()
    runtime_config = apply_installer_voice_pack_preferences(home)
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    packs = voice_config.get("packs") if isinstance(voice_config.get("packs"), dict) else {}
    requested_packs = [
        pack_id
        for pack_id, pack_state in packs.items()
        if isinstance(pack_state, dict) and bool(pack_state.get("requested"))
    ]
    statuses = {pack_id: get_voice_pack_status(pack_id) for pack_id in requested_packs}
    payload: dict[str, Any] = {
        "ok": True,
        "releaseVersion": current_release_version(root),
        "runtimeHome": str(home),
        "voiceConfig": voice_config,
        "requestedPacks": requested_packs,
        "installed": [],
        "errors": {},
        "statuses": statuses,
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    _voice_pack_bootstrap_report_path(home).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _set_voice_engine(engine: str) -> dict[str, Any]:
    if engine not in {VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW, "none"}:
        raise RuntimeError(f"Unsupported voice engine: {engine}")

    _, home, _, _ = _prepare_environment()
    if engine in {VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        update_voice_pack_preferences(
            home=home,
            pack_id=engine,
            requested=True,
            default_engine=engine,
        )
    else:
        update_voice_pack_preferences(home=home, default_engine=engine)
    return _bootstrap_payload(launch_if_needed=False, resolve_current_session=False)


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


def _stop_runtime(home: Path, config: "DesktopRuntimeConfig" | None = None) -> dict[str, Any]:
    config = config or _load_desktop_runtime_config()
    managed_pids = _managed_service_pids(home, config)
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
    _telegram_runtime_pid_path(home).unlink(missing_ok=True)
    _remote_control_runtime_pid_path(home).unlink(missing_ok=True)
    _clear_telegram_status_record(home)
    _clear_remote_control_status_record(home)
    return {
        "ok": True,
        "stopped": not remaining,
        "pid": managed_pids[0] if len(managed_pids) == 1 else None,
        "pids": managed_pids,
        "remainingPids": sorted(remaining),
    }


def _runtime_is_managed(home: Path, config: "DesktopRuntimeConfig" | None = None) -> bool:
    config = config or _load_desktop_runtime_config()
    return bool(_managed_service_pids(home, config))


def _daemon_mode_for_desktop_runtime(*, telegram_enabled: bool, telegram_configured: bool) -> str:
    return "telegram+app" if telegram_enabled and telegram_configured else "desktop-app-only"


def _snapshot_voice_preferences(home: Path) -> dict[str, Any]:
    runtime_config = load_runtime_config(home)
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    packs = voice_config.get("packs") if isinstance(voice_config.get("packs"), dict) else {}
    return {
        "default_engine": str(voice_config.get("default_engine") or VOICE_ENGINE_NONE).strip().lower() or VOICE_ENGINE_NONE,
        "requested": {
            VOICE_ENGINE_ENGLISH: bool((packs.get(VOICE_ENGINE_ENGLISH) or {}).get("requested", False)),
            VOICE_ENGINE_HEBREW: bool((packs.get(VOICE_ENGINE_HEBREW) or {}).get("requested", False)),
        },
    }


def _restore_voice_preferences(home: Path, snapshot: dict[str, Any]) -> None:
    runtime_config = load_runtime_config(home)
    voice_config = runtime_config.setdefault("voice", {})
    packs = voice_config.setdefault("packs", {})
    english_pack = packs.setdefault(VOICE_ENGINE_ENGLISH, {})
    hebrew_pack = packs.setdefault(VOICE_ENGINE_HEBREW, {})

    english_requested = bool((snapshot.get("requested") or {}).get(VOICE_ENGINE_ENGLISH, False))
    hebrew_requested = bool((snapshot.get("requested") or {}).get(VOICE_ENGINE_HEBREW, False))
    english_pack["requested"] = english_requested
    hebrew_pack["requested"] = hebrew_requested
    english_pack["placeholder"] = False
    hebrew_pack["placeholder"] = False
    english_pack.setdefault("display_name", "English voice pack")
    hebrew_pack.setdefault("display_name", "Hebrew voice pack")

    default_engine = str(snapshot.get("default_engine") or VOICE_ENGINE_NONE).strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE

    voice_config["default_engine"] = default_engine
    voice_config["selection_source"] = "settings"
    save_runtime_config(home, runtime_config)


def _save_setup(launch_if_needed: bool) -> dict[str, Any]:
    root, home, env_file, existing = _prepare_environment()
    config = _load_desktop_runtime_config()
    payload = json.loads(sys.stdin.read() or "{}")
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        values = payload if isinstance(payload, dict) else {}

    status_before_save = _get_runtime_status()
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


def _warm_installed_voice_pack(pack_id: str, *, progress_callback=None) -> None:
    label = "Hebrew" if pack_id == VOICE_ENGINE_HEBREW else "English"
    _emit_voice_pack_progress(
        progress_callback,
        pack_id=pack_id,
        state="warming",
        phase="warmup",
        message=f"Warming {label} voice engine...",
        percent=96,
    )
    if pack_id == VOICE_ENGINE_HEBREW:
        from mobile_app.backend.voice_runtime import preload_hebrew_models

        timings = preload_hebrew_models()
        _emit_voice_pack_progress(
            progress_callback,
            pack_id=pack_id,
            state="warming",
            phase="warmup",
            message=f"Hebrew voice engine warmed ({timings.get('final_seconds', 0.0)}s).",
            percent=98,
        )


def _voice_pack_action(pack_id: str, *, install: bool, progress_callback=None) -> dict[str, Any]:
    if pack_id not in VOICE_PACK_IDS:
        raise RuntimeError(f"Unsupported voice pack: {pack_id}")

    _, home, _, _ = _prepare_environment()
    config = _load_desktop_runtime_config()
    status_before_action = _get_runtime_status()
    voice_preferences_before = _snapshot_voice_preferences(home)
    was_running = _runtime_is_managed(home, config) or bool(status_before_action.ok)
    if was_running:
        _emit_voice_pack_progress(
            progress_callback,
            pack_id=pack_id,
            state="starting",
            phase="runtime",
            message="Stopping local runtime before updating voice packs...",
            percent=2,
        )
        _stop_runtime(home, config)
        time.sleep(0.6)

    try:
        if install:
            install_voice_pack(pack_id, progress_callback=progress_callback)
            _warm_installed_voice_pack(pack_id, progress_callback=progress_callback)
            _emit_voice_pack_progress(
                progress_callback,
                pack_id=pack_id,
                state="warming",
                phase="activate",
                message=f"Activating {'Hebrew' if pack_id == VOICE_ENGINE_HEBREW else 'English'} voice pack...",
                percent=99,
            )
            update_voice_pack_preferences(home=home, pack_id=pack_id, requested=True, default_engine=pack_id)
        else:
            runtime_config = load_runtime_config(home)
            voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
            current_default = str(voice_config.get("default_engine") or "").strip().lower()
            next_default = current_default
            if current_default == pack_id:
                next_default = VOICE_ENGINE_HEBREW if pack_id == VOICE_ENGINE_ENGLISH else VOICE_ENGINE_ENGLISH
            update_voice_pack_preferences(home=home, pack_id=pack_id, requested=False, default_engine=next_default)
            remove_voice_pack(pack_id)
    except Exception:
        _restore_voice_preferences(home, voice_preferences_before)
        if install:
            try:
                remove_voice_pack(pack_id)
            except Exception:
                pass
        if was_running:
            try:
                _bootstrap_payload(
                    launch_if_needed=True,
                    force_launch=True,
                    resolve_current_session=False,
                )
            except Exception:
                pass
        raise

    payload = _bootstrap_payload(
        launch_if_needed=True,
        force_launch=was_running,
        resolve_current_session=False,
    )
    if install:
        _emit_voice_pack_progress(
            progress_callback,
            pack_id=pack_id,
            state="ready",
            phase="complete",
            message=f"{'Hebrew' if pack_id == VOICE_ENGINE_HEBREW else 'English'} voice pack is ready.",
            percent=100,
        )
    return payload


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


def _validate_hebrew_runtime_dependencies() -> dict[str, Any]:
    _prepare_environment()
    from mobile_app.backend.hebrew_transformers_runtime import validate_transformers_runtime_stack

    versions = validate_transformers_runtime_stack()
    return {
        "ok": True,
        "transformersVersion": versions.get("transformers"),
        "regexVersion": versions.get("regex"),
    }


def _cleanup_runtime_home(*, voice_packs_only: bool = False) -> dict[str, Any]:
    _, home, _, _ = _prepare_environment()
    config = _load_desktop_runtime_config()
    stop_result = _stop_runtime(home, config)

    removed_paths: list[str] = []
    if voice_packs_only:
        managed_voice_root = managed_voice_packs_root()
        if managed_voice_root.exists():
            shutil.rmtree(managed_voice_root, ignore_errors=True)
            if not managed_voice_root.exists():
                removed_paths.append(str(managed_voice_root))

        for path in (
            _voice_pack_bootstrap_report_path(home),
            _runtime_pid_path(home),
            _telegram_runtime_pid_path(home),
            _telegram_runtime_status_path(home),
            _remote_control_runtime_pid_path(home),
            _remote_control_runtime_status_path(home),
        ):
            if path.exists():
                path.unlink(missing_ok=True)
                if not path.exists():
                    removed_paths.append(str(path))

        try:
            if home.exists() and not any(home.iterdir()):
                home.rmdir()
        except Exception:
            pass
    else:
        for child in list(home.iterdir()) if home.exists() else []:
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            except Exception:
                continue
            if not child.exists():
                removed_paths.append(str(child))
        try:
            if home.exists() and not any(home.iterdir()):
                home.rmdir()
                removed_paths.append(str(home))
        except Exception:
            pass

    return {
        "ok": True,
        "runtimeHome": str(home),
        "voicePacksOnly": voice_packs_only,
        "removedPaths": removed_paths,
        "stopResult": stop_result,
    }


def _run_telegram_worker() -> int:
    root, home, _, existing = _prepare_environment()
    effective_existing, _ = _effective_release_env_values(root, home, existing, mark_rebind_required=False)
    config_fingerprint = _telegram_config_fingerprint_from_values(effective_existing)
    _write_telegram_pid_record(home, config_fingerprint=config_fingerprint or None)
    atexit.register(_clear_telegram_pid_record, home)
    _write_telegram_status_record(
        home,
        state="starting",
        detail="Telegram worker is starting in the background.",
        config_fingerprint=config_fingerprint or None,
    )

    previous_skip_app = os.environ.get("EMPLOAI_SKIP_EMBEDDED_APP_SERVER")
    previous_skip_cron = os.environ.get("EMPLOAI_SKIP_CRON_SCHEDULER")
    os.environ["EMPLOAI_SKIP_EMBEDDED_APP_SERVER"] = "1"
    os.environ["EMPLOAI_SKIP_CRON_SCHEDULER"] = "1"

    try:
        from telegram_bot.telegram_agent import main as telegram_main

        print("Starting EmploAI Telegram worker", flush=True)
        telegram_main()
        return 0
    except Exception as exc:
        _write_telegram_status_record(
            home,
            state="degraded",
            detail=f"{type(exc).__name__}: {exc}",
            config_fingerprint=config_fingerprint or None,
        )
        raise
    finally:
        if previous_skip_app is None:
            os.environ.pop("EMPLOAI_SKIP_EMBEDDED_APP_SERVER", None)
        else:
            os.environ["EMPLOAI_SKIP_EMBEDDED_APP_SERVER"] = previous_skip_app

        if previous_skip_cron is None:
            os.environ.pop("EMPLOAI_SKIP_CRON_SCHEDULER", None)
        else:
            os.environ["EMPLOAI_SKIP_CRON_SCHEDULER"] = previous_skip_cron


def _run_remote_control_worker() -> int:
    root, home, _, existing = _prepare_environment()
    effective_existing, _ = _effective_release_env_values(root, home, existing, mark_rebind_required=False)
    config_fingerprint = _remote_control_config_fingerprint_from_values(effective_existing)
    _write_remote_control_pid_record(home, config_fingerprint=config_fingerprint or None)
    atexit.register(_clear_remote_control_pid_record, home)
    _write_remote_control_status_record(
        home,
        state="starting",
        detail="Remote control worker is starting in the background.",
        config_fingerprint=config_fingerprint or None,
        desktop_name=str(effective_existing.get("EMPLOAI_REMOTE_DESKTOP_NAME") or "EmploAI Desktop"),
    )

    try:
        from mobile_app.backend.remote_desktop_client import main as remote_main

        print("Starting EmploAI remote control worker", flush=True)
        return int(remote_main([]))
    except Exception as exc:
        _write_remote_control_status_record(
            home,
            state="degraded",
            detail=f"{type(exc).__name__}: {exc}",
            config_fingerprint=config_fingerprint or None,
            desktop_name=str(effective_existing.get("EMPLOAI_REMOTE_DESKTOP_NAME") or "EmploAI Desktop"),
        )
        raise


def _run_daemon(host: str | None, port: int | None) -> int:
    root, home, env_file, existing = _prepare_environment()
    config = _load_desktop_runtime_config()
    run_host = str(host or config.host or DEFAULT_DESKTOP_HOST)
    run_port = int(port or config.port or DEFAULT_DESKTOP_PORT)
    telegram_enabled = bool(configure_channels_enabled("telegram"))
    effective_existing, _ = _effective_release_env_values(root, home, existing, mark_rebind_required=True)
    telegram_configured = bool(effective_existing.get("TELEGRAM_BOT_TOKEN") and effective_existing.get("ALLOWED_USER_IDS"))
    telegram_config_fingerprint = _telegram_config_fingerprint_from_values(effective_existing)
    remote_control_configured = _remote_control_configured_from_values(effective_existing)
    remote_control_config_fingerprint = _remote_control_config_fingerprint_from_values(effective_existing)
    mode = "app-first" if telegram_enabled and telegram_configured else "desktop-app-only"

    _write_pid_record(home, mode=mode, host=run_host, port=run_port)
    atexit.register(_clear_pid_record, home)

    if telegram_enabled and telegram_configured:
        _ensure_telegram_worker(
            home,
            enabled=True,
            configured=True,
            config_fingerprint=telegram_config_fingerprint,
        )
    else:
        _stop_telegram_worker(home)

    if remote_control_configured:
        _ensure_remote_control_worker(
            home,
            configured=True,
            config_fingerprint=remote_control_config_fingerprint,
        )
    else:
        _stop_remote_control_worker(home)

    print(f"Starting EmploAI backend in {mode} mode", flush=True)
    asyncio.run(_run_desktop_runtime_server(host=run_host, port=run_port))
    return 0


def configure_channels_enabled(channel_name: str) -> bool:
    config = _load_desktop_runtime_config()
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

    start_parser = subparsers.add_parser("start", help="launch the local runtime if needed and print bootstrap JSON")
    start_parser.add_argument("--attach-timeout-seconds", type=int, default=None)
    start_parser.add_argument("--restart-attach-timeout-seconds", type=int, default=None)
    subparsers.add_parser("stop", help="stop the managed local runtime and print bootstrap JSON")
    subparsers.add_parser("status", help="print the current runtime status JSON")
    subparsers.add_parser("setup-state", help="print the current setup state JSON")

    save_setup_parser = subparsers.add_parser("save-setup", help="save setup JSON from stdin and print bootstrap JSON")
    save_setup_parser.add_argument("--launch-if-needed", action="store_true")

    voice_pack_install_parser = subparsers.add_parser("install-voice-pack", help="install a managed voice pack and print bootstrap JSON")
    voice_pack_install_parser.add_argument("--pack", required=True, choices=VOICE_PACK_IDS)
    voice_pack_install_parser.add_argument("--stream-progress", action="store_true")

    voice_pack_remove_parser = subparsers.add_parser("remove-voice-pack", help="remove a managed voice pack and print bootstrap JSON")
    voice_pack_remove_parser.add_argument("--pack", required=True, choices=VOICE_PACK_IDS)

    voice_pack_bootstrap_parser = subparsers.add_parser(
        "bootstrap-installer-voice-packs",
        help="apply installer voice-pack selections and install any requested packs without failing the MSI",
    )
    voice_pack_bootstrap_parser.add_argument("--json-only", action="store_true")

    voice_engine_parser = subparsers.add_parser(
        "set-voice-engine",
        help="set the default desktop voice engine without reopening the full setup form",
    )
    voice_engine_parser.add_argument("--engine", required=True, choices=[*VOICE_PACK_IDS, "none"])

    cleanup_runtime_parser = subparsers.add_parser("cleanup-runtime-home", help="clean managed runtime artifacts")
    cleanup_runtime_parser.add_argument("--voice-packs-only", action="store_true")

    subparsers.add_parser("validate-hebrew-runtime", help="validate packaged Hebrew runtime dependencies")

    updates_parser = subparsers.add_parser("check-updates", help="check for release updates and print JSON")
    updates_parser.add_argument("--force", action="store_true")

    subparsers.add_parser("install-update", help="download and launch the latest MSI update")

    voice_bridge_parser = subparsers.add_parser("voice-bridge", help="forward commands into the standalone whisper live bridge")
    voice_bridge_parser.add_argument("voice_args", nargs=argparse.REMAINDER)

    run_parser = subparsers.add_parser("run-daemon", help="run the managed local runtime daemon")
    run_parser.add_argument("--host", default=None)
    run_parser.add_argument("--port", type=int, default=None)
    telegram_worker_parser = subparsers.add_parser("run-telegram-worker", help="run the managed Telegram worker without starting the app server")
    telegram_worker_parser.add_argument("--home", default=None)
    subparsers.add_parser("run-remote-control-worker", help="run the managed remote control worker")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv if argv is not None else sys.argv[1:])
    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    if args.command == "bootstrap":
        return _json_print(_bootstrap_payload(launch_if_needed=bool(args.launch_if_needed), resolve_current_session=False))

    if args.command == "start":
        return _json_print(
            _bootstrap_payload(
                force_launch=True,
                resolve_current_session=False,
                attach_timeout_override=args.attach_timeout_seconds,
                restart_attach_timeout_override=args.restart_attach_timeout_seconds,
            )
        )

    if args.command == "stop":
        _prepare_environment()
        _, home, _ = _runtime_paths()
        _stop_runtime(home)
        return _json_print(_bootstrap_payload(launch_if_needed=False, resolve_current_session=False))

    if args.command == "status":
        _prepare_environment()
        return _json_print(asdict(_get_runtime_status()))

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
        pack_id = str(args.pack)
        if bool(args.stream_progress):
            try:
                payload = _voice_pack_action(
                    pack_id,
                    install=True,
                    progress_callback=lambda progress: _stream_print({"kind": "voice_pack_progress", **progress}),
                )
            except Exception as exc:
                _stream_print(
                    {
                        "kind": "voice_pack_progress",
                        "packId": pack_id,
                        "state": "error",
                        "phase": "error",
                        "message": str(exc),
                    }
                )
                raise
            _stream_print({"kind": "bootstrap", "payload": payload})
            return 0
        return _json_print(_voice_pack_action(pack_id, install=True))

    if args.command == "remove-voice-pack":
        return _json_print(_voice_pack_action(str(args.pack), install=False))

    if args.command == "bootstrap-installer-voice-packs":
        payload = _bootstrap_installer_voice_packs()
        if not args.json_only:
            print(
                f"Installer voice pack bootstrap completed. Requested installs: {', '.join(payload.get('installed', [])) or 'none'}",
                file=sys.stderr,
            )
        return _json_print(payload)

    if args.command == "set-voice-engine":
        return _json_print(_set_voice_engine(str(args.engine)))

    if args.command == "cleanup-runtime-home":
        return _json_print(_cleanup_runtime_home(voice_packs_only=bool(args.voice_packs_only)))

    if args.command == "validate-hebrew-runtime":
        return _json_print(_validate_hebrew_runtime_dependencies())

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

    if args.command == "run-telegram-worker":
        if args.home:
            os.environ["EMPLOAI_HOME"] = str(Path(args.home).resolve())
        return _run_telegram_worker()

    if args.command == "run-remote-control-worker":
        return _run_remote_control_worker()

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
