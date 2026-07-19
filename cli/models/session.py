"""Session data models for chat session persistence."""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from shared.runtime_paths import normalize_legacy_workspace_path
from shared.security_policy import normalize_permission_mode


_LEGACY_AGENT_MODE_MAP = {
    "semi": "auto",
}
_VALID_AGENT_MODES = {"manual", "auto"}


def _normalize_workspace_string(value: Optional[str]) -> str:
    normalized = normalize_legacy_workspace_path(value)
    return str(normalized) if normalized is not None else str(value or "")


def _stable_workspace_id(value: Optional[str]) -> Optional[str]:
    workspace = str(value or "").strip()
    if not workspace:
        return None
    try:
        workspace = str(Path(workspace).expanduser().resolve()).casefold()
    except Exception:
        workspace = workspace.casefold()
    return f"wsp_{hashlib.sha256(workspace.encode('utf-8', errors='ignore')).hexdigest()[:16]}"


def _workspace_binding_status(value: Optional[str]) -> Optional[str]:
    workspace = str(value or "").strip()
    if not workspace:
        return None
    try:
        return "active" if Path(workspace).expanduser().exists() else "needs_reconnect"
    except Exception:
        return "needs_reconnect"


def _sanitize_context_compaction(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not value:
        return value
    cleaned = dict(value)
    cleaned.pop("messages", None)
    return cleaned


def _ensure_stable_persisted_ids(items: List[Dict[str, Any]], *, key: str) -> None:
    for item in items:
        if isinstance(item, dict) and not str(item.get(key) or "").strip():
            item[key] = str(uuid.uuid4())


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
    latest_preview: Optional[str] = None
    origin_channels: List[str] = field(default_factory=list)
    enabled_tool_packs: List[str] = field(default_factory=list)
    security_permission_mode: str = "standard"
    telegram_bot_config_id: Optional[str] = None
    headless_eligible: bool = False
    workspace_id: Optional[str] = None
    workspace_binding_status: Optional[str] = None
    fleet_identity_id: Optional[str] = None
    fleet_identity_role: Optional[str] = None
    fleet_worker_id: Optional[str] = None
    fleet_task_mode: Optional[str] = None
    fleet_task_id: Optional[str] = None
    account_user_id: Optional[int] = None
    account_email: Optional[str] = None
    plan_mode: Optional[Dict[str, Any]] = None
    active_goal: Optional[Dict[str, Any]] = None
    
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
            "latest_preview": self.latest_preview,
            "origin_channels": list(self.origin_channels),
            "enabled_tool_packs": list(self.enabled_tool_packs),
            "security_permission_mode": self.security_permission_mode,
            "telegram_bot_config_id": self.telegram_bot_config_id,
            "headless_eligible": self.headless_eligible,
            "workspace_id": self.workspace_id,
            "workspace_binding_status": self.workspace_binding_status,
            "fleet_identity_id": self.fleet_identity_id,
            "fleet_identity_role": self.fleet_identity_role,
            "fleet_worker_id": self.fleet_worker_id,
            "fleet_task_mode": self.fleet_task_mode,
            "fleet_task_id": self.fleet_task_id,
            "account_user_id": self.account_user_id,
            "account_email": self.account_email,
            "plan_mode": self.plan_mode,
            "active_goal": self.active_goal,
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
            workspace=_normalize_workspace_string(data.get("workspace", "")),
            latest_preview=data.get("latest_preview"),
            origin_channels=list(data.get("origin_channels", []) or []),
            enabled_tool_packs=list(data.get("enabled_tool_packs", []) or []),
            security_permission_mode=data.get("security_permission_mode", "standard"),
            telegram_bot_config_id=data.get("telegram_bot_config_id"),
            headless_eligible=bool(data.get("headless_eligible", False)),
            workspace_id=data.get("workspace_id"),
            workspace_binding_status=data.get("workspace_binding_status"),
            fleet_identity_id=data.get("fleet_identity_id"),
            fleet_identity_role=data.get("fleet_identity_role"),
            fleet_worker_id=data.get("fleet_worker_id"),
            fleet_task_mode=data.get("fleet_task_mode"),
            fleet_task_id=data.get("fleet_task_id"),
            account_user_id=data.get("account_user_id"),
            account_email=data.get("account_email"),
            plan_mode=data.get("plan_mode") if isinstance(data.get("plan_mode"), dict) else None,
            active_goal=data.get("active_goal") if isinstance(data.get("active_goal"), dict) else None,
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
    enabled_tool_packs: List[str] = field(default_factory=list)
    security_permission_mode: str = "standard"
    telegram_bot_config_id: Optional[str] = None
    headless_eligible: bool = False
    workspace_id: Optional[str] = None
    workspace_binding_status: Optional[str] = None
    fleet_identity_id: Optional[str] = None
    fleet_identity_role: Optional[str] = None
    fleet_worker_id: Optional[str] = None
    fleet_task_mode: Optional[str] = None
    fleet_task_id: Optional[str] = None
    account_user_id: Optional[int] = None
    account_email: Optional[str] = None
    plan_mode: Optional[Dict[str, Any]] = None
    active_goal: Optional[Dict[str, Any]] = None
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    event_timeline: List[Dict[str, Any]] = field(default_factory=list)
    task_history: List[Dict[str, Any]] = field(default_factory=list)
    active_task_id: Optional[str] = None
    task_board_armed_next_turn: bool = False
    active_skills: List[str] = field(default_factory=list)
    last_context_compaction: Optional[Dict[str, Any]] = None
    failed_turns: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = self.created_at
        self.agent_mode = normalize_agent_mode(self.agent_mode)
        self.security_permission_mode = normalize_permission_mode(self.security_permission_mode)
        if not self.workspace_id:
            self.workspace_id = _stable_workspace_id(self.workspace)
        if not self.workspace_binding_status:
            self.workspace_binding_status = _workspace_binding_status(self.workspace)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        _ensure_stable_persisted_ids(self.chat_history, key="stable_message_id")
        _ensure_stable_persisted_ids(self.event_timeline, key="id")
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
            "enabled_tool_packs": self.enabled_tool_packs,
            "security_permission_mode": self.security_permission_mode,
            "telegram_bot_config_id": self.telegram_bot_config_id,
            "headless_eligible": self.headless_eligible,
            "workspace_id": self.workspace_id,
            "workspace_binding_status": self.workspace_binding_status,
            "fleet_identity_id": self.fleet_identity_id,
            "fleet_identity_role": self.fleet_identity_role,
            "fleet_worker_id": self.fleet_worker_id,
            "fleet_task_mode": self.fleet_task_mode,
            "fleet_task_id": self.fleet_task_id,
            "account_user_id": self.account_user_id,
            "account_email": self.account_email,
            "plan_mode": self.plan_mode,
            "active_goal": self.active_goal,
            "chat_history": self.chat_history,
            "event_timeline": self.event_timeline,
            "task_history": self.task_history,
            "active_task_id": self.active_task_id,
            "task_board_armed_next_turn": self.task_board_armed_next_turn,
            "active_skills": self.active_skills,
            "last_context_compaction": _sanitize_context_compaction(self.last_context_compaction),
            "failed_turns": list(self.failed_turns),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            workspace=_normalize_workspace_string(data.get("workspace", "")),
            model=data.get("model", "claude-haiku-4.5"),
            variant=data.get("variant", "standard"),
            agent_mode=normalize_agent_mode(data.get("agent_mode", "manual")),
            planner_model=data.get("planner_model"),
            enabled_tool_packs=list(data.get("enabled_tool_packs", []) or []),
            security_permission_mode=data.get("security_permission_mode", "standard"),
            telegram_bot_config_id=data.get("telegram_bot_config_id"),
            headless_eligible=bool(data.get("headless_eligible", False)),
            workspace_id=data.get("workspace_id"),
            workspace_binding_status=data.get("workspace_binding_status"),
            fleet_identity_id=data.get("fleet_identity_id"),
            fleet_identity_role=data.get("fleet_identity_role"),
            fleet_worker_id=data.get("fleet_worker_id"),
            fleet_task_mode=data.get("fleet_task_mode"),
            fleet_task_id=data.get("fleet_task_id"),
            account_user_id=data.get("account_user_id"),
            account_email=data.get("account_email"),
            plan_mode=data.get("plan_mode") if isinstance(data.get("plan_mode"), dict) else None,
            active_goal=data.get("active_goal") if isinstance(data.get("active_goal"), dict) else None,
            chat_history=data.get("chat_history", []),
            event_timeline=data.get("event_timeline", []),
            task_history=data.get("task_history", []),
            active_task_id=data.get("active_task_id"),
            task_board_armed_next_turn=bool(data.get("task_board_armed_next_turn", False)),
            active_skills=data.get("active_skills", []),
            last_context_compaction=_sanitize_context_compaction(data.get("last_context_compaction")),
            failed_turns=list(data.get("failed_turns", []) or []),
        )
    
    def to_summary(self) -> SessionSummary:
        """Create a summary of this session."""
        origin_channels: List[str] = []
        for item in self.chat_history:
            channel = str(item.get("channel", "") or "").strip()
            if channel and channel not in origin_channels:
                origin_channels.append(channel)
        latest_preview = None
        if self.chat_history:
            latest_preview = str(self.chat_history[-1].get("content", ""))[:140]
        return SessionSummary(
            id=self.id,
            name=self.name,
            created_at=self.created_at,
            updated_at=self.updated_at,
            model=self.model,
            planner_model=self.planner_model,
            message_count=len(self.chat_history),
            workspace=self.workspace,
            latest_preview=latest_preview,
            origin_channels=origin_channels,
            enabled_tool_packs=list(self.enabled_tool_packs),
            security_permission_mode=self.security_permission_mode,
            telegram_bot_config_id=self.telegram_bot_config_id,
            headless_eligible=bool(self.headless_eligible),
            workspace_id=self.workspace_id,
            workspace_binding_status=self.workspace_binding_status,
            fleet_identity_id=self.fleet_identity_id,
            fleet_identity_role=self.fleet_identity_role,
            fleet_worker_id=self.fleet_worker_id,
            fleet_task_mode=self.fleet_task_mode,
            fleet_task_id=self.fleet_task_id,
            account_user_id=self.account_user_id,
            account_email=self.account_email,
            plan_mode=self.plan_mode,
            active_goal=self.active_goal,
        )
