"""Textual-based TUI for the unified agentic system.

Chat-first interface:
- Text without / is sent to the AI model
- Commands start with / (e.g., /help, /model, /task)
"""

from __future__ import annotations

import math
import shlex
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List, Dict

from dotenv import load_dotenv
load_dotenv()

from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, TextArea, Static, OptionList, Collapsible

from cli import chat_processor_core
from cli import core_commands
from cli import file_commands
from cli import task_session_commands
from cli import tui_logging
from cli.tui_actions import AgentShellActionsMixin
from cli.tui_input import AgentShellInputMixin
from cli.tui_logging import log, run_safe
from cli.tui_settings import SettingsScreen
from cli.agent_tools.loop import run_tool_loop
from local_agent_runtime.agent import SingleAgent

from cli.tui_constants import (
    AGENT_MODE_COLORS,
    AGENT_MODE_LABELS,
    AGENT_MODES,
    AVAILABLE_MODELS,
    ChatMessage,
    CommandResult,
    MODEL_CONFIGS,
    MODEL_CONTEXT_SIZES,
    RESPONSE_MAX_TOKENS,
    SLASH_COMMANDS,
    SLASH_SUGGESTION_LIMIT,
    SUMMARY_INSTRUCTION,
    SUMMARY_MAX_TOKENS,
    SUMMARY_NOTICE_PERCENT,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_TRIGGER_PERCENT,
    SYSTEM_PROMPT,
    TRIM_TARGET_PERCENT,
    TRIM_TRIGGER_PERCENT,
)
from cli.tui_widgets import ChatLog, LoadingIndicator, LogArea, SlashSuggestionBar, TaskBlock, TextMessageBlock



