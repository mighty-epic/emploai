from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Optional


APP_NAME = "EmploAI"
AGENTSHELL_DIRNAME = ".agentshell"
PACKAGED_DATA_DIRNAME = "data"
CHANNEL_SYNC_DIRNAME = "channel_sync"
LOG_DIRNAME = "logs"


def runtime_home() -> Path | None:
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    if getattr(sys, "frozen", False):
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
        return (Path(base) / APP_NAME).resolve()
    return None


def default_workspace_root() -> Path | None:
    configured = os.getenv("DEFAULT_WORKSPACE", "").strip()
    if not configured:
        return None
    try:
        workspace = Path(configured).expanduser().resolve()
    except Exception:
        return None
    if not workspace.exists() or not workspace.is_dir():
        return None
    return workspace


def normalize_legacy_workspace_path(
    workspace: Optional[Path | str],
    *,
    fallback: Optional[Path | str] = None,
) -> Path | None:
    def _resolve_path(value: Optional[Path | str]) -> Path | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return Path(text).expanduser().resolve()
        except Exception:
            return None

    candidate = _resolve_path(workspace)
    fallback_path = _resolve_path(fallback)
    default_workspace = default_workspace_root()
    app_runtime_home = runtime_home()

    if candidate is not None:
        if default_workspace is not None and app_runtime_home is not None and candidate == app_runtime_home:
            return default_workspace
        return candidate

    return default_workspace or fallback_path


def shared_state_root() -> Path:
    home = runtime_home()
    if home is not None:
        return (home / PACKAGED_DATA_DIRNAME).resolve()
    return (Path.home() / AGENTSHELL_DIRNAME).resolve()


def user_state_root(user_id: int) -> Path:
    return (shared_state_root() / f"user_{int(user_id)}").resolve()


def auth_store_root() -> Path:
    return shared_state_root()


def channel_sync_root() -> Path:
    home = runtime_home()
    if home is not None:
        return (home / CHANNEL_SYNC_DIRNAME).resolve()
    return (Path.home() / AGENTSHELL_DIRNAME / CHANNEL_SYNC_DIRNAME).resolve()


def log_root() -> Path:
    home = runtime_home()
    if home is not None:
        return (home / LOG_DIRNAME).resolve()
    return (Path.home() / AGENTSHELL_DIRNAME / LOG_DIRNAME).resolve()


def scoped_keyring_service(base_service: str) -> str:
    home = runtime_home()
    if home is None:
        return base_service
    digest = hashlib.sha256(str(home).encode("utf-8")).hexdigest()[:12]
    return f"{base_service}-{digest}"
