"""Cron job execution through the live unified tool-loop path.

This phases cron execution away from RefinedAgent without changing the
existing interactive Telegram chat flow.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Optional

from cli.agent_tools.definitions import CLI_AGENT_TOOLS
from cli.agent_tools.loop import run_tool_loop
from cli.tui_constants import MODEL_CONFIGS
from local_agent_runtime.agent import AGENT_TOOLS
from shared import current_session_id
from shared.proactive_runtime import install_background_process_hooks
from shared.tool_packs import (
    filter_openai_tools_by_enabled_packs,
    filter_tools_by_enabled_packs,
    tools_for_enabled_packs,
)
from telegram_bot.telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)


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


def _get_provider_tools(provider: str):
    return _merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS)


async def run_cron_job_via_unified_flow(
    session,
    prompt: str,
    *,
    max_turns: int = 30,
    progress_callback: Optional[Callable[[str], None]] = None,
    scheduled_job_id: Optional[str] = None,
) -> str:
    """Execute one cron prompt using the same unified tool-loop stack as live chat."""
    client, provider = session.get_client_for_model()
    if not client:
        raise RuntimeError(f"No API key configured for provider: {provider}")

    model_config = MODEL_CONFIGS.get(session.current_model, {})
    model_id = model_config.get("id", session.current_model)
    api_type = model_config.get("api", "chat")

    if session.tool_executor:
        session.tool_executor.custom_tool_handlers = get_auto_mode_tool_handlers(session)

    active_tool_packs = list(
        getattr(session, "_active_tool_packs_for_current_run", None)
        or getattr(session, "enabled_tool_packs", [])
        or []
    )
    extra_tools = filter_openai_tools_by_enabled_packs(_get_provider_tools(provider), active_tool_packs)

    skills_index = ""
    active_skills_context = ""
    if session.skill_registry:
        skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
        if session.active_skills:
            active_skills_context = (
                "\n\n# LOADED SPECIALIZED SKILLS\n"
                f"{session.skill_registry.get_active_skills_context(session.active_skills)}"
            )

    memory_context = ""
    if session.memory_manager:
        try:
            build_prompt_context = getattr(session.memory_manager, "build_prompt_context", None)
            if callable(build_prompt_context):
                memory_context = build_prompt_context(
                    session_id=current_session_id(session),
                    recent_days=7,
                    recent_chars=3000,
                    long_term_chars=4000,
                )
            else:
                get_long_term_context = getattr(session.memory_manager, "get_long_term_context", None)
                if callable(get_long_term_context):
                    memory_context = get_long_term_context()
        except Exception:
            memory_context = ""

    custom_system_prompt = build_unified_system_prompt(
        session,
        memory_context=memory_context,
        skills_index=skills_index,
        active_skills_context=active_skills_context,
    )

    messages = [
        {"role": "system", "content": custom_system_prompt},
        {
            "role": "user",
            "content": (
                "[SCHEDULED JOB]\n"
                "This task was triggered automatically by the scheduler. "
                "Complete it and produce the final user-facing result.\n\n"
                f"{prompt}"
            ),
        },
    ]

    response_buffer = []

    def begin_stream_func():
        response_buffer.clear()

    def append_stream_func(text: str):
        response_buffer.append(text)

    def finish_stream_func():
        pass

    def log_func(text: str):
        if progress_callback and text and not text.startswith("  [TOOL]"):
            progress_callback(text)

    callbacks = {
        "log": log_func,
        "log_inline": lambda text: response_buffer.append(text) if text else None,
        "begin_stream": begin_stream_func,
        "append_stream": append_stream_func,
        "finish_stream": finish_stream_func,
        "update_status": lambda: None,
    }

    loop = asyncio.get_running_loop()
    if session.tool_executor:
        install_background_process_hooks(session, event_loop=loop)
    session.current_turn_allowed_tool_names = tools_for_enabled_packs(active_tool_packs)
    session.current_turn_allowed_tool_definitions = filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, active_tool_packs)
    try:
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
                extra_tools=extra_tools,
                base_tools=session.current_turn_allowed_tool_definitions,
                custom_system_prompt=custom_system_prompt,
                api_type=api_type,
            ),
        )
    finally:
        session.current_turn_allowed_tool_names = None
        session.current_turn_allowed_tool_definitions = []

    final_response = result.content or "".join(response_buffer)
    clean_response = final_response.strip() or "Done (no text response)"
    try:
        session.chat_history.append(
            {
                "role": "assistant",
                "content": clean_response,
                "timestamp": datetime.now().isoformat(),
                "scheduled_job": True,
                "scheduled_job_id": scheduled_job_id,
            }
        )
        session.save_session()
    except Exception:
        pass

    if session.memory_manager:
        try:
            session.memory_manager.append_to_daily_log(
                f"Scheduled Job Prompt: {prompt[:200]}...\n\nAssistant: {clean_response[:200]}...",
                "cron",
                session_id=(
                    session.session_manager.current_session.id
                    if session.session_manager and session.session_manager.current_session
                    else None
                ),
            )
        except Exception:
            pass

    return clean_response
