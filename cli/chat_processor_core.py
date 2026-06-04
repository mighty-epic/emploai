"""Core ChatProcessor setup and helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from anthropic import Anthropic
from openai import OpenAI
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

from cli.config_manager import get_config_manager
from cli.models.session import Session
from cli.session_manager import SessionManager
from bot_core.system_info import get_system_info
from cli.tui_constants import (
    AGENT_MODES,
    DEFAULT_AGENT_MODE,
    MODEL_CONTEXT_SIZES,
    MODEL_VARIANTS,
    ChatMessage,
)
from single_agent.agent import SingleAgent
from cli.agent_tools.executor import ToolExecutor
from skills import get_skill_registry
from shared.tool_packs import default_enabled_tool_packs
from telegram_bot.telegram_unified_agent import build_unified_system_prompt


class _PromptConfig(dict):
    def get(self, key, default=None):
        return super().get(key, default)


@dataclass
class _TuiBrowserTaskContext:
    task_id: int = 0
    backend: Optional[str] = None
    primary_tab_id: Optional[Any] = None
    primary_window_id: Optional[Any] = None
    owned_tab_ids: List[Any] = field(default_factory=list)
    last_url: Optional[str] = None
    last_title: Optional[str] = None
    last_snapshot_hash: Optional[str] = None
    healthy: bool = True
    requires_real_chrome: bool = False


class _TuiPromptSession:
    def __init__(self, system_info: str):
        self.live_config = _PromptConfig({"browser.use_extension": False})
        self.user_id = 0
        self.refined_agent = None
        self.browser_tool = None
        self.extension_tool = None
        self.current_task_id = 0
        self.browser_task_context = _TuiBrowserTaskContext(task_id=0)
        self.system_info = system_info
        self.context_loader = None
        self.enabled_tool_packs = default_enabled_tool_packs()
        self._active_tool_packs_for_current_run = list(self.enabled_tool_packs)

    def get_browser_task_context(self):
        return self.browser_task_context


def build_tui_auto_system_prompt(processor, *, skills_index: str = "") -> str:
    prompt_session = _TuiPromptSession(system_info=get_system_info())
    return build_unified_system_prompt(
        prompt_session,
        skills_index=skills_index,
    )


def initialize(
    processor,
    base_path: Path,
    log,
    log_inline,
    detail_log,
    start_task_log,
    finish_task_log,
    update_status,
    open_model_picker,
    open_session_switcher,
) -> None:
    processor.base_path = base_path
    processor.log = log
    processor.log_inline = log_inline
    processor.detail_log = detail_log
    processor.start_task_log = start_task_log
    processor.finish_task_log = finish_task_log
    processor.update_status = update_status
    processor.open_model_picker = open_model_picker
    processor.open_session_switcher = open_session_switcher

    processor.cwd = base_path
    processor.history = []
    processor.history_index = 0

    # Session, Config, and Memory managers
    from shared.memory import get_memory_manager
    processor.session_manager = SessionManager()
    processor.config_manager = get_config_manager()
    processor.memory_manager = get_memory_manager(base_path)

    # Load or create session
    processor.session = None
    
    # Try to resume the last active session
    last_session_id = processor.session_manager.get_current_session_id()
    if last_session_id:
        try:
            processor.session = processor.session_manager.load_session(last_session_id)
            # Restore state from session
            processor.chat_history = [
                ChatMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    timestamp=msg.get("timestamp", datetime.now().timestamp()),
                )
                for msg in processor.session.chat_history
            ]
            processor.current_model = processor.session.model
            processor.current_variant = processor.session.variant
            processor.agent_mode = processor.session.agent_mode
            processor.active_skills = getattr(processor.session, "active_skills", [])
        except Exception:
            # Fallback to new session if load fails
            processor.session = processor.session_manager.create_session(workspace=base_path)
    else:
        # Fresh start if no previous session
        processor.session = processor.session_manager.create_session(workspace=base_path)

    if not processor.session:
         # Final fallback
         processor.session = processor.session_manager.create_session(workspace=base_path)

    processor.current_model = processor.session.model
    processor.current_variant = processor.session.variant
    processor.agent_mode = processor.session.agent_mode
    processor.active_skills = getattr(processor.session, "active_skills", [])

    processor.total_tokens_used = 0
    processor.max_tokens = MODEL_CONTEXT_SIZES.get(processor.current_model, 128000)

    # Legacy context summary buffers from the older split-agent flow.
    processor._cli_context_summary = ""
    processor._task_context_summary = ""

    # LLM clients - load from config manager with env var fallback
    openai_key = processor.config_manager.get_api_key("openai") or os.getenv("OPENAI_API_KEY")
    anthropic_key = processor.config_manager.get_api_key("anthropic") or os.getenv("ANTHROPIC_API_KEY")
    
    # New providers
    google_key = processor.config_manager.get_api_key("google") or os.getenv("GOOGLE_API_KEY")
    xai_key = processor.config_manager.get_api_key("xai") or os.getenv("XAI_API_KEY")
    deepseek_key = processor.config_manager.get_api_key("deepseek") or os.getenv("DEEPSEEK_API_KEY")
    openrouter_key = processor.config_manager.get_api_key("openrouter") or os.getenv("OPENROUTER_API_KEY")

    processor.client = OpenAI(api_key=openai_key) if openai_key else None
    processor.anthropic = Anthropic(api_key=anthropic_key) if anthropic_key else None
    
    # Configure Gemini
    processor.genai = None
    if HAS_GEMINI and google_key:
        genai.configure(api_key=google_key)
        processor.genai = genai

    # Create clients for OpenAI-compatible providers
    processor.xai_client = OpenAI(api_key=xai_key, base_url="https://api.x.ai/v1") if xai_key else None
    processor.deepseek_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com") if deepseek_key else None
    processor.openrouter_client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1") if openrouter_key else None

    # Streaming state
    processor._stream_buffer = ""
    processor._streaming_response = False
    processor.interrupted = False

    # Single agent (Active)
    processor.single_agent = SingleAgent(logger=processor.detail_log)
    
    # Initialize Skill Registry
    processor.skill_registry = get_skill_registry()
    
    # Unified Tool Executor for CLI Agent
    processor.tool_executor = ToolExecutor(
        base_path, 
        single_agent=processor.single_agent,
        skill_registry=processor.skill_registry,
        active_skills=processor.active_skills
    )


def get_default_variant(processor, model: str) -> str:
    """Get the default variant for a model."""
    variant_info = MODEL_VARIANTS.get(model, {"default": "standard"})
    return variant_info.get("default", "standard")


def get_available_variants(processor, model: str) -> List[str]:
    """Get available variants for a model."""
    variant_info = MODEL_VARIANTS.get(model, {"variants": ["standard"]})
    return variant_info.get("variants", ["standard"])


def set_variant(processor, variant: str) -> bool:
    """Set the current variant if valid for the current model."""
    available = get_available_variants(processor, processor.current_model)
    if variant in available:
        processor.current_variant = variant
        return True
    return False


def cycle_agent_mode(processor) -> str:
    """Cycle through agent modes: manual -> auto -> manual."""
    current_mode = processor.agent_mode if processor.agent_mode in AGENT_MODES else DEFAULT_AGENT_MODE
    current_idx = AGENT_MODES.index(current_mode)
    next_idx = (current_idx + 1) % len(AGENT_MODES)
    processor.agent_mode = AGENT_MODES[next_idx]
    auto_save_session(processor)
    return processor.agent_mode


def auto_save_session(processor) -> None:
    """Auto-save current session state."""
    if not processor.session:
        return

    # Update session with current state
    processor.session.chat_history = [
        {
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp,
            "duration": msg.duration,
        }
        for msg in processor.chat_history
    ]
    processor.session.model = processor.current_model
    processor.session.variant = processor.current_variant
    processor.session.agent_mode = processor.agent_mode
    processor.session.active_skills = processor.active_skills

    # Save to disk
    processor.session_manager.save_session(processor.session)


def new_session(processor, name: Optional[str] = None) -> Session:
    """Create a new session and switch to it."""
    processor.session = processor.session_manager.create_session(
        name=name,
        workspace=processor.base_path,
        model=processor.current_model,
        variant=processor.current_variant,
        agent_mode=processor.agent_mode,
    )
    processor.chat_history = []
    return processor.session


def switch_session(processor, session_id: str) -> bool:
    """Switch to a different session."""
    try:
        # Save current session first
        auto_save_session(processor)

        # Load new session
        processor.session = processor.session_manager.load_session(session_id)
        processor.current_model = processor.session.model
        processor.current_variant = processor.session.variant
        processor.agent_mode = processor.session.agent_mode
        processor.max_tokens = MODEL_CONTEXT_SIZES.get(processor.current_model, 128000)

        # Restore chat history
        processor.chat_history = [
            ChatMessage(
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                timestamp=msg.get("timestamp", datetime.now().timestamp()),
                duration=msg.get("duration", ""),
            )
            for msg in processor.session.chat_history
        ]
        processor.active_skills = processor.session.active_skills
        return True
    except Exception:
        return False


def clear_chat(processor) -> None:
    """Clear current chat history."""
    processor.chat_history = []
    auto_save_session(processor)


def generate_context_summary(processor, history: List[ChatMessage], max_tokens: int = 500) -> str:
    """Generate an intelligent summary of chat history for context sharing."""
    if not history:
        return ""

    # Build a simple summary from recent messages
    recent = history[-10:]  # Last 10 messages
    summary_parts = []
    for msg in recent:
        role_prefix = "User" if msg.role == "user" else "Assistant"
        # Truncate long messages
        content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        summary_parts.append(f"{role_prefix}: {content}")

    return "\n".join(summary_parts)


def get_context_for_task_agent(processor) -> str:
    """Get context to inject into Task Agent based on agent mode."""
    if processor.agent_mode == "manual":
        return ""  # No context sharing

    # auto
    # Return full history (subject to context limits)
    full_context = []
    for msg in processor.chat_history[-20:]:
        full_context.append(f"[{msg.role}]: {msg.content}")
    return "\n".join(full_context)


def cycle_variant(processor) -> str:
    """Cycle through available variants for the current model."""
    available = get_available_variants(processor, processor.current_model)
    if len(available) <= 1:
        return processor.current_variant  # No other variants available

    current_idx = available.index(processor.current_variant) if processor.current_variant in available else 0
    next_idx = (current_idx + 1) % len(available)
    processor.current_variant = available[next_idx]
    return processor.current_variant


def begin_stream(processor) -> None:
    processor._stream_buffer = ""
    processor._streaming_response = True
    processor.log_inline(f"[{processor.current_model}]: ")


def append_stream(processor, text: str) -> None:
    if not text:
        return
    processor._stream_buffer += text
    processor.log_inline(text)


def finish_stream(processor) -> str:
    if processor._streaming_response:
        processor.log_inline("\n")
        processor._streaming_response = False
    return processor._stream_buffer


def resolve_path(processor, path_str: str) -> Path:
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = processor.cwd / candidate
    resolved = candidate.resolve()
    if not is_within_base(processor, resolved):
        raise ValueError("Path escapes workspace")
    return resolved


def is_within_base(processor, path: Path) -> bool:
    try:
        path.relative_to(processor.base_path)
        return True
    except ValueError:
        return False


def get_context_percentage(processor) -> float:
    """Get current context usage as percentage."""
    if processor.max_tokens == 0:
        return 0.0
    return (processor.total_tokens_used / processor.max_tokens) * 100
