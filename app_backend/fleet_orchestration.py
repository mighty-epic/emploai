from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, Optional


WorkspaceResolver = Callable[[str], Optional[str]]


def fleet_selected_chat_for_worker(snapshot: Dict[str, Any], worker: Dict[str, Any]) -> Optional[str]:
    selected_by_identity = snapshot.get("selected_chat_by_identity")
    if not isinstance(selected_by_identity, dict):
        return None

    worker_id = str(worker.get("worker_id") or "").strip()
    candidate_identity_ids: list[str] = []
    instance_id = str(worker.get("instance_id") or "").strip()
    if instance_id:
        candidate_identity_ids.append(instance_id)

    for identity in list(snapshot.get("identities") or []):
        if not isinstance(identity, dict):
            continue
        if worker_id and str(identity.get("worker_id") or "").strip() == worker_id:
            identity_id = str(identity.get("identity_id") or "").strip()
            if identity_id:
                candidate_identity_ids.append(identity_id)

    for identity_id in dict.fromkeys(candidate_identity_ids):
        selected_chat_id = str(selected_by_identity.get(identity_id) or "").strip()
        if selected_chat_id:
            return selected_chat_id
    return None


def fleet_task_target_session_id(
    *,
    snapshot: Dict[str, Any],
    worker: Dict[str, Any],
    target_session_id: Optional[str] = None,
    target_mode: Optional[str] = "auto",
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    metadata_value = dict(metadata or {})
    explicit_session_id = str(target_session_id or metadata_value.get("target_session_id") or "").strip()
    if explicit_session_id:
        return explicit_session_id

    clean_target_mode = str(target_mode or "auto").strip().lower()
    if clean_target_mode not in {"", "auto"}:
        return None
    return fleet_selected_chat_for_worker(snapshot, worker)


def task_requires_workspace_write(prompt: str, metadata: Dict[str, Any], explicit: bool = False) -> bool:
    if explicit:
        return True
    if bool(metadata.get("requires_workspace_write") or metadata.get("file_write_required")):
        return True
    lowered = str(prompt or "").lower()
    return bool(
        re.search(
            r"\b(write|save|create|edit|update|modify|append|delete|rename|move|copy|generate)\b.*\b(file|folder|directory|workspace|repo|project|document|artifact)\b",
            lowered,
        )
    )


def workspace_id_for_task(
    *,
    workspace_id: Optional[str] = None,
    target_session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    resolve_workspace_id_for_session: Optional[WorkspaceResolver] = None,
) -> Optional[str]:
    metadata_value = dict(metadata or {})
    clean_workspace_id = str(workspace_id or metadata_value.get("workspace_id") or "").strip()
    if clean_workspace_id:
        return clean_workspace_id
    clean_target_session_id = str(target_session_id or metadata_value.get("target_session_id") or "").strip()
    if not clean_target_session_id or resolve_workspace_id_for_session is None:
        return None
    try:
        return str(resolve_workspace_id_for_session(clean_target_session_id) or "").strip() or None
    except Exception:
        return None


def workspace_binding_blocker_for_task(
    *,
    worker: Dict[str, Any],
    prompt: str,
    metadata: Optional[Dict[str, Any]] = None,
    requires_workspace_write: bool = False,
    workspace_id: Optional[str] = None,
    target_session_id: Optional[str] = None,
    workspace_bindings: Iterable[Dict[str, Any]] = (),
    resolve_workspace_id_for_session: Optional[WorkspaceResolver] = None,
) -> Optional[Dict[str, Any]]:
    metadata_value = dict(metadata or {})
    if not task_requires_workspace_write(prompt, metadata_value, bool(requires_workspace_write)):
        return None

    resolved_workspace_id = workspace_id_for_task(
        workspace_id=workspace_id,
        target_session_id=target_session_id,
        metadata=metadata_value,
        resolve_workspace_id_for_session=resolve_workspace_id_for_session,
    )
    if not resolved_workspace_id:
        return {
            "reason": "workspace_id_missing",
            "message": "This task appears to need workspace file-writing, but no workspace identity was attached.",
        }

    machine_id = str(worker.get("machine_desktop_id") or worker.get("desktop_id") or "").strip()
    candidates = [
        binding
        for binding in list(workspace_bindings or [])
        if str(binding.get("workspace_id") or "") == resolved_workspace_id
        and (not machine_id or str(binding.get("machine_id") or "") == machine_id)
    ]
    active = [
        binding for binding in candidates
        if str(binding.get("status") or "").strip().lower() == "active"
    ]
    if active:
        return None
    return {
        "reason": "workspace_binding_missing_or_inactive",
        "message": "Workspace files must be reconnected before this worker can run file-writing work.",
        "workspace_id": resolved_workspace_id,
        "machine_id": machine_id or None,
        "bindings": candidates,
    }
