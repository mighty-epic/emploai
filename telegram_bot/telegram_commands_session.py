"""Session and status command handlers."""

from __future__ import annotations

import json
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cli.tui_constants import AGENT_MODE_LABELS, MODEL_CONTEXT_SIZES


def build_session_command_handlers(
    *,
    security_manager,
    rate_limited,
    authorized_only,
    get_session,
    track_command_usage,
    safe_reply,
    InlineKeyboardHelper,
):
    @rate_limited(security_manager)
    async def session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Session management."""
        user = update.effective_user

        session = get_session(user.id)
        track_command_usage(session, "session")
        sessions = session.session_manager.list_sessions()

        if not sessions:
            await safe_reply(update, "No sessions found. Sessions are created automatically.")
            return

        keyboard = []
        for s in sessions[:10]:
            label = f"{s.name[:20]}..." if len(s.name) > 20 else s.name
            keyboard.append([InlineKeyboardButton(label, callback_data=f"session:{s.id}")])

        keyboard.append(
            [InlineKeyboardButton("➕ New Session", callback_data="session:new")]
        )
        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_reply(
            update, "**📂 Sessions**\n\nSelect a session:", reply_markup=reply_markup
        )

    @rate_limited(security_manager)
    async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a new session."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "new")

        if session.is_processing:
            await safe_reply(update, "⚠️ Finish or stop the current task before switching sessions.")
            return

        new_session_obj = session.session_manager.create_session(
            workspace=session.workspace,
            name=f"New Session {datetime.now().strftime('%H:%M')}"
        )
        session.load_session_by_id(new_session_obj.id)
        
        # Clear agent histories
        if session.unified_agent:
            session.unified_agent.conversation_history = []
        
        await safe_reply(update, f"✨ **New Session Started**\nID: `{new_session_obj.id}`\n\nMemory context is now fresh.")

    @rate_limited(security_manager)
    async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reset chat history."""
        user = update.effective_user

        session = get_session(user.id)
        track_command_usage(session, "reset")

        reply_markup = InlineKeyboardHelper.confirmation_buttons(
            "reset:confirm", "reset:cancel", "🗑️ Clear", "❌ Cancel"
        )
        await safe_reply(update, "Clear all chat history?", reply_markup=reply_markup)

    @rate_limited(security_manager)
    async def context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show context usage."""
        user = update.effective_user

        session = get_session(user.id)
        track_command_usage(session, "context")
        max_ctx = MODEL_CONTEXT_SIZES.get(session.current_model, 128000)

        tokens_used = 0
        for msg in session.chat_history:
            content = msg.get("content", "")
            if isinstance(content, str):
                tokens_used += len(content) // 4
            elif isinstance(content, list):
                tokens_used += len(json.dumps(content)) // 4

        pct = (tokens_used / max_ctx) * 100 if max_ctx > 0 else 0

        status = (
            "**📊 Context Usage**\n\n"
            f"**Model:** {session.current_model}\n"
            f"**Mode:** {AGENT_MODE_LABELS.get(session.agent_mode, session.agent_mode)}\n"
            f"**Estimated tokens:** {tokens_used:,} / {max_ctx:,}\n"
            f"**Usage:** {pct:.1f}%\n"
            f"**Messages:** {len(session.chat_history)}\n"
        )

        if session.agent_mode == "auto":
            status += (
                "\n**Auto Mode Details:**\n"
                "• Compression triggers at 50%\n"
                "• All tools → Claude Sonnet 4.5\n"
            )

        await safe_reply(update, status)

    @authorized_only(security_manager)
    async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show security status and recent events."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "security")

        summary = security_manager.get_security_summary()

        status = (
            "**🔒 Security Status**\n\n"
            f"**Allowed Users:** {summary['allowed_users_count']}\n"
            f"**Rate Limited Users:** {summary['rate_limited_users']}\n"
            f"**Events (24h):** {summary['security_events_24h']}\n"
            f"  • Warnings: {summary['warning_events_24h']}\n"
            f"  • Errors: {summary['error_events_24h']}\n\n"
            "**Rate Limits:**\n"
            f"  • {security_manager.max_requests_per_minute}/min per command\n"
            f"  • {security_manager.max_requests_per_hour}/hour per command\n\n"
            f"**Your ID:** `{user.id}`\n"
        )

        await safe_reply(update, status)

    return {
        "session_command": session_command,
        "new_command": new_command,
        "reset_command": reset_command,
        "context_command": context_command,
        "security_command": security_command,
    }
