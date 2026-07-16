from __future__ import annotations

from shared.fleet_connection_policy import normalize_connection_permissions


class RemoteControlStoreFleetConnectionMixin:
    def _connection_permission_view(self, row) -> Dict[str, Any]:
        return {
            "desktop_id": str(row["desktop_id"]),
            "permissions": normalize_connection_permissions(_json_loads(row["permissions"], {})),
            "pending_request": _json_loads(row["pending_request"], None),
            "last_decision": _json_loads(row["last_decision"], None),
            "source": row["source"],
            "updated_at": _utc_iso(row["updated_at"]),
        }

    def record_connection_permission_state(
        self,
        *,
        user_id: int,
        desktop_id: str,
        policy: Dict[str, Any],
        source: str = "paired_desktop",
    ) -> Dict[str, Any]:
        clean_desktop_id = str(desktop_id or "").strip()
        if not clean_desktop_id:
            raise ValueError("desktop_id is required")
        with self._lock:
            desktop = self._conn.execute(
                "SELECT desktop_id FROM desktops WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), clean_desktop_id),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown paired desktop")
            permissions = normalize_connection_permissions(
                policy.get("permissions") if isinstance(policy.get("permissions"), dict) else None
            )
            pending = policy.get("pendingRequest") if isinstance(policy.get("pendingRequest"), dict) else None
            decision = policy.get("lastDecision") if isinstance(policy.get("lastDecision"), dict) else None
            now = time.time()
            self._conn.execute(
                """
                INSERT INTO fleet_connection_permissions(
                    user_id, desktop_id, permissions, pending_request, last_decision, source, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, desktop_id) DO UPDATE SET
                    permissions = excluded.permissions,
                    pending_request = excluded.pending_request,
                    last_decision = excluded.last_decision,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    int(user_id), clean_desktop_id, _json_dumps(permissions),
                    _json_dumps(pending) if pending else None,
                    _json_dumps(decision) if decision else None,
                    str(source or "paired_desktop")[:80], now,
                ),
            )
            if decision and str(decision.get("requestId") or ""):
                self._conn.execute(
                    "UPDATE fleet_permission_requests SET status = ?, decided_at = ? WHERE user_id = ? AND desktop_id = ? AND request_id = ?",
                    (
                        str(decision.get("status") or "denied"), now, int(user_id), clean_desktop_id,
                        str(decision.get("requestId") or ""),
                    ),
                )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM fleet_connection_permissions WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), clean_desktop_id),
            ).fetchone()
            return self._connection_permission_view(row)

    def connection_permission_state(self, *, user_id: int, desktop_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_connection_permissions WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), str(desktop_id or "").strip()),
            ).fetchone()
            if row:
                return self._connection_permission_view(row)
            return {
                "desktop_id": str(desktop_id or "").strip(),
                "permissions": normalize_connection_permissions(None),
                "pending_request": None,
                "last_decision": None,
                "source": "pairing_default",
                "updated_at": None,
            }

    def create_connection_permission_request(
        self,
        *,
        user_id: int,
        desktop_id: str,
        requested: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean_desktop_id = str(desktop_id or "").strip()
        with self._lock:
            desktop = self._conn.execute(
                "SELECT desktop_id FROM desktops WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), clean_desktop_id),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown paired desktop")
            request_id = f"fpr_{secrets.token_hex(8)}"
            normalized = normalize_connection_permissions(requested)
            now = time.time()
            self._conn.execute(
                """
                INSERT INTO fleet_permission_requests(
                    request_id, user_id, desktop_id, requested, reason, status, created_at, decided_at
                ) VALUES(?, ?, ?, ?, ?, 'pending', ?, NULL)
                """,
                (request_id, int(user_id), clean_desktop_id, _json_dumps(normalized), str(reason or "")[:1000] or None, now),
            )
            self._conn.commit()
            return {
                "request_id": request_id,
                "desktop_id": clean_desktop_id,
                "requested": normalized,
                "reason": str(reason or "")[:1000] or None,
                "status": "pending",
                "created_at": _utc_iso(now),
            }

    def create_computer_delegation(
        self,
        *,
        user_id: int,
        desktop_id: str,
        prompt: str,
        target_kind: str = "manager",
        target_selector: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_prompt = str(prompt or "").strip()
        clean_desktop_id = str(desktop_id or "").strip()
        clean_target_kind = str(target_kind or "manager").strip().lower()
        if not clean_prompt:
            raise ValueError("prompt is required")
        if clean_target_kind not in {"manager", "worker"}:
            raise ValueError("target_kind must be manager or worker")
        with self._lock:
            desktop = self._conn.execute(
                "SELECT desktop_id FROM desktops WHERE user_id = ? AND desktop_id = ?",
                (int(user_id), clean_desktop_id),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown paired desktop")
            delegation_id = f"fdg_{secrets.token_hex(8)}"
            now = time.time()
            self._conn.execute(
                """
                INSERT INTO fleet_delegations(
                    delegation_id, user_id, desktop_id, target_kind, target_selector, prompt,
                    status, report, metadata, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, 'queued', '{}', ?, ?, ?)
                """,
                (
                    delegation_id, int(user_id), clean_desktop_id, clean_target_kind,
                    str(target_selector or "").strip()[:160] or None, clean_prompt,
                    _json_dumps(metadata or {}), now, now,
                ),
            )
            self._conn.commit()
            return self.get_computer_delegation(user_id=int(user_id), delegation_id=delegation_id)

    def _delegation_view(self, row) -> Dict[str, Any]:
        return {
            "delegation_id": row["delegation_id"],
            "desktop_id": row["desktop_id"],
            "target_kind": row["target_kind"],
            "target_selector": row["target_selector"],
            "prompt": row["prompt"],
            "status": row["status"],
            "report": _json_loads(row["report"], {}),
            "metadata": _json_loads(row["metadata"], {}),
            "created_at": _utc_iso(row["created_at"]),
            "updated_at": _utc_iso(row["updated_at"]),
            "started_at": _utc_iso(row["started_at"]),
            "completed_at": _utc_iso(row["completed_at"]),
            "canceled_at": _utc_iso(row["canceled_at"]),
        }

    def get_computer_delegation(self, *, user_id: int, delegation_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_delegations WHERE user_id = ? AND delegation_id = ?",
                (int(user_id), str(delegation_id or "").strip()),
            ).fetchone()
            if not row:
                raise KeyError("Unknown computer delegation")
            return self._delegation_view(row)

    def update_computer_delegation(
        self,
        *,
        user_id: int,
        delegation_id: str,
        status: str,
        report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_status = str(status or "").strip().lower()
        if clean_status not in {"queued", "running", "needs_review", "completed", "failed", "stopped", "canceled"}:
            raise ValueError("Unsupported delegation status")
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fleet_delegations WHERE user_id = ? AND delegation_id = ?",
                (int(user_id), str(delegation_id or "").strip()),
            ).fetchone()
            if not row:
                raise KeyError("Unknown computer delegation")
            now = time.time()
            started_at = float(row["started_at"] or 0) or (now if clean_status == "running" else None)
            completed_at = now if clean_status in {"needs_review", "completed", "failed", "stopped", "canceled"} else row["completed_at"]
            canceled_at = now if clean_status == "canceled" else row["canceled_at"]
            self._conn.execute(
                """
                UPDATE fleet_delegations
                SET status = ?, report = ?, updated_at = ?, started_at = ?, completed_at = ?, canceled_at = ?
                WHERE user_id = ? AND delegation_id = ?
                """,
                (
                    clean_status,
                    _json_dumps(report) if report is not None else row["report"],
                    now, started_at, completed_at, canceled_at,
                    int(user_id), str(delegation_id or "").strip(),
                ),
            )
            self._conn.commit()
            return self.get_computer_delegation(user_id=int(user_id), delegation_id=str(delegation_id or ""))

    def list_computer_delegations(self, *, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fleet_delegations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (int(user_id), max(1, min(500, int(limit or 100)))),
            ).fetchall()
            return [self._delegation_view(row) for row in rows]

    @staticmethod
    def is_legacy_connection_worker(worker: Dict[str, Any]) -> bool:
        metadata = worker.get("metadata") if isinstance(worker.get("metadata"), dict) else {}
        return bool(
            str(worker.get("kind") or "") == "remote"
            and str(metadata.get("transport") or "") == "yggdrasil"
            and str(metadata.get("source") or "") == "standalone_yggdrasil_pairing"
        )
