"""Session Switch Screen - for switching between chat sessions."""

from datetime import datetime, timedelta
from typing import Callable, List, Optional, Dict

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Input, Label, OptionList, Static

from cli.session_manager import SessionManager
from cli.models.session import SessionSummary


class SessionSwitchScreen(Screen):
    """Modal screen for switching between sessions."""
    
    CSS = """
    SessionSwitchScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #session_list_container {
        width: 70;
        height: auto;
        max-height: 26;
        background: #1a1a1a;
        border: solid #333333;
        padding: 1 2;
    }
    
    #session_header {
        height: 1;
        margin-bottom: 1;
    }
    
    #session_title {
        width: 1fr;
        text-style: bold;
    }
    
    #session_close_hint {
        width: auto;
        color: #666666;
    }
    
    #session_search {
        margin-bottom: 1;
        background: #0a0a0a;
        border: solid #333333;
    }
    
    #session_options {
        height: auto;
        max-height: 16;
        background: #0a0a0a;
        border: solid #333333;
    }
    
    #session_hints {
        margin-top: 1;
        text-align: center;
        color: #666666;
    }
    """
    
    BINDINGS = [
        ("escape", "cancel", "Close"),
        ("ctrl+d", "delete_session", "Delete"),
        ("ctrl+r", "rename_session", "Rename"),
    ]
    
    def __init__(
        self, 
        session_manager: SessionManager,
        current_session_id: Optional[str],
        on_select: Callable[[str], None],
        on_new: Callable[[], None],
        on_delete: Callable[[str], None],
        on_rename: Callable[[str], None],
    ) -> None:
        """Initialize session switch screen.
        
        Args:
            session_manager: SessionManager instance.
            current_session_id: ID of the current session.
            on_select: Callback when a session is selected.
            on_new: Callback to create a new session.
            on_delete: Callback to delete a session.
            on_rename: Callback to rename a session.
        """
        super().__init__()
        self.session_manager = session_manager
        self.current_session_id = current_session_id
        self.on_select = on_select
        self.on_new = on_new
        self.on_delete = on_delete
        self.on_rename = on_rename
        self.filtered_sessions: List[SessionSummary] = []
        # Track which indices are date headers (not selectable)
        self._date_header_indices: set = set()
    
    def _get_date_group(self, iso_time: str) -> str:
        """Get date group label for a timestamp."""
        try:
            dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            
            now = datetime.now()
            today = now.date()
            yesterday = today - timedelta(days=1)
            
            session_date = dt.date()
            
            if session_date == today:
                return "Today"
            elif session_date == yesterday:
                return "Yesterday"
            else:
                # Format as "Fri Jan 23 2026"
                return dt.strftime("%a %b %d %Y")
        except Exception:
            return "Unknown"
    
    def _format_time(self, iso_time: str) -> str:
        """Format timestamp as time (e.g., 3:41 PM)."""
        try:
            dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt.strftime("%-I:%M %p") if hasattr(dt, 'strftime') else dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            return ""
    
    def _format_session_display(self, session: SessionSummary, is_current: bool = False) -> str:
        """Format a session for display."""
        prefix = "● " if is_current else "  "
        name = session.name[:45]  # Truncate long names
        time_str = self._format_time(session.updated_at)
        
        # Calculate padding for right-aligned time
        padding = max(1, 55 - len(prefix) - len(name))
        
        if is_current:
            return f"[bold #f59e0b]{prefix}{name}{' ' * padding}{time_str}[/bold #f59e0b]"
        return f"{prefix}{name}{' ' * padding}[dim]{time_str}[/dim]"
    
    def _rebuild_options(self, search_text: str = "") -> None:
        """Rebuild the session list based on search text, grouped by date."""
        options = self.query_one("#session_options", OptionList)
        options.clear_options()
        
        all_sessions = self.session_manager.list_sessions()
        
        # Filter by search
        search_lower = search_text.lower().strip()
        if search_lower:
            filtered = [
                s for s in all_sessions
                if search_lower in s.name.lower()
            ]
        else:
            filtered = all_sessions
        
        self.filtered_sessions = []
        self._date_header_indices = set()
        
        if not filtered:
            options.add_option("[dim]No sessions found[/dim]")
            return
        
        # Group sessions by date
        groups: Dict[str, List[SessionSummary]] = {}
        for session in filtered:
            date_group = self._get_date_group(session.updated_at)
            if date_group not in groups:
                groups[date_group] = []
            groups[date_group].append(session)
        
        # Order groups: Today first, then Yesterday, then by date descending
        def group_sort_key(group_name: str) -> tuple:
            if group_name == "Today":
                return (0, "")
            elif group_name == "Yesterday":
                return (1, "")
            else:
                return (2, group_name)
        
        sorted_groups = sorted(groups.keys(), key=group_sort_key)
        
        option_idx = 0
        for group_name in sorted_groups:
            # Add date header
            options.add_option(f"[dim]{group_name}[/dim]")
            self._date_header_indices.add(option_idx)
            self.filtered_sessions.append(None)  # Placeholder for header
            option_idx += 1
            
            # Add sessions in this group
            for session in groups[group_name]:
                is_current = session.id == self.current_session_id
                display = self._format_session_display(session, is_current)
                options.add_option(display)
                self.filtered_sessions.append(session)
                option_idx += 1
        
        # Highlight current session or first non-header
        for idx, session in enumerate(self.filtered_sessions):
            if session is not None and session.id == self.current_session_id:
                options.highlighted = idx
                break
        else:
            # Highlight first non-header
            for idx in range(len(self.filtered_sessions)):
                if idx not in self._date_header_indices:
                    options.highlighted = idx
                    break
    
    def compose(self) -> ComposeResult:
        with Vertical(id="session_list_container"):
            with Horizontal(id="session_header"):
                yield Label("Sessions", id="session_title")
                yield Label("[dim]esc[/dim]", id="session_close_hint")
            yield Input(placeholder="Search", id="session_search")
            yield OptionList(id="session_options")
            yield Label("[dim]delete[/dim] ctrl+d  [dim]rename[/dim] ctrl+r", id="session_hints")
    
    def on_mount(self) -> None:
        self._rebuild_options()
        search_input = self.query_one("#session_search", Input)
        search_input.focus()
    
    @on(Input.Changed, "#session_search")
    def handle_search_changed(self, event: Input.Changed) -> None:
        self._rebuild_options(event.value)
    
    @on(OptionList.OptionSelected)
    def handle_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        # Skip if this is a date header
        if idx in self._date_header_indices:
            return
        if idx < len(self.filtered_sessions):
            session = self.filtered_sessions[idx]
            if session is not None:
                self.app.pop_screen()
                self.on_select(session.id)
    
    def _get_selected_session_id(self) -> Optional[str]:
        """Get the ID of the currently highlighted session."""
        options = self.query_one("#session_options", OptionList)
        idx = options.highlighted
        if idx is not None and idx < len(self.filtered_sessions):
            if idx not in self._date_header_indices:
                session = self.filtered_sessions[idx]
                if session is not None:
                    return session.id
        return None
    
    def action_cancel(self) -> None:
        self.app.pop_screen()
    
    def action_delete_session(self) -> None:
        session_id = self._get_selected_session_id()
        if session_id:
            self.app.pop_screen()
            self.on_delete(session_id)
    
    def action_rename_session(self) -> None:
        session_id = self._get_selected_session_id()
        if session_id:
            self.app.pop_screen()
            self.on_rename(session_id)
