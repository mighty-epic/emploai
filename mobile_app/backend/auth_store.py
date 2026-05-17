from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


AUTH_STORE_FILENAME = "app_auth_store.json"


def _utc_iso(timestamp: Optional[float]) -> Optional[str]:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AppAuthStore:
    def __init__(self, root_path: Optional[Path] = None):
        self.root_path = root_path or (Path.home() / ".agentshell")
        self.file_path = self.root_path / AUTH_STORE_FILENAME
        self._lock = threading.RLock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _default_data(self) -> Dict[str, Any]:
        return {
            "pairings": {},
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

        loaded.setdefault("pairings", {})
        loaded.setdefault("devices", {})
        loaded.setdefault("tokens", {})
        self._cleanup(loaded)
        return loaded

    def _save(self) -> None:
        temp_path = self.file_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.file_path)

    def _cleanup(self, data: Optional[Dict[str, Any]] = None) -> None:
        target = data or self._data
        now = time.time()

        pairings = target.setdefault("pairings", {})
        for pairing_id, pairing in list(pairings.items()):
            expires_at = float(pairing.get("expires_at", 0))
            used_at = pairing.get("used_at")
            if used_at or expires_at < now:
                pairings.pop(pairing_id, None)

        devices = target.setdefault("devices", {})
        tokens = target.setdefault("tokens", {})
        for token_hash, token_data in list(tokens.items()):
            if token_data.get("revoked_at"):
                tokens.pop(token_hash, None)
                continue
            expires_at = float(token_data.get("expires_at", 0))
            if expires_at and expires_at < now:
                tokens.pop(token_hash, None)
                continue
            device_id = str(token_data.get("device_id", ""))
            device = devices.get(device_id)
            if not device or device.get("revoked_at"):
                tokens.pop(token_hash, None)

    def create_pairing(
        self,
        *,
        device_name: Optional[str],
        created_by: Optional[str],
        ttl_seconds: int,
    ) -> Dict[str, Any]:
        with self._lock:
            self._cleanup()
            pairing_id = secrets.token_hex(8)
            issued_at = int(time.time())
            record = {
                "pairing_id": pairing_id,
                "device_name": (device_name or "").strip() or None,
                "issued_at": issued_at,
                "expires_at": issued_at + ttl_seconds,
                "created_by": created_by,
                "used_at": None,
            }
            self._data["pairings"][pairing_id] = record
            self._save()
            return dict(record)

    def get_pairing(self, pairing_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._cleanup()
            pairing = self._data["pairings"].get(pairing_id)
            return dict(pairing) if pairing else None

    def complete_pairing(
        self,
        *,
        pairing_id: str,
        user_id: int,
        device_name: Optional[str],
        device_platform: Optional[str],
        token_ttl_seconds: int,
    ) -> Dict[str, Any]:
        with self._lock:
            self._cleanup()
            pairing = self._data["pairings"].get(pairing_id)
            if not pairing:
                raise KeyError("Unknown pairing")

            if pairing.get("used_at"):
                raise ValueError("Pairing token already used")

            expires_at = float(pairing.get("expires_at", 0))
            if expires_at < time.time():
                self._data["pairings"].pop(pairing_id, None)
                self._save()
                raise ValueError("Expired pairing token")

            device_id = secrets.token_hex(12)
            access_token = secrets.token_urlsafe(32)
            token_hash = _hash_token(access_token)
            now = time.time()
            final_device_name = (device_name or pairing.get("device_name") or "EmploAI App").strip()
            device_record = {
                "device_id": device_id,
                "user_id": user_id,
                "device_name": final_device_name,
                "device_platform": (device_platform or "").strip() or None,
                "created_at": now,
                "last_used_at": now,
                "revoked_at": None,
            }
            token_record = {
                "device_id": device_id,
                "user_id": user_id,
                "token_value": access_token,
                "created_at": now,
                "last_used_at": now,
                "expires_at": now + token_ttl_seconds,
                "revoked_at": None,
            }

            self._data["devices"][device_id] = device_record
            self._data["tokens"][token_hash] = token_record
            pairing["used_at"] = now
            pairing["completed_device_id"] = device_id
            self._save()
            return {
                "device_id": device_id,
                "access_token": access_token,
                "expires_at": token_record["expires_at"],
                "device": dict(device_record),
            }

    def resolve_access_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        if not access_token:
            return None

        with self._lock:
            self._cleanup()
            token_hash = _hash_token(access_token)
            token_record = self._data["tokens"].get(token_hash)
            if not token_record:
                return None

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
            token_record["last_used_at"] = now
            device_record["last_used_at"] = now
            self._save()
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

            reusable_token_value: Optional[str] = None
            reusable_expires_at: Optional[float] = None
            if existing_device_id:
                for token_data in self._data["tokens"].values():
                    if token_data.get("device_id") != existing_device_id:
                        continue
                    if token_data.get("revoked_at"):
                        continue
                    expires_at = float(token_data.get("expires_at", 0) or 0)
                    if expires_at and expires_at < now:
                        continue
                    token_value = str(token_data.get("token_value") or "").strip()
                    if not token_value:
                        continue
                    token_data["last_used_at"] = now
                    reusable_token_value = token_value
                    reusable_expires_at = expires_at
                    break

            if reusable_token_value:
                self._save()
                return {
                    "device_id": existing_device_id,
                    "access_token": reusable_token_value,
                    "expires_at": reusable_expires_at,
                    "device": dict(existing_device),
                }

            for token_data in self._data["tokens"].values():
                if token_data.get("device_id") == existing_device_id and not token_data.get("revoked_at"):
                    token_data["revoked_at"] = now

            access_token = secrets.token_urlsafe(32)
            token_record = {
                "device_id": existing_device_id,
                "user_id": int(user_id),
                "token_value": access_token,
                "created_at": now,
                "last_used_at": now,
                "expires_at": now + token_ttl_seconds,
                "revoked_at": None,
            }
            self._data["tokens"][_hash_token(access_token)] = token_record
            self._save()
            return {
                "device_id": existing_device_id,
                "access_token": access_token,
                "expires_at": token_record["expires_at"],
                "device": dict(existing_device),
            }
