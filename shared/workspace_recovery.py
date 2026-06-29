from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.cloud_object_store import CloudObjectStore
from shared.runtime_paths import user_state_root


_FILE_ACCESS_RE = re.compile(
    r"\b(read|open|inspect|summari[sz]e|write|save|create|edit|update|modify|append|delete|rename|move|copy|generate)\b"
    r".{0,80}\b(file|folder|directory|workspace|repo|project|document|artifact|path)\b",
    re.IGNORECASE,
)


@dataclass
class WorkspacePreflightResult:
    ok: bool = True
    action: str = "allowed"
    workspace_id: Optional[str] = None
    restored_path: Optional[str] = None
    restored_files: List[Dict[str, Any]] = field(default_factory=list)
    missing_original_files: List[Dict[str, Any]] = field(default_factory=list)
    conflict_count: int = 0
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "workspace_id": self.workspace_id,
            "restored_path": self.restored_path,
            "restored_files": list(self.restored_files),
            "missing_original_files": list(self.missing_original_files),
            "conflict_count": self.conflict_count,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


def task_likely_needs_workspace_access(text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
    meta = dict(metadata or {})
    if meta.get("requires_workspace_access") or meta.get("requires_workspace_write") or meta.get("file_write_required"):
        return True
    if meta.get("workspace_read_required") or meta.get("file_read_required"):
        return True
    return bool(_FILE_ACCESS_RE.search(str(text or "")))


def managed_workspace_path(*, user_id: int, workspace_id: Optional[str]) -> Path:
    workspace_label = re.sub(r"[^A-Za-z0-9._-]+", "-", str(workspace_id or "workspace").strip()).strip("-") or "workspace"
    return (user_state_root(int(user_id)) / "managed_workspaces" / workspace_label).resolve()


def restore_cloud_workspace_files(
    *,
    user_id: int,
    workspace_id: Optional[str],
    target_dir: Optional[Path] = None,
) -> WorkspacePreflightResult:
    target = Path(target_dir).expanduser().resolve() if target_dir else managed_workspace_path(user_id=user_id, workspace_id=workspace_id)
    store = CloudObjectStore(user_id=int(user_id))
    restored: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    conflicts = 0
    for item in store.list_objects():
        metadata = dict(item.get("metadata") or {})
        item_workspace_id = str(metadata.get("workspace_id") or "").strip()
        legacy_workspace = str(metadata.get("workspace") or "").strip()
        if workspace_id and item_workspace_id and item_workspace_id != str(workspace_id):
            continue
        if workspace_id and not item_workspace_id and legacy_workspace and legacy_workspace != str(workspace_id):
            continue
        object_key = str(item.get("object_key") or "").strip()
        if not object_key:
            continue
        file_name = str(item.get("file_name") or metadata.get("title") or "artifact")
        relative_path = str(metadata.get("file_path") or metadata.get("path") or file_name)
        try:
            result = store.restore_object_to_relative_path(
                object_key=object_key,
                target_dir=target,
                relative_path=relative_path,
                fallback_file_name=file_name,
                preserve_conflicts=True,
            )
            if result.get("conflict_preserved"):
                conflicts += 1
            restored.append(result)
        except FileNotFoundError:
            missing.append({"object_key": object_key, "reason": "cloud_object_missing"})
        except Exception as exc:
            missing.append({"object_key": object_key, "reason": str(exc)})
    return WorkspacePreflightResult(
        ok=bool(restored),
        action="restored" if restored else "no_cloud_files",
        workspace_id=workspace_id,
        restored_path=str(target),
        restored_files=restored,
        missing_original_files=missing,
        conflict_count=conflicts,
        message=(
            f"Restored {len(restored)} cloud-saved workspace file{'s' if len(restored) != 1 else ''}."
            if restored
            else "No cloud-saved generated or evidence files are available for this workspace."
        ),
    )


def ensure_session_workspace_ready_for_task(
    session: Any,
    *,
    user_id: int,
    user_message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> WorkspacePreflightResult:
    if not task_likely_needs_workspace_access(user_message, metadata):
        return WorkspacePreflightResult(ok=True, action="pure_chat_allowed", message="No workspace access needed.")

    workspace = str(getattr(session, "workspace", "") or "").strip()
    workspace_id = str(getattr(session, "workspace_id", "") or "").strip() or None
    binding_status = str(getattr(session, "workspace_binding_status", "") or "").strip().lower()
    if workspace:
        try:
            path = Path(workspace).expanduser()
            if path.exists() and path.is_dir() and binding_status not in {"missing", "needs_reconnect", "read_only", "suspicious"}:
                return WorkspacePreflightResult(ok=True, action="active_binding", workspace_id=workspace_id, message="Workspace is available.")
        except Exception:
            pass

    restored = restore_cloud_workspace_files(user_id=int(user_id), workspace_id=workspace_id)
    if restored.restored_files:
        setattr(session, "workspace", str(restored.restored_path))
        setattr(session, "workspace_binding_status", "active")
        if workspace_id:
            setattr(session, "workspace_id", workspace_id)
        return restored

    return WorkspacePreflightResult(
        ok=False,
        action="missing_original_files",
        workspace_id=workspace_id,
        restored_path=restored.restored_path,
        missing_original_files=[
            {
                "reason": "no_cloud_copy_for_required_workspace",
                "workspace": workspace,
                "workspace_id": workspace_id,
            }
        ],
        message=(
            "This task appears to need local workspace files, but this machine does not have the folder and "
            "there is no cloud-saved generated/evidence copy to restore. Reconnect the original folder or upload the needed files."
        ),
    )
