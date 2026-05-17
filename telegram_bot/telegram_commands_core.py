"""Core Telegram command handlers."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cli.tui_constants import AGENT_MODE_LABELS, AVAILABLE_MODELS, MODEL_CONFIGS
from shared.channel_sync import get_channel_sync_hub


COMMAND_HELP: Dict[str, str] = {
    "help": "Show all commands or details: `/help <command>`",
    "mode": "Auto mode is always enabled. `/mode` is kept only as a compatibility stub.",
    "variant": "Set model variant: `/variant` (standard/thinking)",
    "model": "Switch model: `/model`",
    "models": "List available models: `/models`",
    "planner": "Set planner model: `/planner`, `/planner <model>`, or `/planner auto`",
    "pause": "Pause running task: `/pause`",
    "stop": "Stop running task: `/stop`",
    "spawn": "Spawn sub-agent: `/spawn <prompt>`",
    "subagents": "List sub-agents: `/subagents`",
    "schedule": "Create recurring job: `/schedule <name> <schedule> <prompt>`",
    "jobs": "List scheduled jobs: `/jobs`",
    "job_remove": "Remove job: `/job_remove <job_id>`",
    "session": "Manage sessions: `/session`",
    "task": "Show the active managed task board: `/task`",
    "reassess": "Force a reassessment of the active task board: `/reassess`",
    "history": "Show recent conversation history: `/history [count]`",
    "reset": "Clear chat history: `/reset`",
    "compact": "Compact the current session context: `/compact`",
    "context": "Show token usage: `/context`",
    "settings": "Configure max turns: `/settings`",
    "workspace": "Set workspace path: `/workspace <path>`",
    "headless": "Toggle browser mode: `/headless`",
    "skills": "List skills: `/skills`",
    "skill": "Invoke a skill: `/skill <name>`",
    "skilltest": "Validate a skill: `/skilltest <name>`",
    "files": "Show pending files: `/files`",
    "monitor": "Toggle auto-reply: `/monitor on|off|status`",
    "analytics": "Usage summary: `/analytics [days]`",
    "setup": "Guided setup wizard: `/setup`",
    "forget": "Remove last user message from context: `/forget`",
    "security": "Security status: `/security`",
    "memory": "Search/view memory: `/memory [query]`",
    "memory_update": "Append note to memory: `/memory_update <note>`",
    "config": "View/edit configuration: `/config [key] [value]`",
    "heartbeat": "Control heartbeat: `/heartbeat on|off|status`",
    "bridge": "Toggle the browser extension bridge: `/bridge on|off|status`",
    "restart": "Restart the bot process in-place: `/restart`",
}


def build_core_command_handlers(
    *,
    security_manager,
    rate_limited,
    authorized_only,
    get_session: Callable[[int], Any],
    track_command_usage: Callable[[Any, str], None],
    safe_reply: Callable[..., Any],
    logger,
):
    @authorized_only(security_manager)
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Initialize session and show welcome."""
        user = update.effective_user
        session = get_session(user.id)
        loop = asyncio.get_running_loop()
        session._app = context.application
        session._loop = loop

        mode_label = AGENT_MODE_LABELS.get(session.agent_mode, session.agent_mode)

        await safe_reply(
            update,
            "🧠 **Emploai Agent Connected**\n\n"
            f"**Model:** {session.current_model}\n"
            f"**Variant:** {session.current_variant}\n"
            f"**Planner:** {session.planner_model or 'automatic'}\n"
            f"**Mode:** {mode_label}\n"
            f"**Max Turns:** {session.max_turns}\n"
            f"**Workspace:** `{session.workspace}`\n\n"
            "**Default Chat:** Unified auto agent\n"
            "Send requests directly, including browser or desktop automation.\n\n"
            "Use /help to see available commands.",
        )

    @rate_limited(security_manager)
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available commands."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "help")

        if context.args:
            cmd = context.args[0].lstrip("/")
            detail = COMMAND_HELP.get(cmd)
            if detail:
                await safe_reply(update, f"**/{cmd}**\n\n{detail}")
            else:
                await safe_reply(update, f"❌ Unknown command: `{cmd}`")
            return

        await safe_reply(
            update,
            "**📋 Commands**\n\n"
            "**Agent Control:**\n"
            "/variant - Set model variant\n"
            "/model - Switch model\n"
            "/models - List all models\n\n"
            "/planner - Set planner model\n\n"
            "**Automation & Control:**\n"
            "/pause - Pause running task\n"
            "/stop - Stop running task\n"
            "/spawn <prompt> - Spawn parallel sub-agent\n"
            "/subagents - List running sub-agents\n\n"
            "**Scheduling:**\n"
            "/schedule <name> <schedule> <prompt> - Schedule recurring task\n"
            "/jobs - List scheduled jobs\n"
            "/job_remove <id> - Remove a scheduled job\n\n"
            "**Session & Memory:**\n"
            "/session - Manage sessions\n"
            "/task - Show the active task board\n"
            "/reassess - Force a task reassessment\n"
            "/reset - Clear chat history\n"
            "/compact - Compact the current context\n"
            "/context - Show token usage\n"
            "/memory [query] - Search memory\n"
            "/memory_update <note> - Add note to memory\n\n"
            "**Settings:**\n"
            "/settings - Configure max turns\n"
            "/workspace - Set workspace path\n"
            "/headless - Toggle headless/headed browser mode\n"
            "/config - View/edit configuration\n"
            "/heartbeat - Control heartbeat checks\n"
            "/restart - Restart the bot process\n\n"
            "/bridge - Toggle the browser extension bridge\n\n"
            "**Skills:**\n"
            "/skills - List available skills\n"
            "/skill <name> - Invoke a specific skill\n\n"
            "**Monitoring:**\n"
            "/monitor - Toggle auto-reply\n"
            "/analytics - Usage summary\n"
            "/history - Conversation history\n"
            "/files - Pending files\n"
            "/setup - Guided setup wizard\n"
            "/skilltest - Validate a skill\n"
            "/forget - Remove last user message\n\n"
            "**Security:**\n"
            "/security - Show security status and rate limits\n\n"
            "**Chat Mode (Default):**\n"
            "Send any message to use the unified auto agent with:\n"
            "• File operations (read/write/edit)\n"
            "• Terminal commands\n"
            "• Web search\n"
            "• Codebase search\n"
            "• Browser and desktop automation\n"
            "• 🧠 Persistent memory (auto-loaded & saved)",
        )

    @rate_limited(security_manager)
    async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Explain that the Telegram bot now runs in auto-only mode."""
        await safe_reply(
            update,
            "**Agent Mode:** Auto\n\n"
            "This Telegram bot now runs in unified auto mode only.\n"
            "Send requests directly instead of switching modes.",
        )

    @rate_limited(security_manager)
    async def variant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show variant selector with inline buttons."""
        user = update.effective_user

        session = get_session(user.id)
        available = session.get_available_variants()
        current = session.current_variant

        keyboard = []
        for v in available:
            label = f"{'✓ ' if current == v else ''}{v.title()}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"variant:{v}")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_reply(
            update,
            f"**Current Variant:** {current}\n"
            f"**Available for {session.current_model}:** {', '.join(available)}\n\n"
            "Select a variant:",
            reply_markup=reply_markup,
        )

    @rate_limited(security_manager)
    async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show model selector with inline buttons (paginated)."""
        user = update.effective_user

        session = get_session(user.id)
        session.ensure_current_model_available(AVAILABLE_MODELS)
        current = session.current_model
        model_groups = session.get_available_model_groups(AVAILABLE_MODELS)
        if not model_groups:
            await safe_reply(
                update,
                "❌ No model providers are configured.\n\nAdd at least one API key and restart EmploAI.",
            )
            return

        keyboard = []
        for group in model_groups:
            provider = group["provider"]
            count = len(group["models"])
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{provider.title()} ({count})",
                        callback_data=f"provider:{provider}",
                    )
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_reply(
            update,
            f"**Current Model:** {current}\n\n"
            "Select a provider:",
            reply_markup=reply_markup,
        )

    def _publish_session_config_sync(session, setting: str) -> None:
        try:
            session.save_session()
            session_id = session.session_manager.get_current_session_id() if session.session_manager else None
            if not session_id:
                return
            get_channel_sync_hub().publish(
                user_id=session.user_id,
                event={
                    "type": "session_config",
                    "session_id": session_id,
                    "origin_channel": "telegram",
                    "payload": {
                        "setting": setting,
                        "model": session.current_model,
                        "variant": session.current_variant,
                        "planner_model": getattr(session, "planner_model", None),
                        "max_turns": session.max_turns,
                    },
                },
            )
        except Exception:
            logger.exception("Failed to publish Telegram session config sync")

    def _resolve_planner_model(session: Any, raw: str) -> str | None:
        supported = session.get_supported_planner_models(AVAILABLE_MODELS)
        target = raw.strip().lower()
        exact = next((item for item in supported if item.lower() == target), None)
        if exact:
            return exact
        prefix_matches = [item for item in supported if item.lower().startswith(target)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        contains_matches = [item for item in supported if target in item.lower()]
        if len(contains_matches) == 1:
            return contains_matches[0]
        return None

    @rate_limited(security_manager)
    async def planner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show or switch the lightweight planner model."""
        user = update.effective_user
        session = get_session(user.id)
        session.ensure_current_model_available(AVAILABLE_MODELS)
        track_command_usage(session, "planner")

        supported = session.get_supported_planner_models(AVAILABLE_MODELS)
        current = session.planner_model or "automatic cheapest supported planner"

        if not context.args or context.args[0].lower() in {"status", "list"}:
            lines = [
                "**Planner Model**",
                "",
                f"Current: {current}",
            ]
            if supported:
                lines.extend(["", "Supported planner models:"])
                lines.extend([f"• {model}" for model in supported])
                lines.extend([
                    "",
                    "Use `/planner <model-id>` to pin one, or `/planner auto` to let the runtime choose automatically.",
                ])
            else:
                lines.extend(["", "No supported planner models are available from the configured providers."])
            await safe_reply(update, "\n".join(lines))
            return

        arg = context.args[0].strip().lower()
        if arg in {"auto", "none", "default", "clear", "off"}:
            session.planner_model = None
            _publish_session_config_sync(session, "planner_model")
            await safe_reply(update, "✅ Planner model reset to automatic cheapest supported selection.")
            return

        resolved = _resolve_planner_model(session, " ".join(context.args))
        if not resolved:
            if supported:
                message = "❌ Could not resolve that planner model.\n\n" + "\n".join(
                    [f"• {model}" for model in supported[:20]]
                )
            else:
                message = "❌ No supported planner models are available right now."
            await safe_reply(
                update,
                message,
            )
            return

        session.planner_model = resolved
        _publish_session_config_sync(session, "planner_model")
        await safe_reply(update, f"✅ Planner model pinned to `{resolved}`.")

    @rate_limited(security_manager)
    async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all available models."""
        user = update.effective_user
        session = get_session(user.id)
        session.ensure_current_model_available(AVAILABLE_MODELS)
        model_groups = session.get_available_model_groups(AVAILABLE_MODELS)
        if not model_groups:
            await safe_reply(
                update,
                "❌ No model providers are configured.\n\nAdd at least one API key and restart EmploAI.",
            )
            return

        lines = ["**📋 Available Models**\n"]
        for group in model_groups:
            provider = group["provider"]
            models = group["models"]
            lines.append(f"\n**{provider.title()}:**")
            for model in models[:5]:
                lines.append(f"  • {model}")
            if len(models) > 5:
                lines.append(f"  • ...and {len(models) - 5} more")

        lines.append("\n\nUse /model to switch models.")
        await safe_reply(update, "\n".join(lines))

    @rate_limited(security_manager)
    async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show settings with inline buttons."""
        user = update.effective_user

        session = get_session(user.id)

        keyboard = [
            [
                InlineKeyboardButton("50", callback_data="turns:50"),
                InlineKeyboardButton("100", callback_data="turns:100"),
                InlineKeyboardButton("200", callback_data="turns:200"),
                InlineKeyboardButton("500", callback_data="turns:500"),
            ],
            [InlineKeyboardButton("❌ Close", callback_data="close")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_reply(
            update,
            "**⚙️ Settings**\n\n" f"**Max Turns:** {session.max_turns}\n\n"
            "Select max turns for task execution:",
            reply_markup=reply_markup,
        )

    @rate_limited(security_manager)
    async def workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set the workspace path."""
        user = update.effective_user

        session = get_session(user.id)

        if context.args:
            raw_path = " ".join(context.args)
            sanitized_path = security_manager.sanitize_input(raw_path, max_length=500)

            is_valid, resolved_path, error_msg = security_manager.validate_path(
                sanitized_path, user.id
            )

            if not is_valid:
                await safe_reply(update, error_msg or "❌ Invalid path.")
                return

            if resolved_path and resolved_path.exists() and resolved_path.is_dir():
                try:
                    session.set_workspace(resolved_path)
                except RuntimeError as exc:
                    await safe_reply(update, f"⚠️ {str(exc)}")
                    return

                session.save_session()
                _publish_session_config_sync(session, "workspace")
                await safe_reply(update, f"✅ Workspace set to: `{session.workspace}`")
            else:
                await safe_reply(
                    update,
                    "❌ Invalid path: Path does not exist or is not a directory",
                )
        else:
            await safe_reply(
                update,
                f"**Current Workspace:** `{session.workspace}`\n\n" "Usage: /workspace <path>",
            )

    return {
        "start": start,
        "help_command": help_command,
        "mode_command": mode_command,
        "variant_command": variant_command,
        "model_command": model_command,
        "models_command": models_command,
        "planner_command": planner_command,
        "settings_command": settings_command,
        "workspace_command": workspace_command,
    }
