"""Task execution flow for the Telegram agent."""

import asyncio

from telegram.constants import ChatAction

from telegram_messaging import safe_reply, safe_edit_message
from telegram_unified_agent import build_unified_system_prompt, create_unified_agent_for_task
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
        session.start_browser_task(my_task_id)
        session.should_interrupt = False
        session.is_processing = True

    controls = InlineKeyboardHelper.task_control_buttons(str(my_task_id))
    start_msg = await safe_reply(
        update,
        f"🚀 **Starting Task:** {task_text}",
        reply_markup=controls
    )
    await context.bot.send_chat_action(chat_id=session.user_id, action=ChatAction.TYPING)

    execution_contract = (
        "# Task Execution Contract\n"
        "- Complete one verified step at a time.\n"
        "- Do not repeat steps that are already verified.\n"
        "- Prefer browser DOM tools and task-owned tabs for webpage work.\n"
        "- Use browser_wait_for instead of blind waiting when possible.\n"
        "- The task is done only when the requested state, file, or deliverable is verified.\n"
        "- End with a short completion report: what is done, proof, and any remaining blocker."
    )
    task_sections = [section for section in (execution_contract, task_text) if section]
    effective_task = "\n\n".join(task_sections)

    memory_context = ""
    if session.session_context.can_access_memory:
        current_session_id = (
            session.session_manager.current_session.id
            if session.session_manager and session.session_manager.current_session
            else None
        )
        prompt_memory = session.memory_manager.build_prompt_context(
            recent_days=2,
            recent_chars=2000,
            long_term_chars=4000,
            session_id=current_session_id,
        )
        if prompt_memory:
            memory_context = f"\n\n{prompt_memory}"

    # Inject active skills instructions
    active_skills_context = ""
    if session.active_skills and session.skill_registry:
        active_skills_context = session.skill_registry.get_active_skills_context(session.active_skills)
        if active_skills_context:
            effective_task = f"# LOADED SPECIALIZED SKILLS\n{active_skills_context}\n\n{effective_task}"

    if session.unified_agent:
        skills_index = ""
        if session.skill_registry:
            skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
        session.unified_agent.system_prompt = build_unified_system_prompt(
            session,
            memory_context=memory_context,
            skills_index=skills_index,
            active_skills_context=f"\n\n# LOADED SPECIALIZED SKILLS\n{active_skills_context}" if active_skills_context else "",
        )

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
