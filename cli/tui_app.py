"""Textual-based TUI for the unified agentic system.

Chat-first interface:
- Text without / is sent to the AI model
- Commands start with / (e.g., /help, /model, /task)
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import threading
from threading import Thread
from typing import Callable, Iterable, Optional, List, Dict

from dotenv import load_dotenv
load_dotenv()

from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, TextArea, Static, OptionList, Collapsible

from openai import OpenAI
from anthropic import Anthropic

from cli.dual_agent import DualAgentRunner
from single_agent.agent import SingleAgent


SYSTEM_PROMPT = "You are a helpful AI assistant."
SUMMARY_SYSTEM_PROMPT = "You are a concise assistant that summarizes conversations for later use."
SUMMARY_INSTRUCTION = (
    "Summarize the conversation so far for continuation. "
    "Capture key decisions, open questions, and next steps in concise bullets."
)
SUMMARY_NOTICE_PERCENT = 40.0
SUMMARY_TRIGGER_PERCENT = 60.0
TRIM_TRIGGER_PERCENT = 85.0
TRIM_TARGET_PERCENT = 70.0
RESPONSE_MAX_TOKENS = 2000
SUMMARY_MAX_TOKENS = 600

MODEL_CONFIGS = {
    "gpt-5": {"provider": "openai", "id": "gpt-5", "context": 400000},
    "gpt-5.1": {"provider": "openai", "id": "gpt-5.1", "context": 400000},
    "gpt-5.2": {"provider": "openai", "id": "gpt-5.2", "context": 400000},
    "gpt-4.1": {"provider": "openai", "id": "gpt-4.1", "context": 128000},
    "gpt-4o": {"provider": "openai", "id": "gpt-4o", "context": 128000},
    "gpt-4o-mini": {"provider": "openai", "id": "gpt-4o-mini", "context": 128000},
    "claude-sonnet-4.5": {"provider": "anthropic", "id": "claude-sonnet-4-5-20250929", "context": 200000},
    "claude-opus-4.5": {"provider": "anthropic", "id": "claude-opus-4-5-20250929", "context": 200000},
    "claude-haiku-4.5": {"provider": "anthropic", "id": "claude-haiku-4-5-20251001", "context": 200000},
    "claude-sonnet-4": {"provider": "anthropic", "id": "claude-sonnet-4-20250514", "context": 200000},
    "claude-opus-4": {"provider": "anthropic", "id": "claude-opus-4-20250514", "context": 200000},
    "claude-haiku-4": {"provider": "anthropic", "id": "claude-haiku-4-20250514", "context": 200000},
}

MODEL_ALIASES = {
    "claude-sonnet-4-5": "claude-sonnet-4.5",
    "claude-opus-4-5": "claude-opus-4.5",
    "claude-haiku-4-5": "claude-haiku-4.5",
    "claude-sonnet-4-5-20250929": "claude-sonnet-4.5",
    "claude-opus-4-5-20250929": "claude-opus-4.5",
    "claude-haiku-4-5-20251001": "claude-haiku-4.5",
    "claude-sonnet-4-20250514": "claude-sonnet-4",
    "claude-opus-4-20250514": "claude-opus-4",
    "claude-haiku-4-20250514": "claude-haiku-4",
}

AVAILABLE_MODELS = list(MODEL_CONFIGS.keys())
MODEL_CONTEXT_SIZES = {name: config["context"] for name, config in MODEL_CONFIGS.items()}

SLASH_COMMANDS = [
    "help",
    "exit",
    "quit",
    "clear",
    "history",
    "model",
    "context",
    "reset",
    "pwd",
    "cd",
    "ls",
    "cat",
    "touch",
    "write",
    "append",
    "mv",
    "cp",
    "mkdir",
    "rm",
    "stat",
    "search",
    "edit",
    "run",
    "task",
    "pause",
    "continue",
]

SLASH_SUGGESTION_LIMIT = 12


@dataclass
class CommandResult:
    success: bool
    output: str
    exit: bool = False
    clear: bool = False


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


class ChatLog(Vertical):
    """A container for chat message blocks."""
    pass

class MessageBlock(Static):
    """Base class for a message in the chat log."""
    def __init__(self, content: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.content = content

class TextMessageBlock(MessageBlock):
    """A simple text message block, supports streaming and selection."""
    def compose(self) -> ComposeResult:
        # Use a LogArea for selectable text
        self.text_area = LogArea(self.content, id="message_text")
        self.text_area.read_only = True
        self.text_area.show_line_numbers = False
        yield self.text_area

    def on_mount(self) -> None:
        self._update_height()

    def _update_height(self) -> None:
        # Calculate height based on lines, minimum 1
        lines = self.text_area.document.line_count
        self.text_area.styles.height = max(lines, 1)

    def append_text(self, text: str) -> None:
        self.content += text
        # LogArea handles the insertion nicely
        self.text_area.append_log(text)
        self._update_height()

class TaskBlock(MessageBlock):
    """A block representing a dual-agent task with status and results."""
    def __init__(self, task: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.task_name = task
        self.status = "Initializing..."
        self.execution_logs = ""
        self.is_finished = False
        self.success = False
        self.summary = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="task_container"):
            self.status_label = Label(f"🛠 [bold]Task:[/bold] {self.task_name}\n   └─ [cyan]{self.status}[/cyan]", id="task_status")
            yield self.status_label
            with Collapsible(title="Execution Details", id="task_details", collapsed=True):
                self.details_area = LogArea("", read_only=True, id="task_details_area")
                self.details_area.show_line_numbers = False
                yield self.details_area
        
    def on_mount(self) -> None:
        # Hide details by default
        self.query_one("#task_details").display = False

    def update_status(self, status: str) -> None:
        self.status = status
        self.status_label.update(f"🛠 [bold]Task:[/bold] {self.task_name}\n   └─ [cyan]{self.status}[/cyan]")

    def append_detail(self, text: str) -> None:
        self.execution_logs += text
        if isinstance(self.details_area, LogArea):
            self.details_area.append_log(text)
        else:
            self.details_area.text = self.execution_logs

    def finish(self, success: bool, summary: str) -> None:
        self.is_finished = True
        self.success = success
        self.summary = summary
        icon = "✅" if success else "❌"
        color = "green" if success else "red"
        self.status_label.update(f"{icon} [bold]Task:[/bold] {self.task_name}\n   └─ [{color}]{summary}[/{color}]")
        
        # Show and populate the collapsible
        details = self.query_one("#task_details", Collapsible)
        details.display = True
        self.details_area.text = self.execution_logs
        if isinstance(self.details_area, LogArea):
            self.details_area.scroll_end(animate=False)
        # Scroll to bottom of container
        self.scroll_end()

class LogArea(TextArea):
    """Read-only log widget that auto-copies selections."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_copied = ""
        self._pause_autoscroll = False
        self._drag_autoscroll_step = 2
        self._drag_autoscroll_margin = 1

    def append_log(self, message: str) -> None:
        # Always append at the very end regardless of cursor position
        last_line = max(self.document.line_count - 1, 0)
        end_location = (last_line, len(self.document.lines[last_line]) if self.document.lines else 0)
        if self._pause_autoscroll:
            self.insert(message, location=end_location, scroll_end=False)
        else:
            self.insert(message, location=end_location)
        # Move cursor to end to avoid users typing in the middle
        self.move_cursor(end_location)

    def _copy_selection(self) -> None:
        selected_text = getattr(self, "selected_text", "")
        if not selected_text or selected_text == self._last_copied:
            return
        self._last_copied = selected_text
        app = self.app
        if hasattr(app, "copy_to_clipboard"):
            app.copy_to_clipboard(selected_text)
        elif hasattr(app, "set_clipboard"):
            app.set_clipboard(selected_text)
        elif hasattr(app, "clipboard"):
            try:
                app.clipboard = selected_text
            except Exception:
                return
        if hasattr(app, "notify"):
            app.notify("Copied selection to clipboard", timeout=2)
        else:
            fallback_log = getattr(app, "_log", None)
            if callable(fallback_log):
                fallback_log("[clipboard] Copied selection")

    def _refocus_input(self) -> None:
        app = self.app
        command_input = getattr(app, "command_input", None)
        if command_input:
            command_input.focus()

    def _handle_drag_autoscroll(self, event: events.MouseMove) -> None:
        if not self._pause_autoscroll:
            return
        region = self.content_region
        if not region.contains(event.x, event.y):
            return
        offset_y = event.y - region.y
        if offset_y <= self._drag_autoscroll_margin:
            self.action_scroll_up(self._drag_autoscroll_step)
        elif offset_y >= region.height - 1 - self._drag_autoscroll_margin:
            self.action_scroll_down(self._drag_autoscroll_step)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._pause_autoscroll = True

    def on_mouse_move(self, event: events.MouseMove) -> None:
        self._handle_drag_autoscroll(event)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._pause_autoscroll = False
        self._copy_selection()
        # Refocus input logic: only refocus if it exists
        if hasattr(self.app, "command_input") and self.app.command_input:
            self.app.command_input.focus()


