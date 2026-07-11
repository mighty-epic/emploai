from __future__ import annotations

import argparse
import asyncio
import atexit
import hashlib
import importlib
import json
import os
import shutil
import secrets
import socket
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from app_backend.auth_store import AppAuthStore
from desktop_runtime.config import (
    RUNTIME_DATA_SCHEMA_STATE_KEY,
    RUNTIME_DATA_SCHEMA_VERSION,
    apply_telegram_rebind_gate,
    build_setup_state,
    bundle_root,
    configure_process_environment,
    configured_model_groups,
    configured_planner_models,
    configured_provider_labels,
    current_release_version,
    ensure_runtime_files,
    env_path,
    apply_installer_voice_pack_preferences,
    load_existing_env_values,
    load_release_state,
    load_runtime_config,
    resolve_voice_runtime_status,
    runtime_home,
    save_env,
    save_setup_values,
    save_runtime_config,
    should_require_telegram_rebind,
    strip_local_secret_env_values,
    TTS_BACKEND_KOKORO,
    TTS_BACKEND_KYUTAI,
    TTS_BACKEND_OPENAI,
    update_voice_pack_preferences,
    VOICE_ENGINE_ENGLISH,
    VOICE_ENGINE_HEBREW,
    VOICE_ENGINE_KOKORO_TTS,
    VOICE_ENGINE_KYUTAI_TTS,
    VOICE_ENGINE_NONE,
    _voice_pack_setup_payload,
)
from shared.fleet_connection import fleet_connection_path
from shared.openai_codex_auth import (
    begin_codex_device_login,
    codex_auth_status,
    delete_codex_auth,
    poll_codex_device_login,
)

if TYPE_CHECKING:
    from app_backend.session_bridge import AppSessionBridge


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
TELEGRAM_STATE_USER_ID_ENV = "EMPLOAI_TELEGRAM_STATE_USER_ID"
TELEGRAM_NOTIFY_ON_READY_ENV = "EMPLOAI_TELEGRAM_NOTIFY_ON_READY"
REMOTE_CONTROL_STATUS_PATH_ENV = "EMPLOAI_REMOTE_CONTROL_STATUS_PATH"
RUNTIME_SECRET_OVERLAY_ENV = "EMPLOAI_DESKTOP_RUNTIME_SECRET_OVERLAY_JSON"
RUNTIME_SECRET_OVERLAY_FIELDS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "NVIDIA_API_KEY",
        "OPENROUTER_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "EMPLOAI_TELEGRAM_BOT_TOKENS_JSON",
    }
)
ALLOW_DEV_VOICE_PACK_SOURCES_ENV = "EMPLOAI_ALLOW_DEV_VOICE_PACK_SOURCES"
APP_STT_ENGLISH_PACK_REPO_ENV = "EMPLO_APP_STT_ENGLISH_PACK_REPO"
APP_STT_HEBREW_MODEL_REPO_ENV = "EMPLO_APP_STT_HEBREW_MODEL_REPO"
APP_TTS_KOKORO_PACK_REPO_ENV = "EMPLO_APP_TTS_KOKORO_PACK_REPO"
APP_TTS_KYUTAI_PACK_REPO_ENV = "EMPLO_APP_TTS_KYUTAI_PACK_REPO"
ENGLISH_PACK_ARCHIVE_URL_ENV = "EMPLOAI_ENGLISH_VOICE_PACK_ARCHIVE_URL"
ENGLISH_PACK_REVISION_ENV = "EMPLOAI_ENGLISH_VOICE_PACK_REVISION"
HEBREW_PACK_ARCHIVE_URL_ENV = "EMPLOAI_HEBREW_VOICE_PACK_ARCHIVE_URL"
HEBREW_PACK_REVISION_ENV = "EMPLOAI_HEBREW_VOICE_PACK_REVISION"
KOKORO_TTS_PACK_ARCHIVE_URL_ENV = "EMPLOAI_KOKORO_TTS_PACK_ARCHIVE_URL"
KOKORO_TTS_PACK_REVISION_ENV = "EMPLOAI_KOKORO_TTS_PACK_REVISION"
KYUTAI_TTS_PACK_ARCHIVE_URL_ENV = "EMPLOAI_KYUTAI_TTS_PACK_ARCHIVE_URL"
KYUTAI_TTS_PACK_REVISION_ENV = "EMPLOAI_KYUTAI_TTS_PACK_REVISION"
STT_VOICE_PACK_IDS = (VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW)
TTS_VOICE_PACK_IDS = (VOICE_ENGINE_KOKORO_TTS, VOICE_ENGINE_KYUTAI_TTS)
VOICE_PACK_IDS = (*STT_VOICE_PACK_IDS, *TTS_VOICE_PACK_IDS)


