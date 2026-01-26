"""Session Manager - handles CRUD operations for chat sessions."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from cli.models.session import Session, SessionSummary


class SessionManager:
    """Manages chat sessions - save, load, switch, delete."""
    
    def __init__(self, base_path: Optional[Path] = None):
        """Initialize session manager.
        
        Args:
            base_path: Base path for storing sessions. Defaults to ~/.agentshell
        """
        self.base_path = base_path or Path.home() / ".agentshell"
        self.sessions_dir = self.base_path / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: Optional[Session] = None
    
    def create_session(
        self, 
        name: Optional[str] = None, 
        workspace: Optional[Path] = None,
        model: str = "claude-haiku-4.5",
        variant: str = "standard",
        agent_mode: str = "manual"
    ) -> Session:
        """Create a new session.
        
        Args:
            name: Session name. Auto-generated if not provided.
            workspace: Workspace path. Defaults to cwd.
            model: Model to use.
            variant: Model variant.
            agent_mode: Agent mode setting.
            
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
        )
        
        self._save_session(session)
        self._update_index(session)
        self.current_session = session
        
        return session
    
    def load_session(self, session_id: str) -> Session:
        """Load a session by ID.
        
        Args:
            session_id: The session ID to load.
            
        Returns:
            The loaded Session object.
            
        Raises:
            ValueError: If session not found.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        
        if not session_file.exists():
            raise ValueError(f"Session not found: {session_id}")
        
        data = json.loads(session_file.read_text(encoding="utf-8"))
        session = Session.from_dict(data)
        self.current_session = session
        
        # Update current session in index
        self.set_current_session(session_id)
        
        return session
    
    def save_session(self, session: Session) -> None:
        """Save current session state.
        
        Args:
            session: The session to save.
        """
        session.updated_at = datetime.now().isoformat()
        self._save_session(session)
        self._update_index(session)
    
    def _save_session(self, session: Session) -> None:
        """Internal: write session to disk."""
        session_file = self.sessions_dir / f"{session.id}.json"
        session_file.write_text(
            json.dumps(session.to_dict(), indent=2),
            encoding="utf-8"
        )
    
    def list_sessions(self) -> List[SessionSummary]:
        """List all sessions (summary only, not full history).
        
        Returns:
            List of SessionSummary objects.
        """
        index_file = self.sessions_dir / "index.json"
        
        if not index_file.exists():
            return []
        
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
            return [
                SessionSummary.from_dict(s) 
                for s in data.get("sessions", [])
            ]
        except (json.JSONDecodeError, IOError):
            return []
    
    def delete_session(self, session_id: str) -> None:
        """Delete a session.
        
        Args:
            session_id: The session ID to delete.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        
        if session_file.exists():
            session_file.unlink()
        
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
        session = self.load_session(session_id)
        session.name = new_name
        self.save_session(session)
    
    def get_current_session_id(self) -> Optional[str]:
        """Get the ID of the last active session.
        
        Returns:
            Session ID or None if no current session.
        """
        index_file = self.sessions_dir / "index.json"
        
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                return data.get("current_session_id")
            except (json.JSONDecodeError, IOError):
                pass
        
        return None
    
    def set_current_session(self, session_id: str) -> None:
        """Set the current active session.
        
        Args:
            session_id: The session ID to set as current.
        """
        index_file = self.sessions_dir / "index.json"
        
        data = {"sessions": [], "current_session_id": None}
        
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        
        data["current_session_id"] = session_id
        
        index_file.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )
    
    def _update_index(self, session: Session) -> None:
        """Update the session index with session info."""
        index_file = self.sessions_dir / "index.json"
        
        data = {"sessions": [], "current_session_id": None}
        
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        
        sessions = data.get("sessions", [])
        summary = session.to_summary().to_dict()
        
        # Update or add session in list
        updated = False
        for i, s in enumerate(sessions):
            if s.get("id") == session.id:
                sessions[i] = summary
                updated = True
                break
        
        if not updated:
            sessions.append(summary)
        
        # Sort by updated_at descending (most recent first)
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        
        data["sessions"] = sessions
        
        index_file.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )
    
    def _remove_from_index(self, session_id: str) -> None:
        """Remove a session from the index."""
        index_file = self.sessions_dir / "index.json"
        
        if not index_file.exists():
            return
        
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return
        
        sessions = data.get("sessions", [])
        data["sessions"] = [s for s in sessions if s.get("id") != session_id]
        
        # Clear current session if it was deleted
        if data.get("current_session_id") == session_id:
            data["current_session_id"] = None
        
        index_file.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )
    
    def export_session(self, session_id: str, format: str = "json") -> str:
        """Export a session to a string.
        
        Args:
            session_id: The session ID to export.
            format: Export format ("json" or "markdown").
            
        Returns:
            Exported session as string.
        """
        session = self.load_session(session_id)
        
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
