from __future__ import annotations

from mobile_app.backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreArchiveMixin:
    def archive_item(
        self,
        *,
        user_id: int,
        object_kind: str,
        object_id: str,
        display_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        retention_seconds: int = 60 * 60 * 24 * 30,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            archive_id = f"arc_{secrets.token_hex(8)}"
            self._conn.execute(
                """
                INSERT INTO recovery_archive(
                    archive_id, user_id, object_kind, object_id, display_name, status,
                    payload, metadata, archived_at, expires_at, restored_at, purged_at
                ) VALUES(?, ?, ?, ?, ?, 'archived', ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    archive_id,
                    int(user_id),
                    str(object_kind or "item")[:80],
                    str(object_id or "")[:256],
                    str(display_name or "").strip()[:300] or None,
                    _json_dumps(payload or {}),
                    _json_dumps(metadata or {}),
                    now,
                    now + max(60, int(retention_seconds or 60 * 60 * 24 * 30)),
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="item_archived",
                target_kind=str(object_kind or "item")[:80],
                target_id=str(object_id or "")[:256],
                metadata={"archive_id": archive_id},
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM recovery_archive WHERE archive_id = ?", (archive_id,)).fetchone()
            return self._archive_view(row)

    def list_archived_items(self, *, user_id: int, include_expired: bool = False, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            now = time.time()
            if include_expired:
                rows = self._conn.execute(
                    "SELECT * FROM recovery_archive WHERE user_id = ? AND purged_at IS NULL ORDER BY archived_at DESC LIMIT ?",
                    (int(user_id), max(1, min(int(limit or 500), 2000))),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM recovery_archive WHERE user_id = ? AND purged_at IS NULL AND expires_at > ? ORDER BY archived_at DESC LIMIT ?",
                    (int(user_id), now, max(1, min(int(limit or 500), 2000))),
                ).fetchall()
            return [self._archive_view(row) for row in rows]

    def get_archived_item(self, *, user_id: int, archive_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM recovery_archive WHERE user_id = ? AND archive_id = ? AND purged_at IS NULL",
                (int(user_id), str(archive_id or "").strip()),
            ).fetchone()
            if not row:
                raise KeyError("Unknown archived item")
            return self._archive_view(row)

    def restore_archived_item(self, *, user_id: int, archive_id: str) -> Dict[str, Any]:
        with self._lock:
            clean_id = str(archive_id or "").strip()
            row = self._conn.execute(
                "SELECT * FROM recovery_archive WHERE user_id = ? AND archive_id = ? AND purged_at IS NULL",
                (int(user_id), clean_id),
            ).fetchone()
            if not row:
                raise KeyError("Unknown archived item")
            if row["restored_at"]:
                return self._archive_view(row)
            kind = str(row["object_kind"] or "")
            payload = _json_loads(row["payload"], {})
            now = time.time()
            if kind == "automation":
                item = dict(payload.get("automation") or payload)
                if not item:
                    raise ValueError("Archived automation has no payload")
                self.upsert_automation(
                    user_id=int(user_id),
                    automation_id=str(item.get("automation_id") or item.get("id") or row["object_id"]),
                    name=str(item.get("name") or row["display_name"] or "Restored automation"),
                    prompt=str(item.get("prompt") or ""),
                    schedule=item.get("schedule"),
                    schedule_mode=item.get("schedule_mode"),
                    enabled=bool(item.get("enabled", False)),
                    target_kind=str(item.get("target_kind") or "active_identity"),
                    target_identity_id=item.get("target_identity_id"),
                    target_group_id=item.get("target_group_id"),
                    target_chat_id=item.get("target_chat_id"),
                    chat_target=str(item.get("chat_target") or "existing_or_new"),
                    permission_mode=item.get("permission_mode"),
                    tool_packs=list(item.get("tool_packs") or []),
                    metadata=dict(item.get("metadata") or {}),
                    one_time=bool(item.get("one_time", False)),
                    requires_confirmation=bool(item.get("requires_confirmation", False)),
                    confirmation_status=item.get("confirmation_status"),
                    confirmation_expires_at=None,
                )
            elif kind == "worker":
                item = dict(payload.get("worker") or payload)
                if item:
                    worker_id = str(item.get("worker_id") or row["object_id"])
                    instance_id = str(item.get("instance_id") or f"win_{secrets.token_hex(8)}")
                    exists = self._conn.execute("SELECT worker_id FROM fleet_workers WHERE user_id = ? AND worker_id = ?", (int(user_id), worker_id)).fetchone()
                    if not exists:
                        self._conn.execute(
                            """
                            INSERT INTO fleet_workers(
                                worker_id, user_id, kind, machine_desktop_id, instance_id, display_name,
                                status, detail, group_id, active_task_id, metadata, created_at, updated_at, last_seen_at
                            ) VALUES(?, ?, ?, ?, ?, ?, 'idle', ?, ?, NULL, ?, ?, ?, NULL)
                            """,
                            (
                                worker_id,
                                int(user_id),
                                str(item.get("kind") or "local"),
                                item.get("machine_desktop_id"),
                                instance_id,
                                str(item.get("display_name") or row["display_name"] or worker_id),
                                item.get("detail"),
                                item.get("group_id"),
                                _json_dumps(dict(item.get("metadata") or {})),
                                now,
                                now,
                            ),
                        )
                    terminal_task_statuses = {"completed", "failed", "stopped", "canceled"}
                    for task in list(payload.get("tasks") or []):
                        if not isinstance(task, dict):
                            continue
                        task_id = str(task.get("task_id") or "").strip()
                        if not task_id:
                            continue
                        exists_task = self._conn.execute(
                            "SELECT task_id FROM fleet_tasks WHERE user_id = ? AND task_id = ?",
                            (int(user_id), task_id),
                        ).fetchone()
                        if exists_task:
                            continue
                        original_status = str(task.get("status") or "stopped").strip().lower()
                        restored_status = original_status if original_status in terminal_task_statuses else "stopped"
                        task_metadata = dict(task.get("metadata") or {})
                        if restored_status != original_status:
                            task_metadata["archived_restore_original_status"] = original_status
                            task_metadata.setdefault("archived_restore_note", "Restored as stopped history; archived worker work is not resumed automatically.")
                        created_at = _timestamp_from_archive_value(task.get("created_at"), now) or now
                        updated_at = _timestamp_from_archive_value(task.get("updated_at"), now) or now
                        completed_at = _timestamp_from_archive_value(task.get("completed_at"), now if restored_status in terminal_task_statuses else None)
                        canceled_at = _timestamp_from_archive_value(task.get("canceled_at"), None)
                        self._conn.execute(
                            """
                            INSERT INTO fleet_tasks(
                                task_id, user_id, worker_id, status, prompt, source, queue_position, report_id,
                                metadata, created_at, updated_at, started_at, completed_at, canceled_at
                            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                task_id,
                                int(user_id),
                                worker_id,
                                restored_status,
                                str(task.get("prompt") or "Restored worker task"),
                                str(task.get("source") or "archive_restore")[:80],
                                int(task.get("queue_position") or 0),
                                task.get("report_id"),
                                _json_dumps(task_metadata),
                                created_at,
                                updated_at,
                                _timestamp_from_archive_value(task.get("started_at"), None),
                                completed_at,
                                canceled_at,
                            ),
                        )
                    for report in list(payload.get("reports") or []):
                        if not isinstance(report, dict):
                            continue
                        report_id = str(report.get("report_id") or "").strip()
                        task_id = str(report.get("task_id") or "").strip()
                        if not report_id or not task_id:
                            continue
                        exists_report = self._conn.execute(
                            "SELECT report_id FROM fleet_reports WHERE user_id = ? AND report_id = ?",
                            (int(user_id), report_id),
                        ).fetchone()
                        if exists_report:
                            continue
                        self._conn.execute(
                            """
                            INSERT INTO fleet_reports(
                                report_id, user_id, worker_id, task_id, status, summary, evidence, artifacts,
                                blockers, confidence, next_suggested_action, raw, created_at
                            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                report_id,
                                int(user_id),
                                worker_id,
                                task_id,
                                str(report.get("status") or "completed"),
                                str(report.get("summary") or "Restored worker report."),
                                _json_dumps(list(report.get("evidence") or [])),
                                _json_dumps(list(report.get("artifacts") or [])),
                                _json_dumps(list(report.get("blockers") or [])),
                                str(report.get("confidence") or "medium"),
                                report.get("next_suggested_action"),
                                _json_dumps(dict(report.get("raw") or {})),
                                _timestamp_from_archive_value(report.get("created_at"), now) or now,
                            ),
                        )
            elif kind == "group":
                item = dict(payload.get("group") or payload)
                if item:
                    self.create_or_update_group(
                        user_id=int(user_id),
                        group_id=str(item.get("group_id") or row["object_id"]),
                        display_name=str(item.get("display_name") or row["display_name"] or "Restored group"),
                        description=item.get("description"),
                        metadata=dict(item.get("metadata") or {}),
                        worker_ids=list(item.get("worker_ids") or []),
                    )
            else:
                # Generic restore marks the archive restored. Object-specific restore may be added later.
                pass
            self._conn.execute(
                "UPDATE recovery_archive SET status = 'restored', restored_at = ? WHERE user_id = ? AND archive_id = ?",
                (now, int(user_id), clean_id),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="item_restored",
                target_kind=kind,
                target_id=str(row["object_id"] or ""),
                metadata={"archive_id": clean_id},
            )
            self._conn.commit()
            self._secure_db_files()
            refreshed = self._conn.execute("SELECT * FROM recovery_archive WHERE user_id = ? AND archive_id = ?", (int(user_id), clean_id)).fetchone()
            return self._archive_view(refreshed)

    def permanently_delete_archived_item(self, *, user_id: int, archive_id: str) -> Dict[str, Any]:
        with self._lock:
            clean_id = str(archive_id or "").strip()
            row = self._conn.execute(
                "SELECT * FROM recovery_archive WHERE user_id = ? AND archive_id = ? AND purged_at IS NULL",
                (int(user_id), clean_id),
            ).fetchone()
            if not row:
                raise KeyError("Unknown archived item")
            now = time.time()
            self._conn.execute(
                "UPDATE recovery_archive SET status = 'purged', purged_at = ? WHERE user_id = ? AND archive_id = ?",
                (now, int(user_id), clean_id),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="item_permanently_deleted",
                target_kind=row["object_kind"],
                target_id=row["object_id"],
                metadata={"archive_id": clean_id},
            )
            self._conn.commit()
            self._secure_db_files()
            refreshed = self._conn.execute("SELECT * FROM recovery_archive WHERE user_id = ? AND archive_id = ?", (int(user_id), clean_id)).fetchone()
            return self._archive_view(refreshed)

    def purge_expired_archives(self, *, user_id: int) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            rows = self._conn.execute(
                "SELECT archive_id FROM recovery_archive WHERE user_id = ? AND purged_at IS NULL AND expires_at <= ?",
                (int(user_id), now),
            ).fetchall()
            ids = [str(row["archive_id"]) for row in rows]
            if ids:
                self._conn.executemany(
                    "UPDATE recovery_archive SET status = 'purged', purged_at = ? WHERE user_id = ? AND archive_id = ?",
                    [(now, int(user_id), archive_id) for archive_id in ids],
                )
            self._audit_locked(
                user_id=int(user_id),
                event_type="expired_archives_purged",
                metadata={"count": len(ids)},
            )
            self._conn.commit()
            self._secure_db_files()
            return {"ok": True, "purged": len(ids)}

    def expire_pending_confirmations(self, *, user_id: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            if user_id is None:
                rows = self._conn.execute(
                    "SELECT confirmation_id, user_id, action_kind FROM pending_confirmations WHERE status = 'pending' AND expires_at <= ?",
                    (now,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT confirmation_id, user_id, action_kind FROM pending_confirmations WHERE user_id = ? AND status = 'pending' AND expires_at <= ?",
                    (int(user_id), now),
                ).fetchall()
            if not rows:
                return {"ok": True, "expired": 0}
            ids = [str(row["confirmation_id"]) for row in rows]
            self._conn.executemany(
                "UPDATE pending_confirmations SET status = 'expired', decided_at = ? WHERE confirmation_id = ?",
                [(now, confirmation_id) for confirmation_id in ids],
            )
            for row in rows:
                self._audit_locked(
                    user_id=int(row["user_id"]),
                    event_type="confirmation_expired",
                    target_kind="confirmation",
                    target_id=str(row["confirmation_id"]),
                    metadata={"action_kind": row["action_kind"]},
                )
            self._conn.commit()
            self._secure_db_files()
            return {"ok": True, "expired": len(ids)}

    def create_confirmation(
        self,
        *,
        user_id: int,
        action_kind: str,
        title: str,
        message: str,
        risk_tier: str = "danger",
        origin_surface: Optional[str] = None,
        origin_identity_id: Optional[str] = None,
        origin_chat_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = 300,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            confirmation_id = f"conf_{secrets.token_hex(8)}"
            expires_at = now + max(30, min(int(ttl_seconds or 300), 60 * 30))
            self._conn.execute(
                """
                INSERT INTO pending_confirmations(
                    confirmation_id, user_id, action_kind, title, message, risk_tier, status,
                    origin_surface, origin_identity_id, origin_chat_id, payload,
                    created_at, expires_at, decided_at, decided_by_surface, decided_by_actor
                ) VALUES(?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    confirmation_id,
                    int(user_id),
                    str(action_kind or "action").strip()[:120],
                    str(title or "Confirm action").strip()[:240],
                    str(message or "Confirm this action before it continues.").strip()[:2000],
                    str(risk_tier or "danger").strip()[:80],
                    str(origin_surface or "").strip()[:80] or None,
                    str(origin_identity_id or "").strip()[:256] or None,
                    str(origin_chat_id or "").strip()[:256] or None,
                    _json_dumps(payload or {}),
                    now,
                    expires_at,
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="confirmation_created",
                actor_kind=str(origin_surface or "").strip()[:80] or None,
                actor_id=str(origin_identity_id or "").strip()[:256] or None,
                target_kind="confirmation",
                target_id=confirmation_id,
                metadata={
                    "action_kind": str(action_kind or "action").strip()[:120],
                    "risk_tier": str(risk_tier or "danger").strip()[:80],
                    "origin_chat_id": str(origin_chat_id or "").strip()[:256] or None,
                    "expires_at": _utc_iso(expires_at),
                },
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM pending_confirmations WHERE confirmation_id = ?", (confirmation_id,)).fetchone()
            return self._confirmation_view(row)

    def list_pending_confirmations(self, *, user_id: int, limit: int = 100, include_expired: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            self.expire_pending_confirmations(user_id=int(user_id))
            if include_expired:
                rows = self._conn.execute(
                    "SELECT * FROM pending_confirmations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (int(user_id), max(1, min(int(limit or 100), 500))),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM pending_confirmations WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT ?",
                    (int(user_id), max(1, min(int(limit or 100), 500))),
                ).fetchall()
            return [self._confirmation_view(row) for row in rows]

    def get_confirmation(self, *, user_id: int, confirmation_id: str) -> Dict[str, Any]:
        with self._lock:
            self.expire_pending_confirmations(user_id=int(user_id))
            row = self._conn.execute(
                "SELECT * FROM pending_confirmations WHERE user_id = ? AND confirmation_id = ?",
                (int(user_id), str(confirmation_id or "").strip()),
            ).fetchone()
            if not row:
                raise KeyError("Unknown confirmation")
            return self._confirmation_view(row)

    def decide_confirmation(
        self,
        *,
        user_id: int,
        confirmation_id: str,
        approved: bool,
        decided_by_surface: str,
        decided_by_actor: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            clean_id = str(confirmation_id or "").strip()
            row = self._conn.execute(
                "SELECT * FROM pending_confirmations WHERE user_id = ? AND confirmation_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            if not row:
                raise KeyError("Unknown confirmation")
            now = time.time()
            if row["status"] != "pending":
                return self._confirmation_view(row)
            if float(row["expires_at"] or 0) <= now:
                self._conn.execute(
                    "UPDATE pending_confirmations SET status = 'expired', decided_at = ? WHERE user_id = ? AND confirmation_id = ?",
                    (now, int(user_id), clean_id),
                )
                self._audit_locked(
                    user_id=int(user_id),
                    event_type="confirmation_expired",
                    target_kind="confirmation",
                    target_id=clean_id,
                    metadata={"action_kind": row["action_kind"]},
                )
                self._conn.commit()
                self._secure_db_files()
                refreshed = self._conn.execute(
                    "SELECT * FROM pending_confirmations WHERE user_id = ? AND confirmation_id = ?",
                    (int(user_id), clean_id),
                ).fetchone()
                return self._confirmation_view(refreshed)
            status = "approved" if approved else "denied"
            surface = str(decided_by_surface or "unknown").strip()[:80]
            actor = str(decided_by_actor or "").strip()[:256] or None
            self._conn.execute(
                """
                UPDATE pending_confirmations
                SET status = ?, decided_at = ?, decided_by_surface = ?, decided_by_actor = ?
                WHERE user_id = ? AND confirmation_id = ?
                """,
                (status, now, surface, actor, int(user_id), clean_id),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type=f"confirmation_{status}",
                actor_kind=surface,
                actor_id=actor,
                target_kind="confirmation",
                target_id=clean_id,
                metadata={
                    "action_kind": row["action_kind"],
                    "origin_surface": row["origin_surface"],
                    "origin_identity_id": row["origin_identity_id"],
                    "origin_chat_id": row["origin_chat_id"],
                },
            )
            self._conn.commit()
            self._secure_db_files()
            refreshed = self._conn.execute(
                "SELECT * FROM pending_confirmations WHERE user_id = ? AND confirmation_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            return self._confirmation_view(refreshed)

    def record_confirmation_executed(
        self,
        *,
        user_id: int,
        confirmation_id: str,
        executed_by_surface: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            clean_id = str(confirmation_id or "").strip()
            row = self._conn.execute(
                "SELECT * FROM pending_confirmations WHERE user_id = ? AND confirmation_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            if not row:
                raise KeyError("Unknown confirmation")
            if str(row["status"] or "") != "approved":
                raise ValueError("Confirmation is not approved")
            now = time.time()
            surface = str(executed_by_surface or "unknown").strip()[:80]
            self._conn.execute(
                "UPDATE pending_confirmations SET status = 'executed', decided_at = COALESCE(decided_at, ?) WHERE user_id = ? AND confirmation_id = ?",
                (now, int(user_id), clean_id),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="confirmation_executed",
                actor_kind=surface,
                target_kind="confirmation",
                target_id=clean_id,
                metadata={"action_kind": row["action_kind"], **dict(metadata or {})},
            )
            self._conn.commit()
            self._secure_db_files()
            refreshed = self._conn.execute(
                "SELECT * FROM pending_confirmations WHERE user_id = ? AND confirmation_id = ?",
                (int(user_id), clean_id),
            ).fetchone()
            return self._confirmation_view(refreshed)

    def upsert_cloud_session_snapshot(
        self,
        *,
        user_id: int,
        session_id: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        with self._lock:
            clean_session_id = str(session_id or "").strip()
            if not clean_session_id:
                raise ValueError("session_id is required")
            now = time.time()
            self._conn.execute(
                """
                INSERT INTO cloud_session_snapshots(user_id, session_id, status, payload, metadata, updated_at, archived_at)
                VALUES(?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    status = excluded.status,
                    payload = excluded.payload,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at,
                    archived_at = CASE WHEN excluded.status = 'archived' THEN COALESCE(cloud_session_snapshots.archived_at, excluded.updated_at) ELSE NULL END
                """,
                (
                    int(user_id),
                    clean_session_id,
                    str(status or "active").strip()[:80],
                    _json_dumps(payload or {}),
                    _json_dumps(metadata or {}),
                    now,
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="cloud_session_snapshot_updated",
                target_kind="chat",
                target_id=clean_session_id,
                metadata={"status": str(status or "active").strip()[:80], **dict(metadata or {})},
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute(
                "SELECT * FROM cloud_session_snapshots WHERE user_id = ? AND session_id = ?",
                (int(user_id), clean_session_id),
            ).fetchone()
            return self._cloud_session_snapshot_view(row)

    def archive_cloud_session_snapshot(
        self,
        *,
        user_id: int,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            clean_session_id = str(session_id or "").strip()
            if not clean_session_id:
                raise ValueError("session_id is required")
            now = time.time()
            row = self._conn.execute(
                "SELECT * FROM cloud_session_snapshots WHERE user_id = ? AND session_id = ?",
                (int(user_id), clean_session_id),
            ).fetchone()
            if not row:
                self._conn.execute(
                    """
                    INSERT INTO cloud_session_snapshots(user_id, session_id, status, payload, metadata, updated_at, archived_at)
                    VALUES(?, ?, 'archived', '{}', ?, ?, ?)
                    """,
                    (int(user_id), clean_session_id, _json_dumps(metadata or {}), now, now),
                )
            else:
                merged_metadata = dict(_json_loads(row["metadata"], {}))
                merged_metadata.update(dict(metadata or {}))
                self._conn.execute(
                    "UPDATE cloud_session_snapshots SET status = 'archived', metadata = ?, updated_at = ?, archived_at = COALESCE(archived_at, ?) WHERE user_id = ? AND session_id = ?",
                    (_json_dumps(merged_metadata), now, now, int(user_id), clean_session_id),
                )
            self._audit_locked(
                user_id=int(user_id),
                event_type="cloud_session_snapshot_archived",
                target_kind="chat",
                target_id=clean_session_id,
                metadata=dict(metadata or {}),
            )
            self._conn.commit()
            self._secure_db_files()
            refreshed = self._conn.execute(
                "SELECT * FROM cloud_session_snapshots WHERE user_id = ? AND session_id = ?",
                (int(user_id), clean_session_id),
            ).fetchone()
            return self._cloud_session_snapshot_view(refreshed)

    def list_cloud_session_snapshots(self, *, user_id: int, status: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM cloud_session_snapshots WHERE user_id = ? AND status = ? ORDER BY updated_at DESC LIMIT ?",
                    (int(user_id), str(status).strip()[:80], max(1, min(int(limit or 500), 2000))),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM cloud_session_snapshots WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                    (int(user_id), max(1, min(int(limit or 500), 2000))),
                ).fetchall()
            return [self._cloud_session_snapshot_view(row) for row in rows]

    def paired_desktop_id_for_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        actor_kind = str(payload.get("actor_kind") or "").strip()
        try:
            user_id = int(payload.get("user_id") or 0)
        except (TypeError, ValueError):
            user_id = 0
        if user_id <= 0:
            return None
        if actor_kind == "desktop":
            desktop_id = str(payload.get("desktop_id") or "").strip()
            if not desktop_id:
                return None
            with self._lock:
                desktop = self._conn.execute(
                    "SELECT desktop_id FROM desktops WHERE desktop_id = ? AND user_id = ?",
                    (desktop_id, user_id),
                ).fetchone()
            return desktop_id if desktop else None
        if actor_kind != "mobile":
            return None
        mobile_id = str(payload.get("mobile_id") or "").strip()
        if not mobile_id:
            return None
        with self._lock:
            mobile = self._conn.execute(
                "SELECT paired_desktop_id FROM mobiles WHERE mobile_id = ? AND user_id = ?",
                (mobile_id, user_id),
            ).fetchone()
            if not mobile:
                return None
            paired_desktop_id = str(mobile["paired_desktop_id"] or "").strip()
            return paired_desktop_id or None