def _voice_pack_manager():
    from app_backend import voice_pack_manager

    return voice_pack_manager


def install_voice_pack(pack_id: str, **kwargs):
    return _voice_pack_manager().install_voice_pack(pack_id, **kwargs)


def remove_voice_pack(pack_id: str):
    return _voice_pack_manager().remove_voice_pack(pack_id)


def install_latest_update(home: Path, root: Path, *, restart_executable: Path | None = None) -> dict[str, Any]:
    from desktop_runtime.update import install_latest_update as _install_latest_update

    return _install_latest_update(home, root, restart_executable=restart_executable)


def _desktop_runtime_module():
    from app_backend import local_runtime_server as module

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
        if host in {"::", "[::]"}:
            host = "[::1]"
        elif host in {"0.0.0.0"}:
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

    payload_runtime_home = str(payload.get("runtime_home") or "").strip()
    expected_runtime_home = str(runtime_home()).strip()
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


def _json_error_print(error: BaseException) -> int:
    print(json.dumps({"ok": False, "error": str(error), "errorType": type(error).__name__}))
    return 1


def _codex_auth_status_payload() -> dict[str, Any]:
    _prepare_environment(apply_cloud_overlay=False)
    return codex_auth_status()


def _codex_auth_start_device_payload() -> dict[str, Any]:
    _prepare_environment(apply_cloud_overlay=False)
    return begin_codex_device_login()


def _codex_auth_poll_device_payload() -> dict[str, Any]:
    _prepare_environment(apply_cloud_overlay=False)
    return poll_codex_device_login()


