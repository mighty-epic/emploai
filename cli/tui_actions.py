"""AgentShellApp helper actions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cli.screens import CommandPaletteScreen, ProviderConfigScreen, SessionSwitchScreen
from cli.screens.editor import EditorScreen
from cli.screens.model_select import ModelSelectScreen
from cli.tui_constants import (
    AGENT_MODE_COLORS,
    AVAILABLE_MODELS,
    MODEL_CONFIGS,
    MODEL_CONTEXT_SIZES,
    SLASH_COMMANDS,
    SLASH_SUGGESTION_LIMIT,
    COMMAND_PRIORITIES,
)
from shared.model_availability import filter_models_by_provider_access


class AgentShellActionsMixin:
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
        return {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "google": "Google Gemini",
            "xai": "xAI",
            "deepseek": "DeepSeek",
            "nvidia": "NVIDIA NIM",
            "openrouter": "OpenRouter",
        }.get(provider, provider.capitalize())

    def _update_status(self) -> None:
        def do_update():
            if not self.processor:
                return

            model = self.processor.current_model
            provider = self._get_model_provider(model)
            single_agent = self.processor.single_agent

            # 1. Update Model Info (Inside Input Container)
            # -----------------------------------------------------------------
            agent_mode = self.processor.agent_mode
            mode_display = agent_mode.capitalize()
            mode_color = AGENT_MODE_COLORS.get(agent_mode, "#a855f7")
            
            available_variants = self.processor._get_available_variants(model)
            has_variants = len(available_variants) > 1
            variant = self.processor.current_variant
            variant_display = f" [#fbbf24]· {variant}[/#fbbf24]" if has_variants else ""

            model_info_text = (
                f" [{mode_color}]{mode_display}[/]  "
                f"[bold #ffffff]{model}[/] {variant_display}  "
                f"[#666666]{provider}[/]"
            )
            
            if hasattr(self, "model_info_widget") and self.model_info_widget:
                self.model_info_widget.update(model_info_text)

            # 1.5 Update App Header (Title and Sub-title)
            # -----------------------------------------------------------------
            if self.processor.session:
                self.title = self.processor.session.name
            
            used = self.processor.total_tokens_used
            max_t = self.processor.max_tokens
            pct = self.processor.get_context_percentage()
            self.sub_title = f"{used:,} / {max_t:,} tokens ({pct:.1f}%)"

            # 2. Update Loading / Snake Indicator
            # -----------------------------------------------------------------
            is_active = self.processor._streaming_response or (single_agent.current_task and not single_agent.is_paused)
            
            if hasattr(self, "loading_indicator") and self.loading_indicator:
                if is_active:
                    self.loading_indicator.start()
                    self.loading_indicator.update_snake()
                    if hasattr(self, "interrupt_hint"):
                        self.interrupt_hint.display = True
                        if getattr(self, "esc_pressed", False):
                            self.interrupt_hint.update("  [bold #ff4444]esc again to interrupt[/]")
                        else:
                            self.interrupt_hint.update("  [dim]esc to interrupt[/]")
                else:
                    self.loading_indicator.stop()
                    if hasattr(self, "interrupt_hint"):
                        self.interrupt_hint.display = False

            # 3. Update Shortcuts (Right side)
            # -----------------------------------------------------------------
            variant_hint = "[dim]ctrl+t[/dim] variants  " if has_variants else ""
            if single_agent.current_task:
                if single_agent.is_paused:
                    shortcuts_text = f"{variant_hint}[dim]tab[/dim] agents  [dim]esc[/dim] cancel  [dim]/continue[/dim] resume"
                else:
                    shortcuts_text = f"{variant_hint}[dim]tab[/dim] agents  [dim]esc[/dim] pause"
            else:
                shortcuts_text = f"{variant_hint}[dim]tab[/dim] agents  [dim]ctrl+p[/dim] commands"

            if hasattr(self, "shortcuts") and self.shortcuts:
                self.shortcuts.update(shortcuts_text)

        self._run_safe(do_update)

    def _update_slash_suggestions(self, input_text: str) -> None:
        if not self.slash_suggestions:
            return
        suggestions = self._get_slash_suggestions(input_text)
        self.slash_suggestions.update_suggestions(suggestions, self.use_suggestion)
        self.refresh(layout=True)

    def _get_slash_suggestions(self, input_text: str) -> list[str]:
        if not input_text.startswith("/"):
            return []
            
        partial = input_text[1:].lower()
        if not partial:
            # Sort by priority then alphabetically
            commands = sorted(SLASH_COMMANDS, key=lambda c: (COMMAND_PRIORITIES.get(c, 999), c))
            return [f"/{cmd}" for cmd in commands[:SLASH_SUGGESTION_LIMIT]]

        matches = []
        for cmd in SLASH_COMMANDS:
            cmd_lower = cmd.lower()
            if partial == cmd_lower:
                score = 0
            elif cmd_lower.startswith(partial):
                score = 10
            elif partial in cmd_lower:
                score = 20
            else:
                continue
                
            # Apply priority boost (lowers score)
            priority = COMMAND_PRIORITIES.get(cmd, 999)
            matches.append((score, priority, cmd))

        # Sort matches by score (type of match), then explicit priority, then name
        matches.sort()
        
        return [f"/{m[2]}" for m in matches[:SLASH_SUGGESTION_LIMIT]]

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
            old_model = self.processor.current_model
            self.processor.current_model = model
            self.processor.max_tokens = MODEL_CONTEXT_SIZES.get(model, 128000)

            # Sync variant: if current variant isn't supported, use new model's default
            available_variants = self.processor._get_available_variants(model)
            if self.processor.current_variant not in available_variants:
                self.processor.current_variant = self.processor._get_default_variant(model)

            self._update_status()

        enabled_providers = set(self.processor.config_manager.get_enabled_providers())
        available_models = filter_models_by_provider_access(AVAILABLE_MODELS, MODEL_CONFIGS, enabled_providers)
        self.push_screen(ModelSelectScreen(available_models, self.processor.current_model, on_select, MODEL_CONFIGS))

    def action_open_model_picker(self) -> None:
        """Action handler for ctrl+m keybinding."""
        self._open_model_picker()

    def action_cycle_variant(self) -> None:
        """Action handler for ctrl+t keybinding - cycle through variants."""
        if self.processor:
            available = self.processor._get_available_variants(self.processor.current_model)
            if len(available) > 1:
                self.processor.cycle_variant()
                self.processor._auto_save_session()
                self._update_status()

    def action_open_command_palette(self) -> None:
        """Action handler for ctrl+p - open command palette."""
        if not self.processor:
            return

        def on_action(action: str) -> None:
            """Handle command palette action."""
            handlers = {
                "switch_model": self._open_model_picker,
                "switch_variant": self.action_cycle_variant,
                "new_session": self._new_session,
                "switch_session": self._open_session_switcher,
                "rename_session": self._rename_current_session,
                "delete_session": self._delete_session_prompt,
                "export_session": self._export_current_session,
                "configure_providers": self._open_provider_config,
                "toggle_agent_mode": lambda: self._toggle_agent_mode(),
                "clear_chat": self._clear_chat,
                "show_help": self._show_help,
            }

            handler = handlers.get(action)
            if handler:
                handler()

        self.push_screen(CommandPaletteScreen(on_action))

    def action_new_session(self) -> None:
        """Action handler for ctrl+n - create new session."""
        self._new_session()

    def action_switch_session(self) -> None:
        """Action handler for ctrl+l - switch session."""
        self._open_session_switcher()

    def _new_session(self) -> None:
        """Create a new session."""
        if not self.processor:
            return

        session = self.processor.new_session()
        # Clear the chat log UI
        for child in list(self.chat_log.children):
            child.remove()
        self._log(f"Created new session: {session.name}")
        self._update_status()

    def _open_session_switcher(self) -> None:
        """Open the session switch screen."""
        if not self.processor:
            return

        current_id = self.processor.session.id if self.processor.session else None

        def on_select(session_id: str) -> None:
            if self.processor and self.processor.switch_session(session_id):
                # Reload chat display
                self._reload_chat_display()
                self._update_status()
                self._log(f"Switched to session: {self.processor.session.name}")

        def on_new() -> None:
            self._new_session()

        def on_delete(session_id: str) -> None:
            self._delete_session(session_id)

        def on_rename(session_id: str) -> None:
            self._rename_session(session_id)

        self.push_screen(SessionSwitchScreen(
            session_manager=self.processor.session_manager,
            current_session_id=current_id,
            on_select=on_select,
            on_new=on_new,
            on_delete=on_delete,
            on_rename=on_rename,
        ))

    def _reload_chat_display(self) -> None:
        """Reload chat history into the display."""
        if not self.processor:
            return

        # Clear existing chat log
        for child in list(self.chat_log.children):
            child.remove()

        # Reload messages
        for msg in self.processor.chat_history:
            if msg.role == "user":
                self._log(msg.content, role="user")
            else:
                self._log(msg.content, role="assistant", model=self.processor.current_model, timestamp=msg.duration)

    def _delete_session(self, session_id: str) -> None:
        """Delete a session."""
        if not self.processor:
            return

        # Don't delete current session
        if self.processor.session and self.processor.session.id == session_id:
            self.notify("Cannot delete current session", severity="error")
            return

        self.processor.session_manager.delete_session(session_id)
        self.notify("Session deleted", timeout=2)

    def _delete_session_prompt(self) -> None:
        """Prompt to delete current session (creates new one first)."""
        if not self.processor or not self.processor.session:
            return

        old_id = self.processor.session.id
        old_name = self.processor.session.name

        # Create a new session first
        self._new_session()

        # Then delete the old one
        self.processor.session_manager.delete_session(old_id)
        self.notify(f"Deleted session: {old_name}", timeout=2)

    def _rename_session(self, session_id: str) -> None:
        """Rename a session (for now just log - could show input dialog)."""
        self._log("Session rename: Use /rename <new_name> to rename the current session")

    def _rename_current_session(self) -> None:
        """Rename the current session."""
        self._log("To rename session, use /rename <new_name>")

    def _export_current_session(self) -> None:
        """Export the current session."""
        if not self.processor or not self.processor.session:
            return

        try:
            export_data = self.processor.session_manager.export_session(
                self.processor.session.id,
                format="markdown",
            )
            # Could save to file or copy to clipboard
            # For now just notify
            self._log("Session exported to markdown (clipboard support coming soon)")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    def _open_provider_config(self) -> None:
        """Open the provider configuration screen."""
        if not self.processor:
            return

        def on_save() -> None:
            from cli.chat_processor_core import refresh_llm_clients

            refresh_llm_clients(self.processor)
            self.notify("Provider configuration saved", timeout=2)

        self.push_screen(ProviderConfigScreen(
            config_manager=self.processor.config_manager,
            on_save=on_save,
        ))

    def _toggle_agent_mode(self) -> None:
        """Toggle agent mode."""
        if self.processor:
            self.processor.cycle_agent_mode()
            self._update_status()

    def _clear_chat(self) -> None:
        """Clear the current chat."""
        if not self.processor:
            return

        self.processor.clear_chat()

        # Clear the chat log UI
        for child in list(self.chat_log.children):
            child.remove()

        self._log("Chat cleared")
        self._update_status()

    def _show_help(self) -> None:
        """Show help message."""
        self._log("""
[bold]AgentShell Help[/bold]

[bold]Keyboard Shortcuts:[/bold]
  ctrl+p  - Open command palette
  ctrl+m  - Switch model
  ctrl+n  - New session
  ctrl+l  - Switch session
  ctrl+t  - Cycle variant
  tab     - Cycle agent mode
  esc     - Pause/Cancel (during task)

[bold]Slash Commands:[/bold]
  /help   - Show this help
  /model  - Show/change model
  /mode   - Show/change agent mode
  /clear  - Clear chat
  /task   - Run a task
  /exit   - Exit the app

Type without / to chat with the AI.
""")
