from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Optional

from app_backend.fleet_identity_profiles import role_locked_tool_packs


def _field(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def session_belongs_to_fleet_identity(session: Any, identity: Mapping[str, Any]) -> bool:
    identity_id = str(identity.get("identity_id") or "").strip()
    identity_role = str(identity.get("role") or "").strip().lower()
    session_identity_id = str(_field(session, "fleet_identity_id") or "").strip()
    session_identity_role = str(_field(session, "fleet_identity_role") or "").strip().lower()
    session_worker_id = str(_field(session, "fleet_worker_id") or "").strip()
    identity_company_id = str(
        dict(identity.get("metadata") or {}).get("company_id") or ""
    ).strip()
    session_company_id = str(_field(session, "company_id") or "").strip()
    if (
        identity_company_id
        and session_company_id
        and identity_company_id != session_company_id
    ):
        return False

    if identity_role == "worker":
        if session_identity_id:
            return session_identity_id == identity_id
        return bool(identity.get("worker_id") and session_worker_id == str(identity.get("worker_id")))
    if identity_role == "manager":
        if session_identity_role == "worker" or session_worker_id:
            return False
        if session_identity_id == identity_id or session_identity_role == "manager":
            return True
        return not session_identity_id and not session_identity_role
    return bool(session_identity_id and session_identity_id == identity_id)


def session_id_for_fleet_identity(
    sessions: Sequence[Any],
    identity: Mapping[str, Any],
    selected_session_id: Optional[str] = None,
) -> Optional[str]:
    clean_selected_session_id = str(selected_session_id or "").strip()
    if clean_selected_session_id:
        selected = next(
            (item for item in sessions if str(_field(item, "id") or "").strip() == clean_selected_session_id),
            None,
        )
        if selected is not None and session_belongs_to_fleet_identity(selected, identity):
            return clean_selected_session_id
    fallback = next((item for item in sessions if session_belongs_to_fleet_identity(item, identity)), None)
    if fallback is None:
        return None
    return str(_field(fallback, "id") or "").strip() or None


def reconcile_local_manager_chat_selection(
    *,
    store: Any,
    user_id: int,
    desktop_id: str,
    snapshot: Mapping[str, Any],
    sessions: Sequence[Any],
    company_id: Optional[str] = None,
    include_legacy: bool = False,
    company_computer_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    clean_desktop_id = str(desktop_id or "").strip()
    manager = next(
        (
            identity
            for identity in list(snapshot.get("identities") or [])
            if str(identity.get("role") or "").strip().lower() == "manager"
            and str(identity.get("desktop_id") or "").strip() == clean_desktop_id
        ),
        None,
    )
    if not manager:
        return dict(snapshot)

    identity_id = str(manager.get("identity_id") or "").strip()
    selected_by_identity = dict(snapshot.get("selected_chat_by_identity") or {})
    selected_session_id = str(selected_by_identity.get(identity_id) or "").strip() or None
    resolved_session_id = session_id_for_fleet_identity(sessions, manager, selected_session_id)
    if resolved_session_id == selected_session_id:
        return dict(snapshot)

    company_kwargs: dict[str, Any] = {}
    clean_company_id = str(company_id or "").strip()
    if clean_company_id:
        company_kwargs = {
            "company_id": clean_company_id,
            "include_unscoped_company_records": include_legacy,
        }
    store.set_active_chat_for_fleet_identity(
        user_id=int(user_id),
        identity_id=identity_id,
        chat_id=resolved_session_id,
        source="local_session_reconciliation",
        desktop_id=clean_desktop_id,
        **company_kwargs,
    )
    snapshot_kwargs: dict[str, Any] = dict(company_kwargs)
    if company_computer_ids:
        snapshot_kwargs["company_computer_ids"] = list(company_computer_ids)
    return store.get_fleet_snapshot(
        user_id=int(user_id),
        desktop_id=clean_desktop_id,
        **snapshot_kwargs,
    )


def reconcile_local_identity_session_profiles(
    *,
    bridge: Any,
    snapshot: Mapping[str, Any],
    company_id: Optional[str] = None,
    include_legacy: bool = False,
) -> int:
    """Persist role authority onto legacy local chats without changing their conversation history."""
    identities = [item for item in list(snapshot.get("identities") or []) if isinstance(item, Mapping)]
    manager = next((item for item in identities if str(item.get("role") or "") == "manager"), None)
    changed = 0
    for session in bridge.list_sessions():
        session_company_id = str(_field(session, "company_id") or "").strip()
        clean_company_id = str(company_id or "").strip()
        if clean_company_id and session_company_id != clean_company_id:
            if not (include_legacy and not session_company_id):
                continue
        identity = next(
            (item for item in identities if session_belongs_to_fleet_identity(session, item)),
            None,
        )
        if identity is None:
            # Untagged sessions predate Fleet identities and belong to the
            # local manager. A session already bound to another identity must
            # not be silently promoted when its identity is outside this
            # desktop-scoped snapshot or has since been removed.
            has_existing_binding = any(
                str(_field(session, field) or "").strip()
                for field in ("fleet_identity_id", "fleet_identity_role", "fleet_worker_id")
            )
            if has_existing_binding:
                continue
            identity = manager
        if not identity:
            continue
        role = str(identity.get("role") or "").strip().lower()
        metadata = dict(identity.get("metadata") or {})
        desired_packs = role_locked_tool_packs(
            role=role,
            requested=list(getattr(session, "enabled_tool_packs", []) or []),
            identity_metadata=metadata,
        )
        desired = {
            "fleet_identity_id": str(identity.get("identity_id") or "").strip() or None,
            "fleet_identity_role": role or None,
            "fleet_worker_id": str(identity.get("worker_id") or "").strip() or None,
            "fleet_task_mode": getattr(session, "fleet_task_mode", None) or ("direct" if role == "worker" else None),
            "enabled_tool_packs": desired_packs,
            "company_id": clean_company_id or session_company_id or None,
        }
        if all(getattr(session, key, None) == value for key, value in desired.items()):
            continue
        for key, value in desired.items():
            setattr(session, key, value)
        bridge.session_manager.save_session(session)
        changed += 1
    return changed
