"""Core Telegram command handlers."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cli.agent_tools.executor import ToolExecutor
from cli.tui_constants import AGENT_MODE_LABELS, AVAILABLE_MODELS, MODEL_CONFIGS


COMMAND_HELP: Dict[str, str] = {
    "help": "Show all commands or details: `/help <command>`",
    "mode": "Auto mode is always enabled. `/mode` is kept only as a compatibility stub.",
    "variant": "Set model variant: `/variant` (standard/thinking)",
    "model": "Switch model: `/model`",
    "models": "List available models: `/models`",
    "task": "Compatibility alias. Send the request normally and the auto agent will handle it.",
    "pause": "Pause running task: `/pause`",
    "stop": "Stop running task: `/stop`",
    "spawn": "Spawn sub-agent: `/spawn <prompt>`",
    "subagents": "List sub-agents: `/subagents`",
    "schedule": "Create recurring job: `/schedule <name> <schedule> <prompt>`",
    "jobs": "List scheduled jobs: `/jobs`",
    "job_remove": "Remove job: `/job_remove <job_id>`",
    "session": "Manage sessions: `/session`",
    "history": "Show recent conversation history: `/history [count]`",
    "reset": "Clear chat history: `/reset`",
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
            f"**Mode:** {mode_label}\n"
            f"**Max Turns:** {session.max_turns}\n"
            f"**Workspace:** `{session.workspace}`\n\n"
            "**Default Chat:** Unified auto agent\n"
            "Send requests directly, including browser or desktop automation.\n\n"
            "Use /help to see available commands.",
        )

    @rate_limited(security_manager)
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
            "/reset - Clear chat history\n"
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
                session.workspace = resolved_path

                def path_confirm_callback(msg: str) -> bool:
                    """Request user confirmation for path access"""
                    logger.warning(
                        f"[CONFIRM] Path access confirmation: {msg[:100]}..."
                    )
                    print(f"[CONFIRM REQUEST] {msg}")
                    return True

                session.tool_executor = ToolExecutor(
                    session.workspace, confirm_callback=path_confirm_callback
                )
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
        "settings_command": settings_command,
        "workspace_command": workspace_command,
    }
