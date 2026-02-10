"""
Session Types - Support for different session contexts (main vs isolated)
Similar to Moltbot's session architecture
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SessionType(Enum):
    """Different types of sessions with different contexts."""
    MAIN = "main"           # Direct user chat - has access to MEMORY.md
    ISOLATED = "isolated"   # Background tasks - no MEMORY.md access
    TASK = "task"          # Task-specific session
    SPAWN = "spawn"        # Spawned sub-agent session


@dataclass
class SessionContext:
    """Context for a session."""
    session_id: str
    session_type: SessionType
    user_id: int
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    
    # Session-specific settings
    can_access_memory: bool = True  # Can read MEMORY.md
    can_write_memory: bool = True   # Can update MEMORY.md
    can_access_daily_logs: bool = True
    can_spawn_agents: bool = True
    
    # Context limits
    max_context_tokens: int = 128000
    context_compression_threshold: float = 0.5  # Compress at 50%
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Set permissions based on session type."""
        if self.session_type == SessionType.ISOLATED:
            # Isolated sessions shouldn't read/write long-term memory
            self.can_access_memory = False
            self.can_write_memory = False
        elif self.session_type == SessionType.SPAWN:
            # Spawned agents can read but not write memory
            self.can_write_memory = False
        elif self.session_type == SessionType.TASK:
            # Task sessions limited access
            self.can_write_memory = False
    
    def update_activity(self):
        """Update last active timestamp."""
        self.last_active = datetime.now()
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            'session_id': self.session_id,
            'session_type': self.session_type.value,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'last_active': self.last_active.isoformat(),
            'can_access_memory': self.can_access_memory,
            'can_write_memory': self.can_write_memory,
            'can_access_daily_logs': self.can_access_daily_logs,
            'can_spawn_agents': self.can_spawn_agents,
            'max_context_tokens': self.max_context_tokens,
            'context_compression_threshold': self.context_compression_threshold,
            'metadata': self.metadata,
            'tags': self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SessionContext':
        """Deserialize from dict."""
        return cls(
            session_id=data['session_id'],
            session_type=SessionType(data['session_type']),
            user_id=data['user_id'],
            created_at=datetime.fromisoformat(data['created_at']),
            last_active=datetime.fromisoformat(data['last_active']),
            can_access_memory=data.get('can_access_memory', True),
            can_write_memory=data.get('can_write_memory', True),
            can_access_daily_logs=data.get('can_access_daily_logs', True),
            can_spawn_agents=data.get('can_spawn_agents', True),
            max_context_tokens=data.get('max_context_tokens', 128000),
            context_compression_threshold=data.get('context_compression_threshold', 0.5),
            metadata=data.get('metadata', {}),
            tags=data.get('tags', [])
        )


class SessionRegistry:
    """Registry for managing multiple sessions."""
    
    def __init__(self):
        self.sessions: Dict[str, SessionContext] = {}
    
    def create_session(
        self,
        session_id: str,
        session_type: SessionType,
        user_id: int,
        **kwargs
    ) -> SessionContext:
        """Create a new session."""
        session = SessionContext(
            session_id=session_id,
            session_type=session_type,
            user_id=user_id,
            **kwargs
        )
        self.sessions[session_id] = session
        logger.info(f"Created {session_type.value} session: {session_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get a session by ID."""
        return self.sessions.get(session_id)
    
    def get_or_create_main_session(self, user_id: int) -> SessionContext:
        """Get or create the main session for a user."""
        session_id = f"main_{user_id}"
        if session_id not in self.sessions:
            return self.create_session(session_id, SessionType.MAIN, user_id)
        return self.sessions[session_id]
    
    def list_sessions(self, user_id: Optional[int] = None) -> List[SessionContext]:
        """List all sessions, optionally filtered by user."""
        sessions = list(self.sessions.values())
        if user_id is not None:
            sessions = [s for s in sessions if s.user_id == user_id]
        return sessions
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        return False
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Remove sessions older than max_age_hours."""
        from datetime import timedelta
        now = datetime.now()
        cutoff = now - timedelta(hours=max_age_hours)
        
        to_delete = [
            sid for sid, session in self.sessions.items()
            if session.session_type in [SessionType.ISOLATED, SessionType.TASK, SessionType.SPAWN]
            and session.last_active < cutoff
        ]
        
        for sid in to_delete:
            self.delete_session(sid)
        
        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} old sessions")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        stats = {
            'total': len(self.sessions),
            'by_type': {},
            'by_user': {}
        }
        
        for session in self.sessions.values():
            # Count by type
            stype = session.session_type.value
            stats['by_type'][stype] = stats['by_type'].get(stype, 0) + 1
            
            # Count by user
            uid = session.user_id
            stats['by_user'][uid] = stats['by_user'].get(uid, 0) + 1
        
        return stats


# Global registry
_session_registry = SessionRegistry()


def get_session_registry() -> SessionRegistry:
    """Get the global session registry."""
    return _session_registry
