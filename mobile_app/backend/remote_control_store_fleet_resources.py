from __future__ import annotations

from mobile_app.backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreFleetResourceMixin:
    def upsert_workspace_binding(
        self,
        *,
        user_id: int,
        workspace_id: str,
        machine_id: str,
        local_path: str,
        label: Optional[str] = None,
        status: str = "active",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        workspace = str(workspace_id or "").strip()
        machine = str(machine_id or "").strip()
        path_value = str(local_path or "").strip()
        if not workspace or not machine or not path_value:
            raise ValueError("workspace_id, machine_id, and local_path are required")
        with self._lock:
            now = time.time()
            existing = self._conn.execute(
                "SELECT binding_id FROM fleet_workspace_bindings WHERE user_id = ? AND workspace_id = ? AND machine_id = ?",
                (int(user_id), workspace, machine),
            ).fetchone()
            binding_id = existing["binding_id"] if existing else f"wspb_{secrets.token_hex(8)}"
            self._conn.execute(
                """
                INSERT INTO fleet_workspace_bindings(
                    binding_id, user_id, workspace_id, machine_id, local_path, label, status, metadata, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, workspace_id, machine_id) DO UPDATE SET
                    local_path = excluded.local_path,
                    label = excluded.label,
                    status = excluded.status,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (binding_id, int(user_id), workspace, machine, path_value, label, status, _json_dumps(metadata or {}), now, now),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="workspace_binding_upserted",
                target_kind="workspace",
                target_id=workspace,
                metadata={"machine_id": machine, "status": status},
            )
            self._conn.commit()
            return self._workspace_binding_view(
                self._conn.execute(
                    "SELECT * FROM fleet_workspace_bindings WHERE user_id = ? AND workspace_id = ? AND machine_id = ?",
                    (int(user_id), workspace, machine),
                ).fetchone()
            )

    def claim_fleet_lock(
        self,
        *,
        user_id: int,
        resource_kind: str,
        resource_id: str,
        owner_kind: str,
        owner_id: str,
        task_id: Optional[str] = None,
        ttl_seconds: int = 300,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        claim = normalize_fleet_lock_claim(
            resource_kind=resource_kind,
            resource_id=resource_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            task_id=task_id,
            ttl_seconds=ttl_seconds,
            metadata=metadata,
        )
        with self._lock:
            self._cleanup_locked()
            now = time.time()
            existing = self._conn.execute(
                """
                SELECT * FROM fleet_locks
                WHERE user_id = ? AND resource_kind = ? AND resource_id = ? AND expires_at > ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (int(user_id), claim.resource_kind, claim.resource_id, now),
            ).fetchone()
            expires_at = now + claim.ttl_seconds
            if existing:
                same_owner = fleet_lock_owner_matches(
                    existing_owner_kind=existing["owner_kind"],
                    existing_owner_id=existing["owner_id"],
                    owner_kind=claim.owner_kind,
                    owner_id=claim.owner_id,
                )
                if not same_owner:
                    raise ValueError(FLEET_LOCK_CONFLICT_ERROR)
                self._conn.execute(
                    "UPDATE fleet_locks SET task_id = ?, expires_at = ?, metadata = ? WHERE lock_id = ?",
                    (
                        claim.task_id or existing["task_id"],
                        expires_at,
                        _json_dumps(claim.metadata or _json_loads(existing["metadata"], {})),
                        existing["lock_id"],
                    ),
                )
                self._conn.commit()
                return self._lock_view(self._conn.execute("SELECT * FROM fleet_locks WHERE lock_id = ?", (existing["lock_id"],)).fetchone())

            lock_id = f"flk_{secrets.token_hex(8)}"
            self._conn.execute(
                """
                INSERT INTO fleet_locks(
                    lock_id, user_id, resource_kind, resource_id, owner_kind, owner_id, task_id, created_at, expires_at, metadata
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lock_id,
                    int(user_id),
                    claim.resource_kind,
                    claim.resource_id,
                    claim.owner_kind,
                    claim.owner_id,
                    claim.task_id,
                    now,
                    expires_at,
                    _json_dumps(claim.metadata),
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="fleet_lock_claimed",
                actor_kind=claim.owner_kind,
                actor_id=claim.owner_id,
                target_kind=claim.resource_kind,
                target_id=claim.resource_id,
                task_id=claim.task_id,
            )
            self._conn.commit()
            self._secure_db_files()
            return self._lock_view(self._conn.execute("SELECT * FROM fleet_locks WHERE lock_id = ?", (lock_id,)).fetchone())

    def release_fleet_lock(
        self,
        *,
        user_id: int,
        lock_id: Optional[str] = None,
        resource_kind: Optional[str] = None,
        resource_id: Optional[str] = None,
        owner_kind: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> bool:
        release = normalize_fleet_lock_release(
            lock_id=lock_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
        )
        with self._lock:
            self._cleanup_locked()
            if release.lock_id:
                params: list[Any] = [int(user_id), release.lock_id]
                where = "user_id = ? AND lock_id = ?"
            else:
                params = [int(user_id), release.resource_kind, release.resource_id]
                where = "user_id = ? AND resource_kind = ? AND resource_id = ?"
            if release.owner_kind:
                where += " AND owner_kind = ?"
                params.append(release.owner_kind)
            if release.owner_id:
                where += " AND owner_id = ?"
                params.append(release.owner_id)
            cursor = self._conn.execute(f"DELETE FROM fleet_locks WHERE {where}", tuple(params))
            self._conn.commit()
            self._secure_db_files()
            return cursor.rowcount > 0

    def record_worker_preview_request(
        self,
        *,
        user_id: int,
        worker_id: str,
        preview_id: str,
        status: str,
        requested_by: str = "manager",
        mode: str = FLEET_PREVIEW_MODE,
        command_id: Optional[str] = None,
        detail: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_preview_id = str(preview_id or "").strip()
        clean_worker_id = str(worker_id or "").strip()
        clean_status = str(status or "").strip()[:80] or "recorded"
        if not clean_preview_id or not clean_worker_id:
            raise ValueError("preview_id and worker_id are required")
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), clean_worker_id),
            ).fetchone()
            if not row:
                raise KeyError("Unknown worker")
            now = time.time()
            worker_metadata = _json_loads(row["metadata"], {})
            preview_record = {
                "preview_id": clean_preview_id,
                "status": clean_status,
                "requested_by": str(requested_by or "manager")[:80],
                "mode": str(mode or FLEET_PREVIEW_MODE)[:120],
                "command_id": str(command_id or "").strip() or None,
                "detail": str(detail or "").strip() or None,
                "requested_at": _utc_iso(now),
                "metadata": dict(metadata or {}),
            }
            worker_metadata["latest_preview_request"] = preview_record
            self._conn.execute(
                "UPDATE fleet_workers SET metadata = ?, updated_at = ?, last_seen_at = COALESCE(last_seen_at, ?) WHERE worker_id = ?",
                (_json_dumps(worker_metadata), now, now, clean_worker_id),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_preview_requested",
                actor_kind=str(requested_by or "manager")[:80],
                target_kind="worker",
                target_id=clean_worker_id,
                metadata=preview_record,
            )
            self._conn.commit()
            self._secure_db_files()
            return {
                "preview": preview_record,
                "worker": self._worker_view(
                    self._conn.execute("SELECT * FROM fleet_workers WHERE worker_id = ?", (clean_worker_id,)).fetchone()
                ),
            }

    def request_tool_grant(
        self,
        *,
        user_id: int,
        target_kind: str,
        target_id: str,
        tool_pack_id: str,
        reason: str,
        task_id: Optional[str] = None,
        requested_turns: int = 10,
        requested_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            grant_id = f"grt_{secrets.token_hex(8)}"
            turns = max(1, min(10, int(requested_turns or 10)))
            self._conn.execute(
                """
                INSERT INTO fleet_tool_grants(
                    grant_id, user_id, target_kind, target_id, tool_pack_id, status, reason, task_id,
                    requested_turns, approved_turns, remaining_turns, requested_by, approved_by, created_at, updated_at, expires_at
                ) VALUES(?, ?, ?, ?, ?, 'requested', ?, ?, ?, NULL, NULL, ?, NULL, ?, ?, NULL)
                """,
                (
                    grant_id,
                    int(user_id),
                    str(target_kind or "worker")[:40],
                    str(target_id or "")[:128],
                    str(tool_pack_id or "")[:128],
                    str(reason or "")[:1000],
                    task_id,
                    turns,
                    requested_by,
                    now,
                    now,
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="tool_grant_requested",
                target_kind=str(target_kind or "worker")[:40],
                target_id=str(target_id or "")[:128],
                task_id=task_id,
                metadata={"tool_pack_id": tool_pack_id, "requested_turns": turns},
            )
            self._conn.commit()
            return self._tool_grant_view(self._conn.execute("SELECT * FROM fleet_tool_grants WHERE grant_id = ?", (grant_id,)).fetchone())

    def decide_tool_grant(
        self,
        *,
        user_id: int,
        grant_id: str,
        approved: bool,
        approved_turns: Optional[int] = None,
        approved_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            grant = self._conn.execute(
                "SELECT * FROM fleet_tool_grants WHERE user_id = ? AND grant_id = ?",
                (int(user_id), str(grant_id or "").strip()),
            ).fetchone()
            if not grant:
                raise KeyError("Unknown tool grant")
            now = time.time()
            turns = max(1, min(10, int(approved_turns or grant["requested_turns"] or 10)))
            status = "approved" if approved else "denied"
            self._conn.execute(
                """
                UPDATE fleet_tool_grants
                SET status = ?, approved_turns = ?, remaining_turns = ?, approved_by = ?, updated_at = ?, expires_at = ?
                WHERE grant_id = ?
                """,
                (status, turns if approved else None, turns if approved else None, approved_by, now, now + 60 * 60 if approved else None, grant["grant_id"]),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type=f"tool_grant_{status}",
                target_kind=grant["target_kind"],
                target_id=grant["target_id"],
                task_id=grant["task_id"],
                metadata={"grant_id": grant["grant_id"], "tool_pack_id": grant["tool_pack_id"]},
            )
            self._conn.commit()
            return self._tool_grant_view(self._conn.execute("SELECT * FROM fleet_tool_grants WHERE grant_id = ?", (grant["grant_id"],)).fetchone())
