"""Task execution flow for the Telegram agent."""

import asyncio

from telegram.constants import ChatAction

from telegram_messaging import safe_reply, safe_edit_message
from telegram_unified_agent import create_unified_agent_for_task
from bot_core.ui_helpers import InlineKeyboardHelper


async def run_task_flow(update, context, session, task_text: str) -> None:
    """Execute task using unified agent."""
    session.last_task_text = task_text

    if not session.unified_agent:
        loop = asyncio.get_running_loop()
        create_unified_agent_for_task(session, context.application, loop)

    async with session.lock:
        if session.is_processing:
            print("[DEBUG] Abandoning current processing")
            session.should_interrupt = True
            if session.unified_agent:
                session.unified_agent.stop()

        session.current_task_id += 1
        my_task_id = session.current_task_id
        session.should_interrupt = False
        session.is_processing = True

    controls = InlineKeyboardHelper.task_control_buttons(str(my_task_id))
    start_msg = await safe_reply(
        update,
        f"🚀 **Starting Task:** {task_text}",
        reply_markup=controls
    )
    await context.bot.send_chat_action(chat_id=session.user_id, action=ChatAction.TYPING)

    workspace_context = session.context_loader.build_system_prompt_context()
    effective_task = f"{workspace_context}\n\n{task_text}" if workspace_context else task_text

    if session.session_context.can_access_memory:
        # Pass the current session ID to only see relevant context
        recent_memory = session.memory_manager.get_recent_context(
            days=2, 
            max_chars=2000, 
            session_id=session.session_manager.current_session.id if session.session_manager and session.session_manager.current_session else None
        )
        if recent_memory:
            effective_task = f"# Recent Context\n\n{recent_memory}\n\n{effective_task}"

    # Inject active skills instructions
    if session.active_skills and session.skill_registry:
        active_skills_context = session.skill_registry.get_active_skills_context(session.active_skills)
        if active_skills_context:
            effective_task = f"# LOADED SPECIALIZED SKILLS\n{active_skills_context}\n\n{effective_task}"

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: session.unified_agent.run(effective_task, max_turns=session.max_turns)
        )

        if session.current_task_id != my_task_id:
            return

        session.memory_manager.append_to_daily_log(
            f"Task: {task_text}\nResult: {result}",
            "agent",
            session_id=session.session_manager.current_session.id if session.session_manager and session.session_manager.current_session else None
        )

        await safe_reply(update, f"🏁 **Task Finished**\n{result}")
        await safe_edit_message(start_msg, f"✅ **Task Completed**\n{task_text}")
    except Exception as exc:
        if session.current_task_id == my_task_id:
            reply_markup = InlineKeyboardHelper.retry_buttons("task")
            await safe_reply(update, f"🔥 ERROR: {str(exc)}", reply_markup=reply_markup)
    finally:
        async with session.lock:
            if session.current_task_id == my_task_id:
                session.is_processing = False
