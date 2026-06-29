"""
Shared modules for the EmploAI system.

Keep this package initializer lightweight. Several startup paths import small
``shared.*`` modules before the local API is ready; eagerly importing the agent
runtime here makes the desktop shell wait on model/tool dependencies before it
can answer health checks.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    # Memory
    "MemoryManager": ("shared.memory", "MemoryManager"),
    "get_memory_manager": ("shared.memory", "get_memory_manager"),
    # Context
    "ContextLoader": ("shared.context_loader", "ContextLoader"),
    "get_context_loader": ("shared.context_loader", "get_context_loader"),
    # Heartbeat
    "HeartbeatManager": ("shared.heartbeat", "HeartbeatManager"),
    "get_heartbeat_manager": ("shared.heartbeat", "get_heartbeat_manager"),
    # Sessions
    "SessionType": ("shared.session_types", "SessionType"),
    "SessionContext": ("shared.session_types", "SessionContext"),
    "SessionRegistry": ("shared.session_types", "SessionRegistry"),
    "get_session_registry": ("shared.session_types", "get_session_registry"),
    # Config
    "LiveConfig": ("shared.live_config", "LiveConfig"),
    "ConfigChange": ("shared.live_config", "ConfigChange"),
    "get_live_config": ("shared.live_config", "get_live_config"),
    # Shared runtime
    "TurnReservation": ("shared.channel_runtime", "TurnReservation"),
    "SharedTurnResult": ("shared.channel_runtime", "SharedTurnResult"),
    "compact_session_history": ("shared.channel_runtime", "compact_session_history"),
    "begin_chat_turn": ("shared.channel_runtime", "begin_chat_turn"),
    "current_session_id": ("shared.channel_runtime", "current_session_id"),
    "merge_openai_tools": ("shared.channel_runtime", "merge_openai_tools"),
    "run_reserved_chat_turn": ("shared.channel_runtime", "run_reserved_chat_turn"),
    # Skills
    "SkillMatcher": ("shared.skills_enhanced", "SkillMatcher"),
    "EnhancedSkillsManager": ("shared.skills_enhanced", "EnhancedSkillsManager"),
    "enhance_skill_registry": ("shared.skills_enhanced", "enhance_skill_registry"),
    # Unified Agent
    "UnifiedAgent": ("shared.unified_agent", "UnifiedAgent"),
    "UnifiedToolRegistry": ("shared.unified_agent", "UnifiedToolRegistry"),
    "ModelConfig": ("shared.unified_agent", "ModelConfig"),
    "create_unified_agent": ("shared.unified_agent", "create_unified_agent"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
