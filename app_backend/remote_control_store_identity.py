from __future__ import annotations

from app_backend.fleet_identity_profiles import DEFAULT_WORKER_DISPLAY_NAME
from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreIdentityMixin:
    def ensure_company_membership_identities(
        self,
        *,
        user_id: int,
        desktop_id: str,
        company_id: str,
        company_name: Optional[str] = None,
        membership_role: str = "worker_node",
        adopt_unscoped: bool = False,
    ) -> Dict[str, Any]:
        """Reconcile the manager and optional default worker for one membership."""

        clean_company_id = str(company_id or "").strip()
        if not clean_company_id:
            raise ValueError("A company ID is required.")
        with self._lock:
            manager_name = str(company_name or "EmploAI Desktop").strip()[:MAX_DISPLAY_NAME_CHARS] or "EmploAI Desktop"
            manager = self._ensure_manager_instance_locked(
                user_id=int(user_id),
                desktop_id=str(desktop_id or "").strip(),
                display_name=manager_name,
                company_id=clean_company_id,
                membership_role=membership_role,
                adopt_unscoped=adopt_unscoped,
            )
            worker = self._ensure_default_worker_locked(
                user_id=int(user_id),
                desktop_id=str(desktop_id or "").strip(),
                display_name=DEFAULT_WORKER_DISPLAY_NAME,
                company_id=clean_company_id,
                membership_role=membership_role,
                adopt_unscoped=adopt_unscoped,
            )
            worker_identity_row = (
                self._conn.execute(
                    "SELECT * FROM fleet_instances WHERE instance_id = ?",
                    (worker["instance_id"],),
                ).fetchone()
                if worker
                else None
            )
            self._conn.commit()
            self._secure_db_files()
            return {
                "manager_identity": self._identity_view(
                    self._conn.execute(
                        "SELECT * FROM fleet_instances WHERE instance_id = ?",
                        (manager["instance_id"],),
                    ).fetchone()
                ),
                "default_worker_identity": (
                    self._identity_view(worker_identity_row)
                    if worker_identity_row
                    else None
                ),
            }

    def ensure_standalone_manager_desktop(
        self,
        *,
        user_id: int,
        display_name: Optional[str] = None,
        device_platform: Optional[str] = None,
        device_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            if not user:
                self._conn.execute(
                    """
                    INSERT INTO users(user_id, email, display_name, password_salt, password_hash, created_at, last_login_at, email_verified_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(user_id),
                        f"local-{int(user_id)}@emploai.local",
                        "Local Desktop",
                        "standalone-local",
                        "standalone-local",
                        now,
                        now,
                        now,
                    ),
                )
            else:
                self._conn.execute("UPDATE users SET last_login_at = ? WHERE user_id = ?", (now, int(user_id)))

            self._ensure_user_profile_locked(int(user_id))
            manager_name = str(display_name or "EmploAI Desktop").strip()[:MAX_DISPLAY_NAME_CHARS] or "EmploAI Desktop"
            manager_key = str(device_key or "standalone-desktop").strip()[:MAX_DEVICE_KEY_CHARS] or "standalone-desktop"
            platform = str(device_platform or "desktop-electron").strip()[:MAX_DEVICE_PLATFORM_CHARS] or "desktop-electron"
            desktop_id = self._find_or_create_desktop_locked(
                user_id=int(user_id),
                display_name=manager_name,
                device_key=manager_key,
            )
            self._conn.execute(
                """
                UPDATE desktops
                SET display_name = ?, device_platform = ?, status = 'online', detail = ?, last_seen_at = ?, last_heartbeat_at = ?
                WHERE desktop_id = ?
                """,
                (manager_name, platform, "local standalone manager", now, now, desktop_id),
            )
            self._ensure_manager_instance_locked(user_id=int(user_id), desktop_id=desktop_id, display_name=manager_name)
            self._ensure_default_worker_locked(
                user_id=int(user_id),
                desktop_id=desktop_id,
                display_name=DEFAULT_WORKER_DISPLAY_NAME,
            )
            state = self._ensure_shared_state_locked(int(user_id))
            state["current_desktop_id"] = desktop_id
            state["desktop_connection"] = {
                "status": "online",
                "desktop_id": desktop_id,
                "desktop_name": manager_name,
                "last_heartbeat_at": now,
                "detail": "local standalone manager",
            }
            self._bump_shared_state_locked(int(user_id), state)
            self._conn.commit()
            self._secure_db_files()
            desktop = self._conn.execute("SELECT * FROM desktops WHERE desktop_id = ?", (desktop_id,)).fetchone()
            return self._desktop_view(desktop)

    def _find_or_create_desktop_locked(self, *, user_id: int, display_name: str, device_key: Optional[str]) -> str:
        if device_key:
            row = self._conn.execute(
                "SELECT desktop_id FROM desktops WHERE user_id = ? AND device_key = ?",
                (int(user_id), device_key),
            ).fetchone()
            if row:
                return str(row["desktop_id"])
        desktop_id = f"dsk_{secrets.token_hex(8)}"
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO desktops(
                desktop_id, user_id, device_key, display_name, device_platform, status, detail,
                created_at, last_seen_at, last_heartbeat_at, paired_mobile_ids
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (desktop_id, int(user_id), device_key, display_name, None, "offline", None, now, now, None, "[]"),
        )
        return desktop_id

    def resolve_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        token_hash = _hash_token(token)
        with self._lock:
            self._cleanup_locked()
            record = self._conn.execute("SELECT * FROM remote_sessions WHERE token_hash = ?", (token_hash,)).fetchone()
            if not record or record["revoked_at"] or str(record["actor_kind"] or "") != "desktop":
                return None
            now = time.time()
            expires_at = float(record["expires_at"] or 0)
            if expires_at and expires_at < now:
                self._conn.execute("DELETE FROM remote_sessions WHERE token_hash = ?", (token_hash,))
                self._conn.commit()
                return None
            user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (int(record["user_id"]),)).fetchone()
            if not user:
                return None
            self._conn.execute("UPDATE remote_sessions SET last_used_at = ? WHERE token_hash = ?", (now, token_hash))
            payload = {
                "auth_kind": "remote_session",
                "user_id": int(record["user_id"]),
                "actor_kind": str(record["actor_kind"] or ""),
                "session_token_hash": token_hash,
                "expires_at": expires_at,
                "desktop_id": record["desktop_id"],
            }
            if record["desktop_id"]:
                desktop = self._conn.execute("SELECT * FROM desktops WHERE desktop_id = ?", (record["desktop_id"],)).fetchone()
                if desktop:
                    payload["desktop_name"] = desktop["display_name"]
            self._conn.commit()
            self._secure_db_files()
            return payload

    def is_session_token_hash_active(
        self,
        *,
        token_hash: str,
        user_id: int,
        actor_kind: Optional[str] = None,
        desktop_id: Optional[str] = None,
    ) -> bool:
        clean_hash = str(token_hash or "").strip().lower()
        if not clean_hash:
            return False
        with self._lock:
            self._cleanup_locked()
            record = self._conn.execute("SELECT * FROM remote_sessions WHERE token_hash = ?", (clean_hash,)).fetchone()
            if not record or record["revoked_at"]:
                return False
            now = time.time()
            expires_at = float(record["expires_at"] or 0)
            if expires_at and expires_at < now:
                self._conn.execute("DELETE FROM remote_sessions WHERE token_hash = ?", (clean_hash,))
                self._conn.commit()
                self._secure_db_files()
                return False
            if int(record["user_id"] or 0) != int(user_id):
                return False
            if actor_kind is not None and str(record["actor_kind"] or "") != str(actor_kind or ""):
                return False
            if desktop_id is not None and str(record["desktop_id"] or "") != str(desktop_id or ""):
                return False
            return True

    def revoke_session_token(self, token: str) -> bool:
        if not token:
            return False
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE remote_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (time.time(), _hash_token(token)),
            )
            self._cleanup_locked()
            self._conn.commit()
            return cursor.rowcount > 0

    def get_user_profile(self, *, user_id: int) -> Dict[str, Any]:
        with self._lock:
            profile = self._ensure_user_profile_locked(int(user_id))
            self._conn.commit()
            self._secure_db_files()
            return json.loads(json.dumps(profile))

    def update_user_profile(self, *, user_id: int, profile: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            user = self._conn.execute("SELECT user_id FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            if not user:
                raise KeyError("Unknown local identity")
            sanitized = _sanitize_user_profile(profile)
            self._conn.execute(
                "INSERT INTO user_profiles(user_id, payload, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
                (int(user_id), _json_dumps(sanitized), time.time()),
            )
            self._conn.commit()
            self._secure_db_files()
            return json.loads(json.dumps(sanitized))
