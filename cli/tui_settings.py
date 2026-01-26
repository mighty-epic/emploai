"""Settings screen for the TUI."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Footer, Switch, Label, Button, Input, Static
from cli.config_manager import get_config_manager

class SettingsScreen(Screen):
    """A screen for application settings."""
    
    BINDINGS = [
        ("escape", "dismiss", "Discard & Back"),
        ("ctrl+s", "save", "Save & Back"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_manager = get_config_manager()

    def compose(self) -> ComposeResult:
        yield Header()
        
        with VerticalScroll(id="settings_container"):
            yield Label("[bold cyan]Agent Safety Settings[/bold cyan]", classes="settings_section_title")
            
            with Horizontal(classes="setting_row"):
                yield Label("Workspace Restriction (1.A vs 1.B)", classes="setting_label")
                yield Switch(
                    value=self.config_manager.get_workspace_restriction(), 
                    id="workspace_restriction"
                )
            yield Label("[dim]If enabled, the agent can only access files within the codebase folder (1.A). If disabled, it can access any file on your system (1.B).[/dim]", classes="setting_hint")
            
            with Horizontal(classes="setting_row"):
                yield Label("Command Confirmation (2.A vs 2.B)", classes="setting_label")
                yield Switch(
                    value=self.config_manager.get_command_confirmation(), 
                    id="command_confirmation"
                )
            yield Label("[dim]If enabled, the agent must ask for permission before running any terminal command (2.A).[/dim]", classes="setting_hint")
            
            yield Label("[bold cyan]Command Allow List[/bold cyan]", classes="settings_section_title")
            yield Label("[dim]Enter commands (separated by commas) that the agent can run without asking (e.g. 'ls, pwd, cat').[/dim]", classes="setting_hint")
            
            allow_list = ", ".join(self.config_manager.get_command_allow_list())
            yield Input(value=allow_list, placeholder="ls, pwd, git status", id="command_allow_list")

            with Horizontal(id="settings_actions"):
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Save Settings", variant="success", id="save_btn")

        yield Footer()

    def action_save(self) -> None:
        """Save settings and dismiss."""
        wr_switch = self.query_one("#workspace_restriction", Switch)
        cc_switch = self.query_one("#command_confirmation", Switch)
        al_input = self.query_one("#command_allow_list", Input)
        
        self.config_manager.set_workspace_restriction(wr_switch.value)
        self.config_manager.set_command_confirmation(cc_switch.value)
        
        # Parse allow list
        raw_list = al_input.value
        allow_list = [item.strip() for item in raw_list.split(",") if item.strip()]
        self.config_manager.set_command_allow_list(allow_list)
        
        self.app.notify("Settings saved successfully!")
        self.dismiss(True)

    @on(Button.Pressed, "#save_btn")
    def on_save_click(self) -> None:
        self.action_save()

    @on(Button.Pressed, "#cancel_btn")
    def on_cancel_click(self) -> None:
        self.dismiss(False)

    DEFAULT_CSS = """
    #settings_container {
        padding: 2 4;
    }
    
    .settings_section_title {
        margin-top: 2;
        margin-bottom: 1;
        background: transparent;
    }
    
    .setting_row {
        height: 3;
        align: middle left;
    }
    
    .setting_label {
        width: 40;
    }
    
    .setting_hint {
        margin-bottom: 2;
        margin-left: 2;
        height: auto;
    }
    
    #command_allow_list {
        margin-bottom: 2;
    }
    
    #settings_actions {
        margin-top: 3;
        height: 3;
        align: middle right;
    }
    
    #settings_actions Button {
        margin-left: 2;
    }
    """