def _codex_auth_logout_payload() -> dict[str, Any]:
    _prepare_environment(apply_cloud_overlay=False)
    return delete_codex_auth()


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

    configured_kokoro_repo = str(payload.get("kokoro_tts_voice_pack_repo") or "").strip()
    if managed_release_voice_mode:
        if configured_kokoro_repo:
            os.environ[APP_TTS_KOKORO_PACK_REPO_ENV] = configured_kokoro_repo
        else:
            os.environ.pop(APP_TTS_KOKORO_PACK_REPO_ENV, None)
    elif not os.getenv(APP_TTS_KOKORO_PACK_REPO_ENV, "").strip() and configured_kokoro_repo:
        os.environ[APP_TTS_KOKORO_PACK_REPO_ENV] = configured_kokoro_repo

    configured_kokoro_archive_url = str(payload.get("kokoro_tts_voice_pack_archive_url") or "").strip()
    if managed_release_voice_mode:
        if configured_kokoro_archive_url:
            os.environ[KOKORO_TTS_PACK_ARCHIVE_URL_ENV] = configured_kokoro_archive_url
        else:
            os.environ.pop(KOKORO_TTS_PACK_ARCHIVE_URL_ENV, None)
    elif not os.getenv(KOKORO_TTS_PACK_ARCHIVE_URL_ENV, "").strip() and configured_kokoro_archive_url:
        os.environ[KOKORO_TTS_PACK_ARCHIVE_URL_ENV] = configured_kokoro_archive_url

    configured_kokoro_revision = str(payload.get("kokoro_tts_voice_pack_revision") or "").strip()
    if managed_release_voice_mode:
        if configured_kokoro_revision:
            os.environ[KOKORO_TTS_PACK_REVISION_ENV] = configured_kokoro_revision
        else:
            os.environ.pop(KOKORO_TTS_PACK_REVISION_ENV, None)
    elif not os.getenv(KOKORO_TTS_PACK_REVISION_ENV, "").strip() and configured_kokoro_revision:
        os.environ[KOKORO_TTS_PACK_REVISION_ENV] = configured_kokoro_revision

    configured_kyutai_repo = str(payload.get("kyutai_tts_voice_pack_repo") or "").strip()
    if managed_release_voice_mode:
        if configured_kyutai_repo:
            os.environ[APP_TTS_KYUTAI_PACK_REPO_ENV] = configured_kyutai_repo
        else:
            os.environ.pop(APP_TTS_KYUTAI_PACK_REPO_ENV, None)
    elif not os.getenv(APP_TTS_KYUTAI_PACK_REPO_ENV, "").strip() and configured_kyutai_repo:
        os.environ[APP_TTS_KYUTAI_PACK_REPO_ENV] = configured_kyutai_repo

    configured_kyutai_archive_url = str(payload.get("kyutai_tts_voice_pack_archive_url") or "").strip()
    if managed_release_voice_mode:
        if configured_kyutai_archive_url:
            os.environ[KYUTAI_TTS_PACK_ARCHIVE_URL_ENV] = configured_kyutai_archive_url
        else:
            os.environ.pop(KYUTAI_TTS_PACK_ARCHIVE_URL_ENV, None)
    elif not os.getenv(KYUTAI_TTS_PACK_ARCHIVE_URL_ENV, "").strip() and configured_kyutai_archive_url:
        os.environ[KYUTAI_TTS_PACK_ARCHIVE_URL_ENV] = configured_kyutai_archive_url

    configured_kyutai_revision = str(payload.get("kyutai_tts_voice_pack_revision") or "").strip()
    if managed_release_voice_mode:
        if configured_kyutai_revision:
            os.environ[KYUTAI_TTS_PACK_REVISION_ENV] = configured_kyutai_revision
        else:
            os.environ.pop(KYUTAI_TTS_PACK_REVISION_ENV, None)
    elif not os.getenv(KYUTAI_TTS_PACK_REVISION_ENV, "").strip() and configured_kyutai_revision:
        os.environ[KYUTAI_TTS_PACK_REVISION_ENV] = configured_kyutai_revision


from desktop_runtime import bootstrap as _runtime_bootstrap
from desktop_runtime import local_environment as _runtime_local_environment
from desktop_runtime import records as _runtime_records
from desktop_runtime import services as _runtime_services

