"""Session Manager - handles CRUD operations for chat sessions."""

import hashlib
import json
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.models.session import Session, SessionSummary
from shared.atomic_io import atomic_write_json
from shared.runtime_paths import shared_state_root


_SESSION_IO_LOCK = threading.RLock()


def _stable_workspace_id(workspace: Optional[Path], explicit: Optional[str] = None) -> Optional[str]:
    clean = str(explicit or "").strip()
    if clean:
        return clean[:256]
    if not workspace:
        return None
    try:
        value = str(Path(workspace).expanduser().resolve()).casefold()
    except Exception:
        value = str(workspace).strip().casefold()
    if not value:
        return None
    return f"wsp_{hashlib.sha256(value.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _workspace_binding_status(workspace: Optional[Path], explicit: Optional[str] = None) -> Optional[str]:
    clean = str(explicit or "").strip().lower()
    if clean:
        return clean[:80]
    if not workspace:
        return None
    try:
        return "active" if Path(workspace).expanduser().exists() else "needs_reconnect"
    except Exception:
        return "needs_reconnect"


class SessionManager:
    """Manages chat sessions - save, load, switch, delete."""
    
    def __init__(self, base_path: Optional[Path] = None):
        """Initialize session manager.
        
        Args:
            base_path: Base path for storing sessions. Defaults to ~/.agentshell
        """
        self.base_path = base_path or shared_state_root()
        self.sessions_dir = self.base_path / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: Optional[Session] = None
    
    def create_session(
        self, 
        name: Optional[str] = None, 
        workspace: Optional[Path] = None,
        model: str = "claude-haiku-4.5",
        variant: str = "standard",
        agent_mode: str = "auto",
        planner_model: Optional[str] = None,
        enabled_tool_packs: Optional[List[str]] = None,
        security_permission_mode: str = "standard",
        telegram_bot_config_id: Optional[str] = None,
        headless_eligible: bool = False,
        workspace_id: Optional[str] = None,
        workspace_binding_status: Optional[str] = None,
    ) -> Session:
        """Create a new session.
        
        Args:
            name: Session name. Auto-generated if not provided.
            workspace: Workspace path. Defaults to cwd.
            model: Model to use.
            variant: Model variant.
            agent_mode: Agent mode setting.
            planner_model: Dedicated planner model override.
            
        Returns:
            The created Session object.
        """
        session_id = str(uuid.uuid4())[:8]
        
        if not name:
            name = f"Session {datetime.now().strftime('%H:%M')}"
        
        now = datetime.now().isoformat()
        
        session = Session(
            id=session_id,
            name=name,
            workspace=str(workspace or Path.cwd()),
            created_at=now,
            updated_at=now,
            model=model,
            variant=variant,
            agent_mode=agent_mode,
            planner_model=planner_model,
            enabled_tool_packs=list(enabled_tool_packs or []),
            security_permission_mode=security_permission_mode,
            telegram_bot_config_id=telegram_bot_config_id,
            headless_eligible=bool(headless_eligible),
            workspace_id=_stable_workspace_id(workspace or Path.cwd(), workspace_id),
            workspace_binding_status=_workspace_binding_status(workspace or Path.cwd(), workspace_binding_status),
        )
        
        with _SESSION_IO_LOCK:
            self._save_session(session)
            self._update_index(session)
            self.current_session = session
        
        return session
    
    def load_session(self, session_id: str, *, set_current: bool = True) -> Session:
        """Load a session by ID.
        
        Args:
            session_id: The session ID to load.
            set_current: Whether to mark the session as the active session.
            
        Returns:
            The loaded Session object.
            
        Raises:
            ValueError: If session not found.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        
        if not session_file.exists() and not self._session_backup_file(session_id).exists():
            raise ValueError(f"Session not found: {session_id}")
        
        data = self._read_session_payload(session_id)
        session = Session.from_dict(data)

        if set_current:
            self.current_session = session
            self.set_current_session(session_id)
        
        return session
    
    def save_session(self, session: Session) -> None:
        """Save current session state.
        
        Args:
            session: The session to save.
        """
        session.updated_at = datetime.now().isoformat()
        with _SESSION_IO_LOCK:
            self._save_session(session)
            self._update_index(session)
        try:
            from app_backend.context_inspection import index_persisted_session

            index_persisted_session(session)
        except Exception:
            # Context inspection is optional and must never block chat persistence.
            pass

    def _recovery_dir(self) -> Path:
        return self.sessions_dir / ".recovery"

    def _session_backup_file(self, session_id: str) -> Path:
        return self._recovery_dir() / f"{session_id}.json.bak"

    def _index_backup_file(self) -> Path:
        return self._recovery_dir() / "index.json.bak"

    def _read_session_payload(self, session_id: str) -> Dict[str, Any]:
        session_file = self.sessions_dir / f"{session_id}.json"
        backup_file = self._session_backup_file(session_id)
        for candidate in (session_file, backup_file):
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if candidate == backup_file:
                atomic_write_json(session_file, payload)
            return payload
        raise ValueError(f"Session data is unreadable: {session_id}")
    
    def _save_session(self, session: Session) -> None:
        """Internal: write session to disk."""
        session_file = self.sessions_dir / f"{session.id}.json"
        atomic_write_json(
            session_file,
            session.to_dict(),
            backup_path=self._session_backup_file(session.id),
        )

    def _index_file(self) -> Path:
        return self.sessions_dir / "index.json"

    def _read_index_payload(self) -> Dict[str, Any]:
        index_file = self._index_file()
        if not index_file.exists() and not self._index_backup_file().exists():
            return {"sessions": [], "current_session_id": None}
        for candidate in (index_file, self._index_backup_file()):
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(raw, dict):
                continue
            if candidate == self._index_backup_file():
                atomic_write_json(index_file, raw)
            return raw
        return {"sessions": [], "current_session_id": None}

    def _write_index_payload(self, payload: Dict[str, Any]) -> None:
        atomic_write_json(
            self._index_file(),
            payload,
            backup_path=self._index_backup_file(),
        )

    def _session_file_paths(self) -> List[Path]:
        return sorted(
            path
            for path in self.sessions_dir.glob("*.json")
            if path.name.lower() != "index.json"
        )

    def _load_session_summary_from_file(self, session_file: Path) -> SessionSummary | None:
        try:
            payload = self._read_session_payload(session_file.stem)
            if not isinstance(payload, dict):
                return None
            chat_history = payload.get("chat_history", [])
            latest_preview = None
            origin_channels: List[str] = []
            if isinstance(chat_history, list):
                for item in chat_history:
                    if not isinstance(item, dict):
                        continue
                    channel = str(item.get("channel", "") or "").strip()
                    if channel and channel not in origin_channels:
                        origin_channels.append(channel)
                if chat_history:
                    last_item = chat_history[-1]
                    if isinstance(last_item, dict):
                        latest_preview = str(last_item.get("content", ""))[:140]
            workspace_text = str(payload.get("workspace", "") or "")
            workspace_path = Path(workspace_text).expanduser() if workspace_text else None
            return SessionSummary(
                id=str(payload.get("id", "") or ""),
                name=str(payload.get("name", "") or ""),
                created_at=str(payload.get("created_at", "") or ""),
                updated_at=str(payload.get("updated_at", payload.get("created_at", "")) or ""),
                model=str(payload.get("model", "claude-haiku-4.5") or "claude-haiku-4.5"),
                planner_model=payload.get("planner_model"),
                message_count=len(chat_history) if isinstance(chat_history, list) else 0,
                workspace=workspace_text,
                latest_preview=latest_preview,
                origin_channels=origin_channels,
                enabled_tool_packs=list(payload.get("enabled_tool_packs", []) or []),
                security_permission_mode=payload.get("security_permission_mode", "standard"),
                telegram_bot_config_id=payload.get("telegram_bot_config_id"),
                headless_eligible=bool(payload.get("headless_eligible", False)),
                workspace_id=payload.get("workspace_id") or _stable_workspace_id(workspace_path),
                workspace_binding_status=payload.get("workspace_binding_status") or _workspace_binding_status(workspace_path),
                fleet_identity_id=payload.get("fleet_identity_id"),
                fleet_identity_role=payload.get("fleet_identity_role"),
                fleet_worker_id=payload.get("fleet_worker_id"),
                fleet_task_mode=payload.get("fleet_task_mode"),
                fleet_task_id=payload.get("fleet_task_id"),
                account_user_id=payload.get("account_user_id"),
                account_email=payload.get("account_email"),
            )
        except Exception:
            return None

    def _sort_summaries(self, summaries: List[SessionSummary]) -> List[SessionSummary]:
        return sorted(
            summaries,
            key=lambda summary: (
                str(summary.updated_at or ""),
                str(summary.created_at or ""),
                str(summary.id or ""),
            ),
            reverse=True,
        )

    def _synchronize_index(self) -> tuple[List[SessionSummary], Optional[str]]:
        with _SESSION_IO_LOCK:
            return self._synchronize_index_locked()

    def _synchronize_index_locked(self) -> tuple[List[SessionSummary], Optional[str]]:
        payload = self._read_index_payload()
        indexed_summaries: Dict[str, SessionSummary] = {}
        for item in payload.get("sessions", []):
            if not isinstance(item, dict):
                continue
            try:
                summary = SessionSummary.from_dict(item)
            except Exception:
                continue
            if summary.id:
                indexed_summaries[summary.id] = summary

        file_summaries: Dict[str, SessionSummary] = {}
        for session_file in self._session_file_paths():
            summary = self._load_session_summary_from_file(session_file)
            if summary and summary.id:
                file_summaries[summary.id] = summary

        merged_summaries = self._sort_summaries(list(file_summaries.values()))
        merged_ids = [summary.id for summary in merged_summaries]
        indexed_ids = [summary.id for summary in self._sort_summaries(list(indexed_summaries.values()))]

        current_session_id = str(payload.get("current_session_id") or "").strip() or None
        if current_session_id and current_session_id not in file_summaries:
            current_session_id = None
        if not current_session_id and merged_summaries:
            current_session_id = merged_summaries[0].id

        needs_repair = merged_ids != indexed_ids or current_session_id != (str(payload.get("current_session_id") or "").strip() or None)
        if not needs_repair:
            for summary in merged_summaries:
                indexed = indexed_summaries.get(summary.id)
                if indexed is None or asdict(indexed) != asdict(summary):
                    needs_repair = True
                    break

        if needs_repair:
            self._write_index_payload(
                {
                    "sessions": [summary.to_dict() for summary in merged_summaries],
                    "current_session_id": current_session_id,
                }
            )

        return merged_summaries, current_session_id
    
    def list_sessions(self) -> List[SessionSummary]:
        """List all sessions (summary only, not full history).
        
        Returns:
            List of SessionSummary objects.
        """
        sessions, _ = self._synchronize_index()
        return sessions
    
    def delete_session(self, session_id: str) -> None:
        """Delete a session.
        
        Args:
            session_id: The session ID to delete.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        
        with _SESSION_IO_LOCK:
            if session_file.exists():
                session_file.unlink()
            backup_file = self._session_backup_file(session_id)
            if backup_file.exists():
                backup_file.unlink()

            self._remove_from_index(session_id)

            # If this was the current session, clear it
            if self.current_session and self.current_session.id == session_id:
                self.current_session = None
    
    def rename_session(self, session_id: str, new_name: str) -> None:
        """Rename a session.
        
        Args:
            session_id: The session ID to rename.
            new_name: The new name for the session.
        """
        session = self.load_session(session_id, set_current=False)
        session.name = new_name
        self.save_session(session)
    
    def get_current_session_id(self) -> Optional[str]:
        """Get the ID of the last active session.
        
        Returns:
            Session ID or None if no current session.
        """
        _, current_session_id = self._synchronize_index()
        return current_session_id
    
    def set_current_session(self, session_id: str) -> None:
        """Set the current active session.
        
        Args:
            session_id: The session ID to set as current.
        """
        with _SESSION_IO_LOCK:
            sessions, current_session_id = self._synchronize_index_locked()
            valid_session_id = session_id if any(summary.id == session_id for summary in sessions) else current_session_id
            self._write_index_payload(
                {
                    "sessions": [summary.to_dict() for summary in sessions],
                    "current_session_id": valid_session_id,
                }
            )
    
    def _update_index(self, session: Session) -> None:
        """Update the session index with session info."""
        with _SESSION_IO_LOCK:
            sessions, current_session_id = self._synchronize_index_locked()
            next_summaries = {summary.id: summary for summary in sessions}
            next_summaries[session.id] = session.to_summary()
            sorted_summaries = self._sort_summaries(list(next_summaries.values()))
            self._write_index_payload(
                {
                    "sessions": [summary.to_dict() for summary in sorted_summaries],
                    "current_session_id": current_session_id or session.id,
                }
            )
    
    def _remove_from_index(self, session_id: str) -> None:
        """Remove a session from the index."""
        with _SESSION_IO_LOCK:
            sessions, current_session_id = self._synchronize_index_locked()
            remaining = [summary for summary in sessions if summary.id != session_id]
            next_current = current_session_id
            if next_current == session_id:
                next_current = remaining[0].id if remaining else None
            self._write_index_payload(
                {
                    "sessions": [summary.to_dict() for summary in remaining],
                    "current_session_id": next_current,
                }
            )
    
    def export_session(self, session_id: str, format: str = "json") -> str:
        """Export a session to a string.
        
        Args:
            session_id: The session ID to export.
            format: Export format ("json" or "markdown").
            
        Returns:
            Exported session as string.
        """
        session = self.load_session(session_id, set_current=False)
        
        if format == "markdown":
            lines = [
                f"# {session.name}",
                "",
                f"**Created:** {session.created_at}",
                f"**Model:** {session.model}",
                f"**Workspace:** {session.workspace}",
                "",
                "---",
                "",
            ]
            
            for msg in session.chat_history:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")
                lines.append(f"### {role}")
                lines.append("")
                lines.append(content)
                lines.append("")
            
            return "\n".join(lines)
        
        # Default to JSON
        return json.dumps(session.to_dict(), indent=2)
