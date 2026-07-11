from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    return WorkspacePreflightResult(
        ok=False,
        action="missing_original_files",
        workspace_id=workspace_id,
        missing_original_files=[
            {
                "reason": "local_workspace_unavailable",
                "workspace": workspace,
                "workspace_id": workspace_id,
            }
        ],
        message="This task needs local workspace files, but the folder is unavailable. Reconnect the original folder or upload the needed files.",
    )
