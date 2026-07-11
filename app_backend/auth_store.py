from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.runtime_paths import auth_store_root


AUTH_STORE_FILENAME = "app_auth_store.json"
LAST_USED_WRITE_INTERVAL_SECONDS = 30.0
SAVE_REPLACE_RETRIES = 5
SAVE_REPLACE_RETRY_DELAY_SECONDS = 0.05
MAX_ACTIVE_TOKENS_PER_DEVICE = 20


def _secure_chmod(path: Path, mode: int) -> None:
    try:
        if path.exists():
            os.chmod(path, mode)
    except Exception:
        pass


def _utc_iso(timestamp: Optional[float]) -> Optional[str]:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AppAuthStore:
    def __init__(self, root_path: Optional[Path] = None):
        self.root_path = root_path or auth_store_root()
        self.file_path = self.root_path / AUTH_STORE_FILENAME
        self._lock = threading.RLock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        _secure_chmod(self.file_path.parent, 0o700)
        self._data = self._load()
        if self._cleanup(self._data):
            self._save()
        else:
            _secure_chmod(self.file_path, 0o600)

    def _default_data(self) -> Dict[str, Any]:
        return {
            "devices": {},
            "tokens": {},
        }

    def _load(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            return self._default_data()

        try:
            loaded = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_data()

        if not isinstance(loaded, dict):
            return self._default_data()

        loaded.pop("pairings", None)
        loaded.setdefault("devices", {})
        loaded.setdefault("tokens", {})
        return loaded

    def _save(self) -> None:
        temp_path = self.file_path.with_name(
            f"{self.file_path.name}.{threading.get_ident()}.{secrets.token_hex(6)}.tmp"
        )
        previous_umask: Optional[int] = None
        try:
            previous_umask = os.umask(0o077)
        except Exception:
            previous_umask = None
        try:
            temp_path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        finally:
            if previous_umask is not None:
                try:
                    os.umask(previous_umask)
                except Exception:
                    pass
        _secure_chmod(temp_path, 0o600)
        last_error: Optional[PermissionError] = None
        try:
            for attempt in range(SAVE_REPLACE_RETRIES):
                try:
                    temp_path.replace(self.file_path)
                    _secure_chmod(self.file_path, 0o600)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(SAVE_REPLACE_RETRY_DELAY_SECONDS * (attempt + 1))
            if last_error is not None:
                raise last_error
        finally:
            temp_path.unlink(missing_ok=True)

    def _save_last_used_best_effort(self) -> None:
        try:
            self._save()
        except PermissionError:
            # A last-used timestamp refresh should never reject an otherwise valid
            # desktop token. On Windows the Electron helper and API process can
            # briefly contend over the same JSON store during startup fan-out.
            return

    def _cleanup(self, data: Optional[Dict[str, Any]] = None) -> bool:
        target = data or self._data
        now = time.time()
        changed = False

        devices = target.setdefault("devices", {})
        tokens = target.setdefault("tokens", {})
        for token_hash, token_data in list(tokens.items()):
            if "token_value" in token_data:
                token_data.pop("token_value", None)
                changed = True
            if token_data.get("revoked_at"):
                tokens.pop(token_hash, None)
                changed = True
                continue
            expires_at = float(token_data.get("expires_at", 0))
            if expires_at and expires_at < now:
                tokens.pop(token_hash, None)
                changed = True
                continue
            device_id = str(token_data.get("device_id", ""))
            device = devices.get(device_id)
            if not device or device.get("revoked_at"):
                tokens.pop(token_hash, None)
                changed = True
        return changed

    def _trim_active_tokens_for_device(self, device_id: str) -> None:
        clean_device_id = str(device_id or "").strip()
        if not clean_device_id:
            return
        active_tokens = [
            (token_hash, token_data)
            for token_hash, token_data in self._data.get("tokens", {}).items()
            if str(token_data.get("device_id") or "") == clean_device_id and not token_data.get("revoked_at")
        ]
        if len(active_tokens) <= MAX_ACTIVE_TOKENS_PER_DEVICE:
            return
        active_tokens.sort(
            key=lambda item: float(item[1].get("last_used_at") or item[1].get("created_at") or 0),
            reverse=True,
        )
        for token_hash, _token_data in active_tokens[MAX_ACTIVE_TOKENS_PER_DEVICE:]:
            self._data["tokens"].pop(token_hash, None)

    def resolve_access_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        if not access_token:
            return None

        with self._lock:
            self._cleanup()
            token_hash = _hash_token(access_token)
            token_record = self._data["tokens"].get(token_hash)
            if not token_record:
                loaded = self._load()
                loaded_changed = self._cleanup(loaded)
                token_record = loaded.get("tokens", {}).get(token_hash)
                if not token_record:
                    return None
                self._data = loaded
                if loaded_changed:
                    self._save()

            if token_record.get("revoked_at"):
                self._data["tokens"].pop(token_hash, None)
                self._save()
                return None

            expires_at = float(token_record.get("expires_at", 0))
            if expires_at and expires_at < time.time():
                self._data["tokens"].pop(token_hash, None)
                self._save()
                return None

            device_id = str(token_record.get("device_id", ""))
            device_record = self._data["devices"].get(device_id)
            if not device_record or device_record.get("revoked_at"):
                self._data["tokens"].pop(token_hash, None)
                self._save()
                return None

            now = time.time()
            token_last_used_at = float(token_record.get("last_used_at", 0) or 0)
            device_last_used_at = float(device_record.get("last_used_at", 0) or 0)
            should_persist_last_used = (
                now - max(token_last_used_at, device_last_used_at) >= LAST_USED_WRITE_INTERVAL_SECONDS
            )
            token_record["last_used_at"] = now
            device_record["last_used_at"] = now
            if should_persist_last_used:
                self._save_last_used_best_effort()
            return {
                "device_id": device_id,
                "user_id": int(token_record.get("user_id", 0)),
                "expires_at": expires_at,
                "device_name": device_record.get("device_name"),
                "device_platform": device_record.get("device_platform"),
            }

    def list_devices(self, *, user_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            self._cleanup()
            devices: List[Dict[str, Any]] = []
            for device in self._data["devices"].values():
                if int(device.get("user_id", -1)) != user_id:
                    continue
                devices.append(
                    {
                        "device_id": device.get("device_id"),
                        "device_name": device.get("device_name"),
                        "device_platform": device.get("device_platform"),
                        "created_at": _utc_iso(device.get("created_at")),
                        "last_used_at": _utc_iso(device.get("last_used_at")),
                        "revoked_at": _utc_iso(device.get("revoked_at")),
                        "revoked": bool(device.get("revoked_at")),
                    }
                )
            devices.sort(key=lambda item: item.get("last_used_at") or "", reverse=True)
            return devices

    def revoke_device(self, *, user_id: int, device_id: str) -> bool:
        with self._lock:
            self._cleanup()
            device = self._data["devices"].get(device_id)
            if not device or int(device.get("user_id", -1)) != user_id:
                return False

            revoked_at = time.time()
            device["revoked_at"] = revoked_at
            for token_data in self._data["tokens"].values():
                if token_data.get("device_id") == device_id:
                    token_data["revoked_at"] = revoked_at
            self._save()
            return True

    def ensure_device_token(
        self,
        *,
        user_id: int,
        device_name: Optional[str],
        device_platform: Optional[str],
        token_ttl_seconds: int,
        device_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._cleanup()
            now = time.time()
            normalized_key = (device_key or "").strip() or None
            normalized_name = (device_name or "").strip() or "EmploAI App"
            normalized_platform = (device_platform or "").strip() or None

            existing_device: Optional[Dict[str, Any]] = None
            existing_device_id: Optional[str] = None
            if normalized_key:
                for device_id, device in self._data["devices"].items():
                    if int(device.get("user_id", -1)) != int(user_id):
                        continue
                    if device.get("revoked_at"):
                        continue
                    if str(device.get("device_key") or "").strip() != normalized_key:
                        continue
                    existing_device = device
                    existing_device_id = device_id
                    break

            if existing_device is None:
                existing_device_id = secrets.token_hex(12)
                existing_device = {
                    "device_id": existing_device_id,
                    "user_id": int(user_id),
                    "device_name": normalized_name,
                    "device_platform": normalized_platform,
                    "device_key": normalized_key,
                    "created_at": now,
                    "last_used_at": now,
                    "revoked_at": None,
                }
                self._data["devices"][existing_device_id] = existing_device
            else:
                existing_device["device_name"] = normalized_name
                existing_device["device_platform"] = normalized_platform
                existing_device["last_used_at"] = now
                if normalized_key:
                    existing_device["device_key"] = normalized_key

            access_token = secrets.token_urlsafe(32)
            token_record = {
                "device_id": existing_device_id,
                "user_id": int(user_id),
                "created_at": now,
                "last_used_at": now,
                "expires_at": now + token_ttl_seconds,
                "revoked_at": None,
            }
            self._data["tokens"][_hash_token(access_token)] = token_record
            self._trim_active_tokens_for_device(str(existing_device_id or ""))
            self._save()
            return {
                "device_id": existing_device_id,
                "access_token": access_token,
                "expires_at": token_record["expires_at"],
                "device": dict(existing_device),
            }