_DESKTOP_RUNTIME_MODULES = (
    _runtime_local_environment,
    _runtime_records,
    _runtime_services,
    _runtime_bootstrap,
)
_LOCAL_ENVIRONMENT_HELPER_NAMES = (
    '_runtime_secret_overlay_values',
    '_apply_runtime_secret_overlay',
    '_prepare_environment',
    '_refresh_setup_model_catalog',
    '_refresh_setup_voice_status',
    '_effective_release_env_values',
)
_RECORD_HELPER_NAMES = (
    '_runtime_pid_path',
    '_runtime_log_path',
    '_telegram_runtime_pid_path',
    '_telegram_runtime_log_path',
    '_telegram_runtime_status_path',
    '_remote_control_runtime_pid_path',
    '_remote_control_runtime_log_path',
    '_remote_control_runtime_status_path',
    '_voice_pack_bootstrap_report_path',
    '_default_user_id',
    '_normalize_allowed_user_ids',
    '_telegram_config_fingerprint',
    '_telegram_config_fingerprint_from_values',
    '_remote_control_config_fingerprint_from_values',
    '_fleet_connection_config_fingerprint',
    '_current_session_id',
    '_ensure_desktop_token',
    '_self_command',
    '_read_pid_record',
    '_read_telegram_pid_record',
    '_read_remote_control_pid_record',
    '_write_pid_record',
    '_write_telegram_pid_record',
    '_write_remote_control_pid_record',
    '_read_telegram_status_record',
    '_read_remote_control_status_record',
    '_write_telegram_status_record',
    '_write_remote_control_status_record',
    '_clear_pid_record',
    '_clear_telegram_pid_record',
    '_clear_remote_control_pid_record',
    '_clear_telegram_status_record',
    '_clear_remote_control_status_record',
    '_stop_telegram_worker',
    '_stop_remote_control_worker',
    '_launch_detached_daemon',
    '_launch_detached_telegram_worker',
    '_launch_detached_remote_control_worker',
    '_tail_text',
    '_runtime_log_failure_detail',
)
_SERVICE_HELPER_NAMES = (
    '_telegram_service_status',
    '_ensure_telegram_worker',
    '_remote_control_configured_from_values',
    '_remote_control_service_status',
    '_ensure_remote_control_worker',
    '_wait_for_runtime',
    '_port_conflict_pids',
    '_ensure_runtime',
    '_runtime_health_process_id',
    '_process_command_line',
    '_process_ids_for_command_markers',
    '_process_executable_path',
    '_is_runtime_process',
    '_is_desktop_runtime_worker_process',
    '_runtime_process_matches_current_build',
    '_attached_runtime_requires_restart_checked',
    '_is_telegram_capable_runtime_command_line',
    '_process_ids_for_port',
    '_managed_runtime_pids',
    '_managed_telegram_worker_pids',
    '_managed_remote_control_worker_pids',
    '_managed_service_pids',
    '_runtime_compatibility_issue',
    '_attached_runtime_requires_restart',
)
_BOOTSTRAP_HELPER_NAMES = (
    '_bootstrap_payload',
    '_bootstrap_installer_voice_packs',
    '_set_voice_engine',
    '_process_exists',
    '_terminate_pid',
    '_request_runtime_agent_stop',
    '_stop_runtime',
    '_runtime_is_managed',
    '_daemon_mode_for_desktop_runtime',
    '_snapshot_voice_preferences',
    '_restore_voice_preferences',
    '_voice_pack_label',
    '_tts_backend_for_pack',
    '_set_release_tts_backend',
    '_save_setup',
    '_warm_installed_voice_pack',
    '_voice_pack_action',
    '_forward_voice_bridge',
    '_validate_hebrew_runtime_dependencies',
    '_cleanup_runtime_home',
)
_DESKTOP_RUNTIME_HELPER_NAMES = (
    *_LOCAL_ENVIRONMENT_HELPER_NAMES,
    *_RECORD_HELPER_NAMES,
    *_SERVICE_HELPER_NAMES,
    *_BOOTSTRAP_HELPER_NAMES,
)
for _runtime_helper_name in _DESKTOP_RUNTIME_HELPER_NAMES:
    for _runtime_helper_module in _DESKTOP_RUNTIME_MODULES:
        if hasattr(_runtime_helper_module, _runtime_helper_name):
            globals()[_runtime_helper_name] = getattr(_runtime_helper_module, _runtime_helper_name)
            break


def _desktop_runtime_delegate(name: str):
    return lambda *args, __name=name, **kwargs: globals()[__name](*args, **kwargs)


def _sync_desktop_runtime_modules() -> None:
    snapshot = dict(globals())
    skip_names = {
        '_runtime_helper_module',
        '_runtime_helper_name',
        '_DESKTOP_RUNTIME_MODULES',
    }
    for module in _DESKTOP_RUNTIME_MODULES:
        for name, value in snapshot.items():
            if name in skip_names:
                continue
            if callable(value) and not isinstance(value, type):
                setattr(module, name, _desktop_runtime_delegate(name))
            else:
                setattr(module, name, value)


_sync_desktop_runtime_modules()

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
        from app_backend.remote_desktop_client import main as remote_main

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


