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
from cli.tui_constants import MODEL_CONFIGS
from bot_core.hooks import HookEvent, HookType
from single_agent.agent import AGENT_TOOLS
from telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)

from telegram_messaging import safe_reply, safe_edit_message
from bot_core.ui_helpers import InlineKeyboardHelper, ThinkingModeVisualizer, SkillTriggerFeedback


logger = logging.getLogger(__name__)

# --- Base64 field names to always strip from verbose output ---
_BASE64_KEYS = frozenset({"image_base64", "base64", "image_data", "data", "screenshot"})


def _merge_openai_tools(*tool_groups):
    merged = []
    seen = set()
    for group in tool_groups:
        for tool in group:
            func = tool.get("function", {})
            name = func.get("name")
            if not name or name in seen:
                continue
            merged.append(tool)
            seen.add(name)
    return merged


def _format_verbose_tool_msg(name: str, args: dict, result, duration_ms: float) -> str:
    """Format a compact tool call + result message for Telegram verbose mode."""
    # -- Truncated args --
    short_parts = []
    for k, v in list(args.items())[:4]:
        v_str = str(v)
        # Skip base64-like fields entirely
        if k in _BASE64_KEYS and len(v_str) > 100:
            continue
        if len(v_str) > 80:
            v_str = v_str[:77] + "..."
        short_parts.append(f"{k}: {v_str}")
    args_str = ", ".join(short_parts)
    if len(args_str) > 200:
        args_str = args_str[:197] + "..."

    # -- Compact result --
    if isinstance(result, dict):
        if "error" in result:
            result_line = f"\u274c {str(result['error'])[:120]}"
        else:
            safe_keys = [k for k in result.keys() if k not in _BASE64_KEYS]
            result_line = f"\u2705 {', '.join(safe_keys[:4])}"
    elif isinstance(result, str):
        clean = result
        if len(clean) > 120:
            clean = clean[:117] + "..."
        result_line = f"\u274c {clean}" if clean.startswith("Error") else f"\u2705 {clean}"
    else:
        result_line = f"\u2705 {str(result)[:120]}"

    msg = f"\U0001f527 {name}({args_str})\n\u2192 {result_line} ({duration_ms:.0f}ms)"
    # Hard cap to prevent Telegram message-too-long errors
    if len(msg) > 500:
        msg = msg[:497] + "..."
    return msg


async def _send_verbose_to_telegram(session, msg: str):
    """Send a verbose tool message to Telegram (fire-and-forget safe)."""
    if not session._app:
        return
    try:
        await session._app.bot.send_message(
            chat_id=session.user_id,
            text=msg,
        )
    except Exception:
        pass  # Never let verbose logging break the flow


