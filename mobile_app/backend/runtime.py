from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic

from cli.agent_tools.loop import run_tool_loop
from cli.tui_constants import MODEL_CONFIGS
from single_agent.agent import AGENT_TOOLS
from telegram_bot.telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)


def _merge_openai_tools(*tool_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
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


def _safe_message_id(session: Any) -> Optional[str]:
    current_id = session.session_manager.get_current_session_id() if session.session_manager else None
    return current_id


async def run_app_chat_turn(
    session: Any,
    *,
    user_message: str,
    source_format: str = "app_text",
    log_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    session.current_task_id += 1
    my_task_id = session.current_task_id
    session.start_browser_task(my_task_id)
    session.should_interrupt = False
    session.is_processing = True

    timestamp = datetime.now().isoformat()
    display_label = "App Voice" if source_format == "app_voice_transcript" else "App"
    session.last_user_message = user_message
    session.chat_history.append(
        {
            "role": "user",
            "content": user_message,
            "timestamp": timestamp,
            "channel": "app",
            "source_format": source_format,
            "display_label": display_label,
        }
    )

    is_session_start = len(session.chat_history) == 1
    if is_session_start:
        session.refresh_system_info()

    if session.context_manager:
        model_id = session.current_model or "claude-sonnet-4-5"
        if session.context_manager.needs_compression(session.chat_history, model_id):
            session.chat_history = session.context_manager.compress(session.chat_history)

    session.save_session()

    client, provider = session.get_client_for_model()
    if not client:
        session.is_processing = False
        raise RuntimeError(f"No API key configured for provider: {provider}")

    file_context = ""
    if session.pending_files:
        safe_files = []
        for f in session.pending_files:
            safe_file = dict(f)
            if "image_base64" in safe_file:
                safe_file["image_base64"] = "[omitted - stored]"
            safe_files.append(safe_file)
        session.pending_files = []
        if safe_files:
            import json
            file_context = json.dumps(safe_files, indent=2)
            if len(file_context) > 8000:
                file_context = file_context[:7800] + "\n... [truncated]"

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
    if session.session_context and session.session_context.can_access_memory and session.memory_manager:
        memory_context = session.memory_manager.get_long_term_context()

    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": "You are EmploAI operating through the mobile app channel.",
        }
    ]
    if file_context:
        messages.append(
            {
                "role": "system",
                "content": f"USER ATTACHMENTS (structured data):\n{file_context}",
            }
        )
    messages.extend(session.chat_history)

    response_buffer: List[str] = []

    running_loop = asyncio.get_running_loop()

    async def emit(event: Dict[str, Any]) -> None:
        if log_callback:
            maybe = log_callback(event)
            if asyncio.iscoroutine(maybe):
                await maybe

    def _schedule_emit(event: Dict[str, Any]) -> None:
        if not log_callback:
            return
        try:
            asyncio.run_coroutine_threadsafe(emit(event), running_loop)
        except RuntimeError:
            pass

    def log_func(text: str):
        _schedule_emit({"type": "log", "message": text})

    def log_inline_func(text: str):
        if text.strip():
            response_buffer.append(text)

    def begin_stream_func():
        response_buffer.clear()

    def append_stream_func(text: str):
        response_buffer.append(text)
        _schedule_emit({"type": "assistant_delta", "delta": text})

    def finish_stream_func():
        return None

    def update_status_func():
        return None

    def on_tool_use_func(tool_name, tool_args, tool_result, dur_ms):
        _schedule_emit(
            {
                "type": "tool_use",
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_result": tool_result,
                "duration_ms": dur_ms,
            }
        )

    callbacks = {
        "log": log_func,
        "log_inline": log_inline_func,
        "begin_stream": begin_stream_func,
        "append_stream": append_stream_func,
        "finish_stream": finish_stream_func,
        "update_status": update_status_func,
        "on_tool_use": on_tool_use_func,
    }

    model_config = MODEL_CONFIGS.get(session.current_model, {})
    auto_provider = model_config.get("provider", "openai")
    auto_model_id = model_config.get("id", session.current_model)
    api_type = model_config.get("api", "chat")

    auto_client = client
    if auto_provider == "anthropic" and not session.anthropic_client:
        api_key = session.config_manager.get_api_key("anthropic") or os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            session.anthropic_client = Anthropic(api_key=api_key)
            auto_client = session.anthropic_client
        else:
            session.is_processing = False
            raise RuntimeError("Claude requires API key")

    if not session.single_agent:
        session.init_single_agent(None, asyncio.get_running_loop())

    if session.tool_executor:
        session.tool_executor.custom_tool_handlers = get_auto_mode_tool_handlers(session)

    extra_tools = _merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS)
    custom_system_prompt = build_unified_system_prompt(
        session,
        memory_context=memory_context,
        skills_index=skills_index,
        active_skills_context=active_skills_context,
    )

    await emit({"type": "status", "message": "running"})
    start_time = time.time()

    try:
        loop = asyncio.get_running_loop()
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
            ),
        )

        final_response = result.content or "".join(response_buffer)
        session.chat_history.append(
            {
                "role": "assistant",
                "content": final_response,
                "timestamp": datetime.now().isoformat(),
                "channel": "app",
                "source_format": "app_system",
                "display_label": "App",
            }
        )
        session.save_session()
        duration = time.time() - start_time
        return {
            "ok": True,
            "session_id": _safe_message_id(session),
            "assistant_text": final_response,
            "duration_seconds": duration,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
        }
    finally:
        session.is_processing = False