class ChatProcessor:
    """Handles chat and slash commands."""

    def __init__(
        self,
        base_path: Path,
        log: Callable[[str], None],
        log_inline: Callable[[str], None],
        detail_log: Callable[[str], None],
        start_task_log: Callable[[str], None],
        finish_task_log: Callable[[str], bool, str, None],
        update_status: Callable[[], None],
        open_model_picker: Callable[[], None],
        open_session_switcher: Callable[[], None],
    ) -> None:
        chat_processor_core.initialize(
            self,
            base_path,
            log,
            log_inline,
            detail_log,
            start_task_log,
            finish_task_log,
            update_status,
            open_model_picker,
            open_session_switcher,
        )
    
    _get_default_variant = chat_processor_core.get_default_variant
    _get_available_variants = chat_processor_core.get_available_variants
    set_variant = chat_processor_core.set_variant
    cycle_agent_mode = chat_processor_core.cycle_agent_mode
    _auto_save_session = chat_processor_core.auto_save_session
    new_session = chat_processor_core.new_session
    switch_session = chat_processor_core.switch_session
    clear_chat = chat_processor_core.clear_chat
    _generate_context_summary = chat_processor_core.generate_context_summary
    get_context_for_task_agent = chat_processor_core.get_context_for_task_agent
    cycle_variant = chat_processor_core.cycle_variant
    _begin_stream = chat_processor_core.begin_stream
    _append_stream = chat_processor_core.append_stream
    _finish_stream = chat_processor_core.finish_stream
    _resolve_path = chat_processor_core.resolve_path
    _is_within_base = chat_processor_core.is_within_base
    get_context_percentage = chat_processor_core.get_context_percentage

    def handle_input(self, raw: str, open_editor: Callable[[Path, str], None]) -> CommandResult:
        """Handle user input - either chat or slash command."""
        if not raw.strip():
            return CommandResult(True, "")

        # Check if it's a slash command
        if raw.startswith("/"):
            return self._handle_slash_command(raw[1:], open_editor)
        else:
            # It's a chat message
            return self._handle_chat(raw)

    def _handle_chat(self, message: str) -> CommandResult:
        """Send message to the current AI model."""
        # Add user message to history
        self.chat_history.append(ChatMessage(role="user", content=message))

        # Auto-rename session on first message if it has a default name
        if len(self.chat_history) == 1 and self.session and self.session.name.startswith("Session "):
            new_name = message[:40].strip()
            if len(message) > 40:
                new_name += "..."
            self.session.name = new_name
            self.session_manager.save_session(self.session)

        # Estimate tokens (rough: 4 chars = 1 token)
        message_tokens = len(message) // 4
        self.total_tokens_used += message_tokens

        try:
            model_key = self.current_model
            model_config = MODEL_CONFIGS.get(model_key)
            if not model_config:
                return CommandResult(False, f"Unknown model: {self.current_model}.")
            
            provider = model_config["provider"]
            self.interrupted = False
            # Start tracking the turn time for coalescing blocks
            self._turn_start_time = time.time()
            self._begin_stream()
            assistant_message = ""

            # Determine which client to use based on provider
            client = None
            if provider == "anthropic":
                client = self.anthropic
            elif provider == "google":
                client = getattr(self, "gemini_openai_client", None) or self.genai
            elif provider == "openai":
                client = self.client
            elif provider == "xai":
                client = getattr(self, "xai_client", None)
            elif provider == "deepseek":
                client = getattr(self, "deepseek_client", None)
            elif provider == "openrouter":
                client = getattr(self, "openrouter_client", None)
            elif provider == "nvidia":
                client = getattr(self, "nvidia_client", None)

            if not client:
                return CommandResult(False, f"{provider.upper()} client or API key not configured.")

            # Prepare message history for the loop
            messages = [{"role": msg.role, "content": msg.content} for msg in self.chat_history[-20:]]
            
            # --- AUTO MODE: MERGED TOOLS ---
            extra_tools = None
            custom_prompt = None
            if self.agent_mode == "auto":
                # Get tools from the Task Agent (SingleAgent)
                if hasattr(self.single_agent, "tools"):
                    # SingleAgent.tools is a dict of name: function
                    # We need the OpenAI-style tool definitions (AGENT_TOOLS in agent.py)
                    from local_agent_runtime.agent import AGENT_TOOLS
                    extra_tools = AGENT_TOOLS
                    
                    # Build custom prompt with skills index
                    skills_index = ""
                    if hasattr(self, "skill_registry") and self.skill_registry:
                        skills_index = f"\n\n{self.skill_registry.get_skills_index()}"
                    
                    custom_prompt = chat_processor_core.build_tui_auto_system_prompt(
                        self,
                        skills_index=skills_index,
                    )

            # Call the unified tool loop
            result = run_tool_loop(
                provider=provider,
                model_id=model_config["id"],
                client=client,
                messages=messages,
                tool_executor=self.tool_executor,
                callbacks={
                    "log": self.detail_log,  # Route tool logs to details pane to keep chat clean
                    "log_inline": self.log_inline,
                    "append_stream": self._append_stream,
                    "begin_stream": self._begin_stream,
                    "finish_stream": self._finish_stream,
                    "update_status": self.update_status,
                },
                variant=self.current_variant,
                extra_tools=extra_tools,
                custom_system_prompt=custom_prompt
            )

            assistant_message = result.content
            self.total_tokens_used = result.total_tokens

            # Build assistant message with duration
            elapsed = time.time() - self._stream_start_time
            runtime_str = f"{elapsed:.1f}s"
            self.chat_history.append(ChatMessage(role="assistant", content=assistant_message, duration=runtime_str))

            # Auto-save session after each message
            self._auto_save_session()

            # Update status bar
            self.update_status()
            
            # Reset turn timer
            self._turn_start_time = None

            return CommandResult(True, "")

        except Exception as e:
            if self._streaming_response:
                self._finish_stream()
            return CommandResult(False, f"Error: {str(e)}")

    def _handle_slash_command(self, raw: str, open_editor: Callable[[Path, str], None]) -> CommandResult:
        """Handle slash commands."""
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            return CommandResult(False, f"Parse error: {exc}")

        if not parts:
            return CommandResult(False, "Empty command")

        command, *args = parts

        handlers = {
            "help": lambda a: core_commands.help(self, a, CommandResult),
            "exit": lambda a: core_commands.exit(self, a, CommandResult),
            "quit": lambda a: core_commands.exit(self, a, CommandResult),
            "clear": lambda a: core_commands.clear(self, a, CommandResult),
            "history": lambda a: core_commands.history(self, a, CommandResult),
            "model": lambda a: core_commands.model(self, a, CommandResult),
            "variant": lambda a: core_commands.variant(self, a, CommandResult),
            "mode": lambda a: core_commands.mode(self, a, CommandResult),
            "context": lambda a: core_commands.context_info(self, a, CommandResult),
            "reset": lambda a: core_commands.reset(self, a, CommandResult),
            "pwd": lambda a: file_commands.pwd(self, a, CommandResult),
            "cd": lambda a: file_commands.cd(self, a, CommandResult),
            "ls": lambda a: file_commands.ls(self, a, CommandResult),
            "cat": lambda a: file_commands.cat(self, a, CommandResult),
            "touch": lambda a: file_commands.touch(self, a, CommandResult),
            "write": lambda a: file_commands.write(self, a, CommandResult),
            "append": lambda a: file_commands.append(self, a, CommandResult),
            "mv": lambda a: file_commands.mv(self, a, CommandResult),
            "cp": lambda a: file_commands.cp(self, a, CommandResult),
            "mkdir": lambda a: file_commands.mkdir(self, a, CommandResult),
            "rm": lambda a: file_commands.rm(self, a, CommandResult),
            "stat": lambda a: file_commands.stat(self, a, CommandResult),
            "search": lambda a: file_commands.search(self, a, CommandResult),
            "edit": lambda a: file_commands.edit(self, a, CommandResult, open_editor),
            "run": lambda a: task_session_commands.run_command(self, a, CommandResult),
            "task": lambda a: task_session_commands.task(self, a, CommandResult),
            "pause": lambda a: task_session_commands.pause_task(self, a, CommandResult),
            "continue": lambda a: task_session_commands.continue_task(self, a, CommandResult),
            "session": lambda a: task_session_commands.session(self, a, CommandResult),
            "new": lambda a: CommandResult(True, f"Created new session: {self.new_session(' '.join(a) if a else None).name}", clear=True),
            "rename": lambda a: task_session_commands.rename(self, a, CommandResult),
            "providers": lambda a: task_session_commands.providers(self, a, CommandResult),
            "settings": lambda a: core_commands.settings(self, a, CommandResult),
        }

        handler = handlers.get(command)
        if not handler:
            return CommandResult(False, f"Unknown command: /{command}. Type /help for commands.")

        try:
            return handler(args)
        except Exception as exc:
            return CommandResult(False, f"Error: {exc}")

