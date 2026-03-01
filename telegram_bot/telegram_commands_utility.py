"""Utility command handlers for monitoring and settings."""

from __future__ import annotations

import json

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.ui_helpers import InlineKeyboardHelper


def build_utility_command_handlers(
    *,
    security_manager,
    rate_limited,
    get_session,
    track_command_usage,
    safe_reply,
    InlineKeyboardHelper,
):
    @rate_limited(security_manager)
    async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle auto-reply/monitoring mode."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "monitor")

        arg = context.args[0].lower() if context.args else "status"
        if arg in {"on", "enable", "start"}:
            session.auto_reply_enabled = True
            session.auto_reply_notice_sent = False
            await safe_reply(update, "✅ Auto-reply enabled.")
            return
        if arg in {"off", "disable", "stop"}:
            session.auto_reply_enabled = False
            await safe_reply(update, "⛔ Auto-reply disabled. Use `/monitor on` to re-enable.")
            return

        status = "✅ ON" if session.auto_reply_enabled else "⛔ OFF"
        reply_markup = InlineKeyboardHelper.create_action_buttons(
            [
                {"text": "✅ On", "callback_data": "monitor:on"},
                {"text": "⛔ Off", "callback_data": "monitor:off"},
            ]
        )
        await safe_reply(update, f"**Auto-Reply Status:** {status}", reply_markup=reply_markup)

    @rate_limited(security_manager)
    async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show usage analytics summary."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "analytics")

        days = 7
        if context.args:
            try:
                days = max(1, min(30, int(context.args[0])))
            except ValueError:
                await safe_reply(update, "❌ Days must be a number (1-30).")
                return

        if not session.analytics_tracker:
            await safe_reply(update, "❌ Analytics not initialized.")
            return

        summary = session.analytics_tracker.format_summary_for_telegram(days)
        await safe_reply(update, summary)

    @rate_limited(security_manager)
    async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent conversation history."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "history")

        count = 10
        if context.args:
            try:
                count = max(1, min(50, int(context.args[0])))
            except ValueError:
                await safe_reply(update, "❌ Count must be a number (1-50).")
                return

        if not session.chat_history:
            await safe_reply(update, "No history yet.")
            return

        recent = session.chat_history[-count:]
        lines = ["**🧾 Recent History**\n"]
        for msg in recent:
            role = msg.get("role", "unknown")
            timestamp = msg.get("timestamp", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = json.dumps(content)[:120]
            preview = str(content).replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:120] + "..."
            lines.append(f"• [{timestamp}] **{role}**: {preview}")

        await safe_reply(update, "\n".join(lines))

    @rate_limited(security_manager)
    async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show pending uploaded files."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "files")

        if not session.pending_files:
            await safe_reply(update, "No pending files. Send a document or image to attach.")
            return

        lines = ["**📎 Pending Files**\n"]
        for item in session.pending_files[:10]:
            lines.append(
                f"• `{item.get('filename', 'unknown')}` ({item.get('type', 'file')})"
            )

        reply_markup = InlineKeyboardHelper.confirmation_buttons(
            "files:clear", "files:keep", "🗑️ Clear", "✅ Keep"
        )
        await safe_reply(update, "\n".join(lines), reply_markup=reply_markup)

    @rate_limited(security_manager)
    async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove last user message from context."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "forget")

        reply_markup = InlineKeyboardHelper.confirmation_buttons(
            "forget:confirm", "forget:cancel", "🗑️ Remove", "❌ Cancel"
        )
        await safe_reply(
            update,
            "Remove the last user message from context?",
            reply_markup=reply_markup,
        )

    @rate_limited(security_manager)
    async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guided setup wizard."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "setup")

        session.wizard_state = {"step": "mode"}
        reply_markup = InlineKeyboardHelper.create_action_buttons(
            [
                {"text": "Manual", "callback_data": "setup:mode:manual"},
                {"text": "Semi", "callback_data": "setup:mode:semi"},
                {"text": "Auto", "callback_data": "setup:mode:auto"},
                {"text": "Cancel", "callback_data": "setup:cancel"},
            ]
        )
        await safe_reply(
            update, "**Setup Step 1/3:** Choose agent mode", reply_markup=reply_markup
        )

    @rate_limited(security_manager)
    async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search or view memory."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "memory")

        if context.args:
            query = " ".join(context.args)
            results = session.memory_manager.search_memory(query, max_results=5)

            if not results:
                await safe_reply(update, f"No results found for: {query}")
                return

            response = f"**🔍 Memory Search: {query}**\n\n"
            for result in results:
                response += (
                    f"**{result['source']}:{result['line']}**\n"
                    f"{result['content']}\n\n---\n\n"
                )

            await safe_reply(update, response[:4000])
        else:
            summary = session.memory_manager.export_memory_summary()
            await safe_reply(
                update,
                "**🧠 Memory Summary**\n\n"
                f"Memory file: {summary['memory_file_exists']}\n"
                f"Daily logs: {summary['daily_log_count']}\n"
                f"Oldest: {summary['oldest_log']}\n"
                f"Newest: {summary['newest_log']}\n\n"
                "Usage: `/memory <query>` to search\n"
                "Usage: `/memory_update <note>` to append to memory",
            )

    @rate_limited(security_manager)
    async def memory_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Append a note to memory."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "memory_update")

        if not context.args:
            await safe_reply(
                update,
                "**Usage:** `/memory_update <note>`\n\n"
                "Append a note to your persistent memory.",
            )
            return

        note = " ".join(context.args)
        if session.memory_manager:
            session.memory_manager.append_to_daily_log(note, "user_note")
            await safe_reply(update, f"✅ Appended to memory:\n\n{note[:200]}...")
        else:
            await safe_reply(update, "❌ Memory manager not initialized.")

    @rate_limited(security_manager)
    async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View or edit config."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "config")

        if not context.args:
            all_config = session.live_config.list_all()
            lines = ["**⚙️ Configuration**\n"]
            for key, value in list(all_config.items())[:20]:
                lines.append(f"`{key}` = {value}")
            lines.append("\nUsage: `/config <key>` or `/config <key> <value>`")
            await safe_reply(update, "\n".join(lines))
        elif len(context.args) == 1:
            key = context.args[0]
            value = session.live_config.get(key)
            await safe_reply(update, f"`{key}` = {value}")
        else:
            key = context.args[0]
            value = " ".join(context.args[1:])

            try:
                if value.lower() in ("true", "false"):
                    parsed_value = value.lower() == "true"
                elif value.isdigit():
                    parsed_value = int(value)
                else:
                    parsed_value = value
            except Exception:
                parsed_value = value

            session.live_config.set(key, parsed_value, user.id)
            session.live_config.save_config()
            await safe_reply(update, f"✅ Set `{key}` = {parsed_value}")

    @rate_limited(security_manager)
    async def heartbeat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Control heartbeat."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "heartbeat")

        if not context.args:
            if session.heartbeat_manager:
                status = session.heartbeat_manager.get_status()
                await safe_reply(
                    update,
                    "**💓 Heartbeat Status**\n\n"
                    f"Enabled: {status['enabled']}\n"
                    f"Running: {status['running']}\n"
                    f"Interval: {status['interval_seconds']}s\n"
                    f"Checks: {status['check_count']}\n"
                    f"Last: {status['last_heartbeat']}\n\n"
                    "Usage: `/heartbeat on|off|status`",
                )
            else:
                await safe_reply(update, "Heartbeat not initialized.")
        else:
            cmd = context.args[0].lower()
            if cmd == "on":
                if session.heartbeat_manager:
                    session.heartbeat_manager.start()
                session.live_config.set("heartbeat.enabled", True, user.id)
                session.live_config.save_config()
                await safe_reply(update, "✅ Heartbeat enabled")
            elif cmd == "off":
                if session.heartbeat_manager:
                    session.heartbeat_manager.stop()
                session.live_config.set("heartbeat.enabled", False, user.id)
                session.live_config.save_config()
                await safe_reply(update, "⏹️ Heartbeat disabled")

    @rate_limited(security_manager)
    async def verbose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle verbose tool logging in Telegram."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "verbose")

        arg = context.args[0].lower() if context.args else None
        if arg in {"on", "enable"}:
            session.verbose_mode = True
        elif arg in {"off", "disable"}:
            session.verbose_mode = False
        elif arg is None:
            # No argument: toggle
            session.verbose_mode = not session.verbose_mode

        status = "✅ ON" if session.verbose_mode else "⛔ OFF"
        reply_markup = InlineKeyboardHelper.create_action_buttons(
            [
                {"text": "✅ On", "callback_data": "verbose:on"},
                {"text": "⛔ Off", "callback_data": "verbose:off"},
            ]
        )
        await safe_reply(
            update,
            f"**🔍 Verbose Tool Logging:** {status}\n\n"
            "When ON, each tool call and its result will be shown live in the chat.",
            reply_markup=reply_markup,
        )

    return {
        "monitor_command": monitor_command,
        "analytics_command": analytics_command,
        "history_command": history_command,
        "files_command": files_command,
        "forget_command": forget_command,
        "setup_command": setup_command,
        "memory_command": memory_command,
        "memory_update_command": memory_update_command,
        "config_command": config_command,
        "heartbeat_command": heartbeat_command,
        "verbose_command": verbose_command,
    }