class SlashSuggestionBar(Static):
    """Inline suggestion list for slash commands."""

    def update_suggestions(self, suggestions: list[str]) -> None:
        has_suggestions = bool(suggestions)
        self.display = has_suggestions
        text = "\n".join(suggestions) if has_suggestions else ""
        self.update(text)



class EditorScreen(Screen):
    """Modal editor for file content."""

    def __init__(self, file_path: Path, content: str, on_save: Callable[[str], None]) -> None:
        super().__init__()
        self.file_path = file_path
        self.content = content
        self.on_save = on_save

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Label(f"Editing: {self.file_path}")
            yield TextArea(self.content, id="editor")
            with Horizontal():
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    @on(Button.Pressed)
    def handle_button(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            editor = self.query_one("#editor", TextArea)
            self.on_save(editor.text)
            self.app.pop_screen()
        elif event.button.id == "cancel":
            self.app.pop_screen()


import json

# Path for storing model preferences (recent, favorites)
MODEL_PREFS_FILE = Path(__file__).parent / ".model_prefs.json"


def _load_model_prefs() -> Dict:
    """Load model preferences from file."""
    if MODEL_PREFS_FILE.exists():
        try:
            with open(MODEL_PREFS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"recent": [], "favorites": []}


def _save_model_prefs(prefs: Dict) -> None:
    """Save model preferences to file."""
    try:
        with open(MODEL_PREFS_FILE, "w") as f:
            json.dump(prefs, f, indent=2)
    except IOError:
        pass


def _add_recent_model(model: str) -> None:
    """Add a model to recent list (max 3, most recent first)."""
    prefs = _load_model_prefs()
    recent = prefs.get("recent", [])
    # Remove if already exists
    if model in recent:
        recent.remove(model)
    # Add to front
    recent.insert(0, model)
    # Keep only 3
    prefs["recent"] = recent[:3]
    _save_model_prefs(prefs)


def _toggle_favorite(model: str) -> bool:
    """Toggle favorite status for a model. Returns new status."""
    prefs = _load_model_prefs()
    favorites = prefs.get("favorites", [])
    if model in favorites:
        favorites.remove(model)
        is_favorite = False
    else:
        favorites.append(model)
        is_favorite = True
    prefs["favorites"] = favorites
    _save_model_prefs(prefs)
    return is_favorite


def _format_context_size(tokens: int) -> str:
    """Format context size as abbreviated string (e.g., 400K, 128K)."""
    if tokens >= 1000000:
        return f"{tokens // 1000000}M"
    elif tokens >= 1000:
        return f"{tokens // 1000}K"
    return str(tokens)


def _get_provider_name(model: str) -> str:
    """Get provider display name for a model."""
    config = MODEL_CONFIGS.get(model, {})
    provider = config.get("provider", "")
    if provider == "openai":
        return "OpenAI"
    elif provider == "anthropic":
        return "Anthropic"
    return provider.capitalize() if provider else ""


class ModelSelectScreen(Screen):
    """Modal screen for selecting the chat model with search, recent, and favorites."""

    BINDINGS = [
        ("escape", "cancel", "Close"),
        ("ctrl+f", "toggle_favorite", "Favorite"),
    ]

    def __init__(self, models: list[str], current: str, on_select: Callable[[str], None]) -> None:
        super().__init__()
        self.all_models = models
        self.current = current
        self.on_select = on_select
        self.filtered_models: list[str] = []
        self.prefs = _load_model_prefs()

    def _format_model_display(self, model: str, is_selected: bool = False, is_favorite: bool = False) -> str:
        """Format a model name for display with provider and context size."""
        provider = _get_provider_name(model)
        context = MODEL_CONFIGS.get(model, {}).get("context", 0)
        context_str = _format_context_size(context)
        
        # Build display string
        prefix = "● " if is_selected else "  "
        fav_marker = "★ " if is_favorite else ""
        model_with_provider = f"{model} {provider}" if provider else model
        
        # Calculate padding for alignment (assuming ~50 char width)
        padding = max(1, 40 - len(prefix) - len(fav_marker) - len(model_with_provider))
        
        return f"{prefix}{fav_marker}{model_with_provider}{' ' * padding}{context_str}"

    def _get_display_models(self, search_text: str = "") -> tuple[list[str], list[tuple[str, str]]]:
        """Get models to display based on search, split into recent and all.
        
        Returns: (recent_models, all_models) where each item is (model_key, display_text)
        """
        favorites = self.prefs.get("favorites", [])
        recent = self.prefs.get("recent", [])
        
        # Filter models based on search
        search_lower = search_text.lower()
        if search_text:
            filtered = [m for m in self.all_models if search_lower in m.lower() or 
                       search_lower in _get_provider_name(m).lower()]
        else:
            filtered = self.all_models
        
        # Split into recent and rest
        recent_display = []
        all_display = []
        
        # Add recent models first (up to 3)
        for model in recent[:3]:
            if model in filtered:
                is_selected = model == self.current
                is_favorite = model in favorites
                display = self._format_model_display(model, is_selected, is_favorite)
                recent_display.append((model, display))
        
        # Add all models (excluding those in recent)
        recent_set = set(recent[:3])
        for model in filtered:
            if model not in recent_set:
                is_selected = model == self.current
                is_favorite = model in favorites
                display = self._format_model_display(model, is_selected, is_favorite)
                all_display.append((model, display))
        
        return recent_display, all_display

    def _rebuild_options(self, search_text: str = "") -> None:
        """Rebuild the option list based on search text."""
        options = self.query_one("#model_options", OptionList)
        options.clear_options()
        
        recent_models, all_models = self._get_display_models(search_text)
        self.filtered_models = []
        
        # Add recent section if there are recent models
        if recent_models:
            options.add_option("[dim]Recent[/dim]")
            self.filtered_models.append(None)  # Separator placeholder
            for model_key, display in recent_models:
                options.add_option(display)
                self.filtered_models.append(model_key)
            # Add separator
            options.add_option("[dim]─────────────────────────────────────────[/dim]")
            self.filtered_models.append(None)  # Separator placeholder
        
        # Add all models
        for model_key, display in all_models:
            options.add_option(display)
            self.filtered_models.append(model_key)
        
        # Highlight current model if visible
        for idx, model in enumerate(self.filtered_models):
            if model == self.current:
                options.highlighted = idx
                break

    def compose(self) -> ComposeResult:
        with Vertical(id="model_select_container"):
            with Horizontal(id="model_header"):
                yield Label("Select model", id="model_title")
                yield Label("[dim]esc[/dim]", id="model_close_hint")
            yield Input(placeholder="Search", id="model_search")
            yield OptionList(id="model_options")
            yield Label("[dim]Favorite[/dim] [bold]ctrl+f[/bold]", id="model_footer")

    def on_mount(self) -> None:
        self._rebuild_options()
        # Focus the search input
        search_input = self.query_one("#model_search", Input)
        search_input.focus()

    @on(Input.Changed, "#model_search")
    def handle_search_changed(self, event: Input.Changed) -> None:
        self._rebuild_options(event.value)

    @on(OptionList.OptionSelected)
    def handle_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if idx < len(self.filtered_models):
            model_key = self.filtered_models[idx]
            if model_key is not None:  # Not a separator
                _add_recent_model(model_key)
                self.on_select(model_key)
                self.app.pop_screen()

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def action_toggle_favorite(self) -> None:
        """Toggle favorite status for the highlighted model."""
        options = self.query_one("#model_options", OptionList)
        idx = options.highlighted
        if idx is not None and idx < len(self.filtered_models):
            model_key = self.filtered_models[idx]
            if model_key is not None:
                is_fav = _toggle_favorite(model_key)
                self.prefs = _load_model_prefs()  # Reload prefs
                # Get current search text and rebuild
                search_input = self.query_one("#model_search", Input)
                self._rebuild_options(search_input.value)
                # Re-highlight the same position
                options.highlighted = idx
                status = "added to" if is_fav else "removed from"
                self.notify(f"{model_key} {status} favorites", timeout=2)


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
    ) -> None:
        self.base_path = base_path
        self.log = log
        self.log_inline = log_inline
        self.detail_log = detail_log
        self.start_task_log = start_task_log
        self.finish_task_log = finish_task_log
        self.update_status = update_status
        self.open_model_picker = open_model_picker

        self.cwd = base_path
        self.history: list[str] = []
        self.history_index = 0

        # Chat state
        self.current_model = "claude-haiku-4.5"
        self.chat_history: List[ChatMessage] = []
        self.total_tokens_used = 0
        self.max_tokens = MODEL_CONTEXT_SIZES.get(self.current_model, 128000)

        # LLM client
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Streaming state
        self._stream_buffer = ""
        self._streaming_response = False

        # Dual agent runner
        self.dual_agent = DualAgentRunner(log_callback=self.log, detail_callback=self.detail_log)

        # Single agent (Active)
        self.single_agent = SingleAgent(logger=self.detail_log)

    def _begin_stream(self) -> None:
        self._stream_buffer = ""
        self._streaming_response = True
        self.log_inline(f"[{self.current_model}]: ")

    def _append_stream(self, text: str) -> None:
        if not text:
            return
        self._stream_buffer += text
        self.log_inline(text)

    def _finish_stream(self) -> str:
        if self._streaming_response:
            self.log_inline("\n")
            self._streaming_response = False
        return self._stream_buffer

    def _resolve_path(self, path_str: str) -> Path:
        candidate = Path(path_str)
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        resolved = candidate.resolve()
        if not self._is_within_base(resolved):
            raise ValueError("Path escapes workspace")
        return resolved

    def _is_within_base(self, path: Path) -> bool:
        try:
            path.relative_to(self.base_path)
            return True
        except ValueError:
            return False

    def get_context_percentage(self) -> float:
        """Get current context usage as percentage."""
        if self.max_tokens == 0:
            return 0.0
        return (self.total_tokens_used / self.max_tokens) * 100

    def handle_input(self, raw: str, open_editor: Callable[[Path, str], None]) -> CommandResult:
        """Handle user input - either chat or slash command."""
        if not raw.strip():
            return CommandResult(True, "")

        # Check if it's a slash command
        if raw.startswith("/"):
            return self._handle_slash_command(raw[1:], open_editor)
        else:
            # Check if we're in pause mode - route to memory agent
            if self.dual_agent.is_paused:
                return self._handle_pause_chat(raw)
            # It's a chat message
            return self._handle_chat(raw)
    
    def _handle_pause_chat(self, message: str) -> CommandResult:
        """Handle chat with Memory Agent during pause."""
        self.log(f"[To Memory Agent]: {message}")
        response = self.dual_agent.chat_with_memory(message)
        return CommandResult(True, f"[Memory Agent]: {response}")

    def _handle_chat(self, message: str) -> CommandResult:
        """Send message to the current AI model."""
        # Add user message to history
        self.chat_history.append(ChatMessage(role="user", content=message))

        # Estimate tokens (rough: 4 chars = 1 token)
        message_tokens = len(message) // 4
        self.total_tokens_used += message_tokens

        try:
            # Build messages for API
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for msg in self.chat_history[-20:]:  # Keep last 20 messages for context
                messages.append({"role": msg.role, "content": msg.content})

            model_key = MODEL_ALIASES.get(self.current_model, self.current_model)
            model_config = MODEL_CONFIGS.get(model_key)
            if not model_config:
                return CommandResult(False, f"Unknown model: {self.current_model}.")

            self._begin_stream()
            assistant_message = ""

            if model_config["provider"] == "anthropic":
                response = None
                with self.anthropic.messages.stream(
                    model=model_config["id"],
                    max_tokens=RESPONSE_MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    messages=[
                        {"role": msg["role"], "content": msg["content"]}
                        for msg in messages
                        if msg["role"] != "system"
                    ],
                ) as stream:
                    for event in stream:
                        if getattr(event, "type", None) == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if getattr(delta, "type", None) == "text_delta":
                                self._append_stream(delta.text)
                    response = stream.get_final_message()

                assistant_message = self._finish_stream()
                usage = getattr(response, "usage", None) if response else None
                if usage:
                    self.total_tokens_used = usage.input_tokens + usage.output_tokens
                else:
                    self.total_tokens_used += max(1, len(assistant_message) // 4)
            else:
                request_kwargs = {
                    "model": model_config["id"],
                    "messages": messages,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                }
                if model_key.startswith("gpt-5"):
                    request_kwargs["max_completion_tokens"] = RESPONSE_MAX_TOKENS
                else:
                    request_kwargs["max_tokens"] = RESPONSE_MAX_TOKENS

                response = self.client.chat.completions.create(**request_kwargs)
                usage = None
                for chunk in response:
                    if not chunk.choices:
                        if getattr(chunk, "usage", None):
                            usage = chunk.usage
                        continue
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if content:
                        self._append_stream(content)
                    if getattr(chunk, "usage", None):
                        usage = chunk.usage

                assistant_message = self._finish_stream()
                if usage:
                    self.total_tokens_used = usage.total_tokens
                else:
                    self.total_tokens_used += max(1, len(assistant_message) // 4)

            # Add to history
            self.chat_history.append(ChatMessage(role="assistant", content=assistant_message))

            # Update status bar
            self.update_status()

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
            "help": self._help,
            "exit": self._exit,
            "quit": self._exit,
            "clear": self._clear,
            "history": self._history,
            "model": self._model,
            "context": self._context,
            "reset": self._reset_chat,
            "pwd": self._pwd,
            "cd": self._cd,
            "ls": self._ls,
            "cat": self._cat,
            "touch": self._touch,
            "write": self._write,
            "append": self._append,
            "mv": self._mv,
            "cp": self._cp,
            "mkdir": self._mkdir,
            "rm": self._rm,
            "stat": self._stat,
            "search": self._search,
            "edit": lambda a: self._edit(a, open_editor),
            "run": self._run,
            "task": self._dual_agent,
            "pause": self._pause_task,
            "continue": self._continue_task,
        }

        handler = handlers.get(command)
        if not handler:
            return CommandResult(False, f"Unknown command: /{command}. Type /help for commands.")

        try:
            return handler(args)
        except Exception as exc:
            return CommandResult(False, f"Error: {exc}")

    def _help(self, args: list[str]) -> CommandResult:
        lines = [
            "CHAT MODE:",
            "  Just type to chat with the AI model",
            "",
            "SLASH COMMANDS:",
            "  /help                         Show this help",
            "  /exit | /quit                 Exit the shell",
            "  /clear                        Clear the log",
            "  /history                      Show command history",
            "",
            "MODEL COMMANDS:",
            "  /model                        Open model selector",
            "  /context                      Show context usage",
            "  /reset                        Reset chat history",
            "",
            "FILE COMMANDS:",
            "  /pwd                          Show workspace root",
            "  /cd <path>                    Change working directory",
            "  /ls [path]                    List directory",
            "  /cat <path>                   Show file contents",
            "  /touch <path>                 Create empty file",
            "  /write <path> <text>          Write/overwrite file",
            "  /append <path> <text>         Append to file",
            "  /mv <src> <dest>              Move/rename file",
            "  /cp <src> <dest>              Copy file",
            "  /edit <path>                  Open editor",
            "  /mkdir <path>                 Create directory",
            "  /rm [-r] <path>               Remove file or directory",
            "  /stat <path>                  Show file metadata",
            "  /search <pattern> <path>      Search file contents",
            "",
            "AUTOMATION:",
            "  /run <command>                Run shell command",
            "  /task [options] <task>        Run dual-agent automation task",
            "    Options: --url URL, --max-cycles N",
            "  /continue [max_cycles]        Resume a paused dual-agent task",
            "",
            "PAUSE MODE:",
            "  Press Esc once to pause a running task",
            "  Press Esc again (while pausing or paused) to cancel the task completely",
            "  While paused, chat directly with the Memory Agent",
            "  Use /continue to resume the task",
        ]
        return CommandResult(True, "\n".join(lines))

    def _exit(self, args: list[str]) -> CommandResult:
        return CommandResult(True, "Exiting...", exit=True)

    def _clear(self, args: list[str]) -> CommandResult:
        return CommandResult(True, "", clear=True)

    def _history(self, args: list[str]) -> CommandResult:
        if not self.history:
            return CommandResult(True, "(no history)")
        lines = [f"{idx + 1}: {command}" for idx, command in enumerate(self.history)]
        return CommandResult(True, "\n".join(lines))

    def _model(self, args: list[str]) -> CommandResult:
        if args:
            new_model = args[0]
            if new_model not in AVAILABLE_MODELS:
                return CommandResult(False, f"Unknown model: {new_model}.")
            self.current_model = new_model
            self.max_tokens = MODEL_CONTEXT_SIZES.get(new_model, 128000)
            self.update_status()
            return CommandResult(True, f"Switched to model: {self.current_model}")

        self.open_model_picker()
        return CommandResult(True, "")

    def _context(self, args: list[str]) -> CommandResult:
        pct = self.get_context_percentage()
        lines = [
            f"Model: {self.current_model}",
            f"Context used: {self.total_tokens_used:,} / {self.max_tokens:,} tokens",
            f"Usage: {pct:.1f}%",
            f"Messages in history: {len(self.chat_history)}"
        ]
        return CommandResult(True, "\n".join(lines))

    def _reset_chat(self, args: list[str]) -> CommandResult:
        self.chat_history = []
        self.total_tokens_used = 0
        self.update_status()
        return CommandResult(True, "Chat history reset.")

    def _pwd(self, args: list[str]) -> CommandResult:
        return CommandResult(True, str(self.cwd))

    def _cd(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /cd <path>")
        target = self._resolve_path(args[0])
        if not target.exists() or not target.is_dir():
            return CommandResult(False, f"Not a directory: {target}")
        self.cwd = target
        return CommandResult(True, str(self.cwd))

    def _ls(self, args: list[str]) -> CommandResult:
        target = self._resolve_path(args[0]) if args else self.cwd
        if not target.exists():
            return CommandResult(False, f"Not found: {target}")
        if not target.is_dir():
            return CommandResult(False, f"Not a directory: {target}")
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        rendered = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            rendered.append(f"{entry.name}{suffix}")
        return CommandResult(True, "\n".join(rendered) if rendered else "(empty)")

    def _cat(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /cat <path>")
        target = self._resolve_path(args[0])
        if not target.exists() or not target.is_file():
            return CommandResult(False, f"Not a file: {target}")
        content = target.read_text(encoding="utf-8")
        return CommandResult(True, content)

    def _touch(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /touch <path>")
        target = self._resolve_path(args[0])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        return CommandResult(True, f"Touched {target}")

    def _write(self, args: list[str]) -> CommandResult:
        if len(args) < 2:
            return CommandResult(False, "Usage: /write <path> <text>")
        target = self._resolve_path(args[0])
        target.parent.mkdir(parents=True, exist_ok=True)
        text = " ".join(args[1:])
        target.write_text(text, encoding="utf-8")
        return CommandResult(True, f"Wrote {target}")

    def _append(self, args: list[str]) -> CommandResult:
        if len(args) < 2:
            return CommandResult(False, "Usage: /append <path> <text>")
        target = self._resolve_path(args[0])
        target.parent.mkdir(parents=True, exist_ok=True)
        text = " ".join(args[1:])
        with target.open("a", encoding="utf-8") as handle:
            handle.write(text)
        return CommandResult(True, f"Appended {target}")

    def _mv(self, args: list[str]) -> CommandResult:
        if len(args) < 2:
            return CommandResult(False, "Usage: /mv <src> <dest>")
        source = self._resolve_path(args[0])
        dest = self._resolve_path(args[1])
        if not source.exists():
            return CommandResult(False, f"Not found: {source}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))
        return CommandResult(True, f"Moved {source} -> {dest}")

    def _cp(self, args: list[str]) -> CommandResult:
        if len(args) < 2:
            return CommandResult(False, "Usage: /cp <src> <dest>")
        source = self._resolve_path(args[0])
        dest = self._resolve_path(args[1])
        if not source.exists() or not source.is_file():
            return CommandResult(False, f"Not a file: {source}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return CommandResult(True, f"Copied {source} -> {dest}")

    def _mkdir(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /mkdir <path>")
        target = self._resolve_path(args[0])
        target.mkdir(parents=True, exist_ok=True)
        return CommandResult(True, f"Created {target}")

    def _rm(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /rm [-r] <path>")
        recursive = False
        target_arg = args[0]
        if target_arg == "-r":
            if len(args) < 2:
                return CommandResult(False, "Usage: /rm [-r] <path>")
            recursive = True
            target_arg = args[1]
        target = self._resolve_path(target_arg)
        if not target.exists():
            return CommandResult(False, f"Not found: {target}")
        if target.is_dir():
            if not recursive:
                return CommandResult(False, "Use /rm -r for directories")
            for item in sorted(target.rglob("*"), reverse=True):
                if item.is_file() or item.is_symlink():
                    item.unlink()
                else:
                    item.rmdir()
            target.rmdir()
            return CommandResult(True, f"Removed directory {target}")
        target.unlink()
        return CommandResult(True, f"Removed {target}")

    def _stat(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /stat <path>")
        target = self._resolve_path(args[0])
        if not target.exists():
            return CommandResult(False, f"Not found: {target}")
        stat_info = target.stat()
        lines = [
            f"Path: {target}",
            f"Type: {'directory' if target.is_dir() else 'file'}",
            f"Size: {stat_info.st_size} bytes",
            f"Modified: {datetime.fromtimestamp(stat_info.st_mtime)}",
        ]
        return CommandResult(True, "\n".join(lines))

    def _search(self, args: list[str]) -> CommandResult:
        if len(args) < 2:
            return CommandResult(False, "Usage: /search <pattern> <path>")
        pattern = re.compile(args[0])
        target = self._resolve_path(args[1])
        if not target.exists():
            return CommandResult(False, f"Not found: {target}")
        matches = []
        paths = [target] if target.is_file() else list(target.rglob("*"))
        for file_path in paths:
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for index, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    matches.append(f"{file_path}:{index}: {line.strip()}")
        return CommandResult(True, "\n".join(matches) if matches else "(no matches)")

    def _edit(self, args: list[str], open_editor: Callable[[Path, str], None]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /edit <path>")
        target = self._resolve_path(args[0])
        content = target.read_text(encoding="utf-8") if target.exists() else ""
        open_editor(target, content)
        return CommandResult(True, f"Opened editor for {target}")

    def _run(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /run <command>")
        command_str = " ".join(args)
        result = subprocess.run(
            command_str,
            shell=True,
            cwd=self.cwd,
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip()
        error = result.stderr.strip()
        parts: Iterable[str] = []
        if output:
            parts = [output]
        if error:
            parts = [*parts, f"[stderr]\n{error}"]
        if result.returncode != 0:
            parts = [*parts, f"[exit code] {result.returncode}"]
        return CommandResult(result.returncode == 0, "\n".join(parts) or "(no output)")

    def _dual_agent(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(False, "Usage: /task [--url URL] [--max-cycles N] <task>")
        try:
            url = None
            max_cycles = 50
            idx = 0
            while idx < len(args):
                if args[idx] == "--url" and idx + 1 < len(args):
                    url = args[idx + 1]
                    idx += 2
                elif args[idx] == "--max-cycles" and idx + 1 < len(args):
                    max_cycles = int(args[idx + 1])
                    idx += 2
                else:
                    break
            task = " ".join(args[idx:])
            if not task:
                return CommandResult(False, "Usage: /task [--url URL] [--max-cycles N] <task>")
        except ValueError as exc:
            return CommandResult(False, f"Invalid option: {exc}")

        self.start_task_log(task)
        
        # --- SINGLE AGENT INTEGRATION ---
        try:
            # We use the new SingleAgent
            # It logs automatically to detail_log via the callback we registered
            summary = self.single_agent.run(task, max_turns=max_cycles)
            success = True # SingleAgent doesn't return success explicitly, assume success if no exception
            # We don't fail on "Max turns" anymore, as per user experience
            if "Error" in summary and "Max turns" not in summary:
                success = False
        except Exception as e:
            summary = f"Agent failed: {e}"
            success = False
            
        self.finish_task_log(success, summary)
        return CommandResult(success, summary)
    
    def _pause_task(self, args: list[str]) -> CommandResult:
        """Request the running agent to pause."""
        if not self.single_agent.current_task:
            return CommandResult(False, "No task is currently running.")
        
        self.single_agent.pause()
        return CommandResult(True, f"Pause requested for: {self.single_agent.current_task}. Agent will stop after current turn.")
    
    def _continue_task(self, args: list[str]) -> CommandResult:
        """Continue a paused agent task."""
        # Check SingleAgent first (new)
        if not self.single_agent.current_task:
            return CommandResult(False, "No paused task to continue. Start a task with /task first.")
        
        max_cycles = 50
        if args:
            try:
                max_cycles = int(args[0])
            except ValueError:
                return CommandResult(False, "Usage: /continue [max_cycles]")
        
        self.start_task_log(f"Resuming: {self.single_agent.current_task}")
        
        try:
            summary = self.single_agent.continue_task(max_turns=max_cycles)
            success = True
            if "Error" in summary and "Max turns" not in summary:
                success = False
        except Exception as e:
            summary = f"Resume failed: {e}"
            success = False
            
        self.finish_task_log(success, summary)
        return CommandResult(success, summary)


class AgentShellApp(App):
    """Textual app for agent control and CLI commands."""

    CSS = """
    ChatLog {
        height: 1fr;
        padding: 1;
        background: $surface;
        scrollbar-gutter: stable;
        overflow-y: scroll;
    }

    TextMessageBlock {
        margin: 0 0 1 0;
        padding: 0;
        background: transparent;
        height: auto;
    }

    #message_text {
        background: $surface-lighten-1;
        border: none;
        padding: 0 1;
        width: 100%;
    }

    TaskBlock {
        margin: 1 0;
        padding: 1 2;
        background: $surface-lighten-2;
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
        background: $background-darken-3;
        color: $text-muted;
        border: none;
    }

    #status_bar {
        dock: bottom;
        height: 2;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }

    #slash_suggestions {
        height: auto;
        background: $primary-darken-1;
        color: $text;
        padding: 0 1;
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

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.base_path = Path(__file__).resolve().parents[1]
        self.log_widget: Optional[LogArea] = None
        self.command_input: Optional[Input] = None
        self.status_bar: Optional[Static] = None
        self.slash_suggestions: Optional[SlashSuggestionBar] = None
        self.processor: Optional[ChatProcessor] = None
        
        # Escape detection state
        self._last_escape_time: float = 0
        self._escape_confirm_window: float = 0.5  # seconds
        
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

        self.slash_suggestions = SlashSuggestionBar("", id="slash_suggestions")
        self.slash_suggestions.display = False
        yield self.slash_suggestions
        self.command_input = Input(placeholder="Chat with AI or use /commands", id="command")
        yield self.command_input
        self.status_bar = Static("", id="status_bar")
        yield self.status_bar
        yield Footer()

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
        )
        self._update_status()
        self._update_slash_suggestions("")
        self._log("Welcome! Type to chat with the AI, or use /help for commands.")
        self._log("Workspace: " + str(self.base_path))
        
        # Start status update timer (updates every second)
        self._status_timer = self.set_interval(1.0, self._update_status)

    def _run_safe(self, func: Callable) -> None:
        """Run a function safely on the UI thread."""
        try:
            # Check if we are on the UI thread using multiple indicators
            is_ui_thread = False
            if hasattr(self, "_thread_id"):
                is_ui_thread = threading.get_ident() == self._thread_id
            
            if is_ui_thread:
                func()
            else:
                self.call_from_thread(func)
        except Exception:
            # Fallback for early startup
            try:
                func()
            except:
                pass

    def _log(self, message: str) -> None:
        def do_log():
            # If this is a task-related log and we have an active task block, update it
            if hasattr(self, "_active_task_block") and self._active_task_block:
                # Basic heuristics to extract status from the log line
                status = message.strip()
                if "[Cycle" in status:
                    self._active_task_block.update_status(status)
                elif "TASK COMPLETE" in status or "TASK PAUSED" in status:
                    # We'll finalize in _log_task_finished
                    pass
                else:
                    self._active_task_block.update_status(status)
                return

            # Otherwise, create a new text block
            block = TextMessageBlock(message)
            self.chat_log.mount(block)
            self.chat_log.call_after_refresh(self.chat_log.scroll_end)
        
        self._run_safe(do_log)

    def _log_inline(self, message: str) -> None:
        def do_log_inline():
            # Check if last block is a TextMessageBlock and not a task block
            children = self.chat_log.children
            if children and isinstance(children[-1], TextMessageBlock):
                children[-1].append_text(message)
            else:
                block = TextMessageBlock(message)
                self.chat_log.mount(block)
                self.chat_log.call_after_refresh(self.chat_log.scroll_end)
        
        self._run_safe(do_log_inline)

    def _log_agent(self, message: str) -> None:
        def do_log_agent():
            if not hasattr(self, "agent_log") or not self.agent_log:
                return
            
            # Show the global details if it's currently hidden
            try:
                collapsible = self.query_one("#agent_details_collapsible", Collapsible)
                collapsible.remove_class("hidden")
            except:
                pass
            
            self.agent_log.append_log(message)
            
            # Also feed to the active task block if one exists
            if hasattr(self, "_active_task_block") and self._active_task_block:
                self._active_task_block.append_detail(message)
                
        self._run_safe(do_log_agent)
            
    def _start_task_log(self, task_name: str) -> None:
        def do_start():
            block = TaskBlock(task_name)
            self.chat_log.mount(block)
            self._active_task_block = block
            self.chat_log.call_after_refresh(self.chat_log.scroll_end)
            
            # Clear global agent log for fresh monitoring
            if hasattr(self, "agent_log") and self.agent_log:
                self.agent_log.text = ""
                
        self._run_safe(do_start)

    def _finish_task_log(self, success: bool, summary: str) -> None:
        def do_finish():
            if hasattr(self, "_active_task_block") and self._active_task_block:
                self._active_task_block.finish(success, summary)
                self._active_task_block = None
            
            # Hide the global details monitor
            try:
                collapsible = self.query_one("#agent_details_collapsible", Collapsible)
                collapsible.add_class("hidden")
            except Exception:
                pass
            
        self._run_safe(do_finish)
    
    def _format_elapsed_time(self, seconds: float) -> str:
        """Format elapsed time adaptively: 45s or 2:30"""
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"
    
    def _get_model_provider(self, model: str) -> str:
        """Get the provider name for a model."""
        config = MODEL_CONFIGS.get(model, {})
        provider = config.get("provider", "unknown")
        return provider.capitalize()

    def _update_status(self) -> None:
        def do_update():
            if not self.status_bar or not self.processor:
                return
            
            model = self.processor.current_model
            provider = self._get_model_provider(model)
            dual_agent = self.processor.dual_agent
            context_tokens = self.processor.total_tokens_used
            context_max = self.processor.max_tokens
            context_pct = self.processor.get_context_percentage()
            context_info = f"{context_tokens:,}/{context_max:,} ({context_pct:.1f}%)"
            
            # Build status line 1: Model info and running state
            if dual_agent.is_running or dual_agent.is_paused:
                if dual_agent.is_paused:
                    status_icon = "⏸"
                    status_text = "PAUSED"
                else:
                    status_icon = "●"
                    status_text = "Running"
                
                # Calculate elapsed time
                elapsed = ""
                if dual_agent.start_time:
                    elapsed_seconds = time.time() - dual_agent.start_time
                    elapsed = f" · {self._format_elapsed_time(elapsed_seconds)}"
                
                line1 = f"{status_icon} {status_text}{elapsed} · {model} {provider} · {context_info}"
            else:
                line1 = f"{model} {provider} · {context_info}"
            
            # Build status line 2: Shortcuts
            if dual_agent.is_running:
                if dual_agent.is_paused:
                    line2 = "esc cancel · /continue resume · Type to chat with Memory Agent"
                elif dual_agent.pause_requested:
                    line2 = "Pausing... · esc cancel"
                else:
                    line2 = "esc pause · esc (after pause) cancel"
            else:
                # Regular CLI or idle
                line2 = "esc esc  interrupt"
            
            self.status_bar.update(f"{line1}\n{line2}")
        
        self._run_safe(do_update)

    def _update_slash_suggestions(self, input_text: str) -> None:
        if not self.slash_suggestions:
            return
        suggestions = self._get_slash_suggestions(input_text)
        self.slash_suggestions.update_suggestions(suggestions)
        self.refresh(layout=True)

    def _get_slash_suggestions(self, input_text: str) -> list[str]:
        if not input_text.startswith("/"):
            return []
        partial = input_text[1:]
        if not partial:
            commands = sorted(SLASH_COMMANDS)
        else:
            commands = sorted(cmd for cmd in SLASH_COMMANDS if cmd.startswith(partial))
        return [f"/{command}" for command in commands[:SLASH_SUGGESTION_LIMIT]]

    def _open_editor(self, path: Path, content: str) -> None:
        def save_callback(text: str) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            self._log(f"Saved {path}")

        self.push_screen(EditorScreen(path, content, save_callback))

    def _open_model_picker(self) -> None:
        if not self.processor:
            return

        def on_select(model: str) -> None:
            if not self.processor:
                return
            self.processor.current_model = model
            self.processor.max_tokens = MODEL_CONTEXT_SIZES.get(model, 128000)
            self._update_status()
            self._log(f"Switched to model: {model}")

        self.push_screen(ModelSelectScreen(AVAILABLE_MODELS, self.processor.current_model, on_select))

    def _handle_input(self, input_text: str) -> None:
        if not self.processor:
            return
        result = self.processor.handle_input(input_text, self._open_editor)
        
        if result.clear and self.log_widget:
            self.log_widget.text = ""
        if result.output:
            self._log(result.output)
        if not result.success and not input_text.startswith("/"):
            pass  # Don't show "command failed" for chat
        elif not result.success:
            self._log("(command failed)")
        if result.exit:
            self.action_quit()

    def _handle_async(self, input_text: str) -> None:
        async def runner_logic() -> None:
            # Running inside an active asyncio loop now!
            try:
                # We need to run the synchronous _handle_input
                # Since we are in an async function, we can just call it
                # It will block the thread, but that's fine as it's a dedicated thread
                self._handle_input(input_text)
            except Exception as e:
                self._log(f"[FATAL ERROR in runner] {str(e)}")
                import traceback
                self._log_agent(traceback.format_exc())

        def thread_entry() -> None:
            asyncio.run(runner_logic())

        thread = Thread(target=thread_entry, daemon=True)
        thread.start()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_slash_suggestions(event.value)

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_text = event.value.strip()
        event.input.value = ""
        self._update_slash_suggestions("")
        if not input_text:
            return
        
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
                # Check if this is pause mode chat
                if self.processor and self.processor.dual_agent.is_paused:
                    self._log(f"[To Memory Agent]: {input_text}")
                else:
                    self._log(f"You: {input_text}")
                    self._log("")
            self._handle_async(input_text)
        else:
            self._handle_input(input_text)

    def on_key(self, event: events.Key) -> None:
        # Handle Escape key
        if event.key == "escape":
            # Case 1: Dual Agent is running or paused
            # But if cancel is already requested, we treat it as "normal" mode (Case 2)
            if self.processor and self.processor.dual_agent.is_running and not self.processor.dual_agent.cancel_requested:
                # If not paused AND pause not even requested yet: first Esc triggers pause
                if not self.processor.dual_agent.is_paused and not self.processor.dual_agent.pause_requested:
                    self.processor.dual_agent.request_pause()
                else:
                    # Already paused OR pause requested: second Esc triggers cancel
                    self.processor.dual_agent.request_cancel()
                self._update_status()
                return
            
            # Case 2: Regular CLI agent or idle - double Esc to interrupt
            current_time = time.time()
            if current_time - self._last_escape_time < self._escape_confirm_window:
                # Double Esc detected - interrupt
                self._log("[INTERRUPT] Esc+Esc detected. Interrupting...")
                # Add logic for regular interrupt here if needed
                self._last_escape_time = 0 
            else:
                self._last_escape_time = current_time
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