def _fleet_yggdrasil_status() -> dict[str, Any]:
    _, home, _ = _runtime_paths()
    from shared.fleet_yggdrasil import yggdrasil_status

    return yggdrasil_status(home)


def _fleet_yggdrasil_bootstrap(
    *,
    install: bool,
    start: bool,
    configure_default_peers: bool,
    force_download: bool,
    best_effort: bool,
) -> tuple[dict[str, Any], int]:
    _prepare_environment(apply_cloud_overlay=False)
    _, home, _ = _runtime_paths()
    from shared.fleet_yggdrasil import bootstrap_yggdrasil

    try:
        payload = bootstrap_yggdrasil(
            home,
            install=install,
            start=start,
            configure_default_peers=configure_default_peers,
            force_download=force_download,
        )
    except Exception as exc:
        payload = {"ok": False, "error": str(exc), "errorType": type(exc).__name__}
    return payload, 0 if (best_effort or payload.get("ok")) else 1


def _fleet_yggdrasil_device_identity(home: Path, *, device_name: str | None = None, device_key: str | None = None) -> dict[str, str]:
    identity_path = home / "fleet-yggdrasil-worker-identity.json"
    existing: dict[str, Any] = {}
    try:
        existing = json.loads(identity_path.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
    resolved_key = str(device_key or existing.get("deviceKey") or "").strip()
    if not resolved_key:
        resolved_key = f"ygg-worker-{secrets.token_urlsafe(24)}"
    resolved_name = str(device_name or existing.get("deviceName") or "").strip()
    if not resolved_name:
        hostname = str(socket.gethostname() or "").strip()
        resolved_name = f"EmploAI Worker ({hostname})" if hostname else "EmploAI Worker"
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(
        json.dumps(
            {
                "deviceName": resolved_name,
                "deviceKey": resolved_key,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        identity_path.chmod(0o600)
    except OSError:
        pass
    return {"device_name": resolved_name, "device_key": resolved_key}


def _desktop_runtime_bind_is_yggdrasil_reachable(config: DesktopRuntimeConfig) -> bool:
    host = str(config.host or "").strip().lower()
    return host in {"::", "[::]"} or ":" in host


def _configure_manager_yggdrasil_bind(home: Path) -> bool:
    runtime_config = load_runtime_config(home)
    channels = runtime_config.get("channels") if isinstance(runtime_config.get("channels"), dict) else {}
    next_channels = dict(channels)
    desktop = dict(next_channels.get("desktop") or {})
    app = dict(next_channels.get("app") or {})
    changed = False
    if str(desktop.get("host") or "").strip() not in {"::", "[::]"}:
        desktop["host"] = "::"
        changed = True
    if str(app.get("host") or "").strip() not in {"::", "[::]"}:
        app["host"] = "::"
        changed = True
    next_channels["desktop"] = desktop
    next_channels["app"] = app
    runtime_config["channels"] = next_channels
    if changed:
        save_runtime_config(home, runtime_config)
        _stop_runtime(home)
    return changed


def _fleet_yggdrasil_create_pairing(
    *,
    display_name: str | None,
    expires_in_seconds: int,
    configure_manager_bind: bool,
) -> dict[str, Any]:
    root, home, _, _ = _prepare_environment(apply_cloud_overlay=False)
    from shared.fleet_yggdrasil import (
        DEFAULT_PAIRING_TTL_SECONDS,
        build_pairing_payload,
        encode_pairing_token,
        manager_url_for_yggdrasil,
        request_json,
        yggdrasil_status,
    )

    ygg_status = yggdrasil_status(home)
    if not ygg_status.get("running") or not ygg_status.get("address"):
        raise RuntimeError(
            "Yggdrasil is not running on the manager machine. "
            f"{ygg_status.get('installHint') or 'Install and start Yggdrasil, then try again.'}"
        )

    config = _load_desktop_runtime_config()
    bind_changed = False
    if configure_manager_bind:
        bind_changed = _configure_manager_yggdrasil_bind(home)
        config = _load_desktop_runtime_config()
    if not _desktop_runtime_bind_is_yggdrasil_reachable(config):
        raise RuntimeError(
            "The manager backend is still bound to loopback only. "
            "Run this command again with --configure-manager-bind so workers can reach it over Yggdrasil."
        )

    bootstrap = _bootstrap_payload(force_launch=True, resolve_current_session=False)
    local_api_base_url = str(bootstrap.get("apiBaseUrl") or "").strip().rstrip("/")
    local_token = str(bootstrap.get("accessToken") or "").strip()
    if not local_api_base_url or not local_token:
        raise RuntimeError("Local manager backend is not ready for Fleet enrollment.")

    port = int(urlparse(local_api_base_url).port or config.port or DEFAULT_DESKTOP_PORT)
    manager_url = manager_url_for_yggdrasil(str(ygg_status["address"]), port)
    enrollment = request_json(
        url=f"{local_api_base_url}/api/fleet/enrollments",
        method="POST",
        token=local_token,
        payload={
            "display_name": display_name or "Yggdrasil worker",
            "expires_in_seconds": max(60, int(expires_in_seconds or DEFAULT_PAIRING_TTL_SECONDS)),
            "metadata": {
                "transport": "yggdrasil",
                "manager_url": manager_url,
                "source": "standalone_yggdrasil_pairing",
            },
        },
    )
    payload = build_pairing_payload(
        manager_url=manager_url,
        manager_yggdrasil_ip=str(ygg_status["address"]),
        manager_public_key=str(ygg_status.get("public_key") or ""),
        enrollment_token=str(enrollment.get("enrollment_token") or ""),
        expires_in_seconds=int(enrollment.get("expires_in_seconds") or expires_in_seconds or DEFAULT_PAIRING_TTL_SECONDS),
        display_name=display_name,
    )
    pairing_token = encode_pairing_token(payload)
    return {
        "ok": True,
        "transport": "yggdrasil",
        "managerUrl": manager_url,
        "managerYggdrasilIp": payload["manager_yggdrasil_ip"],
        "managerPublicKey": payload.get("manager_public_key"),
        "pairingToken": pairing_token,
        "expiresAt": payload["expires_at"],
        "expiresInSeconds": int(enrollment.get("expires_in_seconds") or expires_in_seconds or DEFAULT_PAIRING_TTL_SECONDS),
        "runtimeHome": str(home),
        "sourceRoot": str(root),
        "managerBindChanged": bind_changed,
        "backendApiBaseUrl": local_api_base_url,
    }


def _clear_remote_control_env_values(env_file: Path, existing: Mapping[str, str]) -> None:
    cleaned = dict(existing)
    for key in (
        "EMPLOAI_REMOTE_CONTROL_BASE_URL",
        "EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN",
        "EMPLOAI_REMOTE_CONTROL_USER_ID",
        "EMPLOAI_REMOTE_CONTROL_DESKTOP_ID",
        "EMPLOAI_REMOTE_CONTROL_EMAIL",
        "EMPLOAI_REMOTE_CONTROL_PASSWORD",
    ):
        cleaned.pop(key, None)
        os.environ.pop(key, None)
    save_env(env_file, cleaned)


def _fleet_yggdrasil_join_worker(
    *,
    pairing_token: str,
    device_name: str | None,
    device_key: str | None,
    start_worker: bool,
) -> dict[str, Any]:
    _, home, env_file, existing = _prepare_environment(apply_cloud_overlay=False)
    from shared.fleet_yggdrasil import complete_worker_enrollment, decode_pairing_token

    identity = _fleet_yggdrasil_device_identity(home, device_name=device_name, device_key=device_key)
    pairing = decode_pairing_token(pairing_token)
    _clear_remote_control_env_values(env_file, existing)
    completed = complete_worker_enrollment(
        pairing_token=pairing_token,
        home=home,
        device_name=identity["device_name"],
        device_platform=DEFAULT_DEVICE_PLATFORM,
        device_key=identity["device_key"],
    )
    if start_worker:
        _write_remote_control_status_record(
            home,
            state="starting",
            detail="Yggdrasil Fleet worker relay is starting in the background.",
            desktop_name=identity["device_name"],
        )
        _launch_detached_remote_control_worker(home)
    return {
        "ok": True,
        "transport": "yggdrasil",
        "managerUrl": pairing["manager_url"],
        "worker": completed.get("worker") or {},
        "desktop": completed.get("desktop") or {},
        "sessionPath": str(fleet_connection_path(home)),
        "remoteWorkerStarted": bool(start_worker),
        "deviceName": identity["device_name"],
    }


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

    if not (telegram_enabled and telegram_configured):
        _stop_telegram_worker(home, scan_processes=False)

    if not remote_control_configured:
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


_sync_desktop_runtime_modules()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows release backend helper for the EmploAI desktop app.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="prepare desktop bootstrap state")
    bootstrap_parser.add_argument("--launch-if-needed", action="store_true")
    bootstrap_parser.add_argument("--defer-services", action="store_true")

    start_parser = subparsers.add_parser("start", help="launch the local runtime if needed and print bootstrap JSON")
    start_parser.add_argument("--attach-timeout-seconds", type=int, default=None)
    start_parser.add_argument("--restart-attach-timeout-seconds", type=int, default=None)
    start_parser.add_argument("--defer-services", action="store_true")
    subparsers.add_parser("stop", help="stop the managed local runtime and print bootstrap JSON")
    subparsers.add_parser("status", help="print the current runtime status JSON")
    subparsers.add_parser("setup-state", help="print the current setup state JSON")
    subparsers.add_parser("codex-auth-status", help="print local ChatGPT/Codex auth status JSON")
    subparsers.add_parser("codex-auth-start-device", help="start local ChatGPT/Codex device sign-in JSON")
    subparsers.add_parser("codex-auth-poll-device", help="poll local ChatGPT/Codex device sign-in JSON")
    subparsers.add_parser("codex-auth-logout", help="delete local ChatGPT/Codex auth tokens JSON")

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
    voice_engine_parser.add_argument("--engine", required=True, choices=[*STT_VOICE_PACK_IDS, "none"])

    cleanup_runtime_parser = subparsers.add_parser("cleanup-runtime-home", help="clean managed runtime artifacts")
    cleanup_runtime_parser.add_argument("--voice-packs-only", action="store_true")

    subparsers.add_parser("validate-hebrew-runtime", help="validate packaged Hebrew runtime dependencies")

    updates_parser = subparsers.add_parser("check-updates", help="check for release updates and print JSON")
    updates_parser.add_argument("--force", action="store_true")

    install_update_parser = subparsers.add_parser("install-update", help="download and launch the latest MSI update")
    install_update_parser.add_argument("--restart-executable", default=None)

    voice_bridge_parser = subparsers.add_parser("voice-bridge", help="forward commands into the standalone whisper live bridge")
    voice_bridge_parser.add_argument("voice_args", nargs=argparse.REMAINDER)

    subparsers.add_parser("yggdrasil-status", help="print local Yggdrasil transport status JSON")

    ygg_bootstrap_parser = subparsers.add_parser(
        "yggdrasil-bootstrap",
        help="download/install/start Yggdrasil for standalone Fleet transport",
    )
    ygg_bootstrap_parser.add_argument("--install", action="store_true")
    ygg_bootstrap_parser.add_argument("--start", action="store_true")
    ygg_bootstrap_parser.add_argument("--configure-default-peers", action="store_true")
    ygg_bootstrap_parser.add_argument("--force-download", action="store_true")
    ygg_bootstrap_parser.add_argument("--best-effort", action="store_true")

    ygg_pair_parser = subparsers.add_parser(
        "fleet-yggdrasil-pair",
        help="create a standalone Yggdrasil Fleet pairing token for a remote worker",
    )
    ygg_pair_parser.add_argument("--display-name", default="Yggdrasil worker")
    ygg_pair_parser.add_argument("--expires-in-seconds", type=int, default=30 * 60)
    ygg_pair_parser.add_argument(
        "--configure-manager-bind",
        action="store_true",
        help="bind the manager backend on IPv6 so Yggdrasil workers can reach it",
    )

    ygg_join_parser = subparsers.add_parser(
        "fleet-yggdrasil-join",
        help="join this machine to a manager using an EmploAI Yggdrasil Fleet pairing token",
    )
    ygg_join_parser.add_argument("pairing_token")
    ygg_join_parser.add_argument("--device-name", default=None)
    ygg_join_parser.add_argument("--device-key", default=None)
    ygg_join_parser.add_argument("--no-start-worker", action="store_true")

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
        return _json_print(
            _bootstrap_payload(
                launch_if_needed=bool(args.launch_if_needed),
                resolve_current_session=False,
                defer_services=bool(args.defer_services),
            )
        )

    if args.command == "start":
        return _json_print(
            _bootstrap_payload(
                force_launch=True,
                resolve_current_session=False,
                attach_timeout_override=args.attach_timeout_seconds,
                restart_attach_timeout_override=args.restart_attach_timeout_seconds,
                defer_services=bool(args.defer_services),
            )
        )

    if args.command == "stop":
        _prepare_environment(apply_cloud_overlay=False)
        _, home, _ = _runtime_paths()
        _stop_runtime(home)
        return _json_print(_bootstrap_payload(launch_if_needed=False, resolve_current_session=False))

    if args.command == "status":
        _prepare_environment(apply_cloud_overlay=False)
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

    if args.command == "codex-auth-status":
        return _json_print(_codex_auth_status_payload())

    if args.command == "codex-auth-start-device":
        return _json_print(_codex_auth_start_device_payload())

    if args.command == "codex-auth-poll-device":
        return _json_print(_codex_auth_poll_device_payload())

    if args.command == "codex-auth-logout":
        return _json_print(_codex_auth_logout_payload())

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
        from desktop_runtime.update import check_for_updates

        root, home, _ = _runtime_paths()
        return _json_print(check_for_updates(home, root, force=bool(args.force)))

    if args.command == "install-update":
        root, home, _ = _runtime_paths()
        restart_executable = (
            Path(str(args.restart_executable)).expanduser().resolve()
            if getattr(args, "restart_executable", None)
            else None
        )
        return _json_print(install_latest_update(home, root, restart_executable=restart_executable))

    if args.command == "voice-bridge":
        return _forward_voice_bridge(list(args.voice_args or []))

    if args.command == "yggdrasil-status":
        _prepare_environment(apply_cloud_overlay=False)
        return _json_print(_fleet_yggdrasil_status())

    if args.command == "yggdrasil-bootstrap":
        payload, code = _fleet_yggdrasil_bootstrap(
            install=bool(args.install),
            start=bool(args.start),
            configure_default_peers=bool(args.configure_default_peers),
            force_download=bool(args.force_download),
            best_effort=bool(args.best_effort),
        )
        print(json.dumps(payload))
        return code

    if args.command == "fleet-yggdrasil-pair":
        try:
            return _json_print(
                _fleet_yggdrasil_create_pairing(
                    display_name=str(args.display_name or ""),
                    expires_in_seconds=int(args.expires_in_seconds or 30 * 60),
                    configure_manager_bind=bool(args.configure_manager_bind),
                )
            )
        except Exception as exc:
            return _json_error_print(exc)

    if args.command == "fleet-yggdrasil-join":
        try:
            return _json_print(
                _fleet_yggdrasil_join_worker(
                    pairing_token=str(args.pairing_token or ""),
                    device_name=args.device_name,
                    device_key=args.device_key,
                    start_worker=not bool(args.no_start_worker),
                )
            )
        except Exception as exc:
            return _json_error_print(exc)

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
