"""Message handlers for the Telegram bot."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

from telegram import Update
from telegram.ext import ContextTypes

from mobile_app.backend.session_bridge import AppSessionBridge
from shared.channel_events import publish_current_session_changed
from shared.telegram_bot_config_store import TelegramBotConfigStore


def build_message_handlers(
    *,
    security_manager,
    safe_reply: Callable[..., Any],
    get_session: Callable[[int], Any],
    run_chat_flow: Callable[..., Any],
    logger,
    HookType,
    HookEvent,
    MessageFormatter,
):
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages using CLI Agent with codebase tools."""
        user = update.effective_user
        message = update.effective_message

        if not message or not message.text:
            return

        if not security_manager.is_user_authorized(user.id):
            await message.reply_text("⛔ Unauthorized access.")
            return

        allowed, rate_msg = security_manager.check_rate_limit(user.id, "message")
        if not allowed:
            await message.reply_text(rate_msg or "Rate limit exceeded.")
            return

        raw_text = message.text
        user_message = security_manager.sanitize_input(raw_text)
        if not user_message:
            await safe_reply(update, "❌ Empty or invalid message.")
            return

        session = get_session(user.id)
        turn_orchestrator = None
        turn_lease = None
        raw_state_user_id = getattr(session, "sync_user_id", None)
        state_user_id = int(raw_state_user_id) if raw_state_user_id is not None else int(user.id)
        bridge = AppSessionBridge(user_id=state_user_id, workspace=Path(getattr(session, "workspace", Path.cwd())))
        bot_token = str(getattr(getattr(context, "bot", None), "token", "") or "").strip()
        bot_store = TelegramBotConfigStore(user_id=state_user_id)
        bot_store.ensure_default_from_env(bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
        matched_bot_config_id = None
        for item in bot_store.list_configs():
            if str(item.get("bot_token") or "").strip() == bot_token:
                matched_bot_config_id = str(item.get("id") or "").strip() or None
                break

        def _fleet_active_session_id() -> str | None:
            try:
                from mobile_app.backend.app_server import _get_remote_control_store

                snapshot = _get_remote_control_store().get_fleet_snapshot(user_id=state_user_id)
                active_identity_id = str(snapshot.get("active_identity_id") or "").strip()
                selected_by_identity = snapshot.get("selected_chat_by_identity")
                if not active_identity_id or not isinstance(selected_by_identity, dict):
                    return None
                selected_session_id = str(selected_by_identity.get(active_identity_id) or "").strip()
                return selected_session_id or None
            except Exception:
                logger.debug("Failed to resolve Fleet active session for Telegram message", exc_info=True)
                return None

        fleet_session_id = _fleet_active_session_id()
        focused_session_id = (
            fleet_session_id
            or str(getattr(session, "shared_current_session_id", "") or "").strip()
            or bridge.session_manager.get_current_session_id()
        )
        target_session_id = fleet_session_id or bridge.orchestrator.resolve_session_for_inbound_bot(
            bot_config_id=matched_bot_config_id,
            focused_session_id=focused_session_id,
        )
        if target_session_id:
            previous_session_id = bridge.session_manager.get_current_session_id()
            bridge.session_manager.set_current_session(target_session_id)
            publish_current_session_changed(
                user_id=state_user_id,
                session_id=target_session_id,
                previous_session_id=previous_session_id,
                origin_channel="telegram",
                reason="telegram_inbound_focus",
            )
            session = bridge.orchestrator.get_worker(target_session_id)
            turn_orchestrator = bridge.orchestrator
            # The orchestrator worker is keyed by the shared app user id so it
            # reads/writes the same desktop session state. Telegram delivery
            # still has to target the real Telegram chat/user id; otherwise
            # send_chat_action/replies can fail against chat_id=0 after the
            # user message has already been synced to the desktop.
            session.user_id = int(user.id)
            session.sync_user_id = state_user_id

        async with session.lock:
            session.session_context.update_activity()

            if not session.auto_reply_enabled:
                if not session.auto_reply_notice_sent:
                    await safe_reply(update, "⛔ Auto-reply is disabled. Use `/monitor on` to re-enable.")
                    session.auto_reply_notice_sent = True
                return

            if session.analytics_tracker:
                session.analytics_tracker.track_message(user.id, len(user_message), has_attachment=False)

            if session.hook_manager:
                hook_result = session.hook_manager.trigger(
                    HookType.MESSAGE_RECEIVED,
                    HookEvent.create(HookType.MESSAGE_RECEIVED, user.id, message=user_message),
                )
                if hook_result.get("final_data", {}).get("modified_message"):
                    user_message = hook_result["final_data"]["modified_message"]

                preprocess_result = session.hook_manager.trigger(
                    HookType.MESSAGE_PREPROCESS,
                    HookEvent.create(HookType.MESSAGE_PREPROCESS, user.id, message=user_message),
                )
                if preprocess_result.get("final_data", {}).get("modified_message"):
                    user_message = preprocess_result["final_data"]["modified_message"]

            logger.info(f"👤 USER INPUT: {user_message}")

            if session.is_processing:
                logger.info(f"⚡ Interrupting task {session.current_task_id} with new message")
                session.interrupt_message = user_message
                session.should_interrupt = True
                if session.single_agent:
                    session.single_agent.stop()
                if session.refined_agent:
                    session.refined_agent.stop()
                return

        if turn_orchestrator is not None and target_session_id:
            turn_lease = await turn_orchestrator.prepare_turn(str(target_session_id), origin_channel="telegram")
            if turn_lease.busy:
                await safe_reply(update, turn_lease.error or "⚠️ Already processing a message. Try again in a moment.")
                return
            session = turn_lease.worker
            session.user_id = int(user.id)
            session.sync_user_id = state_user_id

        try:
            await run_chat_flow(update, context, session, user_message)
        finally:
            if turn_orchestrator is not None and turn_lease is not None:
                await turn_orchestrator.complete_turn(turn_lease)

    async def handle_message_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle edited messages and update context."""
        user = update.effective_user

        if not security_manager.is_user_authorized(user.id):
            return

        allowed, message = security_manager.check_rate_limit(user.id, "edit")
        if not allowed:
            await safe_reply(update, message or "Rate limit exceeded.")
            return

        edited_message = update.edited_message
        if not edited_message or not edited_message.text:
            return

        session = get_session(user.id)
        new_text = security_manager.sanitize_input(edited_message.text)
        if not new_text:
            return

        msg_id = edited_message.message_id
        async with session.lock:
            idx = session.message_id_map.get(msg_id)
            if idx is None:
                await safe_reply(update, "⚠️ Edited message not found in context.")
                return

            session.chat_history[idx]["content"] = new_text
            session.chat_history[idx]["edited"] = True
            session.chat_history[idx]["edited_at"] = datetime.now().isoformat()
            session.last_user_message = new_text
        await safe_reply(update, "✏️ Updated message in context.")

    async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, file_obj):
        """Process a file upload and store for next message."""
        user = update.effective_user

        if not security_manager.is_user_authorized(user.id):
            return

        allowed, message = security_manager.check_rate_limit(user.id, "file")
        if not allowed:
            await safe_reply(update, message or "Rate limit exceeded.")
            return

        session = get_session(user.id)

        if not session.file_processor:
            await safe_reply(update, "❌ File processor not initialized.")
            return

        processed = await session.file_processor.process_telegram_file(file_obj, context.bot)
        if processed.error:
            await safe_reply(update, MessageFormatter.format_error(processed.error))
            return

        payload = session.file_processor.format_for_llm(processed)
        session.pending_files.append(payload)

        if session.analytics_tracker:
            session.analytics_tracker.track_message(user.id, 0, has_attachment=True)

        info = MessageFormatter.format_file_info(
            processed.filename,
            processed.size,
            processed.mime_type,
        )
        note = "Stored for your next message. Tell me what to do with it."
        await safe_reply(update, f"{info}\n\n{note}")

    async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document uploads."""
        if not update.message or not update.message.document:
            return
        await handle_file_upload(update, context, update.message.document)

    async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo uploads."""
        if not update.message or not update.message.photo:
            return
        photo = update.message.photo[-1]
        await handle_file_upload(update, context, photo)

    return {
        "handle_message": handle_message,
        "handle_message_edit": handle_message_edit,
        "handle_file_upload": handle_file_upload,
        "handle_document": handle_document,
        "handle_photo": handle_photo,
    }
