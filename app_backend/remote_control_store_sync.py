from __future__ import annotations

from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreSyncMixin:
    def list_desktops(self, *, user_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM desktops WHERE user_id = ? ORDER BY COALESCE(last_seen_at, 0) DESC, COALESCE(display_name, '') DESC",
                (int(user_id),),
            ).fetchall()
            return [self._desktop_view(row) for row in rows]

    def get_shared_state(self, *, user_id: int) -> Dict[str, Any]:
        with self._lock:
            state = self._ensure_shared_state_locked(int(user_id))
            return json.loads(json.dumps(state))

    def get_sidebar_state(self, *, user_id: int) -> Dict[str, Any]:
        state = self.get_shared_state(user_id=user_id)
        sidebar_state = state.get("sidebar_state")
        return json.loads(json.dumps(sidebar_state if isinstance(sidebar_state, dict) else _empty_sidebar_state()))

    def update_sidebar_state(self, *, user_id: int, sidebar_state: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            state = self._ensure_shared_state_locked(int(user_id))
            state["sidebar_state"] = dict(sidebar_state or _empty_sidebar_state())
            next_state = self._bump_shared_state_locked(int(user_id), state)
            self._conn.commit()
            self._secure_db_files()
            return next_state

    def mark_desktop_connection(
        self,
        *,
        user_id: int,
        desktop_id: str,
        status: str,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            desktop = self._conn.execute(
                "SELECT * FROM desktops WHERE desktop_id = ? AND user_id = ?",
                (desktop_id, int(user_id)),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown desktop")
            now = time.time()
            status_value = str(status or "offline").strip().lower() or "offline"
            heartbeat_at = now if status_value == "connected" else desktop["last_heartbeat_at"]
            self._conn.execute(
                "UPDATE desktops SET status = ?, detail = ?, last_seen_at = ?, last_heartbeat_at = ? WHERE desktop_id = ?",
                (status_value, detail, now, heartbeat_at, desktop_id),
            )
            if status_value == "connected":
                self._conn.execute(
                    """
                    UPDATE fleet_workers
                    SET last_seen_at = ?,
                        status = CASE WHEN status IN ('offline', 'stale') THEN 'idle' ELSE status END,
                        updated_at = ?
                    WHERE user_id = ? AND machine_desktop_id = ?
                    """,
                    (now, now, int(user_id), desktop_id),
                )
            state = self._ensure_shared_state_locked(user_id)
            current_desktop_id = str(state.get("current_desktop_id") or "").strip()
            should_update_shared_presence = (
                status_value == "connected"
                or not current_desktop_id
                or current_desktop_id == desktop_id
            )
            if should_update_shared_presence:
                state["current_desktop_id"] = desktop_id
                state["desktop_connection"] = {
                    "status": status_value,
                    "desktop_id": desktop_id,
                    "desktop_name": desktop["display_name"],
                    "last_heartbeat_at": _utc_iso(heartbeat_at),
                    "detail": detail,
                }
                self._bump_shared_state_locked(user_id, state)
            self._conn.commit()
            self._secure_db_files()
            desktop = self._conn.execute("SELECT * FROM desktops WHERE desktop_id = ?", (desktop_id,)).fetchone()
            return self._desktop_view(desktop)

    def heartbeat_desktop(self, *, user_id: int, desktop_id: str, detail: Optional[str] = None) -> Dict[str, Any]:
        return self.mark_desktop_connection(user_id=user_id, desktop_id=desktop_id, status="connected", detail=detail)

    def update_shared_snapshot(
        self,
        *,
        user_id: int,
        desktop_id: str,
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._lock:
            desktop = self._conn.execute(
                "SELECT * FROM desktops WHERE desktop_id = ? AND user_id = ?",
                (desktop_id, int(user_id)),
            ).fetchone()
            if not desktop:
                raise KeyError("Unknown desktop")
            now = time.time()
            identity_row = self._conn.execute(
                """
                SELECT * FROM fleet_instances
                WHERE user_id = ? AND desktop_id = ? AND role = 'worker' AND reset_at IS NULL
                ORDER BY created_at ASC LIMIT 1
                """,
                (int(user_id), desktop_id),
            ).fetchone()
            if identity_row:
                default_identity = self._identity_view(identity_row)
            else:
                default_identity = self._ensure_manager_instance_locked(
                    user_id=int(user_id),
                    desktop_id=desktop_id,
                    display_name=snapshot.get("desktop_name") or desktop["display_name"],
                )
            default_identity_id = str(default_identity.get("identity_id") or default_identity.get("instance_id") or "")
            default_identity_role = str(default_identity.get("role") or "manager")
            default_worker_id = default_identity.get("worker_id") if default_identity_role == "worker" else None
            sessions = list(snapshot.get("sessions") or [])
            session_details = dict(snapshot.get("session_details") or {})
            jobs = list(snapshot.get("jobs") or [])
            current_session_id = str(snapshot.get("current_session_id") or "").strip() or None
            current_model = snapshot.get("current_model")
            current_variant = snapshot.get("current_variant")
            normalized_sessions: List[Dict[str, Any]] = []
            for raw_session in sessions:
                item = dict(raw_session or {})
                item.setdefault("fleet_identity_id", default_identity_id)
                item.setdefault("fleet_identity_role", default_identity_role)
                item.setdefault("fleet_worker_id", default_worker_id)
                normalized_sessions.append(item)
            normalized_details: Dict[str, Any] = {}
            for key, raw_detail in session_details.items():
                detail = dict(raw_detail or {})
                detail.setdefault("fleet_identity_id", default_identity_id)
                detail.setdefault("fleet_identity_role", default_identity_role)
                detail.setdefault("fleet_worker_id", default_worker_id)
                normalized_details[str(key)] = detail

            state = self._ensure_shared_state_locked(user_id)
            state["current_desktop_id"] = desktop_id
            state["current_session_id"] = current_session_id
            state["current_model"] = current_model
            state["current_variant"] = current_variant
            state["sessions"] = normalized_sessions
            state["session_details"] = normalized_details
            state["jobs"] = jobs
            state["project_groups"] = list(snapshot.get("project_groups") or _project_groups_from_sessions(normalized_sessions))
            if isinstance(snapshot.get("sidebar_state"), dict):
                state["sidebar_state"] = dict(snapshot.get("sidebar_state") or {})
            existing_fleet_state = _normalize_fleet_state(state.get("fleet"))
            seed_identity_id = default_identity_id if not existing_fleet_state.get("active_identity_id") else None
            fleet_state = self._ensure_fleet_selection_locked(user_id=int(user_id), state=state, preferred_identity_id=seed_identity_id)
            if current_session_id and str(fleet_state.get("active_identity_id") or "") == default_identity_id:
                selected_by_identity = dict(fleet_state.get("selected_chat_by_identity") or {})
                raw_current_detail = session_details.get(current_session_id)
                raw_current_identity_id = ""
                if isinstance(raw_current_detail, dict):
                    raw_current_identity_id = str(raw_current_detail.get("fleet_identity_id") or "").strip()
                existing_selected_chat_id = str(selected_by_identity.get(default_identity_id) or "").strip()
                if raw_current_identity_id == default_identity_id or not existing_selected_chat_id:
                    selected_by_identity[default_identity_id] = current_session_id
                    fleet_state["selected_chat_by_identity"] = selected_by_identity
                    state["fleet"] = fleet_state
            state["desktop_connection"] = {
                "status": "connected",
                "desktop_id": desktop_id,
                "desktop_name": snapshot.get("desktop_name") or desktop["display_name"],
                "last_heartbeat_at": _utc_iso(now),
                "detail": snapshot.get("desktop_status_detail"),
            }
            self._conn.execute(
                "UPDATE desktops SET status = ?, detail = ?, last_seen_at = ?, last_heartbeat_at = ? WHERE desktop_id = ?",
                ("connected", snapshot.get("desktop_status_detail"), now, now, desktop_id),
            )
            next_state = self._bump_shared_state_locked(user_id, state)
            self._conn.commit()
            self._secure_db_files()
            return next_state
