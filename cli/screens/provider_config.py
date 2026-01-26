"""Provider Configuration Screen - for managing API keys."""

from typing import Callable, List, Dict, Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Input, Label, Button, Checkbox, Static

from cli.config_manager import ConfigManager, PROVIDERS


class ProviderRow(Horizontal):
    """A single provider configuration row."""
    
    DEFAULT_CSS = """
    ProviderRow {
        height: 3;
        margin-bottom: 1;
    }
    
    ProviderRow .provider-checkbox {
        width: 20;
        padding-top: 1;
    }
    
    ProviderRow .provider-key-input {
        width: 35;
    }
    
    ProviderRow .provider-test-btn {
        width: 8;
        margin-left: 1;
    }
    
    ProviderRow .provider-status {
        width: 10;
        padding-top: 1;
        margin-left: 1;
    }
    """
    
    def __init__(self, provider: Dict[str, Any], config_manager: ConfigManager) -> None:
        super().__init__()
        self.provider = provider
        self.config_manager = config_manager
        self.provider_id = provider["id"]
        self.provider_name = provider["name"]
    
    def compose(self) -> ComposeResult:
        # Check if already configured
        has_key = self.config_manager.get_api_key(self.provider_id) is not None
        
        yield Checkbox(
            self.provider_name, 
            value=has_key,
            id=f"enable_{self.provider_id}",
            classes="provider-checkbox"
        )
        yield Input(
            placeholder=f"{self.provider_name} API Key",
            password=True,
            id=f"key_{self.provider_id}",
            classes="provider-key-input"
        )
        yield Button(
            "Test", 
            id=f"test_{self.provider_id}",
            classes="provider-test-btn"
        )
        yield Label(
            "✓ OK" if has_key else "",
            id=f"status_{self.provider_id}",
            classes="provider-status"
        )


class ProviderConfigScreen(Screen):
    """Modal screen for configuring provider API keys."""
    
    CSS = """
    ProviderConfigScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #provider_config_container {
        width: 80;
        height: auto;
        max-height: 28;
        background: #1a1a1a;
        border: solid #333333;
        padding: 1 2;
    }
    
    #provider_header {
        height: 1;
        margin-bottom: 1;
    }
    
    #provider_title {
        width: 1fr;
        text-style: bold;
    }
    
    #provider_close_hint {
        width: auto;
        color: #666666;
    }
    
    #provider_info {
        margin-bottom: 1;
        color: #888888;
    }
    
    #provider_list {
        margin-bottom: 1;
    }
    
    #provider_actions {
        height: 3;
        margin-top: 1;
    }
    
    #save_providers {
        margin-right: 1;
    }
    
    #provider_footer {
        margin-top: 1;
        text-align: center;
        color: #666666;
    }
    """
    
    BINDINGS = [
        ("escape", "cancel", "Close"),
    ]
    
    def __init__(
        self, 
        config_manager: ConfigManager,
        on_save: Callable[[], None],
    ) -> None:
        """Initialize provider config screen.
        
        Args:
            config_manager: ConfigManager instance.
            on_save: Callback when configuration is saved.
        """
        super().__init__()
        self.config_manager = config_manager
        self.on_save_callback = on_save
    
    def compose(self) -> ComposeResult:
        with Vertical(id="provider_config_container"):
            with Horizontal(id="provider_header"):
                yield Label("Provider Configuration", id="provider_title")
                yield Label("[dim]esc[/dim]", id="provider_close_hint")
            
            yield Label(
                "[dim]API keys are stored securely using your system's keychain.[/dim]",
                id="provider_info"
            )
            
            with Vertical(id="provider_list"):
                for provider in PROVIDERS:
                    yield ProviderRow(provider, self.config_manager)
            
            with Horizontal(id="provider_actions"):
                yield Button("Save", variant="primary", id="save_providers")
                yield Button("Cancel", id="cancel_providers")
            
            yield Label(
                "[dim]Enter API keys and click Test to validate[/dim]",
                id="provider_footer"
            )
    
    @on(Button.Pressed, "#save_providers")
    def handle_save(self, event: Button.Pressed) -> None:
        """Save all provider configurations."""
        saved_count = 0
        
        for provider in PROVIDERS:
            provider_id = provider["id"]
            
            # Get the key input
            try:
                key_input = self.query_one(f"#key_{provider_id}", Input)
                checkbox = self.query_one(f"#enable_{provider_id}", Checkbox)
                
                key = key_input.value.strip()
                
                if key and checkbox.value:
                    # Save the key
                    if self.config_manager.set_api_key(provider_id, key):
                        saved_count += 1
                elif not checkbox.value:
                    # Delete the key if disabled
                    self.config_manager.delete_api_key(provider_id)
                    
            except Exception as e:
                self.notify(f"Error saving {provider_id}: {e}", severity="error")
        
        self.notify(f"Saved {saved_count} provider(s)", timeout=2)
        self.app.pop_screen()
        self.on_save_callback()
    
    @on(Button.Pressed, "#cancel_providers")
    def handle_cancel(self, event: Button.Pressed) -> None:
        self.app.pop_screen()
    
    @on(Button.Pressed)
    def handle_test(self, event: Button.Pressed) -> None:
        """Handle test button clicks."""
        button_id = event.button.id
        if not button_id or not button_id.startswith("test_"):
            return
        
        provider_id = button_id.replace("test_", "")
        
        # Get the key from input
        try:
            key_input = self.query_one(f"#key_{provider_id}", Input)
            status_label = self.query_one(f"#status_{provider_id}", Label)
            
            key = key_input.value.strip()
            
            if not key:
                # Try existing key
                key = self.config_manager.get_api_key(provider_id)
                if not key:
                    status_label.update("[red]No key[/red]")
                    return
            
            # Temporarily set key for testing
            if key:
                # Test the key
                # For now, just do a simple validation
                success, message = self._test_key(provider_id, key)
                
                if success:
                    status_label.update("[green]✓ OK[/green]")
                else:
                    status_label.update(f"[red]✗[/red]")
                    self.notify(f"Test failed: {message}", severity="error", timeout=3)
                    
        except Exception as e:
            self.notify(f"Error testing: {e}", severity="error")
    
    def _test_key(self, provider_id: str, key: str) -> tuple[bool, str]:
        """Test an API key.
        
        For now, just does basic validation. Full test would require API calls.
        """
        provider_info = next((p for p in PROVIDERS if p["id"] == provider_id), None)
        if not provider_info:
            return False, "Unknown provider"
        
        key_prefix = provider_info.get("key_prefix", "")
        
        # Basic prefix validation
        if key_prefix and not key.startswith(key_prefix):
            return False, f"Key should start with '{key_prefix}'"
        
        # Minimum length check
        if len(key) < 10:
            return False, "Key too short"
        
        return True, "OK"
    
    def action_cancel(self) -> None:
        self.app.pop_screen()