class AgentShellApp(AgentShellActionsMixin, AgentShellInputMixin, App):
    """Textual app for agent control and CLI commands."""

    CSS = """
    Screen {
        background: #000000;
        layout: vertical;
    }
    
    ChatLog {
        height: 1fr;
        padding: 1;
        background: #000000;
        scrollbar-gutter: stable;
        overflow-y: scroll;
        margin-bottom: 1; /* Space for input area overlay if needed */
    }

    TextMessageBlock {
        margin: 0 0 1 0;
        padding: 0;
        background: transparent;
        height: auto;
    }

    #message_text {
        background: #111111;
        color: #ffffff;
        border: none;
        padding: 0 1;
        width: 100%;
        overflow: hidden;
        scrollbar-size: 0 0;
    }

    TaskBlock {
        margin: 1 0;
        padding: 1 2;
        background: #1a1a1a;
        border-left: double $accent;
        height: auto;
    }

    #task_status {
        margin-bottom: 1;
        text-style: bold;
        color: $text;
    }

    #task_details_area {
        height: 20;
        background: #050505;
        color: $text-muted;
        border: none;
    }

    /* --- Footer / Input Area Layout --- */

    #input_area {
        dock: bottom;
        height: auto;
        background: #000000;
        margin: 0;
        padding: 0;
    }

    #input_container {
        background: #121212;
        border-left: solid #3b82f6;
        margin: 0 1;
        padding: 0;
        height: 4;
    }

    #command {
        background: transparent;
        border: none;
        width: 100%;
        padding: 0 1;
        height: 3;
        margin: 0;
    }

    #command:focus {
        border: none;
    }

    #model_info {
        color: #888;
        padding: 0 1;
        height: 1;
        content-align: left top;
    }

    #status_bar {
        height: 1;
        margin: 0 1 1 1;
    }

    #loading_area {
        width: 1fr;
    }

    #loading_indicator {
        width: auto;
        color: #4ade80;
    }

    #interrupt_hint {
        width: auto;
        margin-left: 2;
        color: $text-muted;
    }

    #shortcuts {
        width: auto;
        content-align: right middle;
    }

    #slash_suggestions {
        height: auto;
        max-height: 10;
        background: #1a1a1a;
        color: $text;
        padding: 0 1;
        border-bottom: solid #333;
    }
    
    .running-indicator {
        color: #4ade80;
    }
    
    .paused-indicator {
        color: #facc15;
    }

    #agent_log {
        height: 10;
        background: $surface-darken-1;
    }

    Collapsible {
        background: $surface-darken-1;
        color: $text;
        border: none;
    }

    #agent_details_collapsible {
        display: block;
    }
    
    .hidden {
        display: none !important;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+p", "open_command_palette", "Commands"),
        ("ctrl+m", "open_model_picker", "Model"),
        ("ctrl+n", "new_session", "New Session"),
        ("ctrl+l", "switch_session", "Sessions"),
        ("ctrl+t", "cycle_variant", "Variant"),
        ("ctrl+comma", "open_settings", "Settings"),
        ("tab", "noop", "Agent Mode"),
    ]
    
    def action_noop(self) -> None:
        """Placeholder for bindings handled elsewhere (like tab in on_key)."""
        pass

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def open_settings(self) -> None:
        self.action_open_settings()

    _run_safe = tui_logging.run_safe
    _log = tui_logging.log
    _log_inline = tui_logging.log_inline
    _log_agent = tui_logging.log_agent
    _start_task_log = tui_logging.start_task_log
    _finish_task_log = tui_logging.finish_task_log

    # Explicitly implement streaming hooks to handle model names better
    def _begin_stream(self) -> None:
        if not self.processor:
            return
        self.processor._stream_buffer = ""
        self.processor._streaming_response = True
        now = time.time()
        self._stream_start_time = now # Track chunk runtime
        self.processor._stream_start_time = now
        
        # Check if we can coalesce into the existing assistant block
        children = self.chat_log.children
        last_is_assistant = children and isinstance(children[-1], TextMessageBlock) and children[-1].role == "assistant"
        
        # If we are in an active turn and the last block is ours, just append a newline separator if needed
        if self._turn_start_time and last_is_assistant:
            # We are continuing the same response (e.g. after a tool call)
            # Add a separator for clarity between chunks
            # self._append_stream("\n\n") 
            self.esc_pressed = False
            return

        # Start a new block for the assistant
        model = self.processor.current_model
        self.esc_pressed = False 
        self._log("", role="assistant", model=model, timestamp="...")

    def _append_stream(self, text: str) -> None:
        if not self.processor:
            return
        if not text:
            return
        if not self.processor._stream_buffer:
            text = text.lstrip("\n")
            if not text:
                return
        self.processor._stream_buffer += text
        self._log_inline(text)

    def _finish_stream(self) -> str:
        if not self.processor:
            return ""
        if self.processor._streaming_response:
            self.processor._streaming_response = False
            
            # Update last message with runtime
            # If we are in a turn, use the total turn time. Otherwise use chunk time.
            start_time = self._turn_start_time if self._turn_start_time else self._stream_start_time
            elapsed = time.time() - start_time
            runtime_str = f"{elapsed:.1f}s"
            
            def update_last_msg():
                children = self.chat_log.children
                if children and isinstance(children[-1], TextMessageBlock):
                    children[-1].update_metadata(timestamp=runtime_str)
            
            self.call_from_thread(update_last_msg)

        self.esc_pressed = False # Reset on finish
        return self.processor._stream_buffer

    def __init__(self) -> None:
        super().__init__()
        self.base_path = Path(__file__).resolve().parents[1]
        self.log_widget: Optional[LogArea] = None
        self.command_input: Optional[Input] = None
        self.loading_indicator: Optional[Label] = None
        self.shortcuts: Optional[Label] = None
        self.input_status: Optional[Label] = None
        self.slash_suggestions: Optional[SlashSuggestionBar] = None
        self.processor: Optional[ChatProcessor] = None
        
        # Escape detection state
        self.esc_pressed = False
        
        # Turn state tracking for coalescing outputs
        self._turn_start_time: Optional[float] = None
        
        # Status update timer
        self._status_timer: Optional[object] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        self.chat_log = ChatLog(id="log")
        yield self.chat_log
        
        with Collapsible(title="Agent Execution Details", id="agent_details_collapsible"):
            self.agent_log = LogArea("", id="agent_log")
            self.agent_log.read_only = True
            yield self.agent_log

        with Vertical(id="input_area"):
            # 1. Suggestions
            self.slash_suggestions = SlashSuggestionBar(id="slash_suggestions")
            self.slash_suggestions.display = False
            yield self.slash_suggestions
            
            # 2. Input Box with details
            with Vertical(id="input_container"):
                self.command_input = Input(placeholder="Chat with AI or use /commands", id="command")
                yield self.command_input
                self.model_info_widget = Static("", id="model_info")
                yield self.model_info_widget
            
            # 3. Footer / Hints Bar
            with Horizontal(id="status_bar"):
                with Horizontal(id="loading_area"):
                    self.loading_indicator = LoadingIndicator(id="loading_indicator")
                    yield self.loading_indicator
                    self.interrupt_hint = Static("  [dim]esc + esc to interrupt[/]", id="interrupt_hint")
                    self.interrupt_hint.display = False
                    yield self.interrupt_hint
                
                self.shortcuts = Static("", id="shortcuts")
                yield self.shortcuts

    def use_suggestion(self, suggestion: str) -> None:
        """Called when a suggestion is clicked/selected."""
        if self.command_input:
            self.command_input.value = ""
            self.command_input.focus()

        self._submit_input(suggestion)

    def on_mount(self) -> None:
        # Hide agent details by default
        self.query_one("#agent_details_collapsible").add_class("hidden")

        self.processor = ChatProcessor(
            self.base_path,
            self._log,
            self._log_inline,
            self._log_agent,
            self._start_task_log,
            self._finish_task_log,
            self._update_status,
            self._open_model_picker,
            self._open_session_switcher,
        )
        # Override processor streaming methods with ours
        self.processor._begin_stream = self._begin_stream
        self.processor._append_stream = self._append_stream
        self.processor._finish_stream = self._finish_stream

        self._update_status()
        self._update_slash_suggestions("")
        self._log("Welcome! Type to chat with the AI, or use /help for commands.", role="info")
        self._log("Workspace: " + str(self.base_path), role="info")
        
        # Start status update timer (updates frequently for snake animation)
        self._status_timer = self.set_interval(0.2, self._update_status)

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_slash_suggestions(event.value)

    def _submit_input(self, input_text: str) -> None:
        if not input_text:
            return

        # FEATURE: Auto-complete to top suggestion on Enter for slash commands
        if input_text.startswith("/") and self.slash_suggestions and self.slash_suggestions.top_suggestion:
            top = self.slash_suggestions.top_suggestion
            # Only auto-complete if the input is a prefix of the suggestion
            if top.startswith(input_text):
                input_text = top

        self._update_slash_suggestions("")
        
        if self.processor:
            self.processor.history.append(input_text)
            self.processor.history_index = len(self.processor.history)
            if len(self.processor.history) > 200:
                self.processor.history = self.processor.history[-200:]
                self.processor.history_index = len(self.processor.history)

        # Chat and long-running commands run async
        long_running_commands = ["/task", "/continue"]
        is_long_running = any(input_text.startswith(cmd) for cmd in long_running_commands)

        if not input_text.startswith("/") or is_long_running:
            if input_text.startswith("/"):
                self._log(f"> {input_text}")
            else:
                # Log user message with new style
                self._log(input_text, role="user")
                # self._log("") # No extra newline needed with block margins
            self._handle_async(input_text)
        else:
            self._handle_input(input_text)

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_text = event.value.strip()
        event.input.value = ""
        self._submit_input(input_text)

    def on_key(self, event: events.Key) -> None:
        # Handle Tab key - cycle agent modes (override default focus behavior)
        if event.key == "tab":
            if self.processor:
                self.processor.cycle_agent_mode()
                self._update_status()
            event.stop()  # Prevent default tab focus behavior
            event.prevent_default()
            return

        # Handle Escape key
        if event.key == "escape":
            if not self.processor:
                return
                
            is_active = self.processor._streaming_response or (self.processor.single_agent.current_task and not self.processor.single_agent.is_paused)
            
            if self.esc_pressed:
                # Second Esc detected - interrupt immediately without logging or toast
                self.processor.interrupted = True
                self.processor.single_agent.is_paused = True # Set directly to bypass logging if possible
                self.processor.single_agent.pause()
                self.esc_pressed = False
                self._update_status()
            elif is_active:
                # First Esc detected
                self.esc_pressed = True
                self._update_status()
            return

        if not self.command_input or not self.command_input.has_focus:
            return
        if event.key == "up":
            if not self.processor or not self.processor.history:
                return
            self.processor.history_index = max(0, self.processor.history_index - 1)
            self.command_input.value = self.processor.history[self.processor.history_index]
            self._update_slash_suggestions(self.command_input.value)
            event.stop()
        elif event.key == "down":
            if not self.processor or not self.processor.history:
                return
            self.processor.history_index = min(
                len(self.processor.history),
                self.processor.history_index + 1,
            )
            if self.processor.history_index >= len(self.processor.history):
                self.command_input.value = ""
            else:
                self.command_input.value = self.processor.history[self.processor.history_index]
            self._update_slash_suggestions(self.command_input.value)
            event.stop()


def run() -> None:
    AgentShellApp().run()


if __name__ == "__main__":
    run()
