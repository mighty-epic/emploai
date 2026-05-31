from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.runtime_paths import auth_store_root


REMOTE_CONTROL_STORE_FILENAME = "remote_control_plane.json"
REMOTE_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
REMOTE_PAIRING_TTL_SECONDS = 60 * 10


def _utc_iso(timestamp: Optional[float]) -> Optional[str]:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


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


def _normalize_email(value: str) -> str:
    return value.strip().casefold()


def _project_groups_from_sessions(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for session in sessions:
        workspace = str(session.get("workspace") or "").strip()
        if not workspace:
            workspace = "workspace://default"
        label = Path(workspace).name or workspace
        group = groups.setdefault(
            workspace,
            {
                "path": workspace,
                "label": label,
                "session_ids": [],
                "pinned": False,
                "collapsed": False,
            },
        )
        session_id = str(session.get("id") or "").strip()
        if session_id:
            group["session_ids"].append(session_id)
    ordered = list(groups.values())
    ordered.sort(key=lambda item: (str(item.get("label") or "").casefold(), str(item.get("path") or "").casefold()))
    return ordered


class RemoteControlPlaneStore:
    def __init__(self, root_path: Optional[Path] = None):
        self.root_path = root_path or auth_store_root()
        self.file_path = self.root_path / REMOTE_CONTROL_STORE_FILENAME
        self._lock = threading.RLock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _default_data(self) -> Dict[str, Any]:
        return {
            "next_user_id": 1,
            "users": {},
            "users_by_email": {},
            "remote_sessions": {},
            "desktops": {},
            "mobiles": {},
            "pairings": {},
            "shared_state": {},
        }

    def _load(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            return self._default_data()
        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_data()
        if not isinstance(payload, dict):
            return self._default_data()
        payload.setdefault("next_user_id", 1)
        payload.setdefault("users", {})
        payload.setdefault("users_by_email", {})
        payload.setdefault("remote_sessions", {})
        payload.setdefault("desktops", {})
        payload.setdefault("mobiles", {})
        payload.setdefault("pairings", {})
        payload.setdefault("shared_state", {})
        self._cleanup(payload)
        return payload

    def _save(self) -> None:
        temp_path = self.file_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.file_path)

    def _cleanup(self, target: Optional[Dict[str, Any]] = None) -> None:
        data = target or self._data
        now = time.time()

        pairings = data.setdefault("pairings", {})
        for pairing_id, pairing in list(pairings.items()):
            expires_at = float(pairing.get("expires_at", 0) or 0)
            used_at = pairing.get("used_at")
            revoked_at = pairing.get("revoked_at")
            if revoked_at or used_at or (expires_at and expires_at < now):
                pairings.pop(pairing_id, None)

        sessions = data.setdefault("remote_sessions", {})
        for token_hash, session in list(sessions.items()):
            if session.get("revoked_at"):
                sessions.pop(token_hash, None)
                continue
            expires_at = float(session.get("expires_at", 0) or 0)
            if expires_at and expires_at < now:
                sessions.pop(token_hash, None)

    def _next_user_id(self) -> int:
        value = int(self._data.get("next_user_id", 1) or 1)
        self._data["next_user_id"] = value + 1
        return value

    def _user_key(self, user_id: int) -> str:
        return str(int(user_id))

    def _ensure_shared_state(self, user_id: int) -> Dict[str, Any]:
        key = self._user_key(user_id)
        record = self._data.setdefault("shared_state", {}).setdefault(
            key,
            {
                "user_id": int(user_id),
                "current_desktop_id": None,
                "current_session_id": None,
                "current_model": None,
                "current_variant": None,
                "desktop_connection": {
                    "status": "offline",
                    "desktop_id": None,
                    "desktop_name": None,
                    "last_heartbeat_at": None,
                },
                "sessions": [],
                "session_details": {},
                "jobs": [],
                "project_groups": [],
                "sync_version": 0,
                "updated_at": None,
            },
        )
        return record

    def _user_view(self, user: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "user_id": int(user.get("user_id", 0)),
            "email": str(user.get("email") or ""),
            "display_name": user.get("display_name"),
            "created_at": _utc_iso(user.get("created_at")),
            "last_login_at": _utc_iso(user.get("last_login_at")),
        }

    def _desktop_view(self, desktop: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "desktop_id": desktop.get("desktop_id"),
            "device_key": desktop.get("device_key"),
            "display_name": desktop.get("display_name"),
            "status": desktop.get("status", "offline"),
            "detail": desktop.get("detail"),
            "created_at": _utc_iso(desktop.get("created_at")),
            "last_seen_at": _utc_iso(desktop.get("last_seen_at")),
            "last_heartbeat_at": _utc_iso(desktop.get("last_heartbeat_at")),
            "paired_mobile_ids": list(desktop.get("paired_mobile_ids") or []),
        }

    def _mobile_view(self, mobile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mobile_id": mobile.get("mobile_id"),
            "device_name": mobile.get("device_name"),
            "device_platform": mobile.get("device_platform"),
            "paired_desktop_id": mobile.get("paired_desktop_id"),
            "created_at": _utc_iso(mobile.get("created_at")),
            "last_used_at": _utc_iso(mobile.get("last_used_at")),
        }

    def register_user(self, *, email: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        normalized_email = _normalize_email(email)
        if not normalized_email:
            raise ValueError("Email is required")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        with self._lock:
            self._cleanup()
            existing_user_id = self._data["users_by_email"].get(normalized_email)
            if existing_user_id:
                raise ValueError("An account with that email already exists")

            user_id = self._next_user_id()
            now = time.time()
            salt = secrets.token_hex(16)
            user = {
                "user_id": user_id,
                "email": normalized_email,
                "display_name": (display_name or "").strip() or normalized_email.split("@", 1)[0],
                "password_salt": salt,
                "password_hash": _hash_password(password, salt),
                "created_at": now,
                "last_login_at": None,
            }
            self._data["users"][self._user_key(user_id)] = user
            self._data["users_by_email"][normalized_email] = user_id
            self._ensure_shared_state(user_id)
            self._save()
            return self._user_view(user)

    def login(
        self,
        *,
        email: str,
        password: str,
        actor_kind: str,
        device_name: Optional[str] = None,
        device_platform: Optional[str] = None,
        device_key: Optional[str] = None,
        token_ttl_seconds: int = REMOTE_SESSION_TTL_SECONDS,
    ) -> Dict[str, Any]:
        normalized_email = _normalize_email(email)
        if actor_kind not in {"mobile", "desktop"}:
            raise ValueError("actor_kind must be mobile or desktop")

        with self._lock:
            self._cleanup()
            user_id = self._data["users_by_email"].get(normalized_email)
            if not user_id:
                raise ValueError("Unknown account")
            user = self._data["users"].get(self._user_key(int(user_id)))
            if not user:
                raise ValueError("Unknown account")

            expected = _hash_password(password, str(user.get("password_salt") or ""))
            if expected != str(user.get("password_hash") or ""):
                raise ValueError("Invalid password")

            now = time.time()
            user["last_login_at"] = now
            session_token = secrets.token_urlsafe(48)
            session_record: Dict[str, Any] = {
                "token_value": session_token,
                "user_id": int(user_id),
                "actor_kind": actor_kind,
                "created_at": now,
                "last_used_at": now,
                "expires_at": now + token_ttl_seconds,
                "revoked_at": None,
            }

            normalized_key = (device_key or "").strip() or None
            normalized_name = (device_name or "").strip() or ("EmploAI Desktop" if actor_kind == "desktop" else "EmploAI Mobile")
            normalized_platform = (device_platform or "").strip() or None

            if actor_kind == "desktop":
                desktop_id = self._find_or_create_desktop(
                    user_id=int(user_id),
                    display_name=normalized_name,
                    device_key=normalized_key,
                )
                desktop = self._data["desktops"][desktop_id]
                desktop["display_name"] = normalized_name
                desktop["device_platform"] = normalized_platform
                desktop["last_seen_at"] = now
                session_record["desktop_id"] = desktop_id
            else:
                mobile_id = self._find_or_create_mobile(
                    user_id=int(user_id),
                    device_name=normalized_name,
                    device_platform=normalized_platform,
                    device_key=normalized_key,
                )
                mobile = self._data["mobiles"][mobile_id]
                mobile["device_name"] = normalized_name
                mobile["device_platform"] = normalized_platform
                mobile["last_used_at"] = now
                session_record["mobile_id"] = mobile_id

            self._data["remote_sessions"][_hash_token(session_token)] = session_record
            self._save()
            return {
                "session_token": session_token,
                "expires_at": session_record["expires_at"],
                "user": self._user_view(user),
                "actor_kind": actor_kind,
                "desktop": self._desktop_view(self._data["desktops"][session_record["desktop_id"]]) if actor_kind == "desktop" else None,
                "mobile": self._mobile_view(self._data["mobiles"][session_record["mobile_id"]]) if actor_kind == "mobile" else None,
            }

    def _find_or_create_desktop(self, *, user_id: int, display_name: str, device_key: Optional[str]) -> str:
        for desktop_id, desktop in self._data["desktops"].items():
            if int(desktop.get("user_id", -1)) != int(user_id):
                continue
            if device_key and str(desktop.get("device_key") or "").strip() == device_key:
                return desktop_id
        desktop_id = f"dsk_{secrets.token_hex(8)}"
        now = time.time()
        self._data["desktops"][desktop_id] = {
            "desktop_id": desktop_id,
            "user_id": int(user_id),
            "display_name": display_name,
            "device_key": device_key,
            "created_at": now,
            "last_seen_at": now,
            "last_heartbeat_at": None,
            "status": "offline",
            "detail": None,
            "paired_mobile_ids": [],
        }
        return desktop_id

    def _find_or_create_mobile(
        self,
        *,
        user_id: int,
        device_name: str,
        device_platform: Optional[str],
        device_key: Optional[str],
    ) -> str:
        for mobile_id, mobile in self._data["mobiles"].items():
            if int(mobile.get("user_id", -1)) != int(user_id):
                continue
            if device_key and str(mobile.get("device_key") or "").strip() == device_key:
                return mobile_id
        mobile_id = f"mob_{secrets.token_hex(8)}"
        now = time.time()
        self._data["mobiles"][mobile_id] = {
            "mobile_id": mobile_id,
            "user_id": int(user_id),
            "device_name": device_name,
            "device_platform": device_platform,
            "device_key": device_key,
            "paired_desktop_id": None,
            "created_at": now,
            "last_used_at": now,
        }
        return mobile_id

    def resolve_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self._lock:
            self._cleanup()
            record = self._data["remote_sessions"].get(_hash_token(token))
            if not record:
                return None
            if record.get("revoked_at"):
                return None
            now = time.time()
            expires_at = float(record.get("expires_at", 0) or 0)
            if expires_at and expires_at < now:
                self._data["remote_sessions"].pop(_hash_token(token), None)
                self._save()
                return None
            record["last_used_at"] = now
            user = self._data["users"].get(self._user_key(int(record.get("user_id", 0))))
            if not user:
                return None
            payload = {
                "auth_kind": "remote_session",
                "user_id": int(record.get("user_id", 0)),
                "actor_kind": str(record.get("actor_kind") or ""),
                "expires_at": expires_at,
                "email": user.get("email"),
                "display_name": user.get("display_name"),
                "desktop_id": record.get("desktop_id"),
                "mobile_id": record.get("mobile_id"),
            }
            if record.get("desktop_id"):
                desktop = self._data["desktops"].get(str(record.get("desktop_id")))
                if desktop:
                    payload["desktop_name"] = desktop.get("display_name")
            if record.get("mobile_id"):
                mobile = self._data["mobiles"].get(str(record.get("mobile_id")))
                if mobile:
                    payload["device_name"] = mobile.get("device_name")
                    payload["device_platform"] = mobile.get("device_platform")
                    payload["paired_desktop_id"] = mobile.get("paired_desktop_id")
            self._save()
            return payload

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            user = self._data["users"].get(self._user_key(user_id))
            return self._user_view(user) if user else None

    def list_desktops(self, *, user_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            desktops = [
                self._desktop_view(desktop)
                for desktop in self._data["desktops"].values()
                if int(desktop.get("user_id", -1)) == int(user_id)
            ]
            desktops.sort(key=lambda item: (item.get("last_seen_at") or "", item.get("display_name") or ""), reverse=True)
            return desktops

    def create_pairing(self, *, user_id: int, desktop_id: str, ttl_seconds: int = REMOTE_PAIRING_TTL_SECONDS) -> Dict[str, Any]:
        with self._lock:
            desktop = self._data["desktops"].get(desktop_id)
            if not desktop or int(desktop.get("user_id", -1)) != int(user_id):
                raise KeyError("Unknown desktop")
            self._cleanup()
            pairing_id = f"pair_{secrets.token_hex(8)}"
            pairing_token = secrets.token_urlsafe(36)
            now = time.time()
            record = {
                "pairing_id": pairing_id,
                "pairing_token": pairing_token,
                "user_id": int(user_id),
                "desktop_id": desktop_id,
                "created_at": now,
                "expires_at": now + ttl_seconds,
                "used_at": None,
                "revoked_at": None,
            }
            self._data["pairings"][pairing_id] = record
            self._save()
            return {
                "pairing_id": pairing_id,
                "pairing_token": pairing_token,
                "desktop_id": desktop_id,
                "desktop_name": desktop.get("display_name"),
                "expires_in_seconds": ttl_seconds,
                "pairing_uri": f"emploai://pair?token={pairing_token}",
            }

    def complete_pairing(self, *, user_id: int, pairing_token: str, mobile_id: str) -> Dict[str, Any]:
        with self._lock:
            self._cleanup()
            pairing = None
            for item in self._data["pairings"].values():
                if str(item.get("pairing_token") or "") == str(pairing_token):
                    pairing = item
                    break
            if not pairing:
                raise KeyError("Unknown pairing")
            if int(pairing.get("user_id", -1)) != int(user_id):
                raise ValueError("Pairing token belongs to a different account")
            if pairing.get("used_at"):
                raise ValueError("Pairing token already used")
            desktop_id = str(pairing.get("desktop_id") or "")
            desktop = self._data["desktops"].get(desktop_id)
            mobile = self._data["mobiles"].get(mobile_id)
            if not desktop or not mobile:
                raise ValueError("Desktop or mobile device is unavailable")
            if int(desktop.get("user_id", -1)) != int(user_id) or int(mobile.get("user_id", -1)) != int(user_id):
                raise ValueError("Pairing devices do not belong to the same account")
            mobile["paired_desktop_id"] = desktop_id
            paired_mobile_ids = list(desktop.get("paired_mobile_ids") or [])
            if mobile_id not in paired_mobile_ids:
                paired_mobile_ids.append(mobile_id)
            desktop["paired_mobile_ids"] = paired_mobile_ids
            pairing["used_at"] = time.time()
            state = self._ensure_shared_state(user_id)
            state["current_desktop_id"] = desktop_id
            state["updated_at"] = time.time()
            state["sync_version"] = int(state.get("sync_version", 0) or 0) + 1
            self._save()
            return {
                "desktop": self._desktop_view(desktop),
                "mobile": self._mobile_view(mobile),
                "shared_state": dict(state),
            }

    def get_shared_state(self, *, user_id: int) -> Dict[str, Any]:
        with self._lock:
            state = self._ensure_shared_state(user_id)
            return json.loads(json.dumps(state))

    def mark_desktop_connection(
        self,
        *,
        user_id: int,
        desktop_id: str,
        status: str,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            desktop = self._data["desktops"].get(desktop_id)
            if not desktop or int(desktop.get("user_id", -1)) != int(user_id):
                raise KeyError("Unknown desktop")
            now = time.time()
            desktop["status"] = status
            desktop["detail"] = detail
            desktop["last_seen_at"] = now
            desktop["last_heartbeat_at"] = now if status == "connected" else desktop.get("last_heartbeat_at")
            state = self._ensure_shared_state(user_id)
            state["current_desktop_id"] = desktop_id
            state["desktop_connection"] = {
                "status": status,
                "desktop_id": desktop_id,
                "desktop_name": desktop.get("display_name"),
                "last_heartbeat_at": _utc_iso(desktop.get("last_heartbeat_at")),
                "detail": detail,
            }
            state["updated_at"] = now
            state["sync_version"] = int(state.get("sync_version", 0) or 0) + 1
            self._save()
            return self._desktop_view(desktop)

    def heartbeat_desktop(self, *, user_id: int, desktop_id: str, detail: Optional[str] = None) -> Dict[str, Any]:
        return self.mark_desktop_connection(user_id=user_id, desktop_id=desktop_id, status="connected", detail=detail)

    def update_shared_snapshot(
        self,
        *,
        user_id: int,
        desktop_id: str,
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._lock:
            desktop = self._data["desktops"].get(desktop_id)
            if not desktop or int(desktop.get("user_id", -1)) != int(user_id):
                raise KeyError("Unknown desktop")
            now = time.time()
            sessions = list(snapshot.get("sessions") or [])
            session_details = dict(snapshot.get("session_details") or {})
            jobs = list(snapshot.get("jobs") or [])
            current_session_id = str(snapshot.get("current_session_id") or "").strip() or None
            current_model = snapshot.get("current_model")
            current_variant = snapshot.get("current_variant")

            state = self._ensure_shared_state(user_id)
            state["current_desktop_id"] = desktop_id
            state["current_session_id"] = current_session_id
            state["current_model"] = current_model
            state["current_variant"] = current_variant
            state["sessions"] = sessions
            state["session_details"] = session_details
            state["jobs"] = jobs
            state["project_groups"] = list(snapshot.get("project_groups") or _project_groups_from_sessions(sessions))
            state["desktop_connection"] = {
                "status": "connected",
                "desktop_id": desktop_id,
                "desktop_name": snapshot.get("desktop_name") or desktop.get("display_name"),
                "last_heartbeat_at": _utc_iso(now),
                "detail": snapshot.get("desktop_status_detail"),
            }
            state["updated_at"] = now
            state["sync_version"] = int(state.get("sync_version", 0) or 0) + 1

            desktop["status"] = "connected"
            desktop["detail"] = snapshot.get("desktop_status_detail")
            desktop["last_seen_at"] = now
            desktop["last_heartbeat_at"] = now
            self._save()
            return json.loads(json.dumps(state))

    def paired_desktop_id_for_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        actor_kind = str(payload.get("actor_kind") or "").strip()
        if actor_kind == "desktop":
            return str(payload.get("desktop_id") or "").strip() or None
        if actor_kind != "mobile":
            return None
        explicit = str(payload.get("paired_desktop_id") or "").strip()
        if explicit:
            return explicit
        mobile_id = str(payload.get("mobile_id") or "").strip()
        if not mobile_id:
            return None
        with self._lock:
            mobile = self._data["mobiles"].get(mobile_id)
            if not mobile:
                return None
            return str(mobile.get("paired_desktop_id") or "").strip() or None

