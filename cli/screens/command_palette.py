"""Command Palette Screen - unified command interface."""

from typing import Callable, Dict, List, Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Input, Label, OptionList, Static


class CommandPaletteScreen(Screen):
    """Modal screen for the unified command palette."""
    
    CSS = """
    CommandPaletteScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #palette_container {
        width: 70;
        height: auto;
        max-height: 30;
        background: #1a1a1a;
        border: solid #333333;
        padding: 1 2;
    }
    
    #palette_header {
        height: 1;
        margin-bottom: 1;
    }
    
    #palette_title {
        width: 1fr;
        text-style: bold;
    }
    
    #palette_close_hint {
        width: auto;
        color: #666666;
    }
    
    #palette_search {
        margin-bottom: 1;
        background: #0a0a0a;
        border: solid #333333;
    }
    
    #palette_options {
        height: auto;
        max-height: 20;
        background: #0a0a0a;
        border: solid #333333;
    }
    
    #palette_footer {
        margin-top: 1;
        text-align: center;
        color: #666666;
    }
    """
    
    BINDINGS = [
        ("escape", "cancel", "Close"),
    ]
    
    # Command definitions with categories
    COMMANDS: Dict[str, List[Dict[str, Any]]] = {
        "suggested": [
            {"name": "Switch model", "key": "ctrl+m", "action": "switch_model", "icon": "🔄"},
            {"name": "Switch variant", "key": "ctrl+t", "action": "switch_variant", "icon": "⚡"},
        ],
        "session": [
            {"name": "New session", "key": "ctrl+n", "action": "new_session", "icon": "📝"},
            {"name": "Switch session", "key": "ctrl+l", "action": "switch_session", "icon": "📂"},
            {"name": "Rename session", "key": None, "action": "rename_session", "icon": "✏️"},
            {"name": "Delete session", "key": None, "action": "delete_session", "icon": "🗑️"},
            {"name": "Export session", "key": None, "action": "export_session", "icon": "📤"},
        ],
        "system": [
            {"name": "Configure providers", "key": None, "action": "configure_providers", "icon": "🔑"},
            {"name": "Toggle agent mode", "key": "tab", "action": "toggle_agent_mode", "icon": "🤖"},
            {"name": "Clear chat", "key": None, "action": "clear_chat", "icon": "🧹"},
            {"name": "Help", "key": None, "action": "show_help", "icon": "❓"},
        ],
    }
    
    def __init__(self, on_action: Callable[[str], None]) -> None:
        """Initialize command palette.
        
        Args:
            on_action: Callback when a command is selected. Receives action name.
        """
        super().__init__()
        self.on_action = on_action
        self.filtered_commands: List[Dict[str, Any]] = []
        self.all_commands: List[Dict[str, Any]] = []
        
        # Flatten commands for searching
        for category, cmds in self.COMMANDS.items():
            for cmd in cmds:
                cmd_copy = cmd.copy()
                cmd_copy["category"] = category
                self.all_commands.append(cmd_copy)
    
    def _format_command_display(self, cmd: Dict[str, Any], is_selected: bool = False) -> str:
        """Format a command for display in the option list."""
        icon = cmd.get("icon", "")
        name = cmd.get("name", "")
        key = cmd.get("key", "")
        
        prefix = "▶ " if is_selected else "  "
        
        # Calculate padding for alignment
        padding = max(1, 45 - len(prefix) - len(icon) - len(name) - 2)
        
        if key:
            return f"{prefix}{icon} {name}{' ' * padding}[dim]{key}[/dim]"
        return f"{prefix}{icon} {name}"
    
    def _get_commands_for_display(self, search_text: str = "") -> List[tuple[str, Dict[str, Any]]]:
        """Get commands to display based on search.
        
        Returns:
            List of (display_text, command_dict) tuples.
        """
        search_lower = search_text.lower().strip()
        
        if search_lower:
            # Filter by search
            filtered = [
                cmd for cmd in self.all_commands
                if search_lower in cmd.get("name", "").lower()
            ]
        else:
            filtered = self.all_commands
        
        result = []
        current_category = None
        
        for cmd in filtered:
            category = cmd.get("category", "")
            
            # Add category header if changed
            if category != current_category and not search_lower:
                current_category = category
                # Add separator for non-first categories
                if result:
                    result.append(("separator", None))
                result.append(("category", category.capitalize()))
            
            display = self._format_command_display(cmd)
            result.append((display, cmd))
        
        return result
    
    def _rebuild_options(self, search_text: str = "") -> None:
        """Rebuild the option list based on search text."""
        options = self.query_one("#palette_options", OptionList)
        options.clear_options()
        
        display_items = self._get_commands_for_display(search_text)
        self.filtered_commands = []
        
        for display, cmd in display_items:
            if display == "separator":
                options.add_option("[dim]──────────────────────────────────────────────[/dim]")
                self.filtered_commands.append(None)  # Placeholder
            elif display == "category":
                options.add_option(f"[bold dim]{cmd}[/bold dim]")
                self.filtered_commands.append(None)  # Placeholder
            else:
                options.add_option(display)
                self.filtered_commands.append(cmd)
        
        # Highlight first valid option
        for idx, cmd in enumerate(self.filtered_commands):
            if cmd is not None:
                options.highlighted = idx
                break
    
    def compose(self) -> ComposeResult:
        with Vertical(id="palette_container"):
            with Horizontal(id="palette_header"):
                yield Label("Commands", id="palette_title")
                yield Label("[dim]esc[/dim]", id="palette_close_hint")
            yield Input(placeholder="Search commands...", id="palette_search")
            yield OptionList(id="palette_options")
            yield Label("[dim]↑↓[/dim] navigate  [dim]enter[/dim] select", id="palette_footer")
    
    def on_mount(self) -> None:
        self._rebuild_options()
        # Focus the search input
        search_input = self.query_one("#palette_search", Input)
        search_input.focus()
    
    @on(Input.Changed, "#palette_search")
    def handle_search_changed(self, event: Input.Changed) -> None:
        self._rebuild_options(event.value)
    
    @on(OptionList.OptionSelected)
    def handle_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if idx < len(self.filtered_commands):
            cmd = self.filtered_commands[idx]
            if cmd is not None:  # Not a separator or category
                action = cmd.get("action", "")
                if action:
                    self.app.pop_screen()
                    self.on_action(action)
    
    def action_cancel(self) -> None:
        self.app.pop_screen()
