"""Session data models for chat session persistence."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


_LEGACY_AGENT_MODE_MAP = {
    "semi": "auto",
}
_VALID_AGENT_MODES = {"manual", "auto"}


def _sanitize_context_compaction(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not value:
        return value
    cleaned = dict(value)
    cleaned.pop("messages", None)
    return cleaned


def normalize_agent_mode(value: Optional[str], *, default: str = "manual") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _LEGACY_AGENT_MODE_MAP:
        return _LEGACY_AGENT_MODE_MAP[normalized]
    if normalized in _VALID_AGENT_MODES:
        return normalized
    return default


@dataclass
class SessionSummary:
    """Summary of a session for listing (without full history)."""
    id: str
    name: str
    created_at: str
    updated_at: str
    model: str = "claude-haiku-4.5"
    planner_model: Optional[str] = None
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
            "planner_model": self.planner_model,
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
            planner_model=data.get("planner_model"),
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
    planner_model: Optional[str] = None
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    event_timeline: List[Dict[str, Any]] = field(default_factory=list)
    task_history: List[Dict[str, Any]] = field(default_factory=list)
    active_task_id: Optional[str] = None
    active_skills: List[str] = field(default_factory=list)
    last_context_compaction: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = self.created_at
        self.agent_mode = normalize_agent_mode(self.agent_mode)
    
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
            "planner_model": self.planner_model,
            "chat_history": self.chat_history,
            "event_timeline": self.event_timeline,
            "task_history": self.task_history,
            "active_task_id": self.active_task_id,
            "active_skills": self.active_skills,
            "last_context_compaction": _sanitize_context_compaction(self.last_context_compaction),
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
            agent_mode=normalize_agent_mode(data.get("agent_mode", "manual")),
            planner_model=data.get("planner_model"),
            chat_history=data.get("chat_history", []),
            event_timeline=data.get("event_timeline", []),
            task_history=data.get("task_history", []),
            active_task_id=data.get("active_task_id"),
            active_skills=data.get("active_skills", []),
            last_context_compaction=_sanitize_context_compaction(data.get("last_context_compaction")),
        )
    
    def to_summary(self) -> SessionSummary:
        """Create a summary of this session."""
        return SessionSummary(
            id=self.id,
            name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
            model=self.model,
            planner_model=self.planner_model,
            message_count=len(self.chat_history),
            workspace=self.workspace,
        )
