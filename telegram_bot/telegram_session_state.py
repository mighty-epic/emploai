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

from telegram.constants import ParseMode
from telegram.ext import Application

from cli.config_manager import get_config_manager
from cli.session_manager import SessionManager
from cli.agent_tools.executor import ToolExecutor
from cli.tui_constants import MODEL_CONFIGS, MODEL_VARIANTS
from single_agent.agent import SingleAgent
from single_agent.refined_agent import RefinedAgent, create_refined_agent
from single_agent.cron_scheduler import get_scheduler
from single_agent.spawn_tool import get_spawn_tool
from telegram_bot.cron_runner import run_cron_job_via_unified_flow

from bot_core.analytics import get_analytics_tracker, AnalyticsTracker
from bot_core.file_processor import get_file_processor, FileProcessor
from bot_core.hooks import get_hook_manager, HookManager
from bot_core.system_info import get_system_info
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

from openai import OpenAI
from anthropic import Anthropic
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


logger = logging.getLogger(__name__)


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


@dataclass
class TelegramSession:
    """Holds per-user state for the Telegram bot."""
    user_id: int
    current_model: str = "gpt-5.2"
    current_variant: str = "standard"
    agent_mode: str = "auto"  # Default to auto for full autonomous behavior
    max_turns: int = 100
    chat_history: List[Dict] = field(default_factory=list)

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
    xai_client: Optional[OpenAI] = None
    deepseek_client: Optional[OpenAI] = None
    openrouter_client: Optional[OpenAI] = None

    # Telegram context
    _app: Optional[Application] = None
    _loop: Optional[asyncio.AbstractEventLoop] = None

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
    last_task_text: Optional[str] = None
    message_id_map: Dict[int, int] = field(default_factory=dict)
    active_skills: List[str] = field(default_factory=list)

    # Wizard state
    wizard_state: Dict[str, Any] = field(default_factory=dict)

    # Thread safety
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    workspace: Path = field(default_factory=lambda: Path.cwd())

    def refresh_system_info(self):
        """Update system info string with current windows and hardware state."""
        from bot_core.system_info import get_system_info
        self.system_info = get_system_info()

    # Session auto-rename: tracks which message-count thresholds have fired
    _session_rename_checkpoints: set = field(default_factory=set)

    def __post_init__(self):
        # Isolation: Ensure each user has their own dedicated data and workspace directory
        user_data_path = Path.home() / ".agentshell" / f"user_{self.user_id}"
        user_data_path.mkdir(parents=True, exist_ok=True)
        
        # If workspace is still default (cwd), set it to the emploai project directory
        if self.workspace == Path.cwd():
            # telegram_agent.py runs from emploai/telegram_bot/, so parent is emploai/
            self.workspace = Path(__file__).resolve().parent.parent
            # Don't create dirs — workspace should already exist

        # Initialize session context
        session_registry = get_session_registry()
        self.session_context = session_registry.get_or_create_main_session(self.user_id)

        # Initialize memory manager with user-isolated workspace
        self.memory_manager = get_memory_manager(self.workspace)

        # Initialize context loader
        self.context_loader = get_context_loader(self.workspace)
        self.context_loader.initialize_workspace()  # Create default files

        # Initialize live config
        self.live_config = get_live_config(self.workspace / "config.json")
        self.live_config.import_from_env()  # Load from env vars

        # Initialize existing managers - isolation by user_id
        user_base_path = Path.home() / ".agentshell" / f"user_{self.user_id}"
        self.session_manager = SessionManager(base_path=user_base_path)
        
        # Always create a new session on bot/session initialization as requested.
        # This ensures a fresh start whenever the agent is "loaded".
        # Old sessions can still be loaded via /session if needed.
        self.session = self.session_manager.create_session(
            workspace=self.workspace,
            name=f"Session {datetime.datetime.now().strftime('%H:%M')}"
        )
        self.session_manager.set_current_session(self.session.id)
        self.load_session_by_id(self.session.id)
        
        self.config_manager = get_config_manager()
        # Initialize skills and hooks systems
        self.skill_registry = get_skill_registry()
        self.hook_manager = get_hook_manager()
        self.file_processor = get_file_processor()
        self.analytics_tracker = get_analytics_tracker()

        # Enhance skills
        self.enhanced_skills = enhance_skill_registry(self.skill_registry)

        self._init_clients()
        
        if self.gemini_openai_client:
            from cli.agent_tools.context_manager import ContextManager, DEFAULT_CONTEXT_SIZES
            self.context_manager = ContextManager(
                model_context_sizes=DEFAULT_CONTEXT_SIZES,
                compression_client=self.gemini_openai_client,
                compression_model="gemini-2.0-flash"
            )

        def path_confirm_callback(msg: str) -> bool:
            """Allow all path/command adjustments silently without user friction."""
            return True

        self.tool_executor = ToolExecutor(
            self.workspace,
            confirm_callback=path_confirm_callback,
            check_interruption=lambda: self.should_interrupt,
            get_interrupt_message=self.get_interrupt_message,
            clear_interrupt=self._clear_interrupt,
            activate_deferred_interrupts=self.activate_deferred_interrupts,
            has_deferred_interrupts=self.has_deferred_interrupts,
            skill_registry=self.skill_registry,
            active_skills=self.active_skills
        )

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
            self.browser_task_context = BrowserTaskContext(task_id=self.current_task_id)
        return self.browser_task_context

    def reset_browser_task_context(self, task_id: Optional[int] = None) -> BrowserTaskContext:
        """Reset browser backend and task-owned tab tracking."""
        resolved_task_id = self.current_task_id if task_id is None else task_id
        self.browser_task_context = BrowserTaskContext(task_id=resolved_task_id)
        return self.browser_task_context

    def start_browser_task(self, task_id: int) -> BrowserTaskContext:
        """Create a fresh browser context for a newly started task."""
        self.browser_task_context = BrowserTaskContext(task_id=task_id)
        return self.browser_task_context

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
        google_key = self.config_manager.get_api_key("google") or os.getenv("GOOGLE_API_KEY")

        self.openai_client = OpenAI(api_key=openai_key) if openai_key else None
        self.anthropic_client = Anthropic(api_key=anthropic_key) if anthropic_key else None
        self.xai_client = OpenAI(api_key=xai_key, base_url="https://api.x.ai/v1") if xai_key else None
        self.deepseek_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com") if deepseek_key else None
        self.openrouter_client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1") if openrouter_key else None
        
        if HAS_GEMINI and google_key:
            genai.configure(api_key=google_key)
            self.google_client = genai
            self.gemini_openai_client = OpenAI(
                api_key=google_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
        else:
            self.google_client = None
            self.gemini_openai_client = None

    def get_available_variants(self) -> List[str]:
        """Get available variants for current model."""
        variant_info = MODEL_VARIANTS.get(self.current_model, {"variants": ["standard"]})
        return variant_info.get("variants", ["standard"])

    def get_client_for_model(self):
        """Get the appropriate LLM client for the current model."""
        config = MODEL_CONFIGS.get(self.current_model, {})
        provider = config.get("provider", "anthropic")

        if provider == "openai":
            return self.openai_client, provider
        if provider == "anthropic":
            return self.anthropic_client, provider
        if provider == "xai":
            return self.xai_client, provider
        if provider == "deepseek":
            return self.deepseek_client, provider
        if provider == "openrouter":
            return self.openrouter_client, provider
        if provider == "google":
            return self.google_client, provider
        return self.anthropic_client, "anthropic"

    def save_session(self):
        """Save current TelegramSession state to the SessionManager."""
        if not self.session_manager:
            return

        # Get the current session object from manager or create/use current
        current_id = self.session_manager.get_current_session_id()
        session_obj = None
        
        if current_id:
            try:
                session_obj = self.session_manager.load_session(current_id)
            except ValueError:
                pass
        
        if not session_obj:
            session_obj = self.session_manager.create_session(
                model=self.current_model,
                variant=self.current_variant,
                agent_mode=self.agent_mode,
                workspace=self.workspace
            )

        # Update session with current runtime state
        session_obj.chat_history = self.chat_history
        session_obj.model = self.current_model
        session_obj.variant = self.current_variant
        session_obj.agent_mode = "auto"
        session_obj.active_skills = self.active_skills

        # Save to disk
        self.session_manager.save_session(session_obj)

    def load_session_by_id(self, session_id: str):
        """Load session state from disk into this TelegramSession."""
        if not self.session_manager:
            return

        session_obj = self.session_manager.load_session(session_id)

        # Sync to runtime state
        self.chat_history = session_obj.chat_history
        self.current_model = session_obj.model
        self.current_variant = session_obj.variant
        self.agent_mode = "auto"
        self.active_skills = session_obj.active_skills

        # Clear specific agent histories to avoid context leaks
        if self.single_agent:
            self.single_agent.messages = []
        if self.refined_agent:
            self.refined_agent.messages = []
        if self.unified_agent:
            self.unified_agent.conversation_history = []

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
        self._app = app
        self._loop = loop

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

        if not self._app:
            return

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

        try:
            await self._app.bot.send_message(
                chat_id=self.user_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            try:
                await self._app.bot.send_message(chat_id=self.user_id, text=text)
            except Exception:
                pass


user_sessions: Dict[int, TelegramSession] = {}


def get_session(user_id: int) -> TelegramSession:
    """Get or create session for a user."""
    if user_id not in user_sessions:
        user_sessions[user_id] = TelegramSession(user_id=user_id)
    return user_sessions[user_id]


def track_command_usage(session: TelegramSession, command: str) -> None:
    """Track command usage for analytics."""
    if session.analytics_tracker:
        session.analytics_tracker.track_command(session.user_id, command)
