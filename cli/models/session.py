"""Session data models for chat session persistence."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class SessionSummary:
    """Summary of a session for listing (without full history)."""
    id: str
    name: str
    created_at: str
    updated_at: str
    model: str = "claude-haiku-4.5"
    message_count: int = 0
    workspace: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "message_count": self.message_count,
            "workspace": self.workspace,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSummary":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            model=data.get("model", "claude-haiku-4.5"),
            message_count=data.get("message_count", 0),
            workspace=data.get("workspace", ""),
        )


@dataclass
class Session:
    """Full session data including chat history."""
    id: str
    name: str
    created_at: str
    updated_at: str = ""
    workspace: str = ""
    model: str = "claude-haiku-4.5"
    variant: str = "standard"
    agent_mode: str = "manual"
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    task_history: List[Dict[str, Any]] = field(default_factory=list)
    active_skills: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace": self.workspace,
            "model": self.model,
            "variant": self.variant,
            "agent_mode": self.agent_mode,
            "chat_history": self.chat_history,
            "task_history": self.task_history,
            "active_skills": self.active_skills,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            workspace=data.get("workspace", ""),
            model=data.get("model", "claude-haiku-4.5"),
            variant=data.get("variant", "standard"),
            agent_mode=data.get("agent_mode", "manual"),
            chat_history=data.get("chat_history", []),
            task_history=data.get("task_history", []),
            active_skills=data.get("active_skills", []),
        )
    
    def to_summary(self) -> SessionSummary:
        """Create a summary of this session."""
        return SessionSummary(
            id=self.id,
            name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
            model=self.model,
            message_count=len(self.chat_history),
            workspace=self.workspace,
        )
