from __future__ import annotations

from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreFleetSnapshotMixin:
    def get_fleet_snapshot(
        self,
        *,
        user_id: int,
        desktop_id: Optional[str] = None,
        company_id: Optional[str] = None,
        company_computer_ids: Optional[List[str]] = None,
        include_unscoped_company_records: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            clean_desktop_id = str(desktop_id or "").strip()
            scoped_desktop_id = None
            if clean_desktop_id:
                desktop = self._conn.execute(
                    "SELECT * FROM desktops WHERE user_id = ? AND desktop_id = ?",
                    (int(user_id), clean_desktop_id),
                ).fetchone()
                if desktop:
                    scoped_desktop_id = clean_desktop_id
            state = self._ensure_shared_state_locked(int(user_id))
            if not scoped_desktop_id:
                current_desktop_id = str(state.get("current_desktop_id") or "").strip()
                if current_desktop_id:
                    desktop = self._conn.execute(
                        "SELECT desktop_id FROM desktops WHERE user_id = ? AND desktop_id = ?",
                        (int(user_id), current_desktop_id),
                    ).fetchone()
                    if desktop:
                        scoped_desktop_id = current_desktop_id
            if self._reconcile_worker_protection_locked(
                user_id=int(user_id),
                desktop_id=scoped_desktop_id,
            ):
                self._conn.commit()
            all_workers = [
                self._worker_view(row)
                for row in self._conn.execute(
                    "SELECT * FROM fleet_workers WHERE user_id = ? ORDER BY created_at ASC",
                    (int(user_id),),
                ).fetchall()
            ]
            hidden_connection_worker_ids = {
                str(item.get("worker_id") or "")
                for item in all_workers
                if self.is_legacy_connection_worker(item)
            }
            all_instances = [
                self._instance_view(row)
                for row in self._conn.execute(
                    "SELECT * FROM fleet_instances WHERE user_id = ? AND reset_at IS NULL ORDER BY created_at ASC",
                    (int(user_id),),
                ).fetchall()
                if str(row["worker_id"] or "") not in hidden_connection_worker_ids
            ]
            instances = self._scope_fleet_instances_to_desktop(all_instances, scoped_desktop_id)
            all_identities = [
                item
                for item in self._fleet_identities_locked(int(user_id))
                if str(item.get("worker_id") or "") not in hidden_connection_worker_ids
            ]
            identities = self._scope_fleet_identities_to_desktop(all_identities, scoped_desktop_id)
            fleet_state = self._ensure_fleet_selection_locked(
                user_id=int(user_id),
                state=state,
                desktop_id=scoped_desktop_id,
                company_id=company_id,
                include_unscoped_company_records=include_unscoped_company_records,
            )
            active_identity_id = str(fleet_state.get("active_identity_id") or "").strip() or None
            active_identity = next((item for item in identities if item.get("identity_id") == active_identity_id), None)
            if identities and not active_identity:
                active_identity = next((item for item in identities if item.get("role") == "manager"), None) or identities[0]
                active_identity_id = str(active_identity.get("identity_id") or "").strip() or None
                selected_by_identity = dict(fleet_state.get("selected_chat_by_identity") or {})
                current_session_id = str(state.get("current_session_id") or "").strip()
                current_desktop_id = str(state.get("current_desktop_id") or "").strip()
                if (
                    not str(company_id or "").strip()
                    and active_identity_id
                    and scoped_desktop_id
                    and current_desktop_id == scoped_desktop_id
                    and current_session_id
                ):
                    selected_by_identity.setdefault(active_identity_id, current_session_id)
                fleet_state["active_identity_id"] = active_identity_id
                fleet_state["selected_chat_by_identity"] = selected_by_identity
            workers = self._scope_fleet_workers_to_desktop(
                [item for item in all_workers if str(item.get("worker_id") or "") not in hidden_connection_worker_ids],
                scoped_desktop_id,
            )
            visible_worker_ids = {str(item.get("worker_id") or "") for item in workers}
            tasks = [
                self._task_view(row)
                for row in self._conn.execute(
                    "SELECT * FROM fleet_tasks WHERE user_id = ? ORDER BY queue_position ASC, created_at ASC",
                    (int(user_id),),
                ).fetchall()
                if str(row["worker_id"] or "") in visible_worker_ids
            ]
            reports = [
                self._report_view(row)
                for row in self._conn.execute(
                    "SELECT * FROM fleet_reports WHERE user_id = ? ORDER BY created_at DESC LIMIT 200",
                    (int(user_id),),
                ).fetchall()
                if str(row["worker_id"] or "") in visible_worker_ids
            ]
            visible_identity_ids = {str(item.get("identity_id") or "") for item in identities}
            selected_chat_by_identity = {
                key: value
                for key, value in dict(fleet_state.get("selected_chat_by_identity") or {}).items()
                if key in visible_identity_ids
            }
            snapshot = {
                "schema_version": 1,
                "user_id": int(user_id),
                "identities": identities,
                "active_identity_id": active_identity_id,
                "active_identity": active_identity,
                "selected_chat_by_identity": selected_chat_by_identity,
                "active_identity_version": int(fleet_state.get("active_identity_version") or 0),
                "active_identity_updated_at": _utc_iso(fleet_state.get("active_identity_updated_at")),
                "instances": instances,
                "manager": next((item for item in instances if item.get("role") == "manager"), None),
                "desktops": [
                    self._desktop_view(row)
                    for row in self._conn.execute(
                        "SELECT * FROM desktops WHERE user_id = ? ORDER BY created_at ASC",
                        (int(user_id),),
                    ).fetchall()
                ],
                "connection_permissions": [
                    self._connection_permission_view(row)
                    for row in self._conn.execute(
                        "SELECT * FROM fleet_connection_permissions WHERE user_id = ? ORDER BY updated_at DESC",
                        (int(user_id),),
                    ).fetchall()
                ],
                "delegations": self.list_computer_delegations(user_id=int(user_id), limit=200),
                "upstream_requests": self.list_upstream_requests(user_id=int(user_id), limit=200),
                "workers": workers,
                "groups": [
                    {
                        "group_id": row["group_id"],
                        "display_name": row["display_name"],
                        "description": row["description"],
                        "metadata": _json_loads(row["metadata"], {}),
                        "created_at": _utc_iso(row["created_at"]),
                        "updated_at": _utc_iso(row["updated_at"]),
                        "worker_ids": [
                            item["worker_id"]
                            for item in self._conn.execute(
                                "SELECT worker_id FROM fleet_workers WHERE user_id = ? AND group_id = ? ORDER BY display_name ASC",
                                (int(user_id), row["group_id"]),
                            ).fetchall()
                            if str(item["worker_id"] or "") in visible_worker_ids
                        ],
                    }
                    for row in self._conn.execute(
                        "SELECT * FROM fleet_groups WHERE user_id = ? ORDER BY display_name ASC",
                        (int(user_id),),
                    ).fetchall()
                ],
                "tasks": tasks,
                "reports": reports,
                "workspace_bindings": [
                    self._workspace_binding_view(row)
                    for row in self._conn.execute(
                        "SELECT * FROM fleet_workspace_bindings WHERE user_id = ? ORDER BY updated_at DESC",
                        (int(user_id),),
                    ).fetchall()
                ],
                "tool_grants": [
                    self._tool_grant_view(row)
                    for row in self._conn.execute(
                        "SELECT * FROM fleet_tool_grants WHERE user_id = ? ORDER BY updated_at DESC LIMIT 200",
                        (int(user_id),),
                    ).fetchall()
                    if not (
                        str(row["target_kind"] or "") == "worker"
                        and str(row["target_id"] or "") in hidden_connection_worker_ids
                    )
                ],
                "audit_events": [
                    {
                        "event_id": row["event_id"],
                        "event_type": row["event_type"],
                        "actor_kind": row["actor_kind"],
                        "actor_id": row["actor_id"],
                        "target_kind": row["target_kind"],
                        "target_id": row["target_id"],
                        "task_id": row["task_id"],
                        "metadata": _json_loads(row["metadata"], {}),
                        "created_at": _utc_iso(row["created_at"]),
                    }
                    for row in self._conn.execute(
                        "SELECT * FROM fleet_audit_events WHERE user_id = ? ORDER BY created_at DESC LIMIT 200",
                        (int(user_id),),
                    ).fetchall()
                ],
                "locks": [
                    self._lock_view(row)
                    for row in self._conn.execute(
                        "SELECT * FROM fleet_locks WHERE user_id = ? ORDER BY created_at DESC",
                        (int(user_id),),
                    ).fetchall()
                ],
                "feature_gated": True,
            }
            if company_id:
                snapshot = self._scope_fleet_snapshot_to_company(
                    snapshot,
                    company_id=str(company_id),
                    company_computer_ids=company_computer_ids,
                    include_unscoped=bool(include_unscoped_company_records),
                )
            return snapshot

    def _scope_fleet_snapshot_to_company(
        self,
        snapshot: Dict[str, Any],
        *,
        company_id: str,
        company_computer_ids: Optional[List[str]],
        include_unscoped: bool,
    ) -> Dict[str, Any]:
        """Project legacy Fleet records through a fail-closed company boundary."""

        clean_company_id = str(company_id or "").strip()
        allowed_computers = {
            str(item or "").strip()
            for item in list(company_computer_ids or [])
            if str(item or "").strip()
        }

        def company_match(item: Dict[str, Any]) -> bool:
            value = str(dict(item.get("metadata") or {}).get("company_id") or "").strip()
            return value == clean_company_id or (include_unscoped and not value)

        scoped = dict(snapshot)
        scoped["company_id"] = clean_company_id
        scoped["instances"] = [
            item for item in list(snapshot.get("instances") or []) if company_match(item)
        ]
        scoped["identities"] = [
            item for item in list(snapshot.get("identities") or []) if company_match(item)
        ]
        scoped["workers"] = [
            item for item in list(snapshot.get("workers") or []) if company_match(item)
        ]
        identity_ids = {
            str(item.get("identity_id") or "") for item in scoped["identities"]
        }
        worker_ids = {
            str(item.get("worker_id") or "") for item in scoped["workers"]
        }
        scoped["tasks"] = [
            item
            for item in list(snapshot.get("tasks") or [])
            if company_match(item) or str(item.get("worker_id") or "") in worker_ids
        ]
        task_ids = {
            str(item.get("task_id") or "") for item in scoped["tasks"]
        }
        scoped["reports"] = [
            item
            for item in list(snapshot.get("reports") or [])
            if str(item.get("worker_id") or "") in worker_ids
            or str(item.get("task_id") or "") in task_ids
        ]
        scoped["groups"] = [
            item
            for item in list(snapshot.get("groups") or [])
            if company_match(item)
            or any(str(worker_id) in worker_ids for worker_id in list(item.get("worker_ids") or []))
        ]

        if allowed_computers:
            scoped["desktops"] = [
                item
                for item in list(snapshot.get("desktops") or [])
                if str(item.get("desktop_id") or "") in allowed_computers
            ]
            scoped["connection_permissions"] = [
                item
                for item in list(snapshot.get("connection_permissions") or [])
                if str(item.get("desktop_id") or "") in allowed_computers
            ]
        elif not include_unscoped:
            scoped["desktops"] = []
            scoped["connection_permissions"] = []

        def company_or_computer(item: Dict[str, Any]) -> bool:
            item_company_id = str(
                dict(item.get("metadata") or {}).get("company_id") or ""
            ).strip()
            if item_company_id:
                return item_company_id == clean_company_id
            if not include_unscoped:
                return False
            return bool(
                allowed_computers
                and str(item.get("desktop_id") or item.get("machine_id") or "")
                in allowed_computers
            )

        scoped["delegations"] = [
            item for item in list(snapshot.get("delegations") or []) if company_or_computer(item)
        ]
        scoped["upstream_requests"] = [
            item
            for item in list(snapshot.get("upstream_requests") or [])
            if company_or_computer(item)
            or str(item.get("identity_id") or "") in identity_ids
            or str(item.get("task_id") or "") in task_ids
        ]
        scoped["workspace_bindings"] = [
            item for item in list(snapshot.get("workspace_bindings") or []) if company_or_computer(item)
        ]
        scoped["tool_grants"] = [
            item
            for item in list(snapshot.get("tool_grants") or [])
            if (
                str(item.get("target_kind") or "") == "worker"
                and str(item.get("target_id") or "") in worker_ids
            )
            or (
                str(item.get("target_kind") or "") in {"identity", "manager"}
                and str(item.get("target_id") or "") in identity_ids
            )
            or str(item.get("task_id") or "") in task_ids
        ]
        related_ids = identity_ids | worker_ids | task_ids
        scoped["audit_events"] = [
            item
            for item in list(snapshot.get("audit_events") or [])
            if company_match(item)
            or str(item.get("target_id") or "") in related_ids
            or str(item.get("actor_id") or "") in identity_ids
        ]
        scoped["locks"] = [
            item
            for item in list(snapshot.get("locks") or [])
            if company_match(item)
            or str(item.get("owner_id") or "") in identity_ids | worker_ids
            or str(item.get("task_id") or "") in task_ids
        ]

        active_identity_id = str(snapshot.get("active_identity_id") or "")
        active_identity = next(
            (
                item
                for item in scoped["identities"]
                if str(item.get("identity_id") or "") == active_identity_id
            ),
            None,
        )
        if not active_identity:
            active_identity = next(
                (item for item in scoped["identities"] if str(item.get("role") or "") == "manager"),
                None,
            ) or (scoped["identities"][0] if scoped["identities"] else None)
        scoped["active_identity"] = active_identity
        scoped["active_identity_id"] = (
            str((active_identity or {}).get("identity_id") or "").strip() or None
        )
        scoped["selected_chat_by_identity"] = {
            key: value
            for key, value in dict(snapshot.get("selected_chat_by_identity") or {}).items()
            if key in identity_ids
        }
        scoped["manager"] = next(
            (item for item in scoped["instances"] if str(item.get("role") or "") == "manager"),
            None,
        )
        return scoped

    def get_worker(self, *, user_id: int, worker_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchone()
            if not row:
                raise KeyError("Unknown worker")
            worker = self._worker_view(row)
            if self.is_legacy_connection_worker(worker):
                raise KeyError("Unknown worker")
            return worker

    def set_active_fleet_identity(
        self,
        *,
        user_id: int,
        identity_id: str,
        selected_chat_id: Optional[str] = None,
        source: Optional[str] = None,
        desktop_id: Optional[str] = None,
        company_id: Optional[str] = None,
        include_unscoped_company_records: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            identity = self._resolve_scoped_fleet_identity_locked(int(user_id), identity_id, desktop_id)
            if not identity:
                raise KeyError("Unknown fleet identity")
            identity_company_id = str(dict(identity.get("metadata") or {}).get("company_id") or "").strip()
            clean_company_id = str(company_id or "").strip()
            if clean_company_id and identity_company_id != clean_company_id:
                if not (include_unscoped_company_records and not identity_company_id):
                    raise KeyError("Unknown fleet identity")
            effective_desktop_id = str(desktop_id or identity.get("desktop_id") or "").strip() or None
            state = self._ensure_shared_state_locked(int(user_id))
            fleet = self._ensure_fleet_selection_locked(
                user_id=int(user_id),
                state=state,
                preferred_identity_id=str(identity["identity_id"]),
                desktop_id=effective_desktop_id,
                company_id=clean_company_id or None,
                include_unscoped_company_records=include_unscoped_company_records,
            )
            fleet["active_identity_id"] = str(identity["identity_id"])
            selected_by_identity = dict(fleet.get("selected_chat_by_identity") or {})
            clean_chat_id = str(selected_chat_id or "").strip()
            if clean_chat_id:
                selected_by_identity[str(identity["identity_id"])] = clean_chat_id
            fleet["selected_chat_by_identity"] = selected_by_identity
            if not clean_company_id:
                state["current_session_id"] = selected_by_identity.get(str(identity["identity_id"])) or None
            fleet = self._bump_fleet_selection_locked(
                int(user_id),
                state,
                fleet=fleet,
                desktop_id=effective_desktop_id,
                company_id=clean_company_id or None,
                include_unscoped_company_records=include_unscoped_company_records,
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="fleet_identity_changed",
                actor_kind=str(source or "app")[:80],
                target_kind="identity",
                target_id=str(identity["identity_id"]),
                metadata={"selected_chat_id": clean_chat_id or None},
            )
            next_state = self._bump_shared_state_locked(int(user_id), state)
            self._conn.commit()
            self._secure_db_files()
            return {
                "active_identity_id": fleet.get("active_identity_id"),
                "active_identity": identity,
                "selected_chat_by_identity": dict(fleet.get("selected_chat_by_identity") or {}),
                "active_identity_version": int(fleet.get("active_identity_version") or 0),
                "active_identity_updated_at": _utc_iso(fleet.get("active_identity_updated_at")),
            }

    def set_active_chat_for_fleet_identity(
        self,
        *,
        user_id: int,
        identity_id: str,
        chat_id: Optional[str],
        source: Optional[str] = None,
        desktop_id: Optional[str] = None,
        company_id: Optional[str] = None,
        include_unscoped_company_records: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            identity = self._resolve_scoped_fleet_identity_locked(int(user_id), identity_id, desktop_id)
            if not identity:
                raise KeyError("Unknown fleet identity")
            identity_company_id = str(dict(identity.get("metadata") or {}).get("company_id") or "").strip()
            clean_company_id = str(company_id or "").strip()
            if clean_company_id and identity_company_id != clean_company_id:
                if not (include_unscoped_company_records and not identity_company_id):
                    raise KeyError("Unknown fleet identity")
            effective_desktop_id = str(desktop_id or identity.get("desktop_id") or "").strip() or None
            state = self._ensure_shared_state_locked(int(user_id))
            fleet = self._ensure_fleet_selection_locked(
                user_id=int(user_id),
                state=state,
                desktop_id=effective_desktop_id,
                company_id=clean_company_id or None,
                include_unscoped_company_records=include_unscoped_company_records,
            )
            selected_by_identity = dict(fleet.get("selected_chat_by_identity") or {})
            clean_chat_id = str(chat_id or "").strip()
            if clean_chat_id:
                selected_by_identity[str(identity["identity_id"])] = clean_chat_id
            else:
                selected_by_identity.pop(str(identity["identity_id"]), None)
            fleet["selected_chat_by_identity"] = selected_by_identity
            if (
                not clean_company_id
                and str(fleet.get("active_identity_id") or "")
                == str(identity["identity_id"])
            ):
                state["current_session_id"] = clean_chat_id or None
            fleet = self._bump_fleet_selection_locked(
                int(user_id),
                state,
                fleet=fleet,
                desktop_id=effective_desktop_id,
                company_id=clean_company_id or None,
                include_unscoped_company_records=include_unscoped_company_records,
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="fleet_identity_chat_selected",
                actor_kind=str(source or "app")[:80],
                target_kind="identity",
                target_id=str(identity["identity_id"]),
                metadata={"selected_chat_id": clean_chat_id or None},
            )
            next_state = self._bump_shared_state_locked(int(user_id), state)
            self._conn.commit()
            self._secure_db_files()
            return {
                "active_identity_id": fleet.get("active_identity_id"),
                "active_identity": self._resolve_fleet_identity_locked(int(user_id), str(fleet.get("active_identity_id") or "")),
                "selected_chat_by_identity": dict(fleet.get("selected_chat_by_identity") or {}),
                "active_identity_version": int(fleet.get("active_identity_version") or 0),
                "active_identity_updated_at": _utc_iso(fleet.get("active_identity_updated_at")),
            }
