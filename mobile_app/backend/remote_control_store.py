from __future__ import annotations

import hmac
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from mobile_app.backend.remote_account_policy import (
    MAX_DEVICE_KEY_CHARS,
    MAX_DEVICE_PLATFORM_CHARS,
    MAX_DISPLAY_NAME_CHARS,
    MAX_EMAIL_CHARS,
    MAX_PASSWORD_CHARS,
    MAX_SECRET_ITEMS_PER_REQUEST,
    MAX_SECRET_REVEAL_NAMES,
    MAX_SECRET_VALUE_CHARS,
    default_user_profile as _default_user_profile,
    normalize_email as _normalize_email,
    redact_secret_value as _redact_secret_value,
    safe_secret_metadata as _safe_secret_metadata,
    safe_string as _safe_string,
    sanitize_user_profile as _sanitize_user_profile,
    strong_password_errors as _strong_password_errors,
    validate_secret_location as _validate_secret_location,
    validate_secret_namespace as _validate_secret_namespace,
)
from mobile_app.backend.remote_shared_state_policy import (
    empty_fleet_state as _empty_fleet_state,
    empty_sidebar_state as _empty_sidebar_state,
    normalize_fleet_state as _normalize_fleet_state,
    project_groups_from_sessions as _project_groups_from_sessions,
)
from mobile_app.backend.fleet_lock_policy import (
    FLEET_LOCK_CONFLICT_ERROR,
    fleet_lock_owner_matches,
    normalize_fleet_lock_claim,
    normalize_fleet_lock_release,
)
from mobile_app.backend.fleet_policy import (
    FLEET_PREVIEW_MODE,
    ensure_worker_key_not_manager_key,
    normalize_fleet_enrollment_ttl,
    normalize_worker_enrollment_identity,
)
from mobile_app.backend.fleet_report_validation import normalize_worker_task_report
from shared.runtime_paths import auth_store_root


REMOTE_CONTROL_STORE_FILENAME = "remote_control_plane.json"
REMOTE_CONTROL_DB_FILENAME = "remote_control_plane.sqlite3"
REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
AUTH_OTP_TTL_SECONDS = 60 * 10
AUTH_OTP_RESEND_COOLDOWN_SECONDS = 60
AUTH_OTP_MAX_ATTEMPTS = 5
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30
FLEET_STALE_SECONDS = 10
FLEET_OFFLINE_SECONDS = 60
SCHEMA_VERSION = 1
SECRET_VAULT_KEY_ENV = "EMPLOAI_REMOTE_SECRETS_KEY"
SECRET_VAULT_KEY_FILENAME = "remote_secrets.key"
SECRET_VAULT_KEY_VERSION = "v1"


def _utc_iso(timestamp: Optional[float]) -> Optional[str]:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _timestamp_from_archive_value(value: Any, fallback: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return fallback


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_password(password: str, salt: str) -> str:
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return derived.hex()


def _hash_otp_code(code: str, salt: str) -> str:
    derived = hashlib.scrypt(
        str(code or "").encode("utf-8"),
        salt=str(salt or "").encode("utf-8"),
        n=2**13,
        r=8,
        p=1,
        dklen=32,
    )
    return derived.hex()


def _json_loads(value: Any, fallback: Any) -> Any:
    if value in {None, ""}:
        return fallback
    try:
        decoded = json.loads(str(value))
    except Exception:
        return fallback
    return decoded if decoded is not None else fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode_secret_vault_key(value: str) -> Optional[bytes]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) == 64:
        try:
            decoded_hex = bytes.fromhex(raw)
            if len(decoded_hex) == 32:
                return decoded_hex
        except Exception:
            pass
    padded = raw + ("=" * (-len(raw) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _secure_chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except Exception:
        pass


from mobile_app.backend import remote_control_store_accounts as _remote_control_store_accounts
from mobile_app.backend import remote_control_store_archive as _remote_control_store_archive
from mobile_app.backend import remote_control_store_auth as _remote_control_store_auth
from mobile_app.backend import remote_control_store_automations as _remote_control_store_automations
from mobile_app.backend import remote_control_store_commands as _remote_control_store_commands
from mobile_app.backend import remote_control_store_core as _remote_control_store_core
from mobile_app.backend import remote_control_store_fleet_resources as _remote_control_store_fleet_resources
from mobile_app.backend import remote_control_store_fleet_snapshot as _remote_control_store_fleet_snapshot
from mobile_app.backend import remote_control_store_fleet_workers as _remote_control_store_fleet_workers
from mobile_app.backend import remote_control_store_sync as _remote_control_store_sync
from mobile_app.backend import remote_control_store_views as _remote_control_store_views
from mobile_app.backend.remote_control_store_accounts import RemoteControlStoreAccountMixin
from mobile_app.backend.remote_control_store_archive import RemoteControlStoreArchiveMixin
from mobile_app.backend.remote_control_store_auth import RemoteControlStoreAuthMixin
from mobile_app.backend.remote_control_store_automations import RemoteControlStoreAutomationMixin
from mobile_app.backend.remote_control_store_commands import RemoteControlStoreCommandMixin
from mobile_app.backend.remote_control_store_core import RemoteControlStoreCoreMixin
from mobile_app.backend.remote_control_store_fleet_resources import RemoteControlStoreFleetResourceMixin
from mobile_app.backend.remote_control_store_fleet_snapshot import RemoteControlStoreFleetSnapshotMixin
from mobile_app.backend.remote_control_store_fleet_workers import RemoteControlStoreFleetWorkerMixin
from mobile_app.backend.remote_control_store_sync import RemoteControlStoreSyncMixin
from mobile_app.backend.remote_control_store_views import RemoteControlStoreViewMixin

_REMOTE_CONTROL_STORE_MIXIN_MODULES = (
    _remote_control_store_core,
    _remote_control_store_views,
    _remote_control_store_auth,
    _remote_control_store_accounts,
    _remote_control_store_commands,
    _remote_control_store_fleet_snapshot,
    _remote_control_store_fleet_workers,
    _remote_control_store_fleet_resources,
    _remote_control_store_sync,
    _remote_control_store_automations,
    _remote_control_store_archive,
)


def _sync_remote_control_store_mixins() -> None:
    snapshot = dict(globals())
    for module in _REMOTE_CONTROL_STORE_MIXIN_MODULES:
        for name, value in snapshot.items():
            if name.startswith("__"):
                continue
            setattr(module, name, value)


_sync_remote_control_store_mixins()

class RemoteControlPlaneStore(
    RemoteControlStoreCoreMixin,
    RemoteControlStoreViewMixin,
    RemoteControlStoreAuthMixin,
    RemoteControlStoreAccountMixin,
    RemoteControlStoreCommandMixin,
    RemoteControlStoreFleetSnapshotMixin,
    RemoteControlStoreFleetWorkerMixin,
    RemoteControlStoreFleetResourceMixin,
    RemoteControlStoreSyncMixin,
    RemoteControlStoreAutomationMixin,
    RemoteControlStoreArchiveMixin,
):
    def __init__(self, root_path: Optional[Path] = None):
        self.root_path = root_path or auth_store_root()
        self.file_path = self.root_path / REMOTE_CONTROL_STORE_FILENAME
        self.db_path = self.root_path / REMOTE_CONTROL_DB_FILENAME
        self._lock = threading.RLock()
        self.root_path.mkdir(parents=True, exist_ok=True)
        _secure_chmod(self.root_path, 0o700)
        self._conn = self._connect()
        self._initialize()
