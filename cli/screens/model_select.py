"""Model selection screen with search and favorites."""

from __future__ import annotations

from typing import Callable, Dict

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, OptionList

from cli.model_prefs import _add_recent_model, _load_model_prefs, _toggle_favorite


def _format_context_size(tokens: int) -> str:
    """Format context size as abbreviated string (e.g., 400K, 128K)."""
    if tokens >= 1000000:
        return f"{tokens // 1000000}M"
    elif tokens >= 1000:
        return f"{tokens // 1000}K"
    return str(tokens)


class ModelSelectScreen(Screen):
    """Modal screen for selecting the chat model with search, recent, and favorites."""

    CSS = """
    ModelSelectScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #model_select_container {
        width: 60;
        height: auto;
        max-height: 24;
        background: #1a1a1a;
        border: solid #333333;
        padding: 1 2;
    }
    
    #model_header {
        height: 1;
        margin-bottom: 1;
    }
    
    #model_title {
        width: 1fr;
        text-style: bold;
    }
    
    #model_close_hint {
        width: auto;
    }
    
    #model_search {
        margin-bottom: 1;
        background: #0a0a0a;
        border: solid #333333;
    }
    
    #model_options {
        height: auto;
        max-height: 14;
        background: #0a0a0a;
        border: solid #333333;
    }
    
    #model_footer {
        margin-top: 1;
        text-align: center;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Close"),
        ("ctrl+f", "toggle_favorite", "Favorite"),
    ]

    def __init__(
        self,
        models: list[str],
        current: str,
        on_select: Callable[[str], None],
        model_configs: Dict[str, Dict],
    ) -> None:
        super().__init__()
        self.all_models = models
        self.current = current
        self.on_select = on_select
        self.model_configs = model_configs
        self.filtered_models: list[str] = []
        self.prefs = _load_model_prefs()

    def _get_provider_name(self, model: str) -> str:
        """Get provider display name for a model."""
        config = self.model_configs.get(model, {})
        provider = config.get("provider", "")
        if provider == "openai":
            return "OpenAI"
        elif provider == "anthropic":
            return "Anthropic"
        return provider.capitalize() if provider else ""

    def _format_model_display(self, model: str, is_selected: bool = False, is_favorite: bool = False) -> str:
        """Format a model name for display with provider and context size."""
        provider = self._get_provider_name(model)
        context = self.model_configs.get(model, {}).get("context", 0)
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
                       search_lower in self._get_provider_name(m).lower()]
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
