from __future__ import annotations

from app_backend.fleet_identity_profiles import identity_public_metadata, manager_identity_metadata
from app_backend.fleet_presence import desktop_presence_status

from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreViewMixin:
    def _next_user_id_locked(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(user_id), 0) + 1 AS next_id FROM users").fetchone()
        return int(row["next_id"] if row else 1)

    def _ensure_shared_state_locked(self, user_id: int) -> Dict[str, Any]:
        row = self._conn.execute("SELECT payload FROM shared_state WHERE user_id = ?", (int(user_id),)).fetchone()
        if row:
            state = _json_loads(row["payload"], {})
            if isinstance(state, dict):
                state.setdefault("sidebar_state", _empty_sidebar_state())
                state.setdefault("project_groups", [])
                state["fleet"] = _normalize_fleet_state(state.get("fleet"))
                return state
        state = {
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
            "fleet": _empty_fleet_state(),
            "sync_version": 0,
            "updated_at": None,
        }
        self._write_shared_state_locked(user_id, state)
        return state

    def _write_shared_state_locked(self, user_id: int, state: Dict[str, Any]) -> None:
        state["user_id"] = int(user_id)
        state.setdefault("sidebar_state", _empty_sidebar_state())
        state["fleet"] = _normalize_fleet_state(state.get("fleet"))
        self._conn.execute(
            "INSERT INTO shared_state(user_id, payload) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload",
            (int(user_id), _json_dumps(state)),
        )

    def _ensure_user_profile_locked(self, user_id: int) -> Dict[str, Any]:
        row = self._conn.execute("SELECT payload FROM user_profiles WHERE user_id = ?", (int(user_id),)).fetchone()
        if row:
            profile = _sanitize_user_profile(_json_loads(row["payload"], {}))
            serialized = _json_dumps(profile)
            if serialized != str(row["payload"] or ""):
                self._conn.execute(
                    "UPDATE user_profiles SET payload = ?, updated_at = ? WHERE user_id = ?",
                    (serialized, time.time(), int(user_id)),
                )
            return profile
        profile = _default_user_profile()
        self._conn.execute(
            "INSERT INTO user_profiles(user_id, payload, updated_at) VALUES(?, ?, ?)",
            (int(user_id), _json_dumps(profile), time.time()),
        )
        return profile

    def _bump_shared_state_locked(self, user_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
        state["updated_at"] = time.time()
        state["sync_version"] = int(state.get("sync_version", 0) or 0) + 1
        self._write_shared_state_locked(user_id, state)
        return json.loads(json.dumps(state))

    def _user_view(self, user: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "user_id": int(user["user_id"]),
            "display_name": user["display_name"],
            "created_at": _utc_iso(user["created_at"]),
        }

    def _desktop_view(self, desktop: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        persisted_status = str(desktop["status"] or "offline")
        status = desktop_presence_status(persisted_status, desktop["last_heartbeat_at"])
        detail = desktop["detail"]
        if status == "offline" and persisted_status.lower() in {"connected", "online"}:
            detail = "No Fleet heartbeat received in the last minute"
        return {
            "desktop_id": desktop["desktop_id"],
            "device_key": desktop["device_key"],
            "display_name": desktop["display_name"],
            "status": status,
            "detail": detail,
            "created_at": _utc_iso(desktop["created_at"]),
            "last_seen_at": _utc_iso(desktop["last_seen_at"]),
            "last_heartbeat_at": _utc_iso(desktop["last_heartbeat_at"]),
        }

    def _audit_locked(
        self,
        *,
        user_id: int,
        event_type: str,
        actor_kind: Optional[str] = None,
        actor_id: Optional[str] = None,
        target_kind: Optional[str] = None,
        target_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        event_id = f"aud_{secrets.token_hex(8)}"
        self._conn.execute(
            """
            INSERT INTO fleet_audit_events(
                event_id, user_id, event_type, actor_kind, actor_id, target_kind, target_id, task_id, metadata, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                int(user_id),
                str(event_type or "").strip()[:120],
                actor_kind,
                actor_id,
                target_kind,
                target_id,
                task_id,
                _json_dumps(metadata or {}),
                now,
            ),
        )
        return {
            "event_id": event_id,
            "event_type": event_type,
            "actor_kind": actor_kind,
            "actor_id": actor_id,
            "target_kind": target_kind,
            "target_id": target_id,
            "task_id": task_id,
            "metadata": metadata or {},
            "created_at": _utc_iso(now),
        }

    def _instance_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "instance_id": row["instance_id"],
            "user_id": int(row["user_id"]),
            "role": row["role"],
            "desktop_id": row["desktop_id"],
            "worker_id": row["worker_id"],
            "display_name": row["display_name"],
            "status": row["status"],
            "metadata": _json_loads(row["metadata"], {}),
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
            "reset_at": _utc_iso(row["reset_at"]),
        }

    def _identity_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        role = str(row["role"] or "manager")
        display_name = str(row["display_name"] or "").strip()
        if not display_name:
            display_name = "Manager" if role == "manager" else str(row["worker_id"] or "Worker")
        metadata = _json_loads(row["metadata"], {})
        return {
            "identity_id": row["instance_id"],
            "role": role,
            "display_name": display_name,
            "instance_id": row["instance_id"],
            "desktop_id": row["desktop_id"],
            "worker_id": row["worker_id"],
            "status": row["status"] or "active",
            "metadata": metadata,
            **identity_public_metadata(metadata),
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
        }

    def _worker_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        from app_backend.fleet_queue_policy import normalize_queue_policy

        status = str(row["status"] or "idle")
        metadata = _json_loads(row["metadata"], {})
        last_seen_at = row["last_seen_at"]
        baseline_idle_default = bool(metadata.get("is_default")) and status == "idle"
        if not baseline_idle_default and status not in {"working", "blocked", "needs_review"} and last_seen_at:
            age_seconds = max(0.0, time.time() - float(last_seen_at))
            if age_seconds >= FLEET_OFFLINE_SECONDS:
                status = "offline"
            elif age_seconds >= FLEET_STALE_SECONDS:
                status = "stale"
        return {
            "worker_id": row["worker_id"],
            "user_id": int(row["user_id"]),
            "kind": row["kind"],
            "machine_desktop_id": row["machine_desktop_id"],
            "instance_id": row["instance_id"],
            "display_name": row["display_name"],
            "status": status,
            "detail": row["detail"],
            "group_id": row["group_id"],
            "active_task_id": row["active_task_id"],
            "metadata": metadata,
            **identity_public_metadata(metadata),
            "queue_policy": normalize_queue_policy(metadata.get("queue_policy")),
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
            "last_seen_at": _utc_iso(row["last_seen_at"]),
        }

    def _task_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "user_id": int(row["user_id"]),
            "worker_id": row["worker_id"],
            "status": row["status"],
            "prompt": row["prompt"],
            "source": row["source"],
            "queue_position": int(row["queue_position"] or 0),
            "report_id": row["report_id"],
            "metadata": _json_loads(row["metadata"], {}),
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
            "started_at": _utc_iso(row["started_at"]),
            "completed_at": _utc_iso(row["completed_at"]),
            "canceled_at": _utc_iso(row["canceled_at"]),
        }

    def _report_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "report_id": row["report_id"],
            "user_id": int(row["user_id"]),
            "worker_id": row["worker_id"],
            "task_id": row["task_id"],
            "status": row["status"],
            "summary": row["summary"],
            "evidence": list(_json_loads(row["evidence"], [])),
            "artifacts": list(_json_loads(row["artifacts"], [])),
            "blockers": list(_json_loads(row["blockers"], [])),
            "confidence": row["confidence"],
            "next_suggested_action": row["next_suggested_action"],
            "raw": _json_loads(row["raw"], {}),
            "created_at": _utc_iso(row["created_at"]),
        }

    def _workspace_binding_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "binding_id": row["binding_id"],
            "workspace_id": row["workspace_id"],
            "machine_id": row["machine_id"],
            "local_path": row["local_path"],
            "label": row["label"],
            "status": row["status"],
            "metadata": _json_loads(row["metadata"], {}),
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
        }

    def _lock_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "lock_id": row["lock_id"],
            "resource_kind": row["resource_kind"],
            "resource_id": row["resource_id"],
            "owner_kind": row["owner_kind"],
            "owner_id": row["owner_id"],
            "task_id": row["task_id"],
            "created_at": _utc_iso(row["created_at"]),
            "expires_at": _utc_iso(row["expires_at"]),
            "metadata": _json_loads(row["metadata"], {}),
        }

    def _tool_grant_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "grant_id": row["grant_id"],
            "target_kind": row["target_kind"],
            "target_id": row["target_id"],
            "tool_pack_id": row["tool_pack_id"],
            "status": row["status"],
            "reason": row["reason"],
            "task_id": row["task_id"],
            "requested_turns": int(row["requested_turns"] or 0),
            "approved_turns": row["approved_turns"],
            "remaining_turns": row["remaining_turns"],
            "requested_by": row["requested_by"],
            "approved_by": row["approved_by"],
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
            "expires_at": _utc_iso(row["expires_at"]),
        }

    def _automation_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        metadata = _json_loads(row["metadata"], {})
        return {
            "id": row["automation_id"],
            "company_id": metadata.get("company_id"),
            "automation_id": row["automation_id"],
            "user_id": int(row["user_id"]),
            "name": row["name"],
            "prompt": row["prompt"],
            "schedule": row["schedule"],
            "schedule_mode": row["schedule_mode"],
            "enabled": bool(row["enabled"]),
            "status": row["status"],
            "target_kind": row["target_kind"],
            "target_identity_id": row["target_identity_id"],
            "target_group_id": row["target_group_id"],
            "target_chat_id": row["target_chat_id"],
            "chat_target": row["chat_target"],
            "permission_mode": row["permission_mode"],
            "tool_packs": list(_json_loads(row["tool_packs"], [])),
            "metadata": metadata,
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
            "next_run_at": _utc_iso(row["next_run_at"]),
            "last_run_at": _utc_iso(row["last_run_at"]),
            "run_count": int(row["run_count"] or 0),
            "error_count": int(row["error_count"] or 0),
            "one_time": bool(row["one_time"]),
            "requires_confirmation": bool(row["requires_confirmation"]),
            "confirmation_status": row["confirmation_status"],
            "confirmation_expires_at": _utc_iso(row["confirmation_expires_at"]),
        }

    def _automation_event_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        metadata = _json_loads(row["metadata"], {})
        return {
            "id": row["event_id"],
            "company_id": metadata.get("company_id"),
            "event_id": row["event_id"],
            "user_id": int(row["user_id"]),
            "automation_id": row["automation_id"],
            "job_id": row["automation_id"],
            "event_type": row["event_type"],
            "event_source": row["event_source"],
            "kind": row["kind"],
            "content": row["content"],
            "status": row["status"],
            "importance": row["importance"],
            "target_identity_id": row["target_identity_id"],
            "target_chat_id": row["target_chat_id"],
            "dedupe_key": row["dedupe_key"],
            "metadata": metadata,
            "created_at": _utc_iso(row["created_at"]),
            "timestamp": _utc_iso(row["created_at"]),
            "scheduled_for": _utc_iso(row["scheduled_for"]),
            "acknowledged_at": _utc_iso(row["acknowledged_at"]),
            "session_id": metadata.get("session_id"),
            "session_name": metadata.get("session_name"),
            "job_name": metadata.get("automation_name") or metadata.get("job_name"),
            "telegram_bot_config_id": metadata.get("telegram_bot_config_id"),
            "telegram_bot_label": metadata.get("telegram_bot_label"),
        }

    def _automation_event_run_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        metadata = _json_loads(row["metadata"], {})
        return {
            "event_run_id": row["event_run_id"],
            "company_id": metadata.get("company_id"),
            "user_id": int(row["user_id"]),
            "event_id": row["event_id"],
            "automation_id": row["automation_id"],
            "status": row["status"],
            "target_identity_id": row["target_identity_id"],
            "target_chat_id": row["target_chat_id"],
            "attempt": int(row["attempt"] or 1),
            "max_attempts": int(row["max_attempts"] or 3),
            "next_attempt_at": _utc_iso(row["next_attempt_at"]),
            "started_at": _utc_iso(row["started_at"]),
            "completed_at": _utc_iso(row["completed_at"]),
            "error": row["error"],
            "result": row["result"],
            "metadata": metadata,
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
        }

    def _process_wait_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "process_wait_id": row["process_wait_id"],
            "user_id": int(row["user_id"]),
            "session_id": row["session_id"],
            "command_id": row["command_id"],
            "pid": row["pid"],
            "command": row["command"],
            "cwd": row["cwd"],
            "shell": row["shell"],
            "status": row["status"],
            "resume_policy": row["resume_policy"],
            "persistent": bool(row["persistent"]),
            "ready_patterns": list(_json_loads(row["ready_patterns"], [])),
            "meaningful_output_patterns": list(_json_loads(row["meaningful_output_patterns"], [])),
            "failure_patterns": list(_json_loads(row["failure_patterns"], [])),
            "metadata": _json_loads(row["metadata"], {}),
            "started_at": _utc_iso(row["started_at"]),
            "last_event_at": _utc_iso(row["last_event_at"]),
            "completed_at": _utc_iso(row["completed_at"]),
        }

    def _planner_contract_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "contract_id": row["contract_id"],
            "user_id": int(row["user_id"]),
            "session_id": row["session_id"],
            "turn_id": row["turn_id"],
            "status": row["status"],
            "action": row["action"],
            "contract": _json_loads(row["contract"], {}),
            "corrections": list(_json_loads(row["corrections"], [])),
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
            "injected_at": _utc_iso(row["injected_at"]),
        }

    def _archive_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "archive_id": row["archive_id"],
            "user_id": int(row["user_id"]),
            "object_kind": row["object_kind"],
            "object_id": row["object_id"],
            "display_name": row["display_name"],
            "status": row["status"],
            "payload": _json_loads(row["payload"], {}),
            "metadata": _json_loads(row["metadata"], {}),
            "archived_at": _utc_iso(row["archived_at"]),
            "expires_at": _utc_iso(row["expires_at"]),
            "restored_at": _utc_iso(row["restored_at"]),
            "purged_at": _utc_iso(row["purged_at"]),
        }

    def _confirmation_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        return {
            "confirmation_id": row["confirmation_id"],
            "user_id": int(row["user_id"]),
            "action_kind": row["action_kind"],
            "title": row["title"],
            "message": row["message"],
            "risk_tier": row["risk_tier"],
            "status": row["status"],
            "origin_surface": row["origin_surface"],
            "origin_identity_id": row["origin_identity_id"],
            "origin_chat_id": row["origin_chat_id"],
            "payload": _json_loads(row["payload"], {}),
            "created_at": _utc_iso(row["created_at"]),
            "expires_at": _utc_iso(row["expires_at"]),
            "decided_at": _utc_iso(row["decided_at"]),
            "decided_by_surface": row["decided_by_surface"],
            "decided_by_actor": row["decided_by_actor"],
        }

    def _ensure_manager_instance_locked(
        self,
        *,
        user_id: int,
        desktop_id: str,
        display_name: Optional[str] = None,
        company_id: Optional[str] = None,
        membership_role: Optional[str] = None,
        adopt_unscoped: bool = False,
    ) -> Dict[str, Any]:
        all_rows = self._conn.execute(
            "SELECT * FROM fleet_instances WHERE user_id = ? AND role = 'manager' AND desktop_id = ? AND reset_at IS NULL ORDER BY created_at ASC",
            (int(user_id), desktop_id),
        ).fetchall()
        clean_company_id = str(company_id or "").strip()
        scoped_rows = [
            row
            for row in all_rows
            if str(_json_loads(row["metadata"], {}).get("company_id") or "").strip() == clean_company_id
        ] if clean_company_id else [
            row
            for row in all_rows
            if not str(_json_loads(row["metadata"], {}).get("company_id") or "").strip()
        ]
        if clean_company_id and not scoped_rows and adopt_unscoped:
            scoped_rows = [
                row
                for row in all_rows
                if not str(_json_loads(row["metadata"], {}).get("company_id") or "").strip()
            ][:1]
        if not clean_company_id and not scoped_rows and all_rows:
            # Once company migration has bound the bootstrap manager, opening the
            # device shell must reuse it rather than recreate a global identity.
            scoped_rows = list(all_rows[:1])
        existing_rows = scoped_rows
        existing = existing_rows[0] if existing_rows else None
        now = time.time()
        if existing:
            metadata = manager_identity_metadata(_json_loads(existing["metadata"], {}))
            if clean_company_id:
                metadata["company_id"] = clean_company_id
                metadata["company_membership_role"] = str(membership_role or "worker_node")
            self._conn.execute(
                "UPDATE fleet_instances SET display_name = COALESCE(?, display_name), status = 'active', metadata = ?, updated_at = ? WHERE instance_id = ?",
                ((display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None, _json_dumps(metadata), now, existing["instance_id"]),
            )
            for duplicate in existing_rows[1:]:
                self._conn.execute(
                    "UPDATE fleet_instances SET status = 'reset', reset_at = ?, updated_at = ? WHERE instance_id = ?",
                    (now, now, duplicate["instance_id"]),
                )
            refreshed = self._conn.execute("SELECT * FROM fleet_instances WHERE instance_id = ?", (existing["instance_id"],)).fetchone()
            return self._instance_view(refreshed)

        instance_id = f"mgr_{secrets.token_hex(8)}"
        metadata = manager_identity_metadata(
            {
                "company_id": clean_company_id,
                "company_membership_role": str(membership_role or "worker_node"),
            } if clean_company_id else None
        )
        self._conn.execute(
            """
            INSERT INTO fleet_instances(
                instance_id, user_id, role, desktop_id, worker_id, display_name, status, metadata, created_at, updated_at, reset_at
            ) VALUES(?, ?, 'manager', ?, NULL, ?, 'active', ?, ?, ?, NULL)
            """,
            (
                instance_id,
                int(user_id),
                desktop_id,
                (display_name or "Manager")[:MAX_DISPLAY_NAME_CHARS],
                _json_dumps(metadata),
                now,
                now,
            ),
        )
        self._audit_locked(
            user_id=user_id,
            event_type="manager_instance_created",
            actor_kind="desktop",
            actor_id=desktop_id,
            target_kind="manager",
            target_id=instance_id,
            metadata={"company_id": clean_company_id or None},
        )
        return self._instance_view(self._conn.execute("SELECT * FROM fleet_instances WHERE instance_id = ?", (instance_id,)).fetchone())

    def _desktop_has_active_session_locked(self, *, user_id: int, desktop_id: str) -> bool:
        clean_desktop_id = str(desktop_id or "").strip()
        if not clean_desktop_id:
            return False
        row = self._conn.execute(
            """
            SELECT 1 FROM remote_sessions
            WHERE user_id = ?
              AND actor_kind = 'desktop'
              AND desktop_id = ?
              AND revoked_at IS NULL
              AND expires_at > ?
            LIMIT 1
            """,
            (int(user_id), clean_desktop_id, time.time()),
        ).fetchone()
        return bool(row)

    def _prune_stale_manager_instances_locked(self, *, user_id: int, desktop_id: Optional[str]) -> int:
        clean_desktop_id = str(desktop_id or "").strip()
        if not clean_desktop_id:
            return 0
        now = time.time()
        stale_instance_ids: List[str] = []
        for row in self._conn.execute(
            """
            SELECT instance_id, desktop_id FROM fleet_instances
            WHERE user_id = ? AND role = 'manager' AND reset_at IS NULL
            """,
            (int(user_id),),
        ).fetchall():
            manager_desktop_id = str(row["desktop_id"] or "").strip()
            if manager_desktop_id == clean_desktop_id:
                continue
            if self._desktop_has_active_session_locked(user_id=int(user_id), desktop_id=manager_desktop_id):
                continue
            stale_instance_ids.append(str(row["instance_id"]))
        if not stale_instance_ids:
            return 0
        placeholders = ",".join("?" for _ in stale_instance_ids)
        self._conn.execute(
            f"""
            UPDATE fleet_instances
            SET status = 'stale', updated_at = ?, reset_at = ?
            WHERE user_id = ? AND instance_id IN ({placeholders})
            """,
            (now, now, int(user_id), *stale_instance_ids),
        )
        return len(stale_instance_ids)

    def _fleet_identity_rows_locked(self, user_id: int) -> List[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM fleet_instances WHERE user_id = ? AND reset_at IS NULL ORDER BY role ASC, created_at ASC",
                (int(user_id),),
            ).fetchall()
        )

    def _fleet_identities_locked(self, user_id: int) -> List[Dict[str, Any]]:
        return [self._identity_view(row) for row in self._fleet_identity_rows_locked(int(user_id))]

    def _scope_fleet_identities_to_desktop(
        self,
        identities: List[Dict[str, Any]],
        desktop_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        clean_desktop_id = str(desktop_id or "").strip()
        if not clean_desktop_id:
            return list(identities)
        return [
            identity
            for identity in identities
            if str(identity.get("desktop_id") or "").strip() == clean_desktop_id
        ]

    def _scope_fleet_instances_to_desktop(
        self,
        instances: List[Dict[str, Any]],
        desktop_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        clean_desktop_id = str(desktop_id or "").strip()
        if not clean_desktop_id:
            return list(instances)
        return [
            instance
            for instance in instances
            if str(instance.get("desktop_id") or "").strip() == clean_desktop_id
        ]

    def _scope_fleet_workers_to_desktop(
        self,
        workers: List[Dict[str, Any]],
        desktop_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        clean_desktop_id = str(desktop_id or "").strip()
        if not clean_desktop_id:
            return list(workers)
        return [
            worker
            for worker in workers
            if str(worker.get("machine_desktop_id") or "").strip() == clean_desktop_id
        ]

    def _resolve_fleet_identity_locked(self, user_id: int, selector: str) -> Optional[Dict[str, Any]]:
        needle = str(selector or "").strip()
        if not needle:
            return None
        lowered = needle.casefold()
        for identity in self._fleet_identities_locked(int(user_id)):
            if str(identity.get("identity_id") or "").casefold() == lowered:
                return identity
            if str(identity.get("worker_id") or "").casefold() == lowered:
                return identity
            if str(identity.get("display_name") or "").strip().casefold() == lowered:
                return identity
        return None

    def _resolve_scoped_fleet_identity_locked(
        self,
        user_id: int,
        selector: str,
        desktop_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        needle = str(selector or "").strip()
        if not needle:
            return None
        lowered = needle.casefold()
        identities = self._scope_fleet_identities_to_desktop(
            self._fleet_identities_locked(int(user_id)),
            desktop_id,
        )
        for identity in identities:
            if str(identity.get("identity_id") or "").casefold() == lowered:
                return identity
            if str(identity.get("worker_id") or "").casefold() == lowered:
                return identity
            if str(identity.get("display_name") or "").strip().casefold() == lowered:
                return identity
        return None

    def _default_manager_identity_locked(self, user_id: int) -> Optional[Dict[str, Any]]:
        identities = self._fleet_identities_locked(int(user_id))
        return next((item for item in identities if item.get("role") == "manager"), None) or (identities[0] if identities else None)

    def _ensure_fleet_selection_locked(
        self,
        *,
        user_id: int,
        state: Dict[str, Any],
        preferred_identity_id: Optional[str] = None,
        desktop_id: Optional[str] = None,
        company_id: Optional[str] = None,
        include_unscoped_company_records: bool = False,
    ) -> Dict[str, Any]:
        fleet_state = _normalize_fleet_state(state.get("fleet"))
        fleet = _fleet_selection_for_desktop(fleet_state, desktop_id, company_id)
        identities = self._scope_fleet_identities_to_desktop(
            self._fleet_identities_locked(int(user_id)),
            desktop_id,
        )
        clean_company_id = str(company_id or "").strip()
        if clean_company_id:
            identities = [
                item
                for item in identities
                if str(dict(item.get("metadata") or {}).get("company_id") or "").strip()
                == clean_company_id
                or (
                    include_unscoped_company_records
                    and not str(dict(item.get("metadata") or {}).get("company_id") or "").strip()
                )
            ]
        identity_ids = {str(item.get("identity_id") or "") for item in identities}
        selected = str(preferred_identity_id or fleet.get("active_identity_id") or "").strip()
        if not selected or selected not in identity_ids:
            manager = next((item for item in identities if item.get("role") == "manager"), None)
            selected = str((manager or (identities[0] if identities else {})).get("identity_id") or "").strip()
        fleet["active_identity_id"] = selected or None
        selected_by_identity = dict(fleet.get("selected_chat_by_identity") or {})
        selected_by_identity = {key: value for key, value in selected_by_identity.items() if key in identity_ids}
        if selected and not selected_by_identity.get(selected) and not clean_company_id:
            current_session_id = str(state.get("current_session_id") or "").strip()
            if current_session_id:
                selected_by_identity[selected] = current_session_id
        fleet["selected_chat_by_identity"] = selected_by_identity
        return fleet

    def _bump_fleet_selection_locked(
        self,
        user_id: int,
        state: Dict[str, Any],
        *,
        fleet: Optional[Dict[str, Any]] = None,
        desktop_id: Optional[str] = None,
        company_id: Optional[str] = None,
        include_unscoped_company_records: bool = False,
    ) -> Dict[str, Any]:
        fleet = dict(fleet or self._ensure_fleet_selection_locked(
            user_id=int(user_id),
            state=state,
            desktop_id=desktop_id,
            company_id=company_id,
            include_unscoped_company_records=include_unscoped_company_records,
        ))
        fleet["active_identity_version"] = int(fleet.get("active_identity_version") or 0) + 1
        fleet["active_identity_updated_at"] = time.time()
        state["fleet"] = _store_fleet_selection_for_desktop(
            state.get("fleet"),
            desktop_id,
            fleet,
            company_id,
        )
        return fleet

    def _next_worker_name_locked(self, user_id: int) -> str:
        count = self._conn.execute("SELECT COUNT(*) AS count FROM fleet_workers WHERE user_id = ?", (int(user_id),)).fetchone()
        return f"Worker-{int(count['count'] or 0) + 1:03d}"

    def _create_remote_session_locked(
        self,
        *,
        user_id: int,
        actor_kind: str,
        device_name: Optional[str],
        device_platform: Optional[str],
        device_key: Optional[str],
        token_ttl_seconds: int,
        ensure_manager: bool = True,
    ) -> Dict[str, Any]:
        if actor_kind != "desktop":
            raise ValueError("Fleet sessions are desktop-only")

        now = time.time()
        expires_at = now + token_ttl_seconds if int(token_ttl_seconds or 0) > 0 else 0.0
        session_token = secrets.token_urlsafe(48)
        token_hash = _hash_token(session_token)
        normalized_key = (device_key or "").strip()[:MAX_DEVICE_KEY_CHARS] or None
        normalized_name = (device_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or "EmploAI Desktop"
        normalized_platform = (device_platform or "").strip()[:MAX_DEVICE_PLATFORM_CHARS] or None
        desktop_id = self._find_or_create_desktop_locked(
            user_id=user_id,
            display_name=normalized_name,
            device_key=normalized_key,
        )
        self._conn.execute(
            "UPDATE desktops SET display_name = ?, device_platform = ?, last_seen_at = ? WHERE desktop_id = ?",
            (normalized_name, normalized_platform, now, desktop_id),
        )
        if ensure_manager:
            self._ensure_manager_instance_locked(user_id=user_id, desktop_id=desktop_id, display_name=normalized_name)
        self._conn.execute(
            """
            INSERT INTO remote_sessions(
                token_hash, user_id, actor_kind, desktop_id, mobile_id, created_at, last_used_at, expires_at, revoked_at
            ) VALUES(?, ?, 'desktop', ?, NULL, ?, ?, ?, NULL)
            """,
            (token_hash, user_id, desktop_id, now, now, expires_at),
        )
        self._ensure_shared_state_locked(user_id)
        refreshed_user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        desktop = self._conn.execute("SELECT * FROM desktops WHERE desktop_id = ?", (desktop_id,)).fetchone()
        return {
            "session_token": session_token,
            "expires_at": expires_at,
            "user": self._user_view(refreshed_user),
            "actor_kind": "desktop",
            "desktop": self._desktop_view(desktop),
        }
