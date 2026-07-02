from __future__ import annotations

from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreAccountMixin:
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

    def _find_or_create_mobile_locked(
        self,
        *,
        user_id: int,
        device_name: str,
        device_platform: Optional[str],
        device_key: Optional[str],
    ) -> str:
        if device_key:
            row = self._conn.execute(
                "SELECT mobile_id FROM mobiles WHERE user_id = ? AND device_key = ?",
                (int(user_id), device_key),
            ).fetchone()
            if row:
                return str(row["mobile_id"])
        mobile_id = f"mob_{secrets.token_hex(8)}"
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO mobiles(mobile_id, user_id, device_name, device_platform, device_key, paired_desktop_id, created_at, last_used_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mobile_id, int(user_id), device_name, device_platform, device_key, None, now, now),
        )
        return mobile_id

    def resolve_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        token_hash = _hash_token(token)
        with self._lock:
            self._cleanup_locked()
            record = self._conn.execute("SELECT * FROM remote_sessions WHERE token_hash = ?", (token_hash,)).fetchone()
            if not record or record["revoked_at"]:
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
                "email": user["email"],
                "display_name": user["display_name"],
                "desktop_id": record["desktop_id"],
                "mobile_id": record["mobile_id"],
            }
            if record["desktop_id"]:
                desktop = self._conn.execute("SELECT * FROM desktops WHERE desktop_id = ?", (record["desktop_id"],)).fetchone()
                if desktop:
                    payload["desktop_name"] = desktop["display_name"]
            if record["mobile_id"]:
                mobile = self._conn.execute("SELECT * FROM mobiles WHERE mobile_id = ?", (record["mobile_id"],)).fetchone()
                if mobile:
                    payload["device_name"] = mobile["device_name"]
                    payload["device_platform"] = mobile["device_platform"]
                    payload["paired_desktop_id"] = mobile["paired_desktop_id"]
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
        mobile_id: Optional[str] = None,
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
            if mobile_id is not None and str(record["mobile_id"] or "") != str(mobile_id or ""):
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

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            return self._user_view(user) if user else None

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
                raise KeyError("Unknown account")
            sanitized = _sanitize_user_profile(profile)
            self._conn.execute(
                "INSERT INTO user_profiles(user_id, payload, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
                (int(user_id), _json_dumps(sanitized), time.time()),
            )
            self._conn.commit()
            self._secure_db_files()
            return json.loads(json.dumps(sanitized))

    def delete_user_account_data(self, *, user_id: int, preserve_session_token_hash: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            user = self._conn.execute("SELECT user_id FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            if not user:
                raise KeyError("Unknown account")
            now = time.time()
            preserved_hash = str(preserve_session_token_hash or "").strip().lower()
            profile = _default_user_profile()
            self._conn.execute(
                "INSERT INTO user_profiles(user_id, payload, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
                (int(user_id), _json_dumps(profile), now),
            )
            secret_cursor = self._conn.execute("DELETE FROM user_secrets WHERE user_id = ?", (int(user_id),))
            if preserved_hash:
                session_cursor = self._conn.execute(
                    "UPDATE remote_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL AND token_hash != ?",
                    (now, int(user_id), preserved_hash),
                )
            else:
                session_cursor = self._conn.execute(
                    "UPDATE remote_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                    (now, int(user_id)),
                )
            pairing_cursor = self._conn.execute(
                "UPDATE pairings SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL AND used_at IS NULL",
                (now, int(user_id)),
            )
            mobile_cursor = self._conn.execute(
                "UPDATE mobiles SET paired_desktop_id = NULL WHERE user_id = ? AND paired_desktop_id IS NOT NULL",
                (int(user_id),),
            )
            desktop_cursor = self._conn.execute(
                """
                UPDATE desktops
                SET status = 'offline', detail = ?, paired_mobile_ids = '[]', last_seen_at = ?, last_heartbeat_at = NULL
                WHERE user_id = ?
                """,
                ("account data reset", now, int(user_id)),
            )
            self._conn.execute("DELETE FROM pending_confirmations WHERE user_id = ?", (int(user_id),))
            self._conn.execute("DELETE FROM cloud_session_snapshots WHERE user_id = ?", (int(user_id),))
            shared_state = {
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
                "sidebar_state": _empty_sidebar_state(),
                "sync_version": int(now),
                "updated_at": now,
            }
            self._write_shared_state_locked(int(user_id), shared_state)
            self._conn.commit()
            self._secure_db_files()
            return {
                "deleted_secrets": int(secret_cursor.rowcount or 0),
                "revoked_sessions": int(session_cursor.rowcount or 0),
                "revoked_pairings": int(pairing_cursor.rowcount or 0),
                "unpaired_mobiles": int(mobile_cursor.rowcount or 0),
                "reset_desktops": int(desktop_cursor.rowcount or 0),
                "profile_reset": True,
                "shared_state_reset": True,
                "profile": json.loads(json.dumps(profile)),
            }

    def upsert_user_secrets(
        self,
        *,
        user_id: int,
        namespace: str = "setup",
        secrets_payload: Dict[str, str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            user = self._conn.execute("SELECT user_id FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            if not user:
                raise KeyError("Unknown account")
            now = time.time()
            metadata_by_name = metadata if isinstance(metadata, dict) else {}
            updated_items: List[Dict[str, Any]] = []
            secret_items = list(dict(secrets_payload or {}).items())
            if len(secret_items) > MAX_SECRET_ITEMS_PER_REQUEST:
                raise ValueError("Too many secrets in one request")
            for raw_name, raw_value in secret_items:
                item_namespace, name = _validate_secret_location(namespace, str(raw_name or ""))
                value = str(raw_value or "").strip()
                if not value:
                    continue
                if len(value) > MAX_SECRET_VALUE_CHARS:
                    raise ValueError("Secret value is too large")
                ciphertext, nonce = self._encrypt_user_secret(
                    user_id=int(user_id),
                    namespace=item_namespace,
                    name=name,
                    value=value,
                )
                item_metadata = _safe_secret_metadata(metadata_by_name.get(name, {}))
                redacted_value = _redact_secret_value(value)
                existing = self._conn.execute(
                    "SELECT created_at FROM user_secrets WHERE user_id = ? AND namespace = ? AND name = ?",
                    (int(user_id), item_namespace, name),
                ).fetchone()
                created_at = float(existing["created_at"]) if existing else now
                self._conn.execute(
                    """
                    INSERT INTO user_secrets(
                        user_id, namespace, name, ciphertext, nonce, key_version, redacted_value, metadata, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, namespace, name) DO UPDATE SET
                        ciphertext = excluded.ciphertext,
                        nonce = excluded.nonce,
                        key_version = excluded.key_version,
                        redacted_value = excluded.redacted_value,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(user_id),
                        item_namespace,
                        name,
                        ciphertext,
                        nonce,
                        SECRET_VAULT_KEY_VERSION,
                        redacted_value,
                        _json_dumps(item_metadata),
                        created_at,
                        now,
                    ),
                )
                updated_items.append(
                    {
                        "namespace": item_namespace,
                        "name": name,
                        "redacted_value": redacted_value,
                        "metadata": item_metadata,
                        "created_at": _utc_iso(created_at),
                        "updated_at": _utc_iso(now),
                    }
                )
            self._conn.commit()
            self._secure_db_files()
            return updated_items

    def list_user_secrets(self, *, user_id: int, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        item_namespace = _validate_secret_namespace(namespace) if namespace is not None else None
        with self._lock:
            params: tuple[Any, ...]
            query = "SELECT namespace, name, redacted_value, metadata, created_at, updated_at FROM user_secrets WHERE user_id = ?"
            params = (int(user_id),)
            if item_namespace:
                query += " AND namespace = ?"
                params = (int(user_id), item_namespace)
            query += " ORDER BY namespace ASC, name ASC"
            rows = self._conn.execute(query, params).fetchall()
            return [
                {
                    "namespace": str(row["namespace"] or ""),
                    "name": str(row["name"] or ""),
                    "redacted_value": str(row["redacted_value"] or ""),
                    "metadata": _json_loads(row["metadata"], {}),
                    "created_at": _utc_iso(row["created_at"]),
                    "updated_at": _utc_iso(row["updated_at"]),
                }
                for row in rows
            ]

    def reveal_user_secrets(self, *, user_id: int, namespace: str = "setup", names: Optional[List[str]] = None) -> Dict[str, str]:
        item_namespace = _validate_secret_namespace(namespace)
        requested_names = [str(name or "").strip() for name in list(names or []) if str(name or "").strip()]
        if len(requested_names) > MAX_SECRET_REVEAL_NAMES:
            raise ValueError("Too many secrets requested")
        for name in requested_names:
            _validate_secret_location(item_namespace, name)
        with self._lock:
            params: List[Any] = [int(user_id), item_namespace]
            query = "SELECT namespace, name, ciphertext, nonce, key_version FROM user_secrets WHERE user_id = ? AND namespace = ?"
            if requested_names:
                placeholders = ",".join("?" for _ in requested_names)
                query += f" AND name IN ({placeholders})"
                params.extend(requested_names)
            rows = self._conn.execute(query, tuple(params)).fetchall()
            revealed: Dict[str, str] = {}
            for row in rows:
                name = str(row["name"] or "")
                revealed[name] = self._decrypt_user_secret(
                    user_id=int(user_id),
                    namespace=str(row["namespace"] or item_namespace),
                    name=name,
                    ciphertext=bytes(row["ciphertext"]),
                    nonce=bytes(row["nonce"]),
                    key_version=str(row["key_version"] or SECRET_VAULT_KEY_VERSION),
                )
            return revealed

    def delete_user_secret(self, *, user_id: int, namespace: str, name: str) -> bool:
        item_namespace, item_name = _validate_secret_location(namespace, name)
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM user_secrets WHERE user_id = ? AND namespace = ? AND name = ?",
                (int(user_id), item_namespace, item_name),
            )
            self._conn.commit()
            self._secure_db_files()
            return cursor.rowcount > 0
