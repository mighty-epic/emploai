from __future__ import annotations

from typing import Any, Dict


_COMPANY_METADATA_TABLES = (
    ("fleet_instances", "instance_id"),
    ("fleet_workers", "worker_id"),
    ("fleet_groups", "group_id"),
    ("fleet_enrollments", "enrollment_id"),
    ("fleet_delegations", "delegation_id"),
    ("fleet_tasks", "task_id"),
    ("fleet_workspace_bindings", "binding_id"),
    ("fleet_locks", "lock_id"),
    ("fleet_audit_events", "event_id"),
    ("automations", "automation_id"),
    ("automation_events", "event_id"),
    ("automation_event_runs", "event_run_id"),
    ("process_waits", "process_wait_id"),
    ("recovery_archive", "archive_id"),
)


class RemoteControlStoreCompanyMigrationMixin:
    """Explicitly bind legacy single-context records to one Company."""

    def preview_unscoped_company_records(
        self,
        *,
        user_id: int,
    ) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        with self._lock:
            for table, _identifier in _COMPANY_METADATA_TABLES:
                rows = self._conn.execute(
                    f"SELECT metadata FROM {table} WHERE user_id = ?",
                    (int(user_id),),
                ).fetchall()
                counts[table] = sum(
                    1
                    for row in rows
                    if not str(
                        _json_loads(row["metadata"], {}).get("company_id")
                        or ""
                    ).strip()
                )
        return {
            "unscoped_total": sum(counts.values()),
            "by_table": counts,
        }

    def migrate_unscoped_company_records(
        self,
        *,
        user_id: int,
        company_id: str,
    ) -> Dict[str, Any]:
        clean_company_id = str(company_id or "").strip()
        if not clean_company_id:
            raise ValueError("A company ID is required for Fleet migration.")
        counts: Dict[str, int] = {}
        now = time.time()
        with self._lock, self._conn:
            for table, identifier in _COMPANY_METADATA_TABLES:
                rows = self._conn.execute(
                    f"SELECT {identifier}, metadata FROM {table} WHERE user_id = ?",
                    (int(user_id),),
                ).fetchall()
                migrated = 0
                for row in rows:
                    metadata = _json_loads(row["metadata"], {})
                    if str(metadata.get("company_id") or "").strip():
                        continue
                    metadata["company_id"] = clean_company_id
                    metadata["company_migrated_at"] = now
                    self._conn.execute(
                        f"UPDATE {table} SET metadata = ? WHERE {identifier} = ?",
                        (_json_dumps(metadata), row[identifier]),
                    )
                    migrated += 1
                counts[table] = migrated
            self._audit_locked(
                user_id=int(user_id),
                event_type="legacy_company_records_migrated",
                actor_kind="desktop",
                actor_id=None,
                target_kind="company",
                target_id=clean_company_id,
                metadata={
                    "company_id": clean_company_id,
                    "counts": counts,
                },
            )
        return {
            "company_id": clean_company_id,
            "migrated_total": sum(counts.values()),
            "by_table": counts,
        }

    def delete_company_records(
        self,
        *,
        user_id: int,
        company_id: str,
    ) -> Dict[str, Any]:
        """Remove only one deleted Company's local Fleet/runtime records."""

        clean_company_id = str(company_id or "").strip()
        if not clean_company_id:
            raise ValueError("A company ID is required for Fleet cleanup.")

        def scoped_ids(table: str, identifier: str) -> set[str]:
            rows = self._conn.execute(
                f"SELECT {identifier}, metadata FROM {table} WHERE user_id = ?",
                (int(user_id),),
            ).fetchall()
            return {
                str(row[identifier])
                for row in rows
                if str(
                    _json_loads(row["metadata"], {}).get("company_id") or ""
                ).strip()
                == clean_company_id
            }

        def delete_ids(
            table: str,
            identifier: str,
            values: set[str],
        ) -> int:
            if not values:
                return 0
            placeholders = ",".join("?" for _ in values)
            cursor = self._conn.execute(
                f"DELETE FROM {table} "
                f"WHERE user_id = ? AND {identifier} IN ({placeholders})",
                (int(user_id), *sorted(values)),
            )
            return int(cursor.rowcount or 0)

        counts: Dict[str, int] = {}
        with self._lock, self._conn:
            instance_ids = scoped_ids("fleet_instances", "instance_id")
            worker_ids = scoped_ids("fleet_workers", "worker_id")
            if instance_ids:
                placeholders = ",".join("?" for _ in instance_ids)
                rows = self._conn.execute(
                    "SELECT worker_id FROM fleet_instances "
                    f"WHERE user_id = ? AND instance_id IN ({placeholders})",
                    (int(user_id), *sorted(instance_ids)),
                ).fetchall()
                worker_ids.update(
                    str(row["worker_id"])
                    for row in rows
                    if str(row["worker_id"] or "").strip()
                )

            task_ids = scoped_ids("fleet_tasks", "task_id")
            if worker_ids:
                placeholders = ",".join("?" for _ in worker_ids)
                task_ids.update(
                    str(row["task_id"])
                    for row in self._conn.execute(
                        "SELECT task_id FROM fleet_tasks "
                        f"WHERE user_id = ? AND worker_id IN ({placeholders})",
                        (int(user_id), *sorted(worker_ids)),
                    ).fetchall()
                )
            automation_ids = scoped_ids("automations", "automation_id")
            event_ids = scoped_ids("automation_events", "event_id")
            if automation_ids:
                placeholders = ",".join("?" for _ in automation_ids)
                event_ids.update(
                    str(row["event_id"])
                    for row in self._conn.execute(
                        "SELECT event_id FROM automation_events "
                        f"WHERE user_id = ? AND automation_id IN ({placeholders})",
                        (int(user_id), *sorted(automation_ids)),
                    ).fetchall()
                )
            event_run_ids = scoped_ids(
                "automation_event_runs",
                "event_run_id",
            )
            if automation_ids or event_ids:
                clauses = []
                params: list[Any] = [int(user_id)]
                if automation_ids:
                    clauses.append(
                        "automation_id IN ("
                        + ",".join("?" for _ in automation_ids)
                        + ")"
                    )
                    params.extend(sorted(automation_ids))
                if event_ids:
                    clauses.append(
                        "event_id IN ("
                        + ",".join("?" for _ in event_ids)
                        + ")"
                    )
                    params.extend(sorted(event_ids))
                event_run_ids.update(
                    str(row["event_run_id"])
                    for row in self._conn.execute(
                        "SELECT event_run_id FROM automation_event_runs "
                        "WHERE user_id = ? AND (" + " OR ".join(clauses) + ")",
                        tuple(params),
                    ).fetchall()
                )

            if worker_ids or task_ids:
                clauses = []
                params = [int(user_id)]
                if worker_ids:
                    clauses.append(
                        "worker_id IN ("
                        + ",".join("?" for _ in worker_ids)
                        + ")"
                    )
                    params.extend(sorted(worker_ids))
                if task_ids:
                    clauses.append(
                        "task_id IN ("
                        + ",".join("?" for _ in task_ids)
                        + ")"
                    )
                    params.extend(sorted(task_ids))
                cursor = self._conn.execute(
                    "DELETE FROM fleet_reports WHERE user_id = ? AND ("
                    + " OR ".join(clauses)
                    + ")",
                    tuple(params),
                )
                counts["fleet_reports"] = int(cursor.rowcount or 0)

            related_identity_ids = set(instance_ids)
            if related_identity_ids or task_ids:
                clauses = []
                params = [int(user_id)]
                if related_identity_ids:
                    clauses.append(
                        "identity_id IN ("
                        + ",".join("?" for _ in related_identity_ids)
                        + ")"
                    )
                    params.extend(sorted(related_identity_ids))
                if task_ids:
                    clauses.append(
                        "task_id IN ("
                        + ",".join("?" for _ in task_ids)
                        + ")"
                    )
                    params.extend(sorted(task_ids))
                cursor = self._conn.execute(
                    "DELETE FROM fleet_upstream_requests "
                    "WHERE user_id = ? AND (" + " OR ".join(clauses) + ")",
                    tuple(params),
                )
                counts["fleet_upstream_requests"] = int(
                    cursor.rowcount or 0
                )

            related_targets = related_identity_ids | worker_ids
            if related_targets or task_ids:
                clauses = []
                params = [int(user_id)]
                if related_targets:
                    clauses.append(
                        "target_id IN ("
                        + ",".join("?" for _ in related_targets)
                        + ")"
                    )
                    params.extend(sorted(related_targets))
                if task_ids:
                    clauses.append(
                        "task_id IN ("
                        + ",".join("?" for _ in task_ids)
                        + ")"
                    )
                    params.extend(sorted(task_ids))
                cursor = self._conn.execute(
                    "DELETE FROM fleet_tool_grants WHERE user_id = ? AND ("
                    + " OR ".join(clauses)
                    + ")",
                    tuple(params),
                )
                counts["fleet_tool_grants"] = int(cursor.rowcount or 0)

            for table, identifier in _COMPANY_METADATA_TABLES:
                if table == "fleet_tasks":
                    values = task_ids
                elif table == "fleet_workers":
                    values = worker_ids
                elif table == "fleet_instances":
                    values = instance_ids
                elif table == "automations":
                    values = automation_ids
                elif table == "automation_events":
                    values = event_ids
                elif table == "automation_event_runs":
                    values = event_run_ids
                else:
                    values = scoped_ids(table, identifier)
                counts[table] = delete_ids(
                    table,
                    identifier,
                    values,
                )

            confirmation_rows = self._conn.execute(
                "SELECT confirmation_id, payload FROM pending_confirmations "
                "WHERE user_id = ?",
                (int(user_id),),
            ).fetchall()
            confirmation_ids = {
                str(row["confirmation_id"])
                for row in confirmation_rows
                if str(
                    _json_loads(row["payload"], {}).get("company_id") or ""
                ).strip()
                == clean_company_id
            }
            counts["pending_confirmations"] = delete_ids(
                "pending_confirmations",
                "confirmation_id",
                confirmation_ids,
            )

            state = self._ensure_shared_state_locked(int(user_id))
            fleet = _normalize_fleet_state(state.get("fleet"))
            by_company = {
                desktop_id: {
                    stored_company_id: selection
                    for stored_company_id, selection in dict(
                        company_selections
                    ).items()
                    if stored_company_id != clean_company_id
                }
                for desktop_id, company_selections in dict(
                    fleet.get("selection_by_company") or {}
                ).items()
            }
            fleet["selection_by_company"] = {
                desktop_id: company_selections
                for desktop_id, company_selections in by_company.items()
                if company_selections
            }
            state["fleet"] = fleet
            self._bump_shared_state_locked(int(user_id), state)

        return {
            "company_id": clean_company_id,
            "deleted_total": sum(counts.values()),
            "by_table": counts,
        }