async def run_chat_flow(update, context, session, user_message: str, is_retry: bool = False):
    """Shared chat execution flow for normal messages and retries."""
    async with session.lock:
        if session.is_processing:
            await safe_reply(update, "⚠️ Already processing a message. Try again in a moment.")
            return

        session.current_task_id += 1
        my_task_id = session.current_task_id
        session.start_browser_task(my_task_id)
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

        # Check if this is the very first message in the session
        is_session_start = len(session.chat_history) == 1
        
        if is_session_start:
            # Refresh system info at session start as requested
            session.refresh_system_info()
            
            # Extract window list for user-facing announcement
            window_info = "Unknown"
            if "Active Windows: " in session.system_info:
                window_info = session.system_info.split("Active Windows: ")[-1]
            
            await safe_reply(
                update,
                "🌍 *Session Started*\n"
                "Checking environment and active windows...\n\n"
                f"**Active Windows:** {window_info}"
            )

        # Smart context compression via LLM summarization
        if session.context_manager:
            model_id = session.current_model or "claude-sonnet-4-5"
            if session.context_manager.needs_compression(session.chat_history, model_id):
                logger.info("[ContextManager] Compressing conversation history...")

                await safe_reply(
                    update,
                    "🔘 *Memory Compressed*\n"
                    "I summarized earlier conversation history to keep the live Telegram session within context limits."
                )

                session.chat_history = session.context_manager.compress(session.chat_history)
                logger.info("[ContextManager] Compression complete")
        
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
        current_session_id = (
            session.session_manager.current_session.id
            if session.session_manager and session.session_manager.current_session
            else None
        )
        prompt_memory = session.memory_manager.build_prompt_context(
            recent_days=7,
            recent_chars=3000,
            long_term_chars=4000,
            session_id=current_session_id,
        )
        if prompt_memory:
            memory_context = f"\n\n{prompt_memory}"

    system_content = build_unified_system_prompt(
        session,
        memory_context=memory_context,
        skills_index=skills_index,
        active_skills_context=active_skills_context,
    )

    messages = [{"role": "system", "content": system_content}] + [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
        for msg in session.chat_history
    ]

    messages.insert(1, {
        "role": "system",
        "content": (
            "TASK EXECUTION CONTRACT:\n"
            "- For complex tasks, keep a short internal checklist and complete one verified step at a time.\n"
            "- Do not repeat a step once the requested state is already verified.\n"
            "- For webpage DOM actions, rely on browser tool results and browser_snapshot first. Use describe_screen or ocr_screen only for browser chrome, desktop apps, or when DOM tools are unavailable.\n"
            "- Prefer ref-based browser tools over focus-dependent typing or synthetic keypresses.\n"
            "- Use browser_wait_for instead of blind delays when waiting for navigation or confirmation text.\n"
            "- A task is done only when the requested file, page state, or deliverable is verified.\n"
            "- End with a short completion report that states what is done, the proof, and any remaining blocker."
        ),
    })

    # --- Kickstart priming: inject a hidden exchange that primes the model to act ---
    # This is invisible to the user but teaches the model its expected behavior pattern.
    # Only inject on first few messages to avoid bloating long conversations.
    if len(session.chat_history) <= 3:
        kickstart = [
            {
                "role": "user",
                "content": (
                    "IMPORTANT REMINDER: You are an autonomous agent with full computer control. "
                    "When I ask you to do something, DO IT immediately using your tools. "
                    "Do not explain what you would do — just do it. "
                    "Do not ask me for permission or credentials — get them yourself. "
                    "Do not list what you can't do — find a way. "
                    "If you need to sign up for a service, open the browser and sign up. "
                    "If you need to install something, install it. "
                    "Use the cheapest verification tool that fits the environment: browser tool results and browser_snapshot first for webpages, "
                    "describe_screen or ocr_screen only for browser chrome, desktop apps, or when DOM tools fail. "
                    "Never chain multiple browser edits without verifying the resulting page state. "
                    "Do not repeat already-completed steps. "
                    "Only declare done after the requested result is verified. "
                    "Act first. Report results after."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Understood. I will act immediately on every request — no explanations, no permission-seeking, "
                    "no listing limitations. I'll use my tools to execute tasks directly, sign up for services myself "
                    "if needed, install packages, write scripts, and verify each step with the lowest-waste tool that can prove it worked. "
                    "For webpages I will stay in the task tab, prefer ref-based DOM tools, avoid repeating completed steps, "
                    "and only finish after the deliverable is verified. Ready for your task."
                ),
            },
        ]
        # Insert right after system message (index 1)
        messages[1:1] = kickstart

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

    # Verbose tool-use callback (sends live tool info to Telegram)
    def on_tool_use_func(tool_name, tool_args, tool_result, dur_ms):
        if not session.verbose_mode:
            return
        if not session._app or not session._loop:
            return
        msg = _format_verbose_tool_msg(tool_name, tool_args, tool_result, dur_ms)
        asyncio.run_coroutine_threadsafe(
            _send_verbose_to_telegram(session, msg), session._loop
        )

    callbacks["on_tool_use"] = on_tool_use_func

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
        # --- Unified path: always provide full tools + prompt regardless of mode ---
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
                        "❌ **Claude requires API Key.**\nSet ANTHROPIC_API_KEY."
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

        if session.tool_executor:
            session.tool_executor.custom_tool_handlers = get_auto_mode_tool_handlers(session)

        # Always provide automation tools + CLI tools
        extra_tools = _merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS)

        # Build custom prompt with skills index, active skills, and memory context
        skills_index = ""
        active_skills_context = ""
        if session.skill_registry:
            skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
            if session.active_skills:
                active_skills_context = f"\n\n# LOADED SPECIALIZED SKILLS\n{session.skill_registry.get_active_skills_context(session.active_skills)}"
        
        custom_system_prompt = build_unified_system_prompt(
            session,
            memory_context=memory_context,
            skills_index=skills_index,
            active_skills_context=active_skills_context,
        )

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

        # Background: auto-rename session at message checkpoints (3, 20)
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, session.auto_rename_session)

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
