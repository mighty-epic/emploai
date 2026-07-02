from __future__ import annotations

from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreCommandMixin:
    def enqueue_remote_desktop_command(
        self,
        *,
        user_id: int,
        desktop_id: str,
        command_type: str,
        payload: Optional[Dict[str, Any]] = None,
        wants_reply: bool = False,
        ttl_seconds: int = 30,
    ) -> Dict[str, Any]:
        clean_desktop_id = str(desktop_id or "").strip()
        clean_command_type = str(command_type or "").strip()
        if not clean_desktop_id or not clean_command_type:
            raise ValueError("desktop_id and command_type are required")
        with self._lock:
            self._cleanup_locked()
            desktop = self._conn.execute(
                "SELECT desktop_id FROM desktops WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), clean_desktop_id),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown desktop")
            now = time.time()
            command_id = f"cmd_{secrets.token_hex(8)}"
            expires_at = now + max(1, min(300, int(ttl_seconds or 30)))
            self._conn.execute(
                """
                INSERT INTO remote_desktop_commands(
                    command_id, user_id, desktop_id, command_type, payload, status, result, error,
                    wants_reply, created_at, expires_at, claimed_at, claimed_by_instance_id, completed_at
                ) VALUES(?, ?, ?, ?, ?, 'pending', '{}', NULL, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    command_id,
                    int(user_id),
                    clean_desktop_id,
                    clean_command_type,
                    _json_dumps(payload or {}),
                    1 if wants_reply else 0,
                    now,
                    expires_at,
                ),
            )
            self._conn.commit()
            return {
                "command_id": command_id,
                "user_id": int(user_id),
                "desktop_id": clean_desktop_id,
                "command_type": clean_command_type,
                "payload": dict(payload or {}),
                "status": "pending",
                "wants_reply": bool(wants_reply),
                "created_at": _utc_iso(now),
                "expires_at": _utc_iso(expires_at),
            }

    def claim_remote_desktop_commands(
        self,
        *,
        user_id: int,
        desktop_id: str,
        instance_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        clean_instance_id = str(instance_id or "").strip()[:128] or "unknown"
        with self._lock:
            self._cleanup_locked()
            now = time.time()
            rows = self._conn.execute(
                """
                SELECT * FROM remote_desktop_commands
                WHERE user_id = ? AND desktop_id = ? AND status = 'pending' AND expires_at > ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (int(user_id), str(desktop_id or "").strip(), now, max(1, min(50, int(limit or 10)))),
            ).fetchall()
            claimed: List[Dict[str, Any]] = []
            for row in rows:
                self._conn.execute(
                    """
                    UPDATE remote_desktop_commands
                    SET status = 'claimed', claimed_at = ?, claimed_by_instance_id = ?
                    WHERE command_id = ? AND status = 'pending'
                    """,
                    (now, clean_instance_id, row["command_id"]),
                )
                claimed.append(
                    {
                        "command_id": row["command_id"],
                        "user_id": int(row["user_id"]),
                        "desktop_id": row["desktop_id"],
                        "command_type": row["command_type"],
                        "payload": _json_loads(row["payload"], {}),
                        "status": "claimed",
                        "wants_reply": bool(row["wants_reply"]),
                        "created_at": _utc_iso(row["created_at"]),
                        "expires_at": _utc_iso(row["expires_at"]),
                    }
                )
            self._conn.commit()
            return claimed

    def complete_remote_desktop_command(
        self,
        *,
        command_id: str,
        user_id: int,
        desktop_id: str,
        ok: bool,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        clean_command_id = str(command_id or "").strip()
        if not clean_command_id:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM remote_desktop_commands WHERE command_id = ? AND user_id = ? AND desktop_id = ?",
                (clean_command_id, int(user_id), str(desktop_id or "").strip()),
            ).fetchone()
            if not row or str(row["status"] or "") in {"completed", "failed", "expired"}:
                return False
            now = time.time()
            result_payload = dict(payload or {})
            status = "completed" if ok else "failed"
            error = None if ok else str(result_payload.get("error") or "Remote desktop command failed")
            self._conn.execute(
                """
                UPDATE remote_desktop_commands
                SET status = ?, result = ?, error = ?, completed_at = ?
                WHERE command_id = ?
                """,
                (status, _json_dumps(result_payload), error, now, clean_command_id),
            )
            self._conn.commit()
            return True

    def fail_remote_desktop_command(
        self,
        *,
        command_id: str,
        user_id: int,
        desktop_id: str,
        error: str,
    ) -> bool:
        return self.complete_remote_desktop_command(
            command_id=command_id,
            user_id=user_id,
            desktop_id=desktop_id,
            ok=False,
            payload={"ok": False, "error": str(error or "Remote desktop command failed")},
        )

    def get_remote_desktop_command_result(self, *, command_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        clean_command_id = str(command_id or "").strip()
        if not clean_command_id:
            return None
        with self._lock:
            self._cleanup_locked()
            row = self._conn.execute(
                "SELECT * FROM remote_desktop_commands WHERE command_id = ? AND user_id = ?",
                (clean_command_id, int(user_id)),
            ).fetchone()
            if not row:
                return None
            status = str(row["status"] or "")
            if status in {"completed", "failed"}:
                payload = _json_loads(row["result"], {})
                if not isinstance(payload, dict):
                    payload = {}
                if "ok" not in payload:
                    payload["ok"] = status == "completed"
                if status == "failed":
                    payload.setdefault("error", row["error"] or "Remote desktop command failed")
                return {
                    "command_id": row["command_id"],
                    "status": status,
                    "payload": payload,
                    "completed_at": _utc_iso(row["completed_at"]),
                }
            if float(row["expires_at"] or 0) < time.time():
                self._conn.execute(
                    "UPDATE remote_desktop_commands SET status = 'expired', completed_at = ?, error = ? WHERE command_id = ?",
                    (time.time(), "Remote desktop command expired", clean_command_id),
                )
                self._conn.commit()
                return {
                    "command_id": row["command_id"],
                    "status": "expired",
                    "payload": {"ok": False, "error": "Remote desktop command expired"},
                    "completed_at": _utc_iso(time.time()),
                }
            return {
                "command_id": row["command_id"],
                "status": status,
                "payload": {},
                "completed_at": None,
            }
