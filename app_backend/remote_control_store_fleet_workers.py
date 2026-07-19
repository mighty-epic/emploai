from __future__ import annotations

from app_backend.fleet_identity_profiles import (
    DEFAULT_WORKER_DISPLAY_NAME,
    additional_worker_metadata,
    default_worker_metadata,
)
from app_backend.fleet_identity_creation import validate_local_worker_creation
from app_backend.fleet_policy import FLEET_PREVIEW_MODE, FLEET_WORKER_SESSION_TTL_SECONDS, normalize_fleet_enrollment_ttl

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreFleetWorkerMixin:
    def set_identity_upstream_visibility(
        self,
        *,
        user_id: int,
        identity_id: str,
        published_upstream: bool,
    ) -> Dict[str, Any]:
        with self._lock:
            identity = self._conn.execute(
                "SELECT * FROM fleet_instances WHERE user_id = ? AND instance_id = ? AND reset_at IS NULL",
                (int(user_id), str(identity_id or "").strip()),
            ).fetchone()
            if not identity:
                raise KeyError("Unknown identity")
            metadata = _json_loads(identity["metadata"], {})
            metadata["published_upstream"] = bool(published_upstream)
            now = time.time()
            self._conn.execute(
                "UPDATE fleet_instances SET metadata = ?, updated_at = ? WHERE instance_id = ?",
                (_json_dumps(metadata), now, identity["instance_id"]),
            )
            worker_id = str(identity["worker_id"] or "").strip()
            if worker_id:
                worker = self._conn.execute(
                    "SELECT metadata FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                    (int(user_id), worker_id),
                ).fetchone()
                worker_metadata = _json_loads(worker["metadata"], {}) if worker else {}
                worker_metadata["published_upstream"] = bool(published_upstream)
                self._conn.execute(
                    "UPDATE fleet_workers SET metadata = ?, updated_at = ? WHERE user_id = ? AND worker_id = ?",
                    (_json_dumps(worker_metadata), now, int(user_id), worker_id),
                )
            self._audit_locked(
                user_id=int(user_id),
                event_type="identity_upstream_visibility_changed",
                actor_kind="manager",
                target_kind=str(identity["role"] or "identity"),
                target_id=str(identity["instance_id"]),
                metadata={"published_upstream": bool(published_upstream)},
            )
            self._conn.commit()
            refreshed = self._conn.execute(
                "SELECT * FROM fleet_instances WHERE instance_id = ?", (identity["instance_id"],)
            ).fetchone()
            return self._identity_view(refreshed)

    def _ensure_default_worker_locked(
        self,
        *,
        user_id: int,
        desktop_id: str,
        display_name: str = DEFAULT_WORKER_DISPLAY_NAME,
    ) -> Dict[str, Any]:
        """Reconcile the protected execution identity owned by one computer.

        This internal migration path intentionally does not use the user-request
        worker creation validator. Public worker creation remains explicit-only.
        """

        rows = self._conn.execute(
            "SELECT * FROM fleet_workers WHERE user_id = ? AND kind = 'local' AND machine_desktop_id = ? ORDER BY created_at ASC",
            (int(user_id), str(desktop_id or "").strip()),
        ).fetchall()
        defaults = [row for row in rows if bool(_json_loads(row["metadata"], {}).get("is_default"))]
        now = time.time()
        for row in rows:
            row_metadata = _json_loads(row["metadata"], {})
            if bool(row_metadata.get("is_default")):
                continue
            # Older worker creation stored the profile only on fleet_workers.
            # Copy an existing configured profile to its identity without
            # inventing a replacement for legacy custom session profiles.
            if any(key in row_metadata for key in ("tool_profile", "enabled_tool_packs", "capability_tags")):
                self._conn.execute(
                    "UPDATE fleet_instances SET metadata = ?, updated_at = ? WHERE instance_id = ?",
                    (_json_dumps(row_metadata), now, row["instance_id"]),
                )
        if defaults:
            worker = defaults[0]
            metadata = default_worker_metadata(_json_loads(worker["metadata"], {}))
            self._conn.execute(
                "UPDATE fleet_workers SET metadata = ?, updated_at = ? WHERE worker_id = ?",
                (_json_dumps(metadata), now, worker["worker_id"]),
            )
            self._conn.execute(
                "UPDATE fleet_instances SET status = 'active', reset_at = NULL, metadata = ?, updated_at = ? WHERE instance_id = ?",
                (_json_dumps(metadata), now, worker["instance_id"]),
            )
            for duplicate in defaults[1:]:
                duplicate_metadata = additional_worker_metadata(_json_loads(duplicate["metadata"], {}))
                self._conn.execute(
                    "UPDATE fleet_workers SET metadata = ?, updated_at = ? WHERE worker_id = ?",
                    (_json_dumps(duplicate_metadata), now, duplicate["worker_id"]),
                )
                self._conn.execute(
                    "UPDATE fleet_instances SET metadata = ?, updated_at = ? WHERE instance_id = ?",
                    (_json_dumps(duplicate_metadata), now, duplicate["instance_id"]),
                )
            return self._worker_view(
                self._conn.execute("SELECT * FROM fleet_workers WHERE worker_id = ?", (worker["worker_id"],)).fetchone()
            )

        worker_id = f"wrk_{secrets.token_hex(8)}"
        instance_id = f"win_{secrets.token_hex(8)}"
        name = str(display_name or DEFAULT_WORKER_DISPLAY_NAME).strip()[:MAX_DISPLAY_NAME_CHARS] or DEFAULT_WORKER_DISPLAY_NAME
        metadata = default_worker_metadata()
        self._conn.execute(
            """
            INSERT INTO fleet_workers(
                worker_id, user_id, kind, machine_desktop_id, instance_id, display_name, status, detail,
                group_id, active_task_id, metadata, created_at, updated_at, last_seen_at
            ) VALUES(?, ?, 'local', ?, ?, ?, 'idle', NULL, NULL, NULL, ?, ?, ?, ?)
            """,
            (worker_id, int(user_id), desktop_id, instance_id, name, _json_dumps(metadata), now, now, now),
        )
        self._conn.execute(
            """
            INSERT INTO fleet_instances(
                instance_id, user_id, role, desktop_id, worker_id, display_name, status, metadata, created_at, updated_at, reset_at
            ) VALUES(?, ?, 'worker', ?, ?, ?, 'active', ?, ?, ?, NULL)
            """,
            (instance_id, int(user_id), desktop_id, worker_id, name, _json_dumps(metadata), now, now),
        )
        self._audit_locked(
            user_id=int(user_id),
            event_type="default_worker_reconciled",
            actor_kind="desktop",
            actor_id=desktop_id,
            target_kind="worker",
            target_id=worker_id,
            metadata={"is_default": True, "protected": True},
        )
        return self._worker_view(
            self._conn.execute("SELECT * FROM fleet_workers WHERE worker_id = ?", (worker_id,)).fetchone()
        )

    def set_worker_queue_policy(self, *, user_id: int, worker_id: str, queue_policy: str) -> Dict[str, Any]:
        from app_backend.fleet_queue_policy import normalize_queue_policy

        policy = normalize_queue_policy(queue_policy)
        with self._lock:
            worker = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchone()
            if not worker:
                raise KeyError("Unknown worker")
            metadata = _json_loads(worker["metadata"], {})
            metadata["queue_policy"] = policy
            now = time.time()
            self._conn.execute(
                "UPDATE fleet_workers SET metadata = ?, updated_at = ? WHERE user_id = ? AND worker_id = ?",
                (_json_dumps(metadata), now, int(user_id), worker["worker_id"]),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_queue_policy_updated",
                actor_kind="manager",
                target_kind="worker",
                target_id=worker["worker_id"],
                metadata={"queue_policy": policy},
            )
            self._conn.commit()
            return self._worker_view(
                self._conn.execute("SELECT * FROM fleet_workers WHERE worker_id = ?", (worker["worker_id"],)).fetchone()
            )

    def rename_worker(self, *, user_id: int, worker_id: str, display_name: str) -> Dict[str, Any]:
        name = str(display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS]
        if not name:
            raise ValueError("display_name is required")
        with self._lock:
            worker = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchone()
            if not worker:
                raise KeyError("Unknown worker")
            now = time.time()
            self._conn.execute(
                "UPDATE fleet_workers SET display_name = ?, updated_at = ? WHERE worker_id = ?",
                (name, now, worker["worker_id"]),
            )
            self._conn.execute(
                "UPDATE fleet_instances SET display_name = ?, updated_at = ? WHERE worker_id = ?",
                (name, now, worker["worker_id"]),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_renamed",
                target_kind="worker",
                target_id=worker["worker_id"],
                metadata={"display_name": name},
            )
            self._conn.commit()
            self._secure_db_files()
            return self._worker_view(self._conn.execute("SELECT * FROM fleet_workers WHERE worker_id = ?", (worker["worker_id"],)).fetchone())

    def create_or_update_group(
        self,
        *,
        user_id: int,
        display_name: str,
        group_id: Optional[str] = None,
        description: Optional[str] = None,
        worker_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        name = str(display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS]
        if not name:
            raise ValueError("display_name is required")
        with self._lock:
            now = time.time()
            clean_group_id = str(group_id or "").strip() or f"grp_{secrets.token_hex(8)}"
            existing = self._conn.execute(
                "SELECT group_id FROM fleet_groups WHERE user_id = ? AND group_id = ?",
                (int(user_id), clean_group_id),
            ).fetchone()
            created_at = now
            if existing:
                created = self._conn.execute("SELECT created_at FROM fleet_groups WHERE group_id = ?", (clean_group_id,)).fetchone()
                created_at = float(created["created_at"] or now) if created else now
            self._conn.execute(
                """
                INSERT INTO fleet_groups(group_id, user_id, display_name, description, metadata, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    description = excluded.description,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (clean_group_id, int(user_id), name, description, _json_dumps(metadata or {}), created_at, now),
            )
            if worker_ids is not None:
                self.set_group_workers_locked(user_id=int(user_id), group_id=clean_group_id, worker_ids=worker_ids)
            self._audit_locked(
                user_id=int(user_id),
                event_type="group_updated" if existing else "group_created",
                target_kind="group",
                target_id=clean_group_id,
                metadata={"display_name": name},
            )
            self._conn.commit()
            self._secure_db_files()
            row = self._conn.execute("SELECT * FROM fleet_groups WHERE group_id = ?", (clean_group_id,)).fetchone()
            return {
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
                        (int(user_id), clean_group_id),
                    ).fetchall()
                ],
            }

    def set_group_workers_locked(self, *, user_id: int, group_id: str, worker_ids: List[str]) -> None:
        clean_ids = [str(item or "").strip() for item in list(worker_ids or []) if str(item or "").strip()]
        self._conn.execute(
            "UPDATE fleet_workers SET group_id = NULL, updated_at = ? WHERE user_id = ? AND group_id = ?",
            (time.time(), int(user_id), group_id),
        )
        if not clean_ids:
            return
        placeholders = ",".join("?" for _ in clean_ids)
        self._conn.execute(
            f"UPDATE fleet_workers SET group_id = ?, updated_at = ? WHERE user_id = ? AND worker_id IN ({placeholders})",
            (group_id, time.time(), int(user_id), *clean_ids),
        )

    def set_group_workers(self, *, user_id: int, group_id: str, worker_ids: List[str]) -> Dict[str, Any]:
        with self._lock:
            group = self._conn.execute(
                "SELECT * FROM fleet_groups WHERE user_id = ? AND group_id = ?",
                (int(user_id), str(group_id or "").strip()),
            ).fetchone()
            if not group:
                raise KeyError("Unknown group")
            self.set_group_workers_locked(user_id=int(user_id), group_id=group["group_id"], worker_ids=worker_ids)
            self._audit_locked(
                user_id=int(user_id),
                event_type="group_members_updated",
                target_kind="group",
                target_id=group["group_id"],
                metadata={"worker_ids": list(worker_ids or [])},
            )
            self._conn.commit()
            self._secure_db_files()
            return self.create_or_update_group(
                user_id=int(user_id),
                group_id=group["group_id"],
                display_name=group["display_name"],
                description=group["description"],
                metadata=_json_loads(group["metadata"], {}),
            )

    def delete_group(self, *, user_id: int, group_id: str) -> Dict[str, Any]:
        with self._lock:
            group = self._conn.execute(
                "SELECT * FROM fleet_groups WHERE user_id = ? AND group_id = ?",
                (int(user_id), str(group_id or "").strip()),
            ).fetchone()
            if not group:
                raise KeyError("Unknown group")
            worker_ids = [
                row["worker_id"]
                for row in self._conn.execute(
                    "SELECT worker_id FROM fleet_workers WHERE user_id = ? AND group_id = ? ORDER BY display_name ASC",
                    (int(user_id), group["group_id"]),
                ).fetchall()
            ]
            self.archive_item(
                user_id=int(user_id),
                object_kind="group",
                object_id=group["group_id"],
                display_name=group["display_name"],
                payload={
                    "group": {
                        "group_id": group["group_id"],
                        "display_name": group["display_name"],
                        "description": group["description"],
                        "metadata": _json_loads(group["metadata"], {}),
                        "created_at": _utc_iso(group["created_at"]),
                        "updated_at": _utc_iso(group["updated_at"]),
                        "worker_ids": worker_ids,
                    },
                },
                metadata={"archive_reason": "group_delete"},
            )
            self._conn.execute(
                "UPDATE fleet_workers SET group_id = NULL, updated_at = ? WHERE user_id = ? AND group_id = ?",
                (time.time(), int(user_id), group["group_id"]),
            )
            self._conn.execute("DELETE FROM fleet_groups WHERE group_id = ?", (group["group_id"],))
            self._audit_locked(
                user_id=int(user_id),
                event_type="group_deleted",
                target_kind="group",
                target_id=group["group_id"],
            )
            self._conn.commit()
            self._secure_db_files()
            return {"ok": True, "deleted": True, "group_id": group["group_id"]}

    def create_local_worker(
        self,
        *,
        user_id: int,
        desktop_id: str,
        display_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        display_name, metadata = validate_local_worker_creation(
            display_name=display_name,
            metadata=metadata,
        )
        metadata = additional_worker_metadata(metadata)
        with self._lock:
            desktop = self._conn.execute(
                "SELECT * FROM desktops WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), str(desktop_id or "").strip()),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown manager desktop")
            self._ensure_manager_instance_locked(user_id=int(user_id), desktop_id=desktop["desktop_id"], display_name=desktop["display_name"])
            now = time.time()
            worker_id = f"wrk_{secrets.token_hex(8)}"
            instance_id = f"win_{secrets.token_hex(8)}"
            name = display_name[:MAX_DISPLAY_NAME_CHARS]
            self._conn.execute(
                """
                INSERT INTO fleet_workers(
                    worker_id, user_id, kind, machine_desktop_id, instance_id, display_name, status, detail,
                    group_id, active_task_id, metadata, created_at, updated_at, last_seen_at
                ) VALUES(?, ?, 'local', ?, ?, ?, 'idle', NULL, NULL, NULL, ?, ?, ?, ?)
                """,
                (worker_id, int(user_id), desktop["desktop_id"], instance_id, name, _json_dumps(metadata or {}), now, now, now),
            )
            self._conn.execute(
                """
                INSERT INTO fleet_instances(
                    instance_id, user_id, role, desktop_id, worker_id, display_name, status, metadata, created_at, updated_at, reset_at
                ) VALUES(?, ?, 'worker', ?, ?, ?, 'active', ?, ?, ?, NULL)
                """,
                (instance_id, int(user_id), desktop["desktop_id"], worker_id, name, _json_dumps({"kind": "local", **metadata}), now, now),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_created",
                actor_kind="manager",
                actor_id=desktop["desktop_id"],
                target_kind="worker",
                target_id=worker_id,
                metadata={
                    "kind": "local",
                    "created_by": str((metadata or {}).get("created_by") or "").strip() or None,
                },
            )
            self._conn.commit()
            self._secure_db_files()
            return self._worker_view(self._conn.execute("SELECT * FROM fleet_workers WHERE worker_id = ?", (worker_id,)).fetchone())

    def create_worker_enrollment(
        self,
        *,
        user_id: int,
        desktop_id: str,
        display_name: Optional[str] = None,
        ttl_seconds: int = FLEET_ENROLLMENT_TTL_SECONDS,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            desktop = self._conn.execute(
                "SELECT * FROM desktops WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), str(desktop_id or "").strip()),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown manager desktop")
            now = time.time()
            enrollment_id = f"enr_{secrets.token_hex(8)}"
            token = f"fw_{secrets.token_urlsafe(24)}"
            expires_in = normalize_fleet_enrollment_ttl(ttl_seconds, FLEET_ENROLLMENT_TTL_SECONDS)
            self._conn.execute(
                """
                INSERT INTO fleet_enrollments(
                    enrollment_id, enrollment_token_hash, user_id, created_by_desktop_id, display_name,
                    metadata, created_at, expires_at, used_at, revoked_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    enrollment_id,
                    _hash_token(token),
                    int(user_id),
                    desktop["desktop_id"],
                    (display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None,
                    _json_dumps(metadata or {}),
                    now,
                    now + expires_in,
                ),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_enrollment_created",
                actor_kind="manager",
                actor_id=desktop["desktop_id"],
                target_kind="enrollment",
                target_id=enrollment_id,
            )
            self._conn.commit()
            self._secure_db_files()
            return {
                "enrollment_id": enrollment_id,
                "enrollment_token": token,
                "expires_in_seconds": expires_in,
                "display_name": display_name,
            }

    def complete_worker_enrollment(
        self,
        *,
        enrollment_token: str,
        device_name: Optional[str],
        device_platform: Optional[str],
        device_key: Optional[str],
        token_ttl_seconds: int = FLEET_WORKER_SESSION_TTL_SECONDS,
    ) -> Dict[str, Any]:
        with self._lock:
            self._cleanup_locked()
            now = time.time()
            enrollment = self._conn.execute(
                "SELECT * FROM fleet_enrollments WHERE enrollment_token_hash = ?",
                (_hash_token(enrollment_token or ""),),
            ).fetchone()
            if not enrollment:
                raise KeyError("Unknown worker enrollment")
            if enrollment["used_at"] or enrollment["revoked_at"]:
                raise ValueError("Worker enrollment was already used or revoked")
            if float(enrollment["expires_at"] or 0) < now:
                raise ValueError("Worker enrollment expired")
            identity = normalize_worker_enrollment_identity(
                device_name=device_name,
                device_platform=device_platform,
                device_key=device_key,
            )
            manager_desktop = self._conn.execute(
                "SELECT device_key FROM desktops WHERE desktop_id = ?",
                (enrollment["created_by_desktop_id"],),
            ).fetchone()
            ensure_worker_key_not_manager_key(
                worker_device_key=str(identity["device_key"] or ""),
                manager_device_key=manager_desktop["device_key"] if manager_desktop else None,
            )
            user_id = int(enrollment["user_id"])
            name = (enrollment["display_name"] or identity["device_name"] or "").strip()[:MAX_DISPLAY_NAME_CHARS] or self._next_worker_name_locked(user_id)
            session = self._create_remote_session_locked(
                user_id=user_id,
                actor_kind="desktop",
                device_name=identity["device_name"] or name,
                device_platform=identity["device_platform"],
                device_key=identity["device_key"],
                token_ttl_seconds=token_ttl_seconds,
                ensure_manager=False,
            )
            desktop_id = str((session.get("desktop") or {}).get("desktop_id") or "")
            enrollment_metadata = _json_loads(enrollment["metadata"], {})
            if not isinstance(enrollment_metadata, dict):
                enrollment_metadata = {}
            connection_only = str(enrollment_metadata.get("transport") or "").strip().lower() == "yggdrasil"
            created_worker = None
            if not connection_only:
                existing_worker = self._conn.execute(
                    "SELECT * FROM fleet_workers WHERE user_id = ? AND kind = 'remote' AND machine_desktop_id = ? ORDER BY created_at ASC LIMIT 1",
                    (user_id, desktop_id),
                ).fetchone()
                worker_id = str(existing_worker["worker_id"]) if existing_worker else f"wrk_{secrets.token_hex(8)}"
                instance_id = str(existing_worker["instance_id"]) if existing_worker else f"win_{secrets.token_hex(8)}"
                worker_metadata = _json_loads(existing_worker["metadata"], {}) if existing_worker else {}
                if not isinstance(worker_metadata, dict):
                    worker_metadata = {}
                worker_metadata.update(enrollment_metadata)
                worker_metadata.update(
                    {
                        "machine_name": identity["device_name"] or name,
                        "device_platform": identity["device_platform"],
                    }
                )
                if existing_worker:
                    self._conn.execute(
                        "UPDATE fleet_workers SET display_name = ?, detail = NULL, metadata = ?, updated_at = ?, last_seen_at = ? WHERE worker_id = ?",
                        (name, _json_dumps(worker_metadata), now, now, worker_id),
                    )
                    self._conn.execute(
                        "UPDATE fleet_instances SET display_name = ?, status = 'active', metadata = ?, updated_at = ?, reset_at = NULL WHERE instance_id = ?",
                        (name, _json_dumps({"kind": "remote", **worker_metadata}), now, instance_id),
                    )
                else:
                    self._conn.execute(
                        """
                        INSERT INTO fleet_workers(
                            worker_id, user_id, kind, machine_desktop_id, instance_id, display_name, status, detail,
                            group_id, active_task_id, metadata, created_at, updated_at, last_seen_at
                        ) VALUES(?, ?, 'remote', ?, ?, ?, 'idle', NULL, NULL, NULL, ?, ?, ?, ?)
                        """,
                        (worker_id, user_id, desktop_id, instance_id, name, _json_dumps(worker_metadata), now, now, now),
                    )
                    self._conn.execute(
                        """
                        INSERT INTO fleet_instances(
                            instance_id, user_id, role, desktop_id, worker_id, display_name, status, metadata, created_at, updated_at, reset_at
                        ) VALUES(?, ?, 'worker', ?, ?, ?, 'active', ?, ?, ?, NULL)
                        """,
                        (instance_id, user_id, desktop_id, worker_id, name, _json_dumps({"kind": "remote", **worker_metadata}), now, now),
                    )
                created_worker = self._worker_view(
                    self._conn.execute("SELECT * FROM fleet_workers WHERE worker_id = ?", (worker_id,)).fetchone()
                )
            new_token_hash = _hash_token(str(session.get("session_token") or ""))
            self._conn.execute(
                "UPDATE remote_sessions SET revoked_at = ? WHERE desktop_id = ? AND token_hash <> ? AND revoked_at IS NULL",
                (now, desktop_id, new_token_hash),
            )
            self._conn.execute("UPDATE fleet_enrollments SET used_at = ? WHERE enrollment_id = ?", (now, enrollment["enrollment_id"]))
            self._audit_locked(
                user_id=user_id,
                event_type="computer_paired" if connection_only else "worker_enrolled",
                actor_kind="enrollment",
                actor_id=enrollment["enrollment_id"],
                target_kind="desktop" if connection_only else "worker",
                target_id=desktop_id if connection_only else str((created_worker or {}).get("worker_id") or ""),
                metadata={
                    "desktop_id": desktop_id,
                    "transport": "yggdrasil",
                    "creates_worker": not connection_only,
                },
            )
            self._conn.commit()
            self._secure_db_files()
            return {
                **session,
                "worker": created_worker,
            }

    def _remove_worker_from_fleet_selection_locked(self, *, user_id: int, worker_id: str) -> None:
        identity_ids = {
            str(row["instance_id"] or "").strip()
            for row in self._conn.execute(
                "SELECT instance_id FROM fleet_instances WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchall()
            if str(row["instance_id"] or "").strip()
        }
        if not identity_ids:
            return

        state = self._ensure_shared_state_locked(int(user_id))
        fleet = _normalize_fleet_state(state.get("fleet"))
        selected_by_identity = {
            key: value
            for key, value in dict(fleet.get("selected_chat_by_identity") or {}).items()
            if key not in identity_ids
        }
        active_identity_id = str(fleet.get("active_identity_id") or "").strip()
        fleet["selected_chat_by_identity"] = selected_by_identity
        if active_identity_id in identity_ids:
            fleet["active_identity_id"] = None
            state["current_session_id"] = None
        state["fleet"] = fleet
        self._bump_fleet_selection_locked(int(user_id), state)
        self._bump_shared_state_locked(int(user_id), state)

    def delete_worker(self, *, user_id: int, worker_id: str, wipe_state: bool = True) -> Dict[str, Any]:
        with self._lock:
            worker = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchone()
            if not worker:
                raise KeyError("Unknown worker")
            if bool(_json_loads(worker["metadata"], {}).get("protected")):
                raise PermissionError("The protected default worker cannot be deleted")
            now = time.time()
            machine_desktop_id = str(worker["machine_desktop_id"] or "").strip()
            related_tasks = [
                self._task_view(row)
                for row in self._conn.execute(
                    "SELECT * FROM fleet_tasks WHERE user_id = ? AND worker_id = ? ORDER BY created_at DESC LIMIT 500",
                    (int(user_id), worker["worker_id"]),
                ).fetchall()
            ]
            related_reports = [
                self._report_view(row)
                for row in self._conn.execute(
                    "SELECT * FROM fleet_reports WHERE user_id = ? AND worker_id = ? ORDER BY created_at DESC LIMIT 500",
                    (int(user_id), worker["worker_id"]),
                ).fetchall()
            ]
            related_grants = [
                self._tool_grant_view(row)
                for row in self._conn.execute(
                    "SELECT * FROM fleet_tool_grants WHERE user_id = ? AND target_kind = 'worker' AND target_id = ? ORDER BY updated_at DESC LIMIT 200",
                    (int(user_id), worker["worker_id"]),
                ).fetchall()
            ]
            self.archive_item(
                user_id=int(user_id),
                object_kind="worker",
                object_id=worker["worker_id"],
                display_name=worker["display_name"],
                payload={
                    "worker": self._worker_view(worker),
                    "tasks": related_tasks,
                    "reports": related_reports,
                    "tool_grants": related_grants,
                },
                metadata={"wipe_state": bool(wipe_state), "archive_reason": "worker_delete"},
            )
            self._remove_worker_from_fleet_selection_locked(user_id=int(user_id), worker_id=worker["worker_id"])
            self._conn.execute("UPDATE fleet_instances SET reset_at = ?, status = 'reset' WHERE worker_id = ?", (now, worker["worker_id"]))
            if wipe_state:
                self._conn.execute(
                    """
                    DELETE FROM fleet_tasks
                    WHERE worker_id = ?
                      AND status IN ('queued', 'running', 'paused', 'blocked', 'needs_review')
                    """,
                    (worker["worker_id"],),
                )
                self._conn.execute("DELETE FROM fleet_tool_grants WHERE target_kind = 'worker' AND target_id = ?", (worker["worker_id"],))
            self._conn.execute("DELETE FROM fleet_workers WHERE worker_id = ?", (worker["worker_id"],))
            connection_revoked = False
            if machine_desktop_id and str(worker["kind"] or "").strip().lower() == "remote":
                remaining_remote_workers = self._conn.execute(
                    "SELECT COUNT(*) AS count FROM fleet_workers WHERE user_id = ? AND kind = 'remote' AND machine_desktop_id = ?",
                    (int(user_id), machine_desktop_id),
                ).fetchone()
                if int(remaining_remote_workers["count"] or 0) == 0:
                    self._conn.execute(
                        "UPDATE remote_sessions SET revoked_at = ? WHERE user_id = ? AND actor_kind = 'desktop' AND desktop_id = ? AND revoked_at IS NULL",
                        (now, int(user_id), machine_desktop_id),
                    )
                    self._conn.execute(
                        "UPDATE desktops SET status = 'offline', detail = 'Fleet worker removed' WHERE user_id = ? AND desktop_id = ?",
                        (int(user_id), machine_desktop_id),
                    )
                    connection_revoked = True
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_deleted",
                target_kind="worker",
                target_id=worker["worker_id"],
                metadata={"wipe_state": bool(wipe_state)},
            )
            self._conn.commit()
            self._secure_db_files()
            return {
                "ok": True,
                "deleted": True,
                "worker_id": worker["worker_id"],
                "wipe_state": bool(wipe_state),
                "connection_revoked": connection_revoked,
            }

    def assign_worker_task(
        self,
        *,
        user_id: int,
        worker_id: str,
        prompt: str,
        source: str = "manager",
        target_session_id: Optional[str] = None,
        target_mode: str = "auto",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prompt_text = str(prompt or "").strip()
        if not prompt_text:
            raise ValueError("Task prompt is required")
        with self._lock:
            worker = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchone()
            if not worker:
                raise KeyError("Unknown worker")
            task_metadata = dict(metadata or {})
            clean_target_session_id = str(target_session_id or task_metadata.get("target_session_id") or "").strip()
            if not clean_target_session_id and worker["active_task_id"]:
                active_task = self._conn.execute(
                    "SELECT metadata FROM fleet_tasks WHERE user_id = ? AND task_id = ?",
                    (int(user_id), worker["active_task_id"]),
                ).fetchone()
                active_metadata = _json_loads(active_task["metadata"], {}) if active_task else {}
                clean_target_session_id = str(active_metadata.get("target_session_id") or "").strip()
            if clean_target_session_id:
                task_metadata["target_session_id"] = clean_target_session_id
            task_metadata["target_mode"] = str(target_mode or task_metadata.get("target_mode") or "auto")[:40]
            row = self._conn.execute(
                "SELECT COALESCE(MAX(queue_position), 0) AS max_pos FROM fleet_tasks WHERE user_id = ? AND worker_id = ? AND status IN ('queued', 'running', 'paused', 'blocked', 'needs_review')",
                (int(user_id), worker["worker_id"]),
            ).fetchone()
            position = int(row["max_pos"] or 0) + 1
            now = time.time()
            task_id = f"tsk_{secrets.token_hex(8)}"
            self._conn.execute(
                """
                INSERT INTO fleet_tasks(
                    task_id, user_id, worker_id, status, prompt, source, queue_position, report_id,
                    metadata, created_at, updated_at, started_at, completed_at, canceled_at
                ) VALUES(?, ?, ?, 'queued', ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL)
                """,
                (task_id, int(user_id), worker["worker_id"], prompt_text, str(source or "manager")[:80], position, _json_dumps(task_metadata), now, now),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="task_assigned",
                actor_kind=str(source or "manager")[:80],
                target_kind="worker",
                target_id=worker["worker_id"],
                task_id=task_id,
            )
            self._conn.commit()
            return self._task_view(self._conn.execute("SELECT * FROM fleet_tasks WHERE task_id = ?", (task_id,)).fetchone())

    def get_next_queued_worker_task(self, *, user_id: int, worker_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            worker = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchone()
            if not worker:
                raise KeyError("Unknown worker")
            active = self._conn.execute(
                """
                SELECT task_id FROM fleet_tasks
                WHERE user_id = ? AND worker_id = ? AND status IN ('running', 'paused', 'blocked', 'needs_review')
                ORDER BY queue_position ASC, created_at ASC
                LIMIT 1
                """,
                (int(user_id), worker["worker_id"]),
            ).fetchone()
            if active:
                return None
            worker_metadata = _json_loads(worker["metadata"], {})
            review_gate = worker_metadata.get("queue_review_required")
            if isinstance(review_gate, dict) and str(review_gate.get("report_id") or "").strip():
                return None
            queued = self._conn.execute(
                """
                SELECT * FROM fleet_tasks
                WHERE user_id = ? AND worker_id = ? AND status = 'queued'
                ORDER BY queue_position ASC, created_at ASC
                LIMIT 1
                """,
                (int(user_id), worker["worker_id"]),
            ).fetchone()
            return self._task_view(queued) if queued else None

    def get_worker_task(self, *, user_id: int, task_id: str) -> Dict[str, Any]:
        clean_task_id = str(task_id or "").strip()
        if not clean_task_id:
            raise KeyError("Unknown task")
        with self._lock:
            task = self._conn.execute(
                "SELECT * FROM fleet_tasks WHERE user_id = ? AND task_id = ?",
                (int(user_id), clean_task_id),
            ).fetchone()
            if not task:
                raise KeyError("Unknown task")
            return self._task_view(task)

    def mark_worker_queue_reviewed(
        self,
        *,
        user_id: int,
        worker_id: str,
        reviewed_report_id: Optional[str],
        source: str = "manager",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_worker_id = str(worker_id or "").strip()
        clean_report_id = str(reviewed_report_id or "").strip()
        with self._lock:
            worker = self._conn.execute(
                "SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), clean_worker_id),
            ).fetchone()
            if not worker:
                raise KeyError("Unknown worker")
            worker_metadata = _json_loads(worker["metadata"], {})
            review_gate = worker_metadata.get("queue_review_required")
            if isinstance(review_gate, dict) and str(review_gate.get("report_id") or "").strip():
                expected_report_id = str(review_gate.get("report_id") or "").strip()
                if clean_report_id and clean_report_id != expected_report_id:
                    raise ValueError("reviewed_report_id does not match the latest worker report")
                worker_metadata.pop("queue_review_required", None)
            effective_report_id = clean_report_id
            if not effective_report_id and isinstance(review_gate, dict):
                effective_report_id = str(review_gate.get("report_id") or "").strip()
            worker_metadata["last_queue_review"] = {
                "reviewed_report_id": effective_report_id or None,
                "source": str(source or "manager")[:80],
                "reviewed_at": _utc_iso(time.time()),
                "metadata": dict(metadata or {}),
            }
            now = time.time()
            self._conn.execute(
                "UPDATE fleet_workers SET metadata = ?, updated_at = ? WHERE user_id = ? AND worker_id = ?",
                (_json_dumps(worker_metadata), now, int(user_id), clean_worker_id),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_queue_reviewed",
                actor_kind=str(source or "manager")[:80],
                target_kind="worker",
                target_id=clean_worker_id,
                metadata={"reviewed_report_id": worker_metadata["last_queue_review"].get("reviewed_report_id")},
            )
            self._conn.commit()
            return self._worker_view(
                self._conn.execute("SELECT * FROM fleet_workers WHERE user_id = ? AND worker_id = ?", (int(user_id), clean_worker_id)).fetchone()
            )

    def update_worker_task_status(
        self,
        *,
        user_id: int,
        task_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        allowed = {"queued", "running", "paused", "blocked", "needs_review", "completed", "failed", "stopped", "canceled"}
        normalized_status = str(status or "").strip()
        if normalized_status not in allowed:
            raise ValueError("Invalid task status")
        with self._lock:
            task = self._conn.execute(
                "SELECT * FROM fleet_tasks WHERE user_id = ? AND task_id = ?",
                (int(user_id), str(task_id or "").strip()),
            ).fetchone()
            if not task:
                raise KeyError("Unknown task")
            now = time.time()
            self._conn.execute(
                """
                UPDATE fleet_tasks
                SET status = ?, metadata = ?, updated_at = ?,
                    started_at = CASE WHEN ? = 'running' AND started_at IS NULL THEN ? ELSE started_at END,
                    completed_at = CASE WHEN ? IN ('completed', 'failed', 'stopped') AND completed_at IS NULL THEN ? ELSE completed_at END,
                    canceled_at = CASE WHEN ? = 'canceled' AND canceled_at IS NULL THEN ? ELSE canceled_at END
                WHERE task_id = ?
                """,
                (
                    normalized_status,
                    _json_dumps({**_json_loads(task["metadata"], {}), **(metadata or {})}),
                    now,
                    normalized_status,
                    now,
                    normalized_status,
                    now,
                    normalized_status,
                    now,
                    task["task_id"],
                ),
            )
            if normalized_status == "running":
                self._conn.execute(
                    "UPDATE fleet_workers SET status = 'working', active_task_id = ?, updated_at = ?, last_seen_at = ? WHERE worker_id = ?",
                    (task["task_id"], now, now, task["worker_id"]),
                )
            if normalized_status in {"paused", "blocked", "needs_review"}:
                self._conn.execute(
                    "UPDATE fleet_workers SET status = ?, active_task_id = ?, updated_at = ?, last_seen_at = ? WHERE worker_id = ?",
                    (normalized_status, task["task_id"], now, now, task["worker_id"]),
                )
            if normalized_status in {"completed", "failed", "stopped", "canceled"}:
                self._conn.execute(
                    "UPDATE fleet_workers SET status = 'idle', active_task_id = NULL, updated_at = ?, last_seen_at = ? WHERE worker_id = ? AND active_task_id = ?",
                    (now, now, task["worker_id"], task["task_id"]),
                )
            self._audit_locked(
                user_id=int(user_id),
                event_type=f"task_{normalized_status}",
                target_kind="task",
                target_id=task["task_id"],
                task_id=task["task_id"],
            )
            self._conn.commit()
            return self._task_view(self._conn.execute("SELECT * FROM fleet_tasks WHERE task_id = ?", (task["task_id"],)).fetchone())

    def reorder_worker_tasks(self, *, user_id: int, worker_id: str, task_ids: List[str]) -> List[Dict[str, Any]]:
        clean_task_ids = [str(item or "").strip() for item in list(task_ids or []) if str(item or "").strip()]
        if not clean_task_ids:
            raise ValueError("task_ids are required")
        with self._lock:
            worker = self._conn.execute(
                "SELECT worker_id FROM fleet_workers WHERE user_id = ? AND worker_id = ?",
                (int(user_id), str(worker_id or "").strip()),
            ).fetchone()
            if not worker:
                raise KeyError("Unknown worker")
            placeholders = ",".join("?" for _ in clean_task_ids)
            rows = self._conn.execute(
                f"""
                SELECT task_id, status FROM fleet_tasks
                WHERE user_id = ? AND worker_id = ? AND task_id IN ({placeholders})
                """,
                (int(user_id), worker["worker_id"], *clean_task_ids),
            ).fetchall()
            found = {str(row["task_id"]) for row in rows if str(row["status"]) == "queued"}
            missing = [task_id for task_id in clean_task_ids if task_id not in found]
            if missing:
                raise ValueError("Only queued tasks for this worker can be reordered")
            for position, task_id in enumerate(clean_task_ids, start=1):
                self._conn.execute(
                    "UPDATE fleet_tasks SET queue_position = ?, updated_at = ? WHERE task_id = ?",
                    (position, time.time(), task_id),
                )
            self._audit_locked(
                user_id=int(user_id),
                event_type="queue_reordered",
                target_kind="worker",
                target_id=worker["worker_id"],
                metadata={"task_ids": clean_task_ids},
            )
            self._conn.commit()
            return [
                self._task_view(row)
                for row in self._conn.execute(
                    """
                    SELECT * FROM fleet_tasks
                    WHERE user_id = ? AND worker_id = ? AND status = 'queued'
                    ORDER BY queue_position ASC, created_at ASC
                    """,
                    (int(user_id), worker["worker_id"]),
                ).fetchall()
            ]

    def redirect_worker_task(
        self,
        *,
        user_id: int,
        task_id: str,
        direction: str,
        source: str = "manager",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        direction_text = str(direction or "").strip()
        if not direction_text:
            raise ValueError("direction is required")
        with self._lock:
            task = self._conn.execute(
                "SELECT * FROM fleet_tasks WHERE user_id = ? AND task_id = ?",
                (int(user_id), str(task_id or "").strip()),
            ).fetchone()
            if not task:
                raise KeyError("Unknown task")
            if str(task["status"] or "") not in {"running", "paused", "blocked", "needs_review"}:
                raise ValueError("Only an active task can be redirected")
            existing = _json_loads(task["metadata"], {})
            redirects = list(existing.get("redirects") or [])
            redirects.append(
                {
                    "direction": direction_text,
                    "source": str(source or "manager")[:80],
                    "created_at": _utc_iso(time.time()),
                    "metadata": dict(metadata or {}),
                }
            )
            existing["redirects"] = redirects
            existing["latest_redirect"] = direction_text
            now = time.time()
            next_status = "running" if str(task["status"] or "") in {"blocked", "needs_review", "paused"} else str(task["status"] or "")
            self._conn.execute(
                "UPDATE fleet_tasks SET status = ?, metadata = ?, updated_at = ? WHERE task_id = ?",
                (next_status, _json_dumps(existing), now, task["task_id"]),
            )
            self._audit_locked(
                user_id=int(user_id),
                event_type="task_redirected",
                actor_kind=str(source or "manager")[:80],
                target_kind="task",
                target_id=task["task_id"],
                task_id=task["task_id"],
                metadata={"direction": direction_text},
            )
            self._conn.commit()
            return self._task_view(self._conn.execute("SELECT * FROM fleet_tasks WHERE task_id = ?", (task["task_id"],)).fetchone())

    def search_fleet_reports(
        self,
        *,
        user_id: int,
        query: Optional[str] = None,
        worker: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        with self._lock:
            worker_id: Optional[str] = None
            worker_selector = str(worker or "").strip()
            if worker_selector:
                resolved_worker = self._conn.execute(
                    """
                    SELECT worker_id FROM fleet_workers
                    WHERE user_id = ? AND (worker_id = ? OR lower(display_name) = lower(?))
                    """,
                    (int(user_id), worker_selector, worker_selector),
                ).fetchone()
                if not resolved_worker:
                    raise KeyError("Unknown worker")
                worker_id = str(resolved_worker["worker_id"])
            q = str(query or "").strip().casefold()
            status_filter = str(status or "").strip().casefold()
            reports: List[Dict[str, Any]] = []
            for row in self._conn.execute(
                "SELECT * FROM fleet_reports WHERE user_id = ? ORDER BY created_at DESC LIMIT 500",
                (int(user_id),),
            ).fetchall():
                view = self._report_view(row)
                if worker_id and str(view.get("worker_id") or "") != worker_id:
                    continue
                if status_filter and str(view.get("status") or "").casefold() != status_filter:
                    continue
                haystack = "\n".join(
                    [
                        str(view.get("summary") or ""),
                        str(view.get("next_suggested_action") or ""),
                        json.dumps(view.get("evidence") or [], ensure_ascii=False),
                        json.dumps(view.get("artifacts") or [], ensure_ascii=False),
                        json.dumps(view.get("blockers") or [], ensure_ascii=False),
                    ]
                ).casefold()
                if q and q not in haystack:
                    continue
                reports.append(view)
                if len(reports) >= max(1, min(200, int(limit or 20))):
                    break
            return {"reports": reports, "count": len(reports)}

    def complete_worker_task_report(
        self,
        *,
        user_id: int,
        task_id: str,
        status: str,
        summary: str,
        evidence: Optional[List[Any]] = None,
        artifacts: Optional[List[Any]] = None,
        blockers: Optional[List[Any]] = None,
        confidence: Optional[str] = None,
        next_suggested_action: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_report = normalize_worker_task_report(
            status=status,
            summary=summary,
            evidence=evidence,
            artifacts=artifacts,
            blockers=blockers,
            confidence=confidence,
            next_suggested_action=next_suggested_action,
            raw=raw,
        )
        with self._lock:
            task = self._conn.execute(
                "SELECT * FROM fleet_tasks WHERE user_id = ? AND task_id = ?",
                (int(user_id), str(task_id or "").strip()),
            ).fetchone()
            if not task:
                raise KeyError("Unknown task")
            if str(task["report_id"] or "").strip():
                raise ValueError("Worker task already has a completed report")
            now = time.time()
            report_id = f"rep_{secrets.token_hex(8)}"
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
                    task["worker_id"],
                    task["task_id"],
                    normalized_report.status,
                    normalized_report.summary,
                    _json_dumps(normalized_report.evidence),
                    _json_dumps(normalized_report.artifacts),
                    _json_dumps(normalized_report.blockers),
                    normalized_report.confidence,
                    normalized_report.next_suggested_action,
                    _json_dumps(normalized_report.raw),
                    now,
                ),
            )
            final_status = normalized_report.status
            task_metadata = _json_loads(task["metadata"], {})
            review_gate = {
                "report_id": report_id,
                "status": final_status,
                "confidence": normalized_report.confidence,
                "created_at": _utc_iso(now),
            }
            task_metadata["queue_review_required"] = review_gate
            self._conn.execute(
                "UPDATE fleet_tasks SET status = ?, report_id = ?, metadata = ?, updated_at = ?, completed_at = ? WHERE task_id = ?",
                (final_status, report_id, _json_dumps(task_metadata), now, now if final_status not in {"blocked", "needs_review"} else None, task["task_id"]),
            )
            worker_metadata = _json_loads(
                self._conn.execute("SELECT metadata FROM fleet_workers WHERE worker_id = ?", (task["worker_id"],)).fetchone()["metadata"],
                {},
            )
            from app_backend.fleet_queue_policy import (
                QUEUE_POLICY_AUTO_CONTINUE_SUCCESS,
                normalize_queue_policy,
                report_allows_auto_continue,
            )
            report_for_policy = {
                "status": final_status,
                "summary": normalized_report.summary,
                "evidence": normalized_report.evidence,
                "artifacts": normalized_report.artifacts,
                "blockers": normalized_report.blockers,
                "confidence": normalized_report.confidence,
            }
            auto_continue = (
                normalize_queue_policy(worker_metadata.get("queue_policy")) == QUEUE_POLICY_AUTO_CONTINUE_SUCCESS
                and report_allows_auto_continue(report_for_policy)
            )
            if auto_continue:
                worker_metadata.pop("queue_review_required", None)
                worker_metadata["last_auto_continued_report_id"] = report_id
            else:
                worker_metadata["queue_review_required"] = review_gate

            if final_status in {"blocked", "needs_review"}:
                self._conn.execute(
                    "UPDATE fleet_workers SET status = ?, active_task_id = ?, metadata = ?, updated_at = ?, last_seen_at = ? WHERE worker_id = ?",
                    (final_status, task["task_id"], _json_dumps(worker_metadata), now, now, task["worker_id"]),
                )
            else:
                self._conn.execute(
                    "UPDATE fleet_workers SET status = 'idle', active_task_id = NULL, metadata = ?, updated_at = ?, last_seen_at = ? WHERE worker_id = ?",
                    (_json_dumps(worker_metadata), now, now, task["worker_id"]),
                )
            self._audit_locked(
                user_id=int(user_id),
                event_type="worker_report_completed",
                target_kind="report",
                target_id=report_id,
                task_id=task["task_id"],
                metadata={"worker_id": task["worker_id"], "status": final_status},
            )
            self._conn.commit()
            return self._report_view(self._conn.execute("SELECT * FROM fleet_reports WHERE report_id = ?", (report_id,)).fetchone())
