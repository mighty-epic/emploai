"""Inline callback query handlers for Telegram UI controls."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from shared.channel_sync import get_channel_sync_hub


logger = logging.getLogger(__name__)


def _publish_session_config_sync(session, setting: str) -> None:
    """Persist Telegram-side control changes and notify app clients."""
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


def build_callback_handlers(
    *,
    allowed_user_id,
    get_session,
    safe_edit,
    run_chat_flow,
    stop_command,
    pause_command,
    continue_command,
    InlineKeyboardHelper,
    AVAILABLE_MODELS,
    MODEL_CONFIGS,
):
    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button presses."""
        query = update.callback_query
        await query.answer()

        user = query.from_user
        if user.id != allowed_user_id:
            return

        session = get_session(user.id)
        data = query.data

        if data.startswith("monitor:"):
            setting = data.split(":")[1]
            async with session.lock:
                session.auto_reply_enabled = setting == "on"
                if session.auto_reply_enabled:
                    session.auto_reply_notice_sent = False
            _publish_session_config_sync(session, "auto_reply_enabled")
            status = "✅ ON" if session.auto_reply_enabled else "⛔ OFF"
            await safe_edit(query, f"Auto-reply set to {status}.")
            return

        if data.startswith("bridge:"):
            setting = data.split(":")[1]
            enable = setting == "on"
            async with session.lock:
                session.live_config.set('browser.use_extension', enable, user.id)
                session.live_config.save_config()
                if enable:
                    try:
                        from telegram_bot.telegram_unified_agent import _get_browser_tool
                    except ImportError:
                        from telegram_unified_agent import _get_browser_tool
                    _get_browser_tool(session)
            _publish_session_config_sync(session, "bridge_enabled")
            status = "✅ ENABLED" if enable else "⛔ DISABLED"
            await safe_edit(query, f"Browser bridge set to {status}.")
            return

        if data.startswith("verbose:"):
            setting = data.split(":")[1]
            async with session.lock:
                session.verbose_mode = setting == "on"
            _publish_session_config_sync(session, "verbose_mode")
            status = "✅ ON" if session.verbose_mode else "⛔ OFF"
            await safe_edit(query, f"🔍 Verbose tool logging set to {status}.")
            return

        if data.startswith("files:"):
            action = data.split(":")[1]
            if action == "clear":
                async with session.lock:
                    session.pending_files = []
                await safe_edit(query, "🗑️ Pending files cleared.")
            else:
                await safe_edit(query, "✅ Keeping pending files.")
            return

        if data.startswith("forget:"):
            action = data.split(":")[1]
            if action == "confirm":
                removed = False
                async with session.lock:
                    for idx in range(len(session.chat_history) - 1, -1, -1):
                        if session.chat_history[idx].get("role") == "user":
                            msg_id = session.chat_history[idx].get("message_id")
                            if msg_id in session.message_id_map:
                                del session.message_id_map[msg_id]
                            del session.chat_history[idx]
                            removed = True
                            break
                await safe_edit(
                    query,
                    "🗑️ Last user message removed." if removed else "No user message found.",
                )
            else:
                await safe_edit(query, "❌ Cancelled.")
            return

        if data.startswith("reset:"):
            action = data.split(":")[1]
            if action == "confirm":
                async with session.lock:
                    session.chat_history = []
                    session.pending_files = []
                    session.message_id_map = {}
                    if session.single_agent:
                        session.single_agent.messages = []
                    if session.unified_agent:
                        session.unified_agent.conversation_history = []
                    session.save_session()
                await safe_edit(query, "🗑️ Chat history cleared.")
            else:
                await safe_edit(query, "❌ Cancelled.")
            return

        if data.startswith("setup:"):
            parts = data.split(":")
            if len(parts) >= 2 and parts[1] == "cancel":
                session.wizard_state = {}
                await safe_edit(query, "❌ Setup cancelled.")
                return

            if len(parts) >= 3 and parts[1] == "mode":
                session.agent_mode = "auto"
                session.wizard_state = {"step": "monitor"}
                reply_markup = InlineKeyboardHelper.create_action_buttons(
                    [
                        {"text": "✅ On", "callback_data": "setup:monitor:on"},
                        {"text": "⛔ Off", "callback_data": "setup:monitor:off"},
                        {"text": "Cancel", "callback_data": "setup:cancel"},
                    ]
                )
                await safe_edit(
                    query,
                    "**Setup Step 1/2:** Auto mode is always enabled.\nEnable auto-reply?",
                    reply_markup=reply_markup,
                )
                return

            if len(parts) >= 3 and parts[1] == "monitor":
                setting = parts[2]
                session.auto_reply_enabled = setting == "on"
                if session.auto_reply_enabled:
                    session.auto_reply_notice_sent = False
                session.wizard_state = {"step": "skillnotify"}
                reply_markup = InlineKeyboardHelper.create_action_buttons(
                    [
                        {"text": "✅ On", "callback_data": "setup:skillnotify:on"},
                        {"text": "⛔ Off", "callback_data": "setup:skillnotify:off"},
                        {"text": "Cancel", "callback_data": "setup:cancel"},
                    ]
                )
                await safe_edit(
                    query,
                    "**Setup Step 2/2:** Show skill notifications?",
                    reply_markup=reply_markup,
                )
                return

            if len(parts) >= 3 and parts[1] == "skillnotify":
                setting = parts[2]
                session.show_skill_notifications = setting == "on"
                session.wizard_state = {}
                await safe_edit(
                    query,
                    "✅ Setup complete. You can adjust settings anytime with /monitor and /skills.",
                )
                return

        if data.startswith("retry:"):
            action = data.split(":")[1]
            if action in {"task", "message"} and session.last_user_message:
                await safe_edit(query, "🔄 Retrying message...")
                await run_chat_flow(
                    update,
                    context,
                    session,
                    session.last_user_message,
                    is_retry=True,
                )
            else:
                await safe_edit(query, "❌ Nothing to retry.")
            return

        if data.startswith("skip:"):
            await safe_edit(query, "⏭️ Skipped.")
            return

        if data.startswith("cancel:"):
            parts = data.split(":")
            target = parts[1] if len(parts) > 1 else "task"
            async with session.lock:
                session.should_interrupt = True
                if session.single_agent:
                    session.single_agent.stop()
                if session.refined_agent:
                    session.refined_agent.stop()
                if session.unified_agent:
                    session.unified_agent.stop()
            
            status_text = "⏹️ Current command aborted." if target == "current" else "⏹️ Task cancel requested."
            await safe_edit(query, status_text)
            return

        if data.startswith("stop:"):
            await stop_command(update, context)
            return

        if data.startswith("pause:"):
            await pause_command(update, context)
            return

        if data.startswith("continue:"):
            await continue_command(update, context)
            return

        if data.startswith("mode:"):
            async with session.lock:
                session.agent_mode = "auto"
            await safe_edit(query, "✅ Auto mode is always enabled.")
        elif data.startswith("variant:"):
            variant = data.split(":")[1]
            async with session.lock:
                session.current_variant = variant
            _publish_session_config_sync(session, "variant")
            await safe_edit(query, f"✅ Variant set to: **{variant}**")
        elif data.startswith("provider:"):
            provider = data.split(":")[1]
            session.ensure_current_model_available(AVAILABLE_MODELS)
            model_groups = {
                group["provider"]: group["models"]
                for group in session.get_available_model_groups(AVAILABLE_MODELS)
            }
            provider_models = model_groups.get(provider, [])
            if not provider_models:
                await safe_edit(query, "❌ No models are available for that provider.")
                return

            keyboard = []
            for model in provider_models:
                is_current = "✓ " if model == session.current_model else ""
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{is_current}{model}", callback_data=f"model:{model}"
                        )
                    ]
                )

            keyboard.append(
                [InlineKeyboardButton("« Back", callback_data="model:back")]
            )
            reply_markup = InlineKeyboardMarkup(keyboard)

            await safe_edit(
                query, f"**{provider.title()} Models:**", reply_markup=reply_markup
            )
        elif data.startswith("model:"):
            model = data.split(":")[1]

            if model == "back":
                session.ensure_current_model_available(AVAILABLE_MODELS)
                model_groups = session.get_available_model_groups(AVAILABLE_MODELS)
                if not model_groups:
                    await safe_edit(
                        query,
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
                await safe_edit(
                    query,
                    f"**Current Model:** {session.current_model}\n\nSelect a provider:",
                    reply_markup=reply_markup,
                )
            else:
                available_models = session.get_available_models(AVAILABLE_MODELS)
                if model not in available_models:
                    await safe_edit(
                        query,
                        "❌ That model is unavailable because its provider is not configured.",
                    )
                    return
                session.current_model = model
                available = session.get_available_variants()
                if session.current_variant not in available:
                    session.current_variant = available[0] if available else "standard"

                _publish_session_config_sync(session, "model")
                await safe_edit(query, f"✅ Model switched to: **{model}**")
        elif data.startswith("turns:"):
            turns = int(data.split(":")[1])
            session.max_turns = turns
            _publish_session_config_sync(session, "max_turns")
            await safe_edit(query, f"✅ Max turns set to: **{turns}**")
        elif data.startswith("session:"):
            session_id = data.split(":")[1]

            if session_id == "new":
                if session.is_processing:
                    await safe_edit(query, "⚠️ Finish or stop the current task before switching sessions.")
                    return

                # Save current if exists
                session.save_session()
                
                # Create and load new
                new_sess = session.session_manager.create_session(
                    model=session.current_model,
                    variant=session.current_variant,
                    agent_mode=session.agent_mode,
                    workspace=session.workspace
                )
                session.load_session_by_id(new_sess.id)
                
                await safe_edit(query, f"✅ Created and switched to new session: **{new_sess.name}**")
            else:
                try:
                    if session.is_processing:
                        current_id = session.session_manager.get_current_session_id() if session.session_manager else None
                        if str(current_id or "") != str(session_id):
                            await safe_edit(query, "⚠️ Finish or stop the current task before switching sessions.")
                            return

                    # Save current before switching
                    session.save_session()
                    
                    # Load the requested one
                    session.load_session_by_id(session_id)
                    await safe_edit(query, f"✅ Switched to session: **{session.session_manager.current_session.name}**")
                except RuntimeError as exc:
                    await safe_edit(query, f"⚠️ {exc}")
                except Exception as exc:
                    await safe_edit(query, f"❌ Failed to switch session: {exc}")
        elif data == "close":
            await query.delete_message()

    return {
        "button_callback": button_callback,
    }
