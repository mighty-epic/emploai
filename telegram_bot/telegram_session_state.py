"""Telegram session state and helpers."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram import Bot
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application

from cli.config_manager import get_config_manager
from cli.session_manager import SessionManager
from cli.agent_tools.executor import ToolExecutor
from cli.tui_constants import MODEL_CONFIGS, MODEL_VARIANTS
from local_agent_runtime.agent import SingleAgent
from local_agent_runtime.refined_agent import RefinedAgent, create_refined_agent
from local_agent_runtime.cron_scheduler import get_scheduler
from local_agent_runtime.spawn_tool import get_spawn_tool
from telegram_bot.cron_runner import run_cron_job_via_unified_flow

from runtime_support.analytics import get_analytics_tracker, AnalyticsTracker
from runtime_support.file_processor import get_file_processor, FileProcessor
from runtime_support.hooks import get_hook_manager, HookManager
from runtime_support.system_info import get_system_info
from skills import get_skill_registry, SkillRegistry

from shared import (
    ContextLoader, get_context_loader,
    HeartbeatManager,
    LiveConfig, get_live_config,
    MemoryManager, get_memory_manager,
    SessionContext, get_session_registry,
    EnhancedSkillsManager, enhance_skill_registry,
    UnifiedAgent,
)
from shared.channel_sync import get_channel_sync_hub
from shared.model_availability import (
    enabled_providers_from_clients,
    filter_models_by_provider_access,
    first_available_model,
    group_models_by_provider,
)
from shared.model_defaults import (
    ANTHROPIC_DEFAULT_PLANNER_MODEL,
    GOOGLE_DEFAULT_PLANNER_MODEL,
    OPENAI_CODEX_DEFAULT_PLANNER_MODEL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_PLANNER_MODEL,
    default_model_pair_for_enabled_providers,
    default_planner_for_model,
    is_auto_model_setting,
    provider_for_model,
)
from cli.agent_tools.gemini_client import create_gemini_openai_client
from shared.openai_codex_auth import create_codex_client, is_codex_auth_configured
from shared.runtime_paths import normalize_legacy_workspace_path, user_state_root
from shared.telegram_bot_config_store import TelegramBotConfigStore
from shared.tool_packs import default_enabled_tool_packs

from openai import OpenAI
from anthropic import Anthropic


logger = logging.getLogger(__name__)
_telegram_application: Optional[Application] = None
_telegram_loop: Optional[asyncio.AbstractEventLoop] = None
TELEGRAM_STATE_USER_ID_ENV = "EMPLOAI_TELEGRAM_STATE_USER_ID"
_BASE64_KEYS = frozenset({"image_base64", "base64", "image_data", "data", "screenshot"})
DEFAULT_RUNTIME_MODEL = OPENAI_DEFAULT_MODEL
DEFAULT_PLANNER_MODEL = OPENAI_DEFAULT_PLANNER_MODEL
MODEL_NAME_ALIASES = {
    "claude-sonnet-4-5": "claude-sonnet-4.5",
    "claude-opus-4-5": "claude-opus-4.5",
    "claude-haiku-4-5": "claude-haiku-4.5",
}


def _normalize_model_name(value: Any) -> str:
    cleaned = str(value or "").strip()
    return MODEL_NAME_ALIASES.get(cleaned, cleaned)


REAL_CHROME_TASK_HINTS = (
    "my chrome",
    "user's chrome",
    "users chrome",
    "real chrome",
    "current chrome",
    "existing chrome",
    "my browser",
    "current browser",
    "existing browser",
    "already open tab",
    "current tab",
    "existing tab",
    "logged-in browser",
    "logged in browser",
    "logged-in session",
    "logged in session",
    "already logged in",
    "my session",
    "browser session",
    "my profile",
    "extension popup",
    "chrome extension",
    "browser extension",
    "chrome://extensions",
    "load unpacked",
)


def _task_requires_real_chrome(task_text: Optional[str]) -> bool:
    normalized = " ".join(str(task_text or "").strip().lower().split())
    if not normalized:
        return False
    return any(hint in normalized for hint in REAL_CHROME_TASK_HINTS)


def resolve_telegram_state_user_id(user_id: int) -> int:
    raw = str(os.getenv(TELEGRAM_STATE_USER_ID_ENV, "") or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning("Ignoring invalid %s=%r", TELEGRAM_STATE_USER_ID_ENV, raw)
    return int(user_id)


def _format_verbose_tool_message(payload: Dict[str, Any]) -> str:
    tool_name = str(payload.get("tool_name") or "").strip() or "tool"
    args = payload.get("tool_args") or {}
    result = payload.get("tool_result")
    duration_ms = float(payload.get("duration_ms") or 0.0)

    short_parts: list[str] = []
    for key, value in list(args.items())[:4]:
        value_text = str(value)
        if key in _BASE64_KEYS and len(value_text) > 100:
            continue
        if len(value_text) > 80:
            value_text = value_text[:77] + "..."
        short_parts.append(f"{key}: {value_text}")
    args_text = ", ".join(short_parts)
    if len(args_text) > 200:
        args_text = args_text[:197] + "..."

    if isinstance(result, dict):
        if "error" in result:
            result_text = f"❌ {str(result.get('error') or '')[:180]}"
        else:
            safe_keys = [str(key) for key in result.keys() if str(key) not in _BASE64_KEYS]
            result_text = f"✅ {', '.join(safe_keys[:5]) or 'ok'}"
    else:
        result_value = str(result or "").strip()
        if len(result_value) > 180:
            result_value = result_value[:177] + "..."
        if result_value.lower().startswith("error"):
            result_text = f"❌ {result_value}"
        else:
            result_text = f"✅ {result_value or 'ok'}"

    call_text = f"{tool_name}({args_text})" if args_text else f"{tool_name}()"
    return f"🧰 *Command*\n`{call_text}`\n\n*Command Result*\n{result_text} ({duration_ms:.0f}ms)"


@dataclass
class BrowserTaskContext:
    """Tracks the browser backend and primary task-owned tab for one task."""

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


@dataclass
class TelegramSession:
    """Holds per-user state for the Telegram bot."""
    user_id: int
    sync_user_id: Optional[int] = None
    current_model: str = DEFAULT_RUNTIME_MODEL
    current_variant: str = "standard"
    planner_model: Optional[str] = None
    default_planner_model: Optional[str] = None
    enabled_tool_packs: List[str] = field(default_factory=default_enabled_tool_packs)
    telegram_bot_config_id: Optional[str] = None
    headless_eligible: bool = False
    agent_mode: str = "auto"  # Default to auto for full autonomous behavior
    max_turns: int = 100
    chat_history: List[Dict] = field(default_factory=list)
    event_timeline: List[Dict[str, Any]] = field(default_factory=list)

    # Agents (Legacy SingleAgent for backwards compatibility)
    single_agent: Optional[SingleAgent] = None
    tool_executor: Optional[ToolExecutor] = None

    # Moltbot Clone - RefinedAgent with all new features
    refined_agent: Optional[RefinedAgent] = None
    spawn_tool: Optional[Any] = None
    cron_scheduler: Optional[Any] = None

    # Managers
    session_manager: Optional[SessionManager] = None
    config_manager: Optional[Any] = None
    skill_registry: Optional[SkillRegistry] = None
    hook_manager: Optional[HookManager] = None
    file_processor: Optional[FileProcessor] = None
    analytics_tracker: Optional[AnalyticsTracker] = None

    # NEW: Moltbot-style managers
    memory_manager: Optional[MemoryManager] = None
    context_loader: Optional[ContextLoader] = None
    heartbeat_manager: Optional[HeartbeatManager] = None
    session_context: Optional[SessionContext] = None
    live_config: Optional[LiveConfig] = None
    enhanced_skills: Optional[EnhancedSkillsManager] = None

    # NEW: Unified agent (replaces fragmented agents)
    unified_agent: Optional[UnifiedAgent] = None

    # Compression / Context
    context_manager: Optional[Any] = None

    # LLM Clients
    openai_client: Optional[OpenAI] = None
    anthropic_client: Optional[Anthropic] = None
    google_client: Optional[Any] = None
    gemini_openai_client: Optional[OpenAI] = None
    xai_client: Optional[OpenAI] = None
    deepseek_client: Optional[OpenAI] = None
    openrouter_client: Optional[OpenAI] = None
    nvidia_client: Optional[OpenAI] = None
    openai_codex_client: Optional[Any] = None

    # Telegram context
    _app: Optional[Application] = None
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _channel_sync_subscription_id: Optional[str] = None

    # Environment
    system_info: str = field(default_factory=get_system_info)

    # CLI Agent interruption
    is_processing: bool = False
    should_interrupt: bool = False
    interrupt_message: Optional[str] = None  # The message that caused the interruption
    interrupt_queue: List[str] = field(default_factory=list)
    deferred_interrupt_queue: List[str] = field(default_factory=list)
    current_task_id: int = 0  # Unique ID for current task, to detect abandoned tasks
    browser_task_context: BrowserTaskContext = field(default_factory=BrowserTaskContext)

    # Auto-reply / monitoring
    auto_reply_enabled: bool = True
    auto_reply_notice_sent: bool = False
    show_skill_notifications: bool = True

    # Verbose tool logging to Telegram
    verbose_mode: bool = True  # Default ON so user sees tool actions

    # File handling
    pending_files: List[Dict[str, Any]] = field(default_factory=list)

    # Conversation tracking
    last_user_message: Optional[str] = None
    message_id_map: Dict[int, int] = field(default_factory=dict)
    task_history: List[Dict[str, Any]] = field(default_factory=list)
    active_task_id: Optional[str] = None
    task_board_armed_next_turn: bool = False
    active_skills: List[str] = field(default_factory=list)
    last_context_compaction: Optional[Dict[str, Any]] = None

    # Wizard state
    wizard_state: Dict[str, Any] = field(default_factory=dict)

    # Thread safety
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    workspace: Path = field(default_factory=lambda: Path.cwd())
    create_new_session_on_init: bool = False
    shared_current_session_id: Optional[str] = None

    def refresh_system_info(self):
        """Update system info string with current windows and hardware state."""
        from runtime_support.system_info import get_system_info
        self.system_info = get_system_info()

    def _live_config_string(self, path: str) -> str:
        if not getattr(self, "live_config", None):
            return ""
        try:
            return str(self.live_config.get(path, "") or "").strip()
        except Exception:
            return ""

    def _configured_provider_keys(self) -> set[str]:
        enabled: set[str] = set()
        manager = getattr(self, "config_manager", None)
        for provider, env_var in {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
        }.items():
            configured = ""
            if manager is not None:
                try:
                    configured = str(manager.get_api_key(provider) or "").strip()
                except Exception:
                    configured = ""
            if configured or str(os.getenv(env_var, "") or "").strip():
                enabled.add(provider)
        if is_codex_auth_configured():
            enabled.add("openai-codex")
        return enabled

    def _provider_default_model_pair(self):
        return default_model_pair_for_enabled_providers(self._configured_provider_keys())

    def _configured_default_model(self) -> str:
        raw = str(os.getenv("AGENT_DEFAULT_MODEL", "") or "").strip() or self._live_config_string("agent.default_model")
        if is_auto_model_setting(raw):
            return self._provider_default_model_pair().model
        return _normalize_model_name(raw)

    def _configured_default_planner_model(self, model_name: Optional[str] = None) -> Optional[str]:
        raw = (
            str(os.getenv("PLANNER_MODEL", "") or "").strip()
            or str(os.getenv("AGENT_DEFAULT_PLANNER_MODEL", "") or "").strip()
            or self._live_config_string("agent.default_planner_model")
            or self._live_config_string("agent.planner_model")
        )
        if is_auto_model_setting(raw):
            current_model = str(model_name or getattr(self, "current_model", "") or "").strip()
            return default_planner_for_model(
                current_model,
                enabled_providers=self._configured_provider_keys(),
            )
        configured = _normalize_model_name(raw)
        return configured or None

    # Session auto-rename: tracks which message-count thresholds have fired
    _session_rename_checkpoints: set = field(default_factory=set)

    def __post_init__(self):
        if self.sync_user_id is None:
            self.sync_user_id = resolve_telegram_state_user_id(self.user_id)
        else:
            self.sync_user_id = int(self.sync_user_id)

        # Isolation: Ensure each user has their own dedicated data and workspace directory
        user_data_path = user_state_root(self.sync_user_id)
        user_data_path.mkdir(parents=True, exist_ok=True)
        
        # If workspace is still the implicit cwd default in local/dev runs, switch
        # to the repo root. Desktop/runtime builds set EMPLOAI_HOME and should keep
        # their dedicated runtime home instead of leaking back to a repo checkout.
        runtime_home = os.getenv("EMPLOAI_HOME", "").strip()
        if self.workspace == Path.cwd() and not runtime_home:
            # telegram_agent.py runs from emploai/telegram_bot/, so parent is emploai/
            self.workspace = Path(__file__).resolve().parent.parent
            # Don't create dirs — workspace should already exist

        # Initialize session context
        session_registry = get_session_registry()
        self.session_context = session_registry.get_or_create_main_session(self.sync_user_id)

        # Initialize memory manager with user-isolated workspace
        self.memory_manager = get_memory_manager(self.workspace)

        # Initialize context loader
        self.context_loader = get_context_loader(self.workspace)
        self.context_loader.initialize_workspace()  # Create default files

        self.config_manager = get_config_manager()

        # Initialize live config
        self.live_config = get_live_config(self.workspace / "config.json")
        self.live_config.import_from_env()  # Load from env vars
        configured_default_model = self._configured_default_model()
        if configured_default_model and self.current_model == DEFAULT_RUNTIME_MODEL:
            self.current_model = configured_default_model
        if not self.default_planner_model:
            self.default_planner_model = self._configured_default_planner_model(self.current_model)

        # Initialize existing managers - isolation by user_id
        user_base_path = user_state_root(self.sync_user_id)
        self.session_manager = SessionManager(base_path=user_base_path)

        self._initialize_runtime_session()
        
        # Initialize skills and hooks systems
        self.skill_registry = get_skill_registry()
        self.hook_manager = get_hook_manager()
        self.file_processor = get_file_processor()
        self.analytics_tracker = get_analytics_tracker()

        # Enhance skills
        self.enhanced_skills = enhance_skill_registry(self.skill_registry)

        self._init_clients()
        self.ensure_current_model_available()

        from cli.agent_tools.context_manager import ContextManager, DEFAULT_CONTEXT_SIZES
        self.context_manager = ContextManager(
            model_context_sizes=DEFAULT_CONTEXT_SIZES,
            compression_client=self.gemini_openai_client,
            compression_model="gemini-3.1-flash-lite",
            provider_clients={
                "openai": self.openai_client,
                "openai-codex": self.openai_codex_client,
                "anthropic": self.anthropic_client,
                "google": self.gemini_openai_client or self.google_client,
                "xai": self.xai_client,
                "deepseek": self.deepseek_client,
                "openrouter": self.openrouter_client,
                "nvidia": self.nvidia_client,
            },
        )

        def path_confirm_callback(msg: str) -> bool:
            """Allow all path/command adjustments silently without user friction."""
            return True

        self.rebuild_tool_executor(confirm_callback=path_confirm_callback)

    def _initialize_runtime_session(self) -> None:
        """Bootstrap runtime state from the current session or create a fresh one."""
        current_id = self.session_manager.get_current_session_id() if self.session_manager else None
        should_create = self.create_new_session_on_init or not current_id
        target_session_id = current_id

        if should_create:
            self.session = self.session_manager.create_session(
                workspace=self._preferred_session_workspace(),
                name=f"Session {datetime.datetime.now().strftime('%H:%M')}",
                model=self.current_model,
                variant=self.current_variant,
                agent_mode="auto",
                planner_model=self.planner_model or self.default_planner_model,
                enabled_tool_packs=list(getattr(self, "enabled_tool_packs", []) or default_enabled_tool_packs()),
                telegram_bot_config_id=getattr(self, "telegram_bot_config_id", None),
                headless_eligible=bool(getattr(self, "headless_eligible", False)),
            )
            self.session_manager.set_current_session(self.session.id)
            target_session_id = self.session.id

        if not target_session_id:
            self.shared_current_session_id = self._resolve_shared_current_session_id()
            return

        try:
            self.load_session_by_id(target_session_id)
        except Exception:
            if should_create:
                raise
            self.session = self.session_manager.create_session(
                workspace=self._preferred_session_workspace(),
                name=f"Session {datetime.datetime.now().strftime('%H:%M')}",
                model=self.current_model,
                variant=self.current_variant,
                agent_mode="auto",
                planner_model=self.planner_model or self.default_planner_model,
                enabled_tool_packs=list(getattr(self, "enabled_tool_packs", []) or default_enabled_tool_packs()),
                telegram_bot_config_id=getattr(self, "telegram_bot_config_id", None),
                headless_eligible=bool(getattr(self, "headless_eligible", False)),
            )
            self.session_manager.set_current_session(self.session.id)
            self.load_session_by_id(self.session.id)
        self.shared_current_session_id = self._resolve_shared_current_session_id()

    def _resolve_external_app_current_session_id(self) -> Optional[str]:
        runtime_home = os.getenv("EMPLOAI_HOME", "").strip()
        if runtime_home:
            workspace = Path(runtime_home).expanduser().resolve()
        else:
            workspace = Path(__file__).resolve().parent.parent
        try:
            from app_backend.session_bridge import AppSessionBridge

            bridge = AppSessionBridge(user_id=self._sync_state_user_id(), workspace=workspace)
            current = bridge.get_current_session()
        except Exception:
            return None
        session_id = str(getattr(current, "id", "") or "").strip()
        return session_id or None

    def _resolve_shared_current_session_id(self) -> Optional[str]:
        external_id = self._resolve_external_app_current_session_id()
        if external_id:
            return external_id
        if self.session_manager:
            current_id = str(self.session_manager.get_current_session_id() or "").strip()
            if current_id:
                return current_id
        if self.session:
            session_id = str(getattr(self.session, "id", "") or "").strip()
            if session_id:
                return session_id
        return None

    def _sync_state_user_id(self) -> int:
        return int(self.sync_user_id) if self.sync_user_id is not None else int(self.user_id)

    def _preferred_session_workspace(self) -> Path:
        preferred = normalize_legacy_workspace_path(self.workspace, fallback=self.workspace)
        return preferred or self.workspace

    def rebuild_tool_executor(self, confirm_callback=None) -> ToolExecutor:
        """Rebuild the tool executor while preserving session wiring."""
        callback = confirm_callback
        if callback is None and self.tool_executor:
            callback = self.tool_executor.confirm_callback
        if callback is None:
            callback = lambda _msg: True

        existing_handlers = {}
        if self.tool_executor and getattr(self.tool_executor, "custom_tool_handlers", None):
            existing_handlers = dict(self.tool_executor.custom_tool_handlers)

        self.tool_executor = ToolExecutor(
            self.workspace,
            confirm_callback=callback,
            single_agent=self.single_agent,
            check_interruption=lambda: self.should_interrupt,
            get_interrupt_message=self.get_interrupt_message,
            clear_interrupt=self._clear_interrupt,
            activate_deferred_interrupts=self.activate_deferred_interrupts,
            has_deferred_interrupts=self.has_deferred_interrupts,
            skill_registry=self.skill_registry,
            active_skills=self.active_skills,
        )
        self.tool_executor.allowed_tool_names_provider = (
            lambda: getattr(self, "current_turn_allowed_tool_names", None)
        )
        workspace_for_security = str(getattr(self, "workspace", ""))
        self.tool_executor.security_context_provider = lambda: {
            "permission_mode": getattr(getattr(self, "session", None), "security_permission_mode", "standard"),
            "workspace_path": workspace_for_security,
            "workspace_binding_status": getattr(getattr(self, "session", None), "workspace_binding_status", None),
            "workspace_write_enabled": (
                None
                if not workspace_for_security
                else Path(workspace_for_security).expanduser().exists()
            ),
            "surface": "telegram",
            "session_id": getattr(getattr(self, "session", None), "id", None),
            "identity_id": getattr(getattr(self, "session", None), "fleet_identity_id", None),
        }
        self.tool_executor.custom_tool_handlers = existing_handlers
        return self.tool_executor

    def set_workspace(self, workspace: Path, *, rebuild_tool_executor: bool = False) -> Path:
        """Update the active workspace without dropping executor hooks."""
        resolved = Path(workspace).expanduser().resolve()
        current_workspace = self.workspace.expanduser().resolve()

        if self.is_processing and resolved != current_workspace:
            raise RuntimeError("Cannot change workspace while a task is still running")

        self.workspace = resolved
        self.memory_manager = get_memory_manager(resolved)
        self.context_loader = get_context_loader(resolved)
        self.live_config = LiveConfig(resolved / "config.json")
        self.live_config.import_from_env()
        if not self.default_planner_model:
            self.default_planner_model = self._configured_default_planner_model(self.current_model)

        heartbeat_manager = getattr(self, "heartbeat_manager", None)
        if heartbeat_manager and getattr(heartbeat_manager, "workspace", None) != resolved:
            was_enabled = bool(getattr(heartbeat_manager, "enabled", False))
            interval_seconds = int(getattr(heartbeat_manager, "interval_seconds", 1800) or 1800)
            announcement_callback = getattr(heartbeat_manager, "announcement_callback", None)
            agent_callback = getattr(heartbeat_manager, "agent_callback", None)
            try:
                heartbeat_manager.stop()
            except Exception:
                pass
            from shared.heartbeat import get_heartbeat_manager

            self.heartbeat_manager = get_heartbeat_manager(
                workspace=resolved,
                interval_seconds=interval_seconds,
                announcement_callback=announcement_callback,
                agent_callback=agent_callback,
            )
            if was_enabled:
                self.heartbeat_manager.start()

        if self.tool_executor and not rebuild_tool_executor:
            self.tool_executor.workspace_path = resolved
            self.tool_executor.single_agent = self.single_agent
            self.tool_executor.skill_registry = self.skill_registry
            self.tool_executor.active_skills = self.active_skills
        elif rebuild_tool_executor:
            self.rebuild_tool_executor()
        if getattr(self, "unified_agent", None):
            self.unified_agent.workspace = resolved
        return self.workspace

    def _clear_interrupt(self):
        """Consume one active interrupt and keep any queued steering intact."""
        if self.interrupt_queue:
            self.interrupt_queue.pop(0)
        self.interrupt_message = self.interrupt_queue[0] if self.interrupt_queue else None
        self.should_interrupt = bool(self.interrupt_message)

    def get_interrupt_message(self) -> Optional[str]:
        """Return the next immediate steering/interrupt message."""
        if self.interrupt_queue:
            return self.interrupt_queue[0]
        return self.interrupt_message

    def queue_interrupt(self, message: str, *, deferred: bool = False) -> None:
        """Queue a steering message for immediate or post-tool activation."""
        clean = (message or "").strip()
        if not clean:
            return
        if deferred:
            self.deferred_interrupt_queue.append(clean)
            return
        self.interrupt_queue.append(clean)
        self.interrupt_message = self.interrupt_queue[0]
        self.should_interrupt = True

    def has_deferred_interrupts(self) -> bool:
        return bool(self.deferred_interrupt_queue)

    def activate_deferred_interrupts(self) -> bool:
        if not self.deferred_interrupt_queue:
            return False
        self.interrupt_queue.extend(self.deferred_interrupt_queue)
        self.deferred_interrupt_queue.clear()
        self.interrupt_message = self.interrupt_queue[0] if self.interrupt_queue else None
        self.should_interrupt = bool(self.interrupt_message)
        return self.should_interrupt

    def get_browser_task_context(self) -> BrowserTaskContext:
        """Return the current task-scoped browser context, resetting if stale."""
        if self.browser_task_context.task_id != self.current_task_id:
            self.browser_task_context = self._new_browser_task_context(self.current_task_id)
        return self.browser_task_context

    def reset_browser_task_context(self, task_id: Optional[int] = None) -> BrowserTaskContext:
        """Reset browser backend and task-owned tab tracking."""
        resolved_task_id = self.current_task_id if task_id is None else task_id
        self.browser_task_context = self._new_browser_task_context(resolved_task_id)
        return self.browser_task_context

    def start_browser_task(self, task_id: int, task_text: Optional[str] = None) -> BrowserTaskContext:
        """Create a fresh browser context for a newly started task."""
        self.browser_task_context = self._new_browser_task_context(task_id, task_text=task_text)
        return self.browser_task_context

    def _new_browser_task_context(
        self,
        task_id: int,
        *,
        task_text: Optional[str] = None,
    ) -> BrowserTaskContext:
        scoped_task_text = task_text
        if scoped_task_text is None:
            scoped_task_text = self.last_user_message
        return BrowserTaskContext(
            task_id=task_id,
            requires_real_chrome=_task_requires_real_chrome(scoped_task_text),
        )

    def update_browser_task_context(self, result: Optional[Dict[str, Any]], *, owned_tab: bool = False) -> BrowserTaskContext:
        """Apply browser action results back into the current task context."""
        context = self.get_browser_task_context()
        if not result:
            return context

        if result.get("backend"):
            context.backend = result.get("backend")

        error_type = result.get("error_type")
        if result.get("error"):
            if error_type in {"connection", "protocol", "timeout"}:
                context.healthy = False
            return context

        context.healthy = bool(result.get("success", True))

        tab_id = result.get("tab_id")
        if tab_id is not None:
            context.primary_tab_id = tab_id
            if owned_tab and tab_id not in context.owned_tab_ids:
                context.owned_tab_ids.append(tab_id)

        window_id = result.get("window_id")
        if window_id is not None:
            context.primary_window_id = window_id

        if result.get("url") is not None:
            context.last_url = result.get("url")
        if result.get("title") is not None:
            context.last_title = result.get("title")
        if result.get("snapshot_hash") is not None:
            context.last_snapshot_hash = result.get("snapshot_hash")

        closed_tab_id = result.get("closed_tab_id")
        if closed_tab_id in context.owned_tab_ids:
            context.owned_tab_ids = [tab for tab in context.owned_tab_ids if tab != closed_tab_id]
        if closed_tab_id is not None and context.primary_tab_id == closed_tab_id:
            context.primary_tab_id = result.get("tab_id")

        return context

    def _init_clients(self):
        """Initialize LLM clients from config/env."""
        openai_key = self.config_manager.get_api_key("openai") or os.getenv("OPENAI_API_KEY")
        anthropic_key = self.config_manager.get_api_key("anthropic") or os.getenv("ANTHROPIC_API_KEY")
        xai_key = self.config_manager.get_api_key("xai") or os.getenv("XAI_API_KEY")
        deepseek_key = self.config_manager.get_api_key("deepseek") or os.getenv("DEEPSEEK_API_KEY")
        openrouter_key = self.config_manager.get_api_key("openrouter") or os.getenv("OPENROUTER_API_KEY")
        nvidia_key = self.config_manager.get_api_key("nvidia") or os.getenv("NVIDIA_API_KEY")
        google_key = self.config_manager.get_api_key("google") or os.getenv("GOOGLE_API_KEY")

        self.openai_client = OpenAI(api_key=openai_key) if openai_key else None
        self.anthropic_client = Anthropic(api_key=anthropic_key) if anthropic_key else None
        self.xai_client = OpenAI(api_key=xai_key, base_url="https://api.x.ai/v1") if xai_key else None
        self.deepseek_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com") if deepseek_key else None
        self.openrouter_client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1") if openrouter_key else None
        self.nvidia_client = OpenAI(api_key=nvidia_key, base_url="https://integrate.api.nvidia.com/v1") if nvidia_key else None
        self.openai_codex_client = create_codex_client() if is_codex_auth_configured() else None
        
        if google_key:
            self.google_client = None
            self.gemini_openai_client = create_gemini_openai_client(google_key)
        else:
            self.google_client = None
            self.gemini_openai_client = None

    def get_available_variants(self) -> List[str]:
        """Get available variants for current model."""
        variant_info = MODEL_VARIANTS.get(self.current_model, {"variants": ["standard"]})
        return variant_info.get("variants", ["standard"])

    def get_enabled_providers(self) -> set[str]:
        """Return providers that currently have configured credentials."""
        return enabled_providers_from_clients(
            openai_client=self.openai_client,
            anthropic_client=self.anthropic_client,
            google_client=self.google_client or self.gemini_openai_client,
            xai_client=self.xai_client,
            deepseek_client=self.deepseek_client,
            openrouter_client=self.openrouter_client,
            nvidia_client=self.nvidia_client,
            openai_codex_client=self.openai_codex_client,
        )

    def get_available_models(self, candidate_models: Optional[List[str]] = None) -> List[str]:
        """Return models filtered to providers that currently have credentials."""
        source_models = candidate_models or list(MODEL_CONFIGS.keys())
        return filter_models_by_provider_access(
            source_models,
            MODEL_CONFIGS,
            self.get_enabled_providers(),
        )

    def get_supported_planner_models(self, candidate_models: Optional[List[str]] = None) -> List[str]:
        """Return models that can be used by the lightweight planner helper."""
        available = self.get_available_models(candidate_models)
        supported: List[str] = []
        for model in available:
            config = MODEL_CONFIGS.get(model, {})
            provider = str(config.get("provider", "unknown"))
            if provider == "google":
                if self.gemini_openai_client is not None:
                    supported.append(model)
                continue
            if provider in {"openai", "openai-codex", "anthropic", "xai", "deepseek", "openrouter", "nvidia"}:
                supported.append(model)
        default_planner = self._configured_default_planner_model(self.current_model)
        if default_planner in supported:
            supported = [default_planner, *[model for model in supported if model != default_planner]]
        return supported

    def ensure_planner_model_available(self, candidate_models: Optional[List[str]] = None) -> bool:
        """Keep automatic/default planner selection available and provider-aligned."""
        supported_models = self.get_supported_planner_models(candidate_models)
        supported = set(supported_models)
        current_provider = provider_for_model(self.current_model)
        planner_provider = provider_for_model(self.planner_model or "")
        known_default_planners = {
            OPENAI_DEFAULT_PLANNER_MODEL,
            OPENAI_CODEX_DEFAULT_PLANNER_MODEL,
            ANTHROPIC_DEFAULT_PLANNER_MODEL,
            GOOGLE_DEFAULT_PLANNER_MODEL,
        }
        effective_default = self._configured_default_planner_model(self.current_model)
        registry_first_planner = next((model for model in supported_models if model != effective_default), None)
        changed = False

        if self.planner_model:
            planner_unavailable = self.planner_model not in supported
            stale_default_provider = (
                self.planner_model in known_default_planners
                and current_provider in {"openai", "openai-codex", "anthropic"}
                and planner_provider
                and planner_provider != current_provider
            )
            stale_registry_first_default = (
                bool(effective_default)
                and self.planner_model == registry_first_planner
                and self.planner_model != effective_default
            )
            if planner_unavailable or stale_default_provider or stale_registry_first_default:
                self.planner_model = None
                changed = True

        if self.planner_model is None:
            next_default = effective_default
            if next_default and next_default not in supported and supported_models:
                next_default = supported_models[0]
            if self.default_planner_model != next_default:
                self.default_planner_model = next_default
                changed = True

        return changed

    def get_available_model_groups(self, candidate_models: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Return filtered model groups by provider."""
        return group_models_by_provider(
            self.get_available_models(candidate_models),
            MODEL_CONFIGS,
        )

    def ensure_current_model_available(self, candidate_models: Optional[List[str]] = None) -> bool:
        """Move off an unavailable model when its provider is not configured."""
        available_models = self.get_available_models(candidate_models)
        preferred = first_available_model(available_models, self.current_model)
        provider_default = self._provider_default_model_pair().model
        if self.current_model not in available_models and provider_default in available_models:
            preferred = provider_default
        if preferred is None or preferred == self.current_model:
            return self.ensure_planner_model_available(candidate_models)

        self.current_model = preferred
        available_variants = self.get_available_variants()
        if self.current_variant not in available_variants:
            self.current_variant = available_variants[0] if available_variants else "standard"
        self.ensure_planner_model_available(candidate_models)
        return True

    def get_client_for_specific_model(self, model_name: str):
        """Get the appropriate client for an arbitrary configured model."""
        config = MODEL_CONFIGS.get(model_name, {})
        provider = config.get("provider", "anthropic")

        if provider == "openai":
            return self.openai_client, provider
        if provider == "openai-codex":
            return self.openai_codex_client, provider
        if provider == "anthropic":
            return self.anthropic_client, provider
        if provider == "xai":
            return self.xai_client, provider
        if provider == "deepseek":
            return self.deepseek_client, provider
        if provider == "openrouter":
            return self.openrouter_client, provider
        if provider == "nvidia":
            return self.nvidia_client, provider
        if provider == "google":
            return self.gemini_openai_client or self.google_client, provider
        return None, provider

    def get_client_for_model(self):
        """Get the appropriate LLM client for the current model."""
        config = MODEL_CONFIGS.get(self.current_model, {})
        provider = config.get("provider", "anthropic")

        if provider == "openai":
            return self.openai_client, provider
        if provider == "openai-codex":
            return self.openai_codex_client, provider
        if provider == "anthropic":
            return self.anthropic_client, provider
        if provider == "xai":
            return self.xai_client, provider
        if provider == "deepseek":
            return self.deepseek_client, provider
        if provider == "openrouter":
            return self.openrouter_client, provider
        if provider == "nvidia":
            return self.nvidia_client, provider
        if provider == "google":
            return self.gemini_openai_client or self.google_client, provider
        return self.anthropic_client, "anthropic"

    def save_session(self):
        """Save current TelegramSession state to the SessionManager."""
        if not self.session_manager:
            return

        # Get the current session object from manager or create/use current
        current_id = str(getattr(getattr(self, "session", None), "id", "") or "").strip()
        if not current_id:
            current_id = self.session_manager.get_current_session_id()
        session_obj = None
        
        if current_id:
            try:
                session_obj = self.session_manager.load_session(current_id, set_current=False)
            except ValueError:
                pass
        
        if not session_obj:
            session_obj = self.session_manager.create_session(
                model=self.current_model,
                variant=self.current_variant,
                agent_mode=self.agent_mode,
                planner_model=self.planner_model or self.default_planner_model,
                workspace=self._preferred_session_workspace(),
                enabled_tool_packs=list(getattr(self, "enabled_tool_packs", []) or []),
                telegram_bot_config_id=getattr(self, "telegram_bot_config_id", None),
                headless_eligible=bool(getattr(self, "headless_eligible", False)),
            )

        # Update session with current runtime state
        session_obj.chat_history = self.chat_history
        session_obj.event_timeline = list(getattr(self, "event_timeline", []) or [])
        session_obj.workspace = str(self.workspace)
        session_obj.model = self.current_model
        session_obj.variant = self.current_variant
        session_obj.agent_mode = "auto"
        session_obj.planner_model = self.planner_model
        session_obj.enabled_tool_packs = list(getattr(self, "enabled_tool_packs", []) or [])
        session_obj.telegram_bot_config_id = getattr(self, "telegram_bot_config_id", None)
        session_obj.headless_eligible = bool(getattr(self, "headless_eligible", False))
        session_obj.task_history = self.task_history
        session_obj.active_task_id = self.active_task_id
        session_obj.task_board_armed_next_turn = bool(self.task_board_armed_next_turn)
        session_obj.active_skills = self.active_skills
        session_obj.last_context_compaction = self.last_context_compaction

        # Save to disk
        self.session_manager.save_session(session_obj)

    def load_session_by_id(self, session_id: str, *, set_current: bool = True):
        """Load session state from disk into this TelegramSession."""
        if not self.session_manager:
            return

        current_id = self.session_manager.get_current_session_id()
        if self.is_processing:
            if current_id == session_id:
                return
            raise RuntimeError("Cannot switch sessions while a task is still running")

        try:
            session_obj = self.session_manager.load_session(session_id, set_current=set_current)
        except TypeError:
            session_obj = self.session_manager.load_session(session_id)
        self.session = session_obj

        # Sync to runtime state
        self.chat_history = session_obj.chat_history
        self.event_timeline = list(getattr(session_obj, "event_timeline", []) or [])
        if session_obj.workspace:
            self.set_workspace(Path(session_obj.workspace))
        self.current_model = _normalize_model_name(session_obj.model)
        self.current_variant = session_obj.variant
        self.planner_model = session_obj.planner_model
        if self.planner_model is None:
            self.default_planner_model = self._configured_default_planner_model(self.current_model)
        self.enabled_tool_packs = list(getattr(session_obj, "enabled_tool_packs", []) or [])
        self.telegram_bot_config_id = getattr(session_obj, "telegram_bot_config_id", None)
        self.headless_eligible = bool(getattr(session_obj, "headless_eligible", False))
        self.agent_mode = "auto"
        self.task_history = session_obj.task_history
        self.active_task_id = session_obj.active_task_id
        self.task_board_armed_next_turn = bool(getattr(session_obj, "task_board_armed_next_turn", False))
        self.active_skills = session_obj.active_skills
        self.last_context_compaction = session_obj.last_context_compaction
        self.shared_current_session_id = str(session_obj.id or "").strip() or self.shared_current_session_id

        # Clear specific agent histories to avoid context leaks
        if self.single_agent:
            self.single_agent.messages = []
        if self.refined_agent:
            self.refined_agent.messages = []
        if self.unified_agent:
            self.unified_agent.conversation_history = []

    def refresh_session_from_disk(self, session_id: Optional[str] = None) -> bool:
        """Refresh the active shared session from disk when the runtime is idle."""
        if not self.session_manager or self.is_processing:
            return False

        target_session_id = str(
            session_id
            or self.shared_current_session_id
            or self.session_manager.get_current_session_id()
            or ""
        ).strip()
        if not target_session_id:
            return False

        try:
            self.load_session_by_id(target_session_id)
        except Exception:
            return False
        return True

    def _summarize_history(self, history: List[Dict], max_messages: int = 10) -> str:
        """Simple history summarizer for context sharing."""
        if not history:
            return ""

        subset = history[-max_messages:]
        lines = []
        for msg in subset:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            if len(content) > 150:
                content = content[:150] + "..."
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def auto_rename_session(self):
        """Generate a short session name from conversation history using the cheapest LLM.
        Fires at message counts 3 and 20, then never again for this session."""
        # Count user+assistant messages (skip system, tool, etc.)
        msg_count = sum(
            1 for m in self.chat_history
            if m.get("role") in ("user", "assistant")
        )

        # Determine which checkpoint we're at
        checkpoint = None
        if msg_count >= 3 and 3 not in self._session_rename_checkpoints:
            checkpoint = 3
        elif msg_count >= 20 and 20 not in self._session_rename_checkpoints:
            checkpoint = 20

        if checkpoint is None:
            return

        self._session_rename_checkpoints.add(checkpoint)

        # Build a compact conversation snippet for the summarizer
        snippet_msgs = self.chat_history[-min(msg_count, 10):]
        snippet_lines = []
        for m in snippet_msgs:
            role = m.get("role", "user")
            content = str(m.get("content", ""))
            if len(content) > 200:
                content = content[:200] + "..."
            snippet_lines.append(f"{role}: {content}")
        snippet = "\n".join(snippet_lines)

        prompt_messages = [
            {"role": "system", "content": (
                "Generate a very short session title (3-6 words max) that summarizes "
                "what this conversation is about. Return ONLY the title, nothing else. "
                "No quotes, no punctuation, no explanation."
            )},
            {"role": "user", "content": snippet},
        ]

        # Pick the cheapest available client
        new_name = None
        try:
            if self.openai_client:
                resp = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=prompt_messages,
                    max_tokens=20,
                )
                new_name = resp.choices[0].message.content.strip()
            elif self.anthropic_client:
                resp = self.anthropic_client.messages.create(
                    model="claude-haiku-4-20250514",
                    max_tokens=20,
                    system=prompt_messages[0]["content"],
                    messages=[{"role": "user", "content": snippet}],
                )
                new_name = resp.content[0].text.strip()
            elif self.deepseek_client:
                resp = self.deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=prompt_messages,
                    max_tokens=20,
                )
                new_name = resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning(f"[AUTO-RENAME] Failed to generate session name: {exc}")
            return

        if not new_name or len(new_name) > 60:
            return

        # Apply the new name
        try:
            current_id = self.session_manager.get_current_session_id()
            if current_id:
                self.session_manager.rename_session(current_id, new_name)
                logger.info(f"[AUTO-RENAME] Session renamed to: {new_name}")
        except Exception as exc:
            logger.warning(f"[AUTO-RENAME] Failed to rename session: {exc}")

    def init_single_agent(self, app: Application, loop: asyncio.AbstractEventLoop):
        """Initialize SingleAgent with Telegram logger bridge."""
        self.bind_telegram_runtime(app, loop)

        def logger_func(text: str):
            print(f"[AGENT] {text}")
            if self._app and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._send_log(text), self._loop
                )

        self.single_agent = SingleAgent(logger=logger_func)
        if self.tool_executor:
            self.tool_executor.single_agent = self.single_agent

        self._init_refined_agent(app, loop, logger_func)

    def _init_refined_agent(self, app: Application, loop: asyncio.AbstractEventLoop, logger_func):
        """Initialize RefinedAgent with spawn tool and cron scheduler."""

        async def announcement_callback(text: str):
            """Send announcement to user via Telegram."""
            if self._app and self.user_id:
                try:
                    announcement_text = text[:4000] if len(text) > 4000 else text
                    await self._app.bot.send_message(
                        chat_id=self.user_id,
                        text=announcement_text,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception as exc:
                    print(f"[ANNOUNCE ERROR] {exc}")

        async def spawn_callback(job_id: str, prompt: str):
            """Callback for cron scheduler to run jobs through the live unified path."""
            print(f"[CRON] Running unified job {job_id}: {prompt[:50]}...")
            task_label = f"cron-{job_id}"
            if self._app and self.user_id:
                try:
                    await self._app.bot.send_message(
                        chat_id=self.user_id,
                        text=(
                            f"🧠 **Scheduled Job Running**\n\n"
                            f"Job ID: `{job_id}`\n"
                            f"Execution Path: `unified`\n"
                            f"Task: `{task_label}`"
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception as exc:
                    print(f"[CRON SPAWN ANNOUNCE ERROR] {exc}")

            try:
                result_text = await run_cron_job_via_unified_flow(
                    self,
                    prompt,
                    max_turns=30,
                )
                if self._app and self.user_id:
                    try:
                        await self._app.bot.send_message(
                            chat_id=self.user_id,
                            text=f"🤖 **Scheduled Job Report [{task_label}]**\n\n{result_text[:3500]}",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    except Exception as exc:
                        print(f"[CRON RESULT ANNOUNCE ERROR] {exc}")
                return task_label
            except Exception as exc:
                print(f"[CRON UNIFIED RUN ERROR] {exc}")
                if self._app and self.user_id:
                    try:
                        await self._app.bot.send_message(
                            chat_id=self.user_id,
                            text=f"❌ **Scheduled Job Failed [{task_label}]**\n\n{str(exc)[:3500]}",
                            parse_mode=ParseMode.MARKDOWN,
                        )
                    except Exception as announce_exc:
                        print(f"[CRON FAILURE ANNOUNCE ERROR] {announce_exc}")
                return None

        self.cron_scheduler = get_scheduler(
            job_store="jobs.json",
            spawn_callback=spawn_callback,
            announcement_callback=announcement_callback,
        )
        loop.call_soon_threadsafe(lambda: asyncio.create_task(self.cron_scheduler.start()))

        self.spawn_tool = get_spawn_tool(
            agent_factory=lambda headless=True: create_refined_agent(
                model="claude-sonnet-4-5-20250929",
                headless=headless,
                logger=logger_func,
            ),
            announcement_callback=announcement_callback,
        )

        # Keep refined agent initialization intact for legacy/background paths,
        # but cron execution now routes through the unified live tool-loop path.
        self.refined_agent = RefinedAgent(
            model="claude-sonnet-4-5-20250929",
            headless=True,
            logger=logger_func,
            spawn_tool=self.spawn_tool,
            cron_scheduler=self.cron_scheduler,
        )

    def bind_telegram_runtime(
        self,
        app: Application,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._app = app
        self._loop = loop or self._loop
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                return
        if self._channel_sync_subscription_id:
            return

        async def _callback(event: Dict[str, Any]) -> None:
            await self._handle_channel_sync_event(event)

        self._channel_sync_subscription_id = get_channel_sync_hub().subscribe(
            user_id=self._sync_state_user_id(),
            channel="telegram",
            callback=_callback,
            loop=self._loop,
        )

    def _telegram_bot_store(self) -> TelegramBotConfigStore:
        store = TelegramBotConfigStore(user_id=self._sync_state_user_id())
        store.ensure_default_from_env(bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        return store

    def _resolved_telegram_bot_config(self) -> Optional[Dict[str, Any]]:
        store = self._telegram_bot_store()
        target_id = str(getattr(self, "telegram_bot_config_id", "") or "").strip()
        if target_id:
            config = store.get_config(target_id)
            if config:
                return config
        return store.default_config()

    def _resolved_telegram_bot(self) -> Optional[Bot]:
        config = self._resolved_telegram_bot_config()
        if not config:
            return getattr(self._app, "bot", None)
        token = str(config.get("bot_token") or "").strip()
        if not token:
            return getattr(self._app, "bot", None)
        current_token = str(os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip()
        if current_token and token == current_token and self._app:
            return self._app.bot
        return Bot(token=token)

    def _mark_last_emitting_session(self) -> None:
        config = self._resolved_telegram_bot_config()
        session_id = str(getattr(getattr(self, "session", None), "id", "") or "").strip()
        if not config or not session_id:
            return
        self._telegram_bot_store().set_last_emitting_session(
            bot_config_id=str(config.get("id") or ""),
            session_id=session_id,
        )

    def _current_session_label(self) -> str:
        name = str(getattr(getattr(self, "session", None), "name", "") or "").strip()
        return name or "App Chat"

    def _telegram_chat_id(self) -> Optional[int]:
        try:
            chat_id = int(getattr(self, "user_id", 0) or 0)
        except Exception:
            return None
        return chat_id if chat_id > 0 else None

    async def _safe_send_bot_message(self, text: str) -> None:
        bot = self._resolved_telegram_bot()
        chat_id = self._telegram_chat_id()
        if not bot or chat_id is None:
            return
        if len(text) > 4000:
            text = text[:3900] + "... (truncated)"
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            self._mark_last_emitting_session()
        except Exception:
            try:
                clean_text = text.replace("*", "").replace("_", "").replace("`", "")
                await bot.send_message(chat_id=chat_id, text=clean_text)
                self._mark_last_emitting_session()
            except Exception:
                logger.exception("Failed to mirror synchronized message to Telegram")

    async def _handle_channel_sync_event(self, event: Dict[str, Any]) -> None:
        bot = self._resolved_telegram_bot()
        chat_id = self._telegram_chat_id()
        if not bot or chat_id is None:
            return

        event_session_id = str(event.get("session_id") or "").strip()
        current_id = str(self.shared_current_session_id or "").strip()
        if not current_id and self.session_manager:
            current_id = str(self.session_manager.get_current_session_id() or "").strip()

        origin_channel = str(event.get("origin_channel") or "").strip().lower()
        if origin_channel == "telegram":
            return

        payload = event.get("payload") or {}
        event_type = str(event.get("type") or "").strip()
        session_reloaded = False

        if event_type == "current_session_changed":
            next_session_id = event_session_id or str(payload.get("current_session_id") or "").strip()
            if not next_session_id:
                return
            self.shared_current_session_id = next_session_id
            if next_session_id != current_id:
                try:
                    self.load_session_by_id(next_session_id)
                    session_reloaded = True
                except Exception:
                    logger.info("Following shared current session %s without local Telegram session file", next_session_id)
            else:
                session_reloaded = self.refresh_session_from_disk(next_session_id)
            return

        if event_session_id and event_session_id != current_id and origin_channel == "app":
            self.shared_current_session_id = event_session_id
            try:
                self.load_session_by_id(event_session_id)
                session_reloaded = True
                current_id = event_session_id
            except Exception:
                logger.info("Mirroring app-origin shared session %s without local Telegram session file", event_session_id)
                current_id = event_session_id

        if not event_session_id or event_session_id != current_id:
            return

        if origin_channel == "app" and not session_reloaded:
            self.refresh_session_from_disk(event_session_id)

        if event_type == "user_message":
            message = payload.get("message") or {}
            text = str(message.get("content") or "").strip()
            if not text:
                return
            display_label = str(message.get("display_label") or "App").strip() or "App"
            try:
                bot = self._resolved_telegram_bot()
                if bot:
                    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            await self._safe_send_bot_message(
                f"📲 *{self._current_session_label()} · {display_label}*\n\n{text}"
            )
            return

        if event_type == "assistant_final":
            text = str(payload.get("text") or "").strip()
            if not text:
                return
            await self._safe_send_bot_message(f"*{self._current_session_label()}*\n\n{text}")
            return

        if event_type == "tool_use":
            if not self.verbose_mode:
                return
            formatted = _format_verbose_tool_message(payload)
            await self._safe_send_bot_message(f"*{self._current_session_label()}*\n\n{formatted}")
            return

    async def _send_log(self, message: str):
        """Send agent log to Telegram and print detailed log to console."""
        if "[TOOL]" in message:
            logger.info(f"🔨 {message.strip()}")
        elif "[RESULT]" in message:
            clean_result = message.replace("[RESULT]", "").strip()
            if len(clean_result) > 500:
                logger.info(f"✅ RESULT: {clean_result[:500]}... (truncated)")
            else:
                logger.info(f"✅ RESULT: {clean_result}")
        elif "[ERROR]" in message:
            logger.error(f"❌ {message.strip()}")
        elif "Turn" in message:
            logger.info(f"🔄 {message.strip()}")
        elif "[COMPLETE]" in message:
            logger.info(f"🏁 {message.strip()}")
        elif "[STOPPED]" in message:
            logger.warning(f"🛑 {message.strip()}")
        elif "[PAUSED]" in message:
            logger.warning(f"⏸️ {message.strip()}")
        else:
            logger.info(f"🤖 {message.strip()}")

        if "Turn" in message:
            text = f"🔄 {message.strip()}"
        elif "[TOOL]" in message:
            text = f"🛠️ `{message.strip()}`"
        elif "[RESULT]" in message:
            clean = message.replace("[RESULT]", "").strip()
            if len(clean) > 2000:
                clean = clean[:2000] + "..."
            text = f"✅ `{clean}`"
        elif "[ERROR]" in message:
            text = f"❌ {message}"
        elif "[COMPLETE]" in message:
            text = f"🏁 {message.replace('[COMPLETE]', '').strip()}"
        else:
            text = message

        await self._safe_send_bot_message(text)


user_sessions: Dict[int, TelegramSession] = {}


def set_telegram_application(application: Application) -> None:
    global _telegram_application, _telegram_loop
    _telegram_application = application
    try:
        _telegram_loop = asyncio.get_running_loop()
    except RuntimeError:
        _telegram_loop = None
    if _telegram_application is not None and _telegram_loop is not None:
        for session in user_sessions.values():
            try:
                session.bind_telegram_runtime(_telegram_application, _telegram_loop)
            except Exception:
                logger.exception("Failed to bind Telegram runtime for user %s", session.user_id)


def get_session(
    user_id: int,
    *,
    workspace: Optional[Path] = None,
    create_new_session: bool = False,
) -> TelegramSession:
    """Get or create the live runtime session for a user."""
    if user_id not in user_sessions:
        init_kwargs: Dict[str, Any] = {
            "user_id": user_id,
            "create_new_session_on_init": create_new_session,
        }
        if workspace is not None:
            init_kwargs["workspace"] = workspace
        user_sessions[user_id] = TelegramSession(**init_kwargs)
    session = user_sessions[user_id]
    if _telegram_application is not None and _telegram_loop is not None:
        session.bind_telegram_runtime(_telegram_application, _telegram_loop)
    return session


def track_command_usage(session: TelegramSession, command: str) -> None:
    """Track command usage for analytics."""
    if session.analytics_tracker:
        session.analytics_tracker.track_command(session.user_id, command)
