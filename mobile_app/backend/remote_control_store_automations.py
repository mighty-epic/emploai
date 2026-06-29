from __future__ import annotations

from mobile_app.backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreAutomationMixin:
    def upsert_automation(
        self,
        *,
        user_id: int,
        automation_id: Optional[str] = None,
        name: str,
        prompt: str,
        schedule: Optional[str] = None,
        schedule_mode: Optional[str] = None,
        enabled: bool = True,
        status: str = "active",
        target_kind: str = "active_identity",
        target_identity_id: Optional[str] = None,
        target_group_id: Optional[str] = None,
        target_chat_id: Optional[str] = None,
        chat_target: str = "existing_or_new",
        permission_mode: Optional[str] = None,
        tool_packs: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        next_run_at: Optional[float] = None,
        last_run_at: Optional[float] = None,
        one_time: bool = False,
        requires_confirmation: bool = False,
        confirmation_status: Optional[str] = None,
        confirmation_expires_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        clean_name = str(name or "").strip()[:MAX_DISPLAY_NAME_CHARS]
        clean_prompt = str(prompt or "").strip()
        if not clean_name:
            raise ValueError("name is required")
        if not clean_prompt:
            raise ValueError("prompt is required")
        with self._lock:
            now = time.time()
            clean_id = str(automation_id or "").strip() or f"auto_{secrets.token_hex(8)}"
            existing = self._conn.execute(
                "SELECT created_at, run_count, error_count FROM automations WHERE user_id = ? AND automation_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            created_at = float(existing["created_at"]) if existing else now
            run_count = int(existing["run_count"] or 0) if existing else 0
            error_count = int(existing["error_count"] or 0) if existing else 0
            self._conn.execute(
                """
                INSERT INTO automations(
                    automation_id, user_id, name, prompt, schedule, schedule_mode, enabled, status,
                    target_kind, target_identity_id, target_group_id, target_chat_id, chat_target,
                    permission_mode, tool_packs, metadata, created_at, updated_at, next_run_at,
                    last_run_at, run_count, error_count, one_time, requires_confirmation,
                    confirmation_status, confirmation_expires_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, automation_id) DO UPDATE SET
                    name = excluded.name,
                    prompt = excluded.prompt,
                    schedule = excluded.schedule,
                    schedule_mode = excluded.schedule_mode,
                    enabled = excluded.enabled,
                    status = excluded.status,
                    target_kind = excluded.target_kind,
                    target_identity_id = excluded.target_identity_id,
                    target_group_id = excluded.target_group_id,
                    target_chat_id = excluded.target_chat_id,
                    chat_target = excluded.chat_target,
                    permission_mode = excluded.permission_mode,
                    tool_packs = excluded.tool_packs,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at,
                    next_run_at = excluded.next_run_at,
                    last_run_at = COALESCE(excluded.last_run_at, automations.last_run_at),
                    one_time = excluded.one_time,
                    requires_confirmation = excluded.requires_confirmation,
                    confirmation_status = excluded.confirmation_status,
                    confirmation_expires_at = excluded.confirmation_expires_at
                """,
                (
                    clean_id,
                    int(user_id),
                    clean_name,
                    clean_prompt[:20_000],
                    schedule,
                    schedule_mode,
                    1 if enabled else 0,
                    str(status or "active")[:80],
                    str(target_kind or "active_identity")[:80],
                    target_identity_id,
                    target_group_id,
                    target_chat_id,
                    str(chat_target or "existing_or_new")[:80],
                    permission_mode,
                    _json_dumps(list(tool_packs or [])),
                    _json_dumps(metadata or {}),
                    created_at,
                    now,
                    next_run_at,
                    last_run_at,
                    run_count,
                    error_count,
                    1 if one_time else 0,
                    1 if requires_confirmation else 0,
                    confirmation_status,
                    confirmation_expires_at,
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="automation_upserted",
                target_kind="automation",
                target_id=clean_id,
                metadata={"name": clean_name, "schedule": schedule, "enabled": bool(enabled)},
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM automations WHERE automation_id = ?", (clean_id,)).fetchone()
            return self._automation_view(row)

    def list_automations(self, *, user_id: int, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM automations WHERE user_id = ? ORDER BY enabled DESC, updated_at DESC LIMIT ?",
                (int(user_id), max(1, min(int(limit or 500), 1000))),
            ).fetchall()
            return [self._automation_view(row) for row in rows]

    def get_automation(self, *, user_id: int, automation_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM automations WHERE user_id = ? AND automation_id = ?",
                (int(user_id), str(automation_id or "").strip()),
            ).fetchone()
            if not row:
                raise KeyError("Unknown automation")
            return self._automation_view(row)

    def set_automation_enabled(self, *, user_id: int, automation_id: str, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            cursor = self._conn.execute(
                "UPDATE automations SET enabled = ?, status = ?, updated_at = ? WHERE user_id = ? AND automation_id = ?",
                (1 if enabled else 0, "active" if enabled else "paused", now, int(user_id), str(automation_id or "").strip()),
            )
            if cursor.rowcount <= 0:
                raise KeyError("Unknown automation")
            self._audit_locked(
                user_id=int(user_id),
                event_type="automation_resumed" if enabled else "automation_paused",
                target_kind="automation",
                target_id=str(automation_id or "").strip(),
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute(
                "SELECT * FROM automations WHERE user_id = ? AND automation_id = ?",
                (int(user_id), str(automation_id or "").strip()),
            ).fetchone()
            return self._automation_view(row)

    def record_automation_run(
        self,
        *,
        user_id: int,
        automation_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            if str(status or "").lower() in {"failed", "error"}:
                update = "error_count = error_count + 1"
            else:
                update = "run_count = run_count + 1"
            cursor = self._conn.execute(
                f"UPDATE automations SET {update}, last_run_at = ?, updated_at = ? WHERE user_id = ? AND automation_id = ?",
                (now, now, int(user_id), str(automation_id or "").strip()),
            )
            if cursor.rowcount <= 0:
                raise KeyError("Unknown automation")
            self._audit_locked(
                user_id=int(user_id),
                event_type="automation_run_recorded",
                target_kind="automation",
                target_id=str(automation_id or "").strip(),
                metadata={"status": status, "error": error},
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute(
                "SELECT * FROM automations WHERE user_id = ? AND automation_id = ?",
                (int(user_id), str(automation_id or "").strip()),
            ).fetchone()
            return self._automation_view(row)

    def delete_automation(self, *, user_id: int, automation_id: str) -> bool:
        with self._lock:
            clean_id = str(automation_id or "").strip()
            existing = self._conn.execute(
                "SELECT * FROM automations WHERE user_id = ? AND automation_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            if not existing:
                return False
            self.archive_item(
                user_id=int(user_id),
                object_kind="automation",
                object_id=clean_id,
                display_name=existing["name"],
                payload={"automation": self._automation_view(existing)},
                metadata={"archive_reason": "automation_delete"},
            )
            cursor = self._conn.execute(
                "DELETE FROM automations WHERE user_id = ? AND automation_id = ?",
                (int(user_id), clean_id),
            )
            if cursor.rowcount <= 0:
                return False
            self._audit_locked(
                user_id=int(user_id),
                event_type="automation_deleted",
                target_kind="automation",
                target_id=clean_id,
            )
            self._conn.commit()
            self._secure_db_files()
            return True

    def append_automation_event(
        self,
        *,
        user_id: int,
        kind: str,
        content: str,
        event_type: Optional[str] = None,
        event_source: Optional[str] = None,
        status: Optional[str] = None,
        automation_id: Optional[str] = None,
        target_identity_id: Optional[str] = None,
        target_chat_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        importance: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
        scheduled_for: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            event_id = f"evt_{secrets.token_hex(8)}"
            clean_dedupe = str(dedupe_key or "").strip() or None
            try:
                self._conn.execute(
                    """
                    INSERT INTO automation_events(
                        event_id, user_id, automation_id, event_type, event_source, kind, content,
                        status, importance, target_identity_id, target_chat_id, dedupe_key, metadata,
                        created_at, scheduled_for, acknowledged_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        event_id,
                        int(user_id),
                        automation_id,
                        str(event_type or kind or "event")[:120],
                        str(event_source or "runtime")[:120],
                        str(kind or "event")[:120],
                        str(content or "")[:20_000],
                        status,
                        str(importance or "normal")[:40],
                        target_identity_id,
                        target_chat_id,
                        clean_dedupe,
                        _json_dumps(metadata or {}),
                        now,
                        scheduled_for,
                    ),
                )
            except sqlite3.IntegrityError:
                row = self._conn.execute(
                    "SELECT * FROM automation_events WHERE user_id = ? AND dedupe_key = ?",
                    (int(user_id), clean_dedupe),
                ).fetchone()
                if row:
                    return self._automation_event_view(row)
                raise
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM automation_events WHERE event_id = ?", (event_id,)).fetchone()
            return self._automation_event_view(row)

    def list_automation_events(
        self,
        *,
        user_id: int,
        limit: int = 200,
        include_acknowledged: bool = True,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            sql = "SELECT * FROM automation_events WHERE user_id = ?"
            params: List[Any] = [int(user_id)]
            if not include_acknowledged:
                sql += " AND acknowledged_at IS NULL"
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit or 200), 1000)))
            rows = self._conn.execute(sql, tuple(params)).fetchall()
            return [self._automation_event_view(row) for row in rows]

    def acknowledge_automation_event(self, *, user_id: int, event_id: str) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            cursor = self._conn.execute(
                "UPDATE automation_events SET acknowledged_at = ? WHERE user_id = ? AND event_id = ?",
                (now, int(user_id), str(event_id or "").strip()),
            )
            if cursor.rowcount <= 0:
                raise KeyError("Unknown automation event")
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM automation_events WHERE event_id = ?", (str(event_id or "").strip(),)).fetchone()
            return self._automation_event_view(row)

    def create_or_update_event_run(
        self,
        *,
        user_id: int,
        event_run_id: Optional[str] = None,
        event_id: Optional[str] = None,
        automation_id: Optional[str] = None,
        status: str = "queued",
        target_identity_id: Optional[str] = None,
        target_chat_id: Optional[str] = None,
        attempt: int = 1,
        max_attempts: int = 3,
        next_attempt_at: Optional[float] = None,
        started_at: Optional[float] = None,
        completed_at: Optional[float] = None,
        error: Optional[str] = None,
        result: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            clean_id = str(event_run_id or "").strip() or f"erun_{secrets.token_hex(8)}"
            existing = self._conn.execute(
                "SELECT created_at FROM automation_event_runs WHERE user_id = ? AND event_run_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            created_at = float(existing["created_at"]) if existing else now
            self._conn.execute(
                """
                INSERT INTO automation_event_runs(
                    event_run_id, user_id, event_id, automation_id, status, target_identity_id,
                    target_chat_id, attempt, max_attempts, next_attempt_at, started_at,
                    completed_at, error, result, metadata, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_run_id) DO UPDATE SET
                    event_id = COALESCE(excluded.event_id, automation_event_runs.event_id),
                    automation_id = COALESCE(excluded.automation_id, automation_event_runs.automation_id),
                    status = excluded.status,
                    target_identity_id = excluded.target_identity_id,
                    target_chat_id = excluded.target_chat_id,
                    attempt = excluded.attempt,
                    max_attempts = excluded.max_attempts,
                    next_attempt_at = excluded.next_attempt_at,
                    started_at = COALESCE(excluded.started_at, automation_event_runs.started_at),
                    completed_at = excluded.completed_at,
                    error = excluded.error,
                    result = excluded.result,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_id,
                    int(user_id),
                    event_id,
                    automation_id,
                    str(status or "queued")[:80],
                    target_identity_id,
                    target_chat_id,
                    max(1, int(attempt or 1)),
                    max(1, min(int(max_attempts or 3), 10)),
                    next_attempt_at,
                    started_at,
                    completed_at,
                    error[:4000] if error else None,
                    result[:20_000] if result else None,
                    _json_dumps(metadata or {}),
                    created_at,
                    now,
                ),
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM automation_event_runs WHERE event_run_id = ?", (clean_id,)).fetchone()
            return self._automation_event_run_view(row)

    def list_event_runs(self, *, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM automation_event_runs WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (int(user_id), max(1, min(int(limit or 200), 1000))),
            ).fetchall()
            return [self._automation_event_run_view(row) for row in rows]

    def cancel_event_runs_for_session(self, *, user_id: int, session_id: str, reason: str = "stopped") -> List[Dict[str, Any]]:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return []
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM automation_event_runs
                WHERE user_id = ?
                  AND target_chat_id = ?
                  AND status IN ('queued', 'retrying', 'dispatching', 'running')
                """,
                (int(user_id), clean_session_id),
            ).fetchall()
            updated: List[Dict[str, Any]] = []
            now = time.time()
            for row in rows:
                metadata = _json_loads(row["metadata"], {})
                metadata.update({"stop_reason": reason, "stopped_at": now})
                self._conn.execute(
                    """
                    UPDATE automation_event_runs
                    SET status = 'stopped', completed_at = ?, error = ?, metadata = ?, updated_at = ?
                    WHERE user_id = ? AND event_run_id = ?
                    """,
                    (now, str(reason or "stopped")[:4000], _json_dumps(metadata), now, int(user_id), row["event_run_id"]),
                )
                refreshed = dict(row)
                refreshed["status"] = "stopped"
                refreshed["completed_at"] = now
                refreshed["error"] = str(reason or "stopped")[:4000]
                refreshed["metadata"] = _json_dumps(metadata)
                refreshed["updated_at"] = now
                updated.append(self._automation_event_run_view(refreshed))
            if updated:
                self._audit_locked(
                    user_id=int(user_id),
                    event_type="event_runs_stopped_for_session",
                    target_kind="session",
                    target_id=clean_session_id,
                    metadata={"count": len(updated), "reason": reason},
                )
                self._conn.commit()
                self._secure_db_files()
            return updated

    def find_active_event_run(self, *, user_id: int, automation_id: str) -> Optional[Dict[str, Any]]:
        clean_automation_id = str(automation_id or "").strip()
        if not clean_automation_id:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM automation_event_runs
                WHERE user_id = ?
                  AND automation_id = ?
                  AND status IN ('queued', 'retrying', 'dispatching', 'running')
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (int(user_id), clean_automation_id),
            ).fetchone()
            return self._automation_event_run_view(row) if row else None

    def claim_due_event_runs(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        """Lease queued/retrying event runs for local dispatch/reconciliation."""
        with self._lock:
            now = time.time()
            rows = self._conn.execute(
                """
                SELECT * FROM automation_event_runs
                WHERE status IN ('queued', 'retrying')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (now, max(1, min(int(limit or 20), 100))),
            ).fetchall()
            claimed: List[Dict[str, Any]] = []
            for row in rows:
                metadata = _json_loads(row["metadata"], {})
                metadata.update({"claimed_at": now, "previous_status": row["status"]})
                self._conn.execute(
                    """
                    UPDATE automation_event_runs
                    SET status = 'dispatching', metadata = ?, updated_at = ?
                    WHERE event_run_id = ? AND status IN ('queued', 'retrying')
                    """,
                    (_json_dumps(metadata), now, row["event_run_id"]),
                )
                refreshed = dict(row)
                refreshed["status"] = "dispatching"
                refreshed["metadata"] = _json_dumps(metadata)
                refreshed["updated_at"] = now
                claimed.append(self._automation_event_run_view(refreshed))
            if claimed:
                self._conn.commit()
                self._secure_db_files()
            return claimed

    def update_event_run_status(
        self,
        *,
        user_id: int,
        event_run_id: str,
        status: str,
        error: Optional[str] = None,
        result: Optional[str] = None,
        next_attempt_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            clean_id = str(event_run_id or "").strip()
            existing = self._conn.execute(
                "SELECT * FROM automation_event_runs WHERE user_id = ? AND event_run_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            if not existing:
                raise KeyError("Unknown event run")
            now = time.time()
            normalized = str(status or "queued").strip()[:80]
            completed_at = now if normalized in {"completed", "failed", "stopped", "canceled"} else None
            next_attempt_at = None
            attempt = int(existing["attempt"] or 1)
            if normalized == "retrying":
                attempt = min(int(existing["max_attempts"] or 3), attempt + 1)
                next_attempt_at = next_attempt_at if isinstance(next_attempt_at, (int, float)) else now
            merged_metadata = _json_loads(existing["metadata"], {})
            merged_metadata.update(metadata or {})
            self._conn.execute(
                """
                UPDATE automation_event_runs
                SET status = ?, attempt = ?, next_attempt_at = ?, completed_at = ?,
                    error = ?, result = ?, metadata = ?, updated_at = ?
                WHERE user_id = ? AND event_run_id = ?
                """,
                (
                    normalized,
                    attempt,
                    next_attempt_at,
                    completed_at,
                    error[:4000] if error else None,
                    result[:20_000] if result else None,
                    _json_dumps(merged_metadata),
                    now,
                    int(user_id),
                    clean_id,
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type=f"event_run_{normalized}",
                target_kind="event_run",
                target_id=clean_id,
                metadata={"status": normalized},
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM automation_event_runs WHERE user_id = ? AND event_run_id = ?", (int(user_id), clean_id)).fetchone()
            return self._automation_event_run_view(row)

    def record_loop_guard_event(
        self,
        *,
        user_id: int,
        guard_key: str,
        failed: bool = False,
        max_events_per_hour: int = 240,
        cooldown_seconds: int = 600,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_key = str(guard_key or "").strip()[:256] or "global"
        with self._lock:
            now = time.time()
            window_start = float(int(now // 3600) * 3600)
            row = self._conn.execute(
                "SELECT * FROM automation_loop_guards WHERE user_id = ? AND guard_key = ?",
                (int(user_id), clean_key),
            ).fetchone()
            previous_window = float(row["window_start"]) if row else window_start
            same_window = previous_window == window_start
            event_count = int(row["event_count"] or 0) if row and same_window else 0
            failure_count = int(row["failure_count"] or 0) if row and same_window else 0
            last_failure_at = float(row["last_failure_at"] or 0) if row and row["last_failure_at"] else None

            allowed = True
            reason: Optional[str] = None
            if event_count >= max(1, int(max_events_per_hour or 240)):
                allowed = False
                reason = "max_events_per_hour"
            elif failed and last_failure_at and now - last_failure_at < max(1, int(cooldown_seconds or 600)):
                allowed = False
                reason = "repeated_failure_cooldown"

            next_event_count = event_count + 1
            next_failure_count = failure_count + (1 if failed else 0)
            next_last_failure_at = now if failed else last_failure_at
            existing_metadata = _json_loads(row["metadata"], {}) if row else {}
            existing_metadata.update(metadata or {})
            existing_metadata.update(
                {
                    "allowed": allowed,
                    "reason": reason,
                    "max_events_per_hour": max_events_per_hour,
                    "cooldown_seconds": cooldown_seconds,
                }
            )
            self._conn.execute(
                """
                INSERT INTO automation_loop_guards(
                    user_id, guard_key, window_start, event_count, last_failure_at,
                    failure_count, metadata, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, guard_key) DO UPDATE SET
                    window_start = excluded.window_start,
                    event_count = excluded.event_count,
                    last_failure_at = excluded.last_failure_at,
                    failure_count = excluded.failure_count,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    int(user_id),
                    clean_key,
                    window_start,
                    next_event_count,
                    next_last_failure_at,
                    next_failure_count,
                    _json_dumps(existing_metadata),
                    now,
                ),
            )
            self._conn.commit()
            self._secure_db_files()
            return {
                "allowed": allowed,
                "reason": reason,
                "guard_key": clean_key,
                "event_count": next_event_count,
                "failure_count": next_failure_count,
                "window_start": _utc_iso(window_start),
                "cooldown_until": _utc_iso((last_failure_at or now) + cooldown_seconds) if reason == "repeated_failure_cooldown" else None,
            }

    def upsert_process_wait(
        self,
        *,
        user_id: int,
        command_id: str,
        session_id: Optional[str] = None,
        pid: Optional[int] = None,
        command: Optional[str] = None,
        cwd: Optional[str] = None,
        shell: Optional[str] = None,
        status: str = "waiting_on_process",
        resume_policy: Optional[str] = None,
        persistent: bool = False,
        ready_patterns: Optional[List[str]] = None,
        meaningful_output_patterns: Optional[List[str]] = None,
        failure_patterns: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        started_at: Optional[float] = None,
        completed_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        clean_command_id = str(command_id or "").strip()
        if not clean_command_id:
            raise ValueError("command_id is required")
        with self._lock:
            now = time.time()
            process_wait_id = f"proc_{int(user_id)}_{clean_command_id}"
            first_started = float(started_at or now)
            self._conn.execute(
                """
                INSERT INTO process_waits(
                    process_wait_id, user_id, session_id, command_id, pid, command, cwd, shell,
                    status, resume_policy, persistent, ready_patterns, meaningful_output_patterns,
                    failure_patterns, metadata, started_at, last_event_at, completed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, command_id) DO UPDATE SET
                    session_id = COALESCE(excluded.session_id, process_waits.session_id),
                    pid = COALESCE(excluded.pid, process_waits.pid),
                    command = COALESCE(excluded.command, process_waits.command),
                    cwd = COALESCE(excluded.cwd, process_waits.cwd),
                    shell = COALESCE(excluded.shell, process_waits.shell),
                    status = excluded.status,
                    resume_policy = COALESCE(excluded.resume_policy, process_waits.resume_policy),
                    persistent = excluded.persistent,
                    ready_patterns = excluded.ready_patterns,
                    meaningful_output_patterns = excluded.meaningful_output_patterns,
                    failure_patterns = excluded.failure_patterns,
                    metadata = excluded.metadata,
                    last_event_at = excluded.last_event_at,
                    completed_at = excluded.completed_at
                """,
                (
                    process_wait_id,
                    int(user_id),
                    session_id,
                    clean_command_id,
                    pid,
                    command[:4000] if command else None,
                    cwd,
                    shell,
                    str(status or "waiting_on_process")[:80],
                    resume_policy,
                    1 if persistent else 0,
                    _json_dumps(list(ready_patterns or [])),
                    _json_dumps(list(meaningful_output_patterns or [])),
                    _json_dumps(list(failure_patterns or [])),
                    _json_dumps(metadata or {}),
                    first_started,
                    now,
                    completed_at,
                ),
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute(
                "SELECT * FROM process_waits WHERE user_id = ? AND command_id = ?",
                (int(user_id), clean_command_id),
            ).fetchone()
            return self._process_wait_view(row)

    def list_process_waits(self, *, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM process_waits WHERE user_id = ? ORDER BY last_event_at DESC LIMIT ?",
                (int(user_id), max(1, min(int(limit or 200), 1000))),
            ).fetchall()
            return [self._process_wait_view(row) for row in rows]

    def stop_process_waits_for_session(self, *, user_id: int, session_id: str, reason: str = "stopped") -> List[Dict[str, Any]]:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return []
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM process_waits
                WHERE user_id = ?
                  AND session_id = ?
                  AND status NOT IN ('canceled', 'stopped', 'process_completed', 'process_failed')
                """,
                (int(user_id), clean_session_id),
            ).fetchall()
            updated: List[Dict[str, Any]] = []
            now = time.time()
            for row in rows:
                metadata = _json_loads(row["metadata"], {})
                metadata.update({"stop_reason": reason, "stopped_at": now})
                self._conn.execute(
                    """
                    UPDATE process_waits
                    SET status = 'stopped', metadata = ?, last_event_at = ?, completed_at = ?
                    WHERE user_id = ? AND process_wait_id = ?
                    """,
                    (_json_dumps(metadata), now, now, int(user_id), row["process_wait_id"]),
                )
                refreshed = dict(row)
                refreshed["status"] = "stopped"
                refreshed["metadata"] = _json_dumps(metadata)
                refreshed["last_event_at"] = now
                refreshed["completed_at"] = now
                updated.append(self._process_wait_view(refreshed))
            if updated:
                self._audit_locked(
                    user_id=int(user_id),
                    event_type="process_waits_stopped_for_session",
                    target_kind="session",
                    target_id=clean_session_id,
                    metadata={"count": len(updated), "reason": reason},
                )
                self._conn.commit()
                self._secure_db_files()
            return updated

    def update_process_wait(
        self,
        *,
        user_id: int,
        process_wait_id: str,
        status: Optional[str] = None,
        persistent: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            clean_id = str(process_wait_id or "").strip()
            row = self._conn.execute(
                "SELECT * FROM process_waits WHERE user_id = ? AND process_wait_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            if not row:
                raise KeyError("Unknown process wait")
            now = time.time()
            normalized = str(status or row["status"] or "waiting_on_process")[:80]
            completed_at = now if normalized in {"canceled", "stopped", "process_completed", "process_failed"} else row["completed_at"]
            merged_metadata = _json_loads(row["metadata"], {})
            merged_metadata.update(metadata or {})
            self._conn.execute(
                """
                UPDATE process_waits
                SET status = ?, persistent = ?, metadata = ?, last_event_at = ?, completed_at = ?
                WHERE user_id = ? AND process_wait_id = ?
                """,
                (
                    normalized,
                    1 if (bool(persistent) if persistent is not None else bool(row["persistent"])) else 0,
                    _json_dumps(merged_metadata),
                    now,
                    completed_at,
                    int(user_id),
                    clean_id,
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type=f"process_wait_{normalized}",
                target_kind="process_wait",
                target_id=clean_id,
                metadata={"status": normalized},
            )
            self._conn.commit()
            self._secure_db_files()
            refreshed = self._conn.execute("SELECT * FROM process_waits WHERE user_id = ? AND process_wait_id = ?", (int(user_id), clean_id)).fetchone()
            return self._process_wait_view(refreshed)

    def upsert_planner_contract(
        self,
        *,
        user_id: int,
        session_id: Optional[str],
        turn_id: Optional[str],
        status: str,
        action: Optional[str] = None,
        contract: Optional[Dict[str, Any]] = None,
        corrections: Optional[List[Dict[str, Any]]] = None,
        injected_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            clean_session_id = str(session_id or "").strip() or "unknown"
            clean_turn_id = str(turn_id or "").strip() or "current"
            existing = self._conn.execute(
                "SELECT contract_id, created_at FROM planner_contracts WHERE user_id = ? AND session_id = ? AND turn_id = ?",
                (int(user_id), clean_session_id, clean_turn_id),
            ).fetchone()
            contract_id = str(existing["contract_id"]) if existing else f"plan_{secrets.token_hex(8)}"
            created_at = float(existing["created_at"]) if existing else now
            self._conn.execute(
                """
                INSERT INTO planner_contracts(
                    contract_id, user_id, session_id, turn_id, status, action, contract,
                    corrections, created_at, updated_at, injected_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_id, turn_id) DO UPDATE SET
                    status = excluded.status,
                    action = excluded.action,
                    contract = excluded.contract,
                    corrections = excluded.corrections,
                    updated_at = excluded.updated_at,
                    injected_at = COALESCE(excluded.injected_at, planner_contracts.injected_at)
                """,
                (
                    contract_id,
                    int(user_id),
                    clean_session_id,
                    clean_turn_id,
                    str(status or "pending")[:80],
                    action,
                    _json_dumps(contract or {}),
                    _json_dumps(corrections or []),
                    created_at,
                    now,
                    injected_at,
                ),
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM planner_contracts WHERE contract_id = ?", (contract_id,)).fetchone()
            return self._planner_contract_view(row)

    def list_planner_contracts(self, *, user_id: int, session_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    "SELECT * FROM planner_contracts WHERE user_id = ? AND session_id = ? ORDER BY updated_at DESC LIMIT ?",
                    (int(user_id), str(session_id), max(1, min(int(limit or 100), 500))),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM planner_contracts WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                    (int(user_id), max(1, min(int(limit or 100), 500))),
                ).fetchall()
            return [self._planner_contract_view(row) for row in rows]

    def update_planner_contract_status(
        self,
        *,
        user_id: int,
        contract_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            clean_id = str(contract_id or "").strip()
            existing = self._conn.execute(
                "SELECT * FROM planner_contracts WHERE user_id = ? AND contract_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            if not existing:
                raise KeyError("Unknown planner contract")
            now = time.time()
            contract = _json_loads(existing["contract"], {})
            if metadata:
                contract.setdefault("metadata", {}).update(metadata)
            self._conn.execute(
                "UPDATE planner_contracts SET status = ?, contract = ?, updated_at = ? WHERE user_id = ? AND contract_id = ?",
                (str(status or "pending")[:80], _json_dumps(contract), now, int(user_id), clean_id),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type=f"planner_contract_{str(status or 'updated')[:80]}",
                target_kind="planner_contract",
                target_id=clean_id,
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM planner_contracts WHERE user_id = ? AND contract_id = ?", (int(user_id), clean_id)).fetchone()
            return self._planner_contract_view(row)
