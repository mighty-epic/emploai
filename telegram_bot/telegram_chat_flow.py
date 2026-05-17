"""Chat execution flow for the Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import time

from telegram.constants import ChatAction

try:
    from telegram_bot.telegram_unified_agent import (
        build_unified_system_prompt,
        get_auto_mode_extra_tools,
        get_auto_mode_tool_handlers,
    )
    from telegram_bot.telegram_messaging import safe_reply, safe_edit_message
except ImportError:
    from telegram_unified_agent import (
        build_unified_system_prompt,
        get_auto_mode_extra_tools,
        get_auto_mode_tool_handlers,
    )
    from telegram_messaging import safe_reply, safe_edit_message
from bot_core.ui_helpers import InlineKeyboardHelper, ThinkingModeVisualizer
from single_agent.agent import AGENT_TOOLS
from shared import begin_chat_turn, merge_openai_tools, run_reserved_chat_turn
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME


logger = logging.getLogger(__name__)

# --- Base64 field names to always strip from verbose output ---
_BASE64_KEYS = frozenset({"image_base64", "base64", "image_data", "data", "screenshot"})


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
    message_id = update.effective_message.message_id if update.effective_message else None
    session._app = context.application
    session._loop = asyncio.get_running_loop()

    reservation = await begin_chat_turn(
        session,
        user_message=user_message,
        user_message_payload={
            "channel": "telegram",
            "source_format": "telegram_text",
            "display_label": "Telegram",
            "message_id": message_id,
            "retry": is_retry,
        },
    )
    if reservation.busy:
        await safe_reply(update, "⚠️ Already processing a message. Try again in a moment.")
        return

    my_task_id = reservation.task_id

    if reservation.is_session_start:
        window_info = "Unknown"
        if "Active Windows: " in session.system_info:
            window_info = session.system_info.split("Active Windows: ")[-1]

        await safe_reply(
            update,
            "🌍 *Session Started*\n"
            "Checking environment and active windows...\n\n"
            f"**Active Windows:** {window_info}"
        )

    if reservation.context_compressed:
        logger.info("[ContextManager] Compression complete")
        compaction = reservation.context_compaction or {}
        compaction_msg = compaction.get("message") or (
            "I summarized earlier conversation history to keep the live Telegram session within context limits."
        )
        await safe_reply(
            update,
            "**🔘 Context Compacted**\n\n"
            f"{compaction_msg}\n\n"
            "Use `/context` to inspect the updated usage.",
        )

    if is_retry and session.analytics_tracker:
        session.analytics_tracker.track_message(session.user_id, len(user_message), has_attachment=False)

    await context.bot.send_chat_action(chat_id=session.user_id, action=ChatAction.TYPING)
    await context.bot.send_chat_action(chat_id=session.user_id, action=ChatAction.TYPING)

    # --- Kickstart priming: inject a hidden exchange that primes the model to act ---
    # This is invisible to the user but teaches the model its expected behavior pattern.
    # Only inject on first few messages to avoid bloating long conversations.
    prelude_messages = []
    if len(session.chat_history) <= 3:
        kickstart = [
            {
                "role": "user",
                "content": (
                    "IMPORTANT REMINDER: You are an autonomous agent with full computer control. "
                    "When I ask you to do something, DO IT immediately using your tools. "
                    "Do not explain what you would do — just do it. "
                    "Do not list what you can't do — find a way. "
                    "If you need to install something, install it. "
                    "Use browser DOM tools only when they are actually available for the current browser context. "
                    "If the task is in the user's real Chrome and the extension bridge is unavailable, do NOT use browser_* tools for that page — "
                    "switch to describe_screen plus atomic desktop actions, and use ocr_screen only when you need exact text coordinates or a fallback click. "
                    "Use the cheapest verification tool that fits the environment. "
                    "Never chain multiple browser or desktop edits without verifying the resulting state. "
                    "If a method fails and the state has not changed, do not repeat it — choose a different method. "
                    "Only declare done after the requested result is verified. "
                    "Before you finish, quickly assess what worked, what failed, and save only durable reusable lessons to memory. "
                    "Act first. Report results after."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Understood. I will act immediately, verify each step, and use only the tools that match the current environment. "
                    "If the task is in the user's Chrome without the extension bridge, I will not pretend Selenium or browser_* tools control that page; "
                    "I will switch to visual observation and atomic desktop actions instead. "
                    "I will avoid retrying failed methods unless state changed, and before finishing I will preserve only durable lessons worth remembering. "
                    "Ready for your task."
                ),
            },
        ]
        prelude_messages.extend(kickstart)

    system_messages = [
        {
            "role": "system",
            "content": (
            "TASK EXECUTION CONTRACT:\n"
            "- For complex tasks, keep a short internal checklist and complete one verified step at a time.\n"
            "- The managed task board is runtime-owned. Do not try to create, rewrite, or complete it yourself.\n"
            f"- Use {TASK_BOARD_INTERNAL_TOOL_NAME} only after the same concrete method has genuinely failed three times, or when the task truly requires credentials, 2FA, or account choice from the user.\n"
            "- The runtime will create, reassess, and complete the board. Your job is to execute the task and report proof.\n"
            "- Do not repeat a step once the requested state is already verified, and do not retry a failed method unless the page or app state changed.\n"
            "- For webpage DOM actions, rely on browser tool results and browser_snapshot only when the current browser context actually supports them.\n"
            "- If the task is in the user's real Chrome and the extension bridge is unavailable, browser_* tools do NOT control that page; use describe_screen first, then ocr_screen only for exact text coordinates or fallback clicks.\n"
                "- Prefer describe_screen for visual discovery, button finding, and layout understanding. Use ocr_screen mainly for exact text extraction and coordinate fallback.\n"
                "- Prefer ref-based browser tools over focus-dependent typing or synthetic keypresses.\n"
                "- Use browser_wait_for instead of blind delays when waiting for navigation or confirmation text.\n"
                "- Ask the user only for true user-dependent blockers such as credentials, 2FA, or account choice. All other failures should continue autonomously.\n"
                "- Before final completion, assess what worked vs failed. Save only durable reusable lessons to memory.\n"
                "- A task is done only when the requested file, page state, or deliverable is verified.\n"
                "- End with a short completion report that states what is done, the proof, and any remaining blocker."
            ),
        }
    ]

    progress_message = None
    controls = InlineKeyboardHelper.create_action_buttons([
        {"text": "⏹ Stop", "callback_data": f"stop:{my_task_id}"}
    ])
    progress_label = "🤔 *Thinking...*" if ThinkingModeVisualizer.should_show_thinking(
        session.current_model, session.current_variant
    ) else "⏳ *Working...*"
    progress_message = await safe_reply(update, progress_label, reply_markup=controls)

    success = False

    try:
        async def event_sink(event):
            event_type = event.get("type")
            if event_type == "log":
                if session._app and session._loop:
                    await session._send_log(event.get("message", ""))
                return
            if event_type == "tool_use":
                if not session.verbose_mode or not session._app or not session._loop:
                    return
                msg = _format_verbose_tool_msg(
                    event.get("tool_name", ""),
                    event.get("tool_args") or {},
                    event.get("tool_result"),
                    float(event.get("duration_ms") or 0.0),
                )
                await _send_verbose_to_telegram(session, msg)
                return
            if event_type == "task_board":
                summary = str(event.get("summary") or "").strip()
                board = event.get("board") or {}
                lines = ["Task board update"]
                if board.get("main_goal"):
                    lines.append(f"Goal: {board['main_goal']}")
                if summary:
                    lines.append(summary)
                if board.get("progress_summary"):
                    lines.append(f"Progress: {board['progress_summary']}")
                await safe_reply(update, "\n".join(lines))
                return

        result = await run_reserved_chat_turn(
            session,
            reservation,
            prompt_builder=build_unified_system_prompt,
            tool_handlers_builder=get_auto_mode_tool_handlers,
            extra_tools_builder=lambda runtime_session: merge_openai_tools(
                get_auto_mode_extra_tools(),
                AGENT_TOOLS,
            ),
            system_messages=system_messages,
            prelude_messages=prelude_messages,
            assistant_message_payload={
                "channel": "telegram",
                "source_format": "telegram_response",
                "display_label": "Telegram",
            },
            event_sink=event_sink,
            initialize_single_agent=lambda current_loop: session.init_single_agent(
                context.application,
                current_loop,
            ),
            assistant_content_transform=lambda response: (
                ThinkingModeVisualizer.extract_thinking_content(response)[0]
                if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant)
                else response
            ),
        )
        if result.abandoned:
            return

        clean_response = result.assistant_text
        thinking_content = None

        if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant):
            clean_response, thinking_content = ThinkingModeVisualizer.extract_thinking_content(result.raw_response)

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
                async with session.lock:
                    if session.chat_history and session.chat_history[-1].get("role") == "assistant":
                        session.chat_history[-1]["message_ids"] = sent_ids
                        session.save_session()
            else:
                msg = await safe_reply(update, clean_response)
                async with session.lock:
                    if session.chat_history and session.chat_history[-1].get("role") == "assistant":
                        session.chat_history[-1]["message_id"] = msg.message_id if msg else None
                        session.save_session()
        else:
            await safe_reply(update, "Done (no text response)")

        if result.context_compressed and not reservation.context_compressed:
            compaction = result.context_compaction or {}
            compaction_msg = compaction.get("message") or "Context compacted."
            await safe_reply(
                update,
                "**🔘 Context Compacted**\n\n"
                f"{compaction_msg}\n\n"
                "Use `/context` to inspect the updated usage.",
            )

        success = True

    except Exception as exc:
        if session.current_task_id == my_task_id:
            message = str(exc)
            if message.startswith("No API key configured for provider:"):
                message = (
                    f"❌ {message}\n\n"
                    "Set the appropriate environment variable or configure via /settings"
                )
            elif message == "Claude requires API key":
                message = "❌ **Claude requires API Key.**\nSet ANTHROPIC_API_KEY."
            reply_markup = InlineKeyboardHelper.retry_buttons("message")
            await safe_reply(update, message, reply_markup=reply_markup)
    finally:
        if progress_message:
            status_text = "✅ *Completed*" if success else "⚠️ *Failed*"
            await safe_edit_message(progress_message, status_text, reply_markup=None)
