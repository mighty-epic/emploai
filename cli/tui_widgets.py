"""Reusable Textual widgets for the TUI."""

from __future__ import annotations

import math

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Collapsible, Label, Static, TextArea, Markdown


class LoadingIndicator(Static):
    """A fluid loading indicator using Unicode braille waves."""
    
    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.frame = 0
        self.active = False
        # Fluid wave patterns using braille
        self.chars = "⠁⠂⠄⡀⢀⠠⠐⠈"
        self.width = 8
        
    def start(self):
        if not self.active:
            self.active = True
            self.frame = 0
            self.update_wave()
        
    def stop(self):
        self.active = False
        self.update("")

    def update_wave(self):
        if not self.active:
            return
            
        content = ""
        for i in range(self.width):
            # Create a moving wave effect
            idx1 = (self.frame + i) % len(self.chars)
            idx2 = (self.frame + i + 4) % len(self.chars) # Offset for second layer
            content += self.chars[idx1]
            
        self.update(f"[bold #4ade80]{content}[/]")
        self.frame += 1
    
    # Alias for compatibility with existing code
    update_snake = update_wave


class LogArea(TextArea):
    """Read-only log widget that auto-copies selections."""

    def __init__(self, *args, follow_cursor: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_copied = ""
        self._pause_autoscroll = False
        self._drag_autoscroll_step = 2
        self._drag_autoscroll_margin = 1
        self._follow_cursor = follow_cursor

    def append_log(self, message: str) -> None:
        # Always append at the very end regardless of cursor position
        last_line = max(self.document.line_count - 1, 0)
        end_location = (
            last_line,
            len(self.document.lines[last_line]) if self.document.lines else 0,
        )
        scroll_end = self._follow_cursor and not self._pause_autoscroll
        
        # Unlock, insert, then relock if needed
        was_read_only = self.read_only
        self.read_only = False
        try:
            self.insert(message, location=end_location, scroll_end=scroll_end)
        finally:
            self.read_only = was_read_only

        if self._follow_cursor:
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
            # Scroll up (negative relative y)
            self.scroll_relative(y=-self._drag_autoscroll_step)
        elif offset_y >= region.height - 1 - self._drag_autoscroll_margin:
            # Scroll down (positive relative y)
            self.scroll_relative(y=self._drag_autoscroll_step)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        handler = getattr(super(), "on_mouse_down", None)
        if callable(handler):
            handler(event)
        self._pause_autoscroll = True

    def on_mouse_move(self, event: events.MouseMove) -> None:
        self._handle_drag_autoscroll(event)
        handler = getattr(super(), "on_mouse_move", None)
        if callable(handler):
            handler(event)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        handler = getattr(super(), "on_mouse_up", None)
        if callable(handler):
            handler(event)
        self._pause_autoscroll = False
        self._copy_selection()
        # Refocus input logic: only refocus if it exists
        if hasattr(self.app, "command_input") and self.app.command_input:
            self.app.command_input.focus()


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

    DEFAULT_CSS = """
    TextMessageBlock {
        margin: 0 0 1 0;
        height: auto;
    }
    
    .user-message {
        background: #1f1f1f;
        border-left: wide $accent; 
        padding: 1 2;
        margin-bottom: 1;
        margin-top: 1;
    }
    
    .assistant-message {
        background: transparent;
        padding: 0;
        margin-bottom: 2;
    }

    .metadata {
        color: $text-muted;
        text-align: right;
        padding-right: 2;
        text-style: italic;
        width: 100%;
    }
    """

    def __init__(self, content: str = "", role: str = "info", model: str = "", timestamp: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.content = content
        self.role = role
        self.model = model
        self.timestamp = timestamp
        self.text_area = None

    def compose(self) -> ComposeResult:
        if self.role == "user":
            self.add_class("user-message")
        elif self.role == "assistant":
            self.add_class("assistant-message")

        # Use Markdown for message content to support native terminal selection (Shift+Select)
        # and better formatting.
        self.content_widget = Markdown(self.content, id="message_text")
        yield self.content_widget
        
        # Add metadata footer for assistant messages
        if self.role == "assistant":
            self.metadata_label = Label(self.get_meta_text(), classes="metadata")
            yield self.metadata_label

    def get_meta_text(self) -> str:
        meta_text = f"{self.model}"
        if self.timestamp:
            meta_text += f" • {self.timestamp}"
        return meta_text

    def update_metadata(self, model: str = "", timestamp: str = "") -> None:
        if model:
            self.model = model
        if timestamp:
            self.timestamp = timestamp
        if hasattr(self, "metadata_label"):
            self.metadata_label.update(self.get_meta_text())

    def on_mount(self) -> None:
        pass

    def on_resize(self, event: events.Resize) -> None:
        pass

    def append_text(self, text: str) -> None:
        self.content += text
        if hasattr(self, "content_widget"):
             self.content_widget.update(self.content)


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
            self.status_label = Label(
                f"🛠 [bold]Task:[/bold] {self.task_name}\n   └─ [cyan]{self.status}[/cyan]",
                id="task_status",
            )
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
        self.status_label.update(
            f"🛠 [bold]Task:[/bold] {self.task_name}\n   └─ [cyan]{self.status}[/cyan]"
        )

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
        self.status_label.update(
            f"{icon} [bold]Task:[/bold] {self.task_name}\n   └─ [{color}]{summary}[/{color}]"
        )

        # Show and populate the collapsible
        details = self.query_one("#task_details", Collapsible)
        details.display = True
        self.details_area.text = self.execution_logs
        if isinstance(self.details_area, LogArea):
            self.details_area.scroll_end(animate=False)
        # Scroll to bottom of container
        self.scroll_end()


class SuggestionItem(Label):
    """A clickable suggestion item."""

    def __init__(self, text: str, callback, is_top: bool = False) -> None:
        super().__init__(text, classes="suggestion-item")
        self.callback = callback
        self.suggestion_text = text
        if is_top:
            self.add_class("top-suggestion")

    def on_click(self) -> None:
        self.callback(self.suggestion_text)


class SlashSuggestionBar(VerticalScroll):
    """Scrollable suggestion list for slash commands."""

    DEFAULT_CSS = """
    SlashSuggestionBar {
        height: 10;
        background: #1a1a1a;
        color: $text;
        overflow-y: scroll;
        border-top: solid #333;
    }
    
    .suggestion-item {
        padding: 0 1;
        width: 100%;
    }
    
    .suggestion-item:hover {
        background: $accent;
        color: black;
    }

    .top-suggestion {
        background: #333;
        border-right: wide $accent;
        color: #fff;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.top_suggestion: str | None = None

    def update_suggestions(self, suggestions: list[str], callback) -> None:
        self.remove_children()
        self.top_suggestion = None
        
        if not suggestions:
            self.display = False
            return
            
        self.display = True
        self.top_suggestion = suggestions[0]
        for i, suggestion in enumerate(suggestions):
            self.mount(SuggestionItem(suggestion, callback, is_top=(i == 0)))
