"""Chat execution flow for the Telegram bot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime

from anthropic import Anthropic
from telegram.constants import ChatAction

from cli.agent_tools.loop import run_tool_loop
from cli.tui_constants import MODEL_CONFIGS, SYSTEM_PROMPT, UNIFIED_AGENT_PROMPT
from bot_core.hooks import HookEvent, HookType
from single_agent.agent import AGENT_TOOLS

from telegram_messaging import safe_reply, safe_edit_message
from bot_core.ui_helpers import InlineKeyboardHelper, ThinkingModeVisualizer, SkillTriggerFeedback


logger = logging.getLogger(__name__)


async def run_chat_flow(update, context, session, user_message: str, is_retry: bool = False):
    """Shared chat execution flow for normal messages and retries."""
    async with session.lock:
        if session.is_processing:
            await safe_reply(update, "⚠️ Already processing a message. Try again in a moment.")
            return

        session.current_task_id += 1
        my_task_id = session.current_task_id
        session.should_interrupt = False
        session.is_processing = True

        session._app = context.application
        session._loop = asyncio.get_running_loop()

        message_id = update.effective_message.message_id if update.effective_message else None
        timestamp = datetime.now().isoformat()
        session.last_user_message = user_message
        session.chat_history.append({
            "role": "user",
            "content": user_message,
            "timestamp": timestamp,
            "message_id": message_id,
            "retry": is_retry
        })
        if message_id is not None:
            session.message_id_map[message_id] = len(session.chat_history) - 1

        estimated_tokens = sum(len(str(msg.get('content', ''))) // 4 for msg in session.chat_history)
        if estimated_tokens > 50000:
            session.chat_history = session.chat_history[-50:]
            logger.info("Compressed conversation history")
        
        # Save session to disk
        session.save_session()

    if is_retry and session.analytics_tracker:
        session.analytics_tracker.track_message(session.user_id, len(user_message), has_attachment=False)

    client, provider = session.get_client_for_model()
    if not client:
        await safe_reply(
            update,
            f"❌ No API key configured for provider: {provider}\n\n"
            "Set the appropriate environment variable or configure via /settings",
        )
        session.is_processing = False
        return

    await context.bot.send_chat_action(chat_id=session.user_id, action=ChatAction.TYPING)

    await context.bot.send_chat_action(chat_id=session.user_id, action=ChatAction.TYPING)

    file_context = ""
    if session.pending_files:
        safe_files = []
        for f in session.pending_files:
            safe_file = dict(f)
            if "image_base64" in safe_file:
                safe_file["image_base64"] = "[omitted - stored]"
            safe_files.append(safe_file)

        file_context = json.dumps(safe_files, indent=2)
        if len(file_context) > 8000:
            file_context = file_context[:7800] + "\n... [truncated]"
        session.pending_files = []

    # Build system content with skills index and active skills
    skills_index = ""
    active_skills_context = ""
    if session.skill_registry:
        skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
        if session.active_skills:
            active_skills_context = f"\n\n# LOADED SPECIALIZED SKILLS\n{session.skill_registry.get_active_skills_context(session.active_skills)}"

    memory_context = ""
    if session.session_context.can_access_memory:
        # Pass the current session ID to only see relevant context
        recent_memory = session.memory_manager.get_recent_context(
            days=7, 
            max_chars=3000,
            session_id=session.session_manager.current_session.id if session.session_manager and session.session_manager.current_session else None
        )
        if recent_memory:
            memory_context = f"\n\n## Recent Context from Memory\n\n{recent_memory}"

    system_content = f"{SYSTEM_PROMPT}{memory_context}{skills_index}{active_skills_context}"

    messages = [{"role": "system", "content": system_content}] + [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
        for msg in session.chat_history
    ]

    if file_context:
        messages.insert(1, {
            "role": "system",
            "content": f"USER ATTACHMENTS (structured data):\n{file_context}"
        })

    extra_tools = None
    custom_prompt = None

    if session.agent_mode == "semi":
        if session.single_agent and session.single_agent.messages:
            summary = session._summarize_history(session.single_agent.messages)
            if summary:
                messages.insert(1, {
                    "role": "system",
                    "content": (
                        "RECENT AUTOMATION CONTEXT:\n"
                        f"{summary}\n\n"
                        "(Use this context to understand what was done on the desktop/browser recently.)"
                    )
                })

    model_config = MODEL_CONFIGS.get(session.current_model, {})
    model_id = model_config.get("id", session.current_model)

    response_buffer = []

    def log_func(text: str):
        """Uniform logging for both Task and Auto agents."""
        if session._app and session._loop:
            asyncio.run_coroutine_threadsafe(
                session._send_log(text), session._loop
            )

    def log_inline_func(text: str):
        if text.strip():
            response_buffer.append(text)

    def begin_stream_func():
        response_buffer.clear()

    def append_stream_func(text: str):
        response_buffer.append(text)

    def finish_stream_func():
        pass

    def update_status_func():
        pass

    callbacks = {
        "log": log_func,
        "log_inline": log_inline_func,
        "begin_stream": begin_stream_func,
        "append_stream": append_stream_func,
        "finish_stream": finish_stream_func,
        "update_status": update_status_func,
    }

    loop = asyncio.get_running_loop()

    api_type = model_config.get("api", "chat")

    progress_message = None
    controls = InlineKeyboardHelper.create_action_buttons([
        {"text": "⏹ Stop", "callback_data": f"stop:{my_task_id}"}
    ])
    progress_label = "🤔 *Thinking...*" if ThinkingModeVisualizer.should_show_thinking(
        session.current_model, session.current_variant
    ) else "⏳ *Working...*"
    progress_message = await safe_reply(update, progress_label, reply_markup=controls)

    start_time = time.time()
    success = False

    try:
        if session.agent_mode == "auto":
            current_model_config = MODEL_CONFIGS.get(session.current_model, {})
            auto_provider = current_model_config.get("provider", "openai")
            auto_model_id = current_model_config.get("id", session.current_model)

            auto_client = None
            if auto_provider == "anthropic":
                if not session.anthropic_client:
                    api_key = session.config_manager.get_api_key("anthropic") or os.getenv("ANTHROPIC_API_KEY")
                    if api_key:
                        session.anthropic_client = Anthropic(api_key=api_key)
                        auto_client = session.anthropic_client
                    else:
                        await safe_reply(
                            update,
                            "❌ **Auto mode with Claude requires API Key.**\nSet ANTHROPIC_API_KEY."
                        )
                        session.is_processing = False
                        return
                else:
                    auto_client = session.anthropic_client
            elif auto_provider == "google":
                auto_client, auto_provider = session.get_client_for_model()
                if not auto_client:
                    await safe_reply(update, f"❌ **No API key for {auto_provider}.**")
                    session.is_processing = False
                    return
            else:
                auto_client, auto_provider = session.get_client_for_model()
                if not auto_client:
                    await safe_reply(update, f"❌ **No API key for {auto_provider}.**")
                    session.is_processing = False
                    return

            if not session.single_agent:
                session.init_single_agent(context.application, loop)

            # Auto mode uses the Task Agent (SingleAgent) tools merged with CLI tools
            # CLI tools are already included by run_tool_loop(provider=...)
            # so we only need to pass the automation tools as extra_tools.
            extra_tools = AGENT_TOOLS

            # Build custom prompt with skills index, active skills, and memory context
            skills_index = ""
            active_skills_context = ""
            if session.skill_registry:
                skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
                if session.active_skills:
                    active_skills_context = f"\n\n# LOADED SPECIALIZED SKILLS\n{session.skill_registry.get_active_skills_context(session.active_skills)}"
            
            custom_system_prompt = f"{UNIFIED_AGENT_PROMPT}{memory_context}{skills_index}{active_skills_context}"

            result = await loop.run_in_executor(
                None,
                lambda: run_tool_loop(
                    provider=auto_provider,
                    model_id=auto_model_id,
                    client=auto_client,
                    messages=messages,
                    tool_executor=session.tool_executor,
                    callbacks=callbacks,
                    variant=session.current_variant,
                    api_type=api_type,
                    extra_tools=extra_tools,
                    custom_system_prompt=custom_system_prompt,
                )
            )
        else:
            result = await loop.run_in_executor(
                None,
                lambda: run_tool_loop(
                    provider=provider,
                    model_id=model_id,
                    client=client,
                    messages=messages,
                    tool_executor=session.tool_executor,
                    callbacks=callbacks,
                    variant=session.current_variant,
                    api_type=api_type,
                    extra_tools=extra_tools,
                    custom_system_prompt=custom_prompt,
                )
            )

        if session.current_task_id != my_task_id:
            print(f"[DEBUG] Task {my_task_id} was abandoned, discarding result")
            return

        final_response = result.content or "".join(response_buffer)
        clean_response = final_response
        thinking_content = None

        if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant):
            clean_response, thinking_content = ThinkingModeVisualizer.extract_thinking_content(final_response)

        if thinking_content:
            thinking_msg = ThinkingModeVisualizer.format_thinking_for_telegram(thinking_content)
            await safe_reply(update, thinking_msg)

        if hasattr(session, 'pending_confirmations') and session.pending_confirmations:
            confirm_messages = []
            for confirm_id, confirm_data in list(session.pending_confirmations.items()):
                if time.time() - confirm_data['timestamp'] > 3600:
                    del session.pending_confirmations[confirm_id]
                    continue

                if not confirm_data['confirmed']:
                    confirm_messages.append(f"🔒 {confirm_data['message']}")
                    confirm_data['confirmed'] = True

            if confirm_messages:
                access_msg = "\n\n---\n\n".join(confirm_messages)
                await safe_reply(update, f"📂 **Path Access Log**\n\n{access_msg}")

        if clean_response:
            if len(clean_response) > 4000:
                parts = [clean_response[i:i+4000] for i in range(0, len(clean_response), 4000)]
                sent_ids = []
                for part in parts:
                    msg = await safe_reply(update, part)
                    if msg:
                        sent_ids.append(msg.message_id)
                session.chat_history.append({
                    "role": "assistant",
                    "content": clean_response,
                    "timestamp": datetime.now().isoformat(),
                    "message_ids": sent_ids
                })
            else:
                msg = await safe_reply(update, clean_response)
                session.chat_history.append({
                    "role": "assistant",
                    "content": clean_response,
                    "timestamp": datetime.now().isoformat(),
                    "message_id": msg.message_id if msg else None
                })
            
            # Save session to disk
            session.save_session()
        else:
            await safe_reply(update, "Done (no text response)")

        if session.memory_manager:
            session.memory_manager.append_to_daily_log(
                f"User: {user_message[:200]}...\n\nAssistant: {clean_response[:200]}...",
                "chat",
                session_id=session.session_manager.current_session.id if session.session_manager and session.session_manager.current_session else None
            )

        if session.hook_manager:
            session.hook_manager.trigger(
                HookType.MESSAGE_PROCESSED,
                HookEvent.create(HookType.MESSAGE_PROCESSED, session.user_id, response=clean_response)
            )

        duration = time.time() - start_time
        if session.analytics_tracker:
            session.analytics_tracker.track_llm_request(
                session.user_id,
                session.current_model,
                result.input_tokens,
                result.output_tokens,
                duration
            )

        success = True

    except Exception as exc:
        if session.current_task_id == my_task_id:
            reply_markup = InlineKeyboardHelper.retry_buttons("message")
            await safe_reply(update, f"Error: {str(exc)}", reply_markup=reply_markup)
    finally:
        if progress_message:
            status_text = "✅ *Completed*" if success else "⚠️ *Failed*"
            await safe_edit_message(progress_message, status_text, reply_markup=None)

        # Only mark processing complete if this task is still current
        async with session.lock:
            if session.current_task_id == my_task_id:
                session.is_processing = False
