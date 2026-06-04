from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from bot_core.ui_helpers import ThinkingModeVisualizer
from cli.agent_tools.definitions import CLI_AGENT_TOOLS
from single_agent.tool_manifest import AGENT_TOOLS
from shared.channel_sync import get_channel_sync_hub
from telegram_bot.telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME, get_active_task_board

from shared import begin_chat_turn, merge_openai_tools, run_reserved_chat_turn
from shared.live_config import get_live_config
from shared.task_intent import is_screen_observation_message, is_task_like_message
from shared.tool_pack_prompts import (
    build_pack_aware_kickstart_prelude,
    build_pack_aware_screen_observation_contract,
    build_pack_aware_task_execution_contract,
)
from shared.tool_packs import (
    filter_openai_tools_by_enabled_packs,
    filter_tools_by_enabled_packs,
    tools_for_enabled_packs,
)


STEERING_BETA_ENV = "EMPLO_APP_STEERING_BETA_ENABLED"


def _kickstart_prelude(enabled_tool_packs) -> list[dict[str, str]]:
    return build_pack_aware_kickstart_prelude(enabled_tool_packs)


def _task_execution_contract(session: Any, enabled_tool_packs) -> dict[str, str]:
    return build_pack_aware_task_execution_contract(
        enabled_tool_packs,
        task_board_internal_tool_name=TASK_BOARD_INTERNAL_TOOL_NAME,
        task_board_enabled=bool(get_active_task_board(session)),
        workspace_path=str(getattr(session, "workspace", "") or ""),
    )


def _conversational_turn_guard() -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "CONVERSATIONAL STYLE NOTE:\n"
            "- All enabled tools remain available on this turn.\n"
            "- For greetings, acknowledgements, thanks, or light conversation, answer directly without forcing unnecessary tool use.\n"
            "- If the user asks about the current workspace, files, browser, desktop, or any other state that requires observation, use the relevant enabled tools instead of claiming they are unavailable.\n"
            "- AGENTS.md, SOUL.md, USER.md, TOOLS.md, and MEMORY.md are already injected when available. If asked about them, answer from injected context instead of calling file tools for those filenames.\n"
            "- Do not read MEMORY.md just to begin work. Touch memory only when you are intentionally saving durable reusable information.\n"
            "- For desktop launches and other major desktop actions, treat the action as an attempt until visual verification confirms the resulting state.\n"
            "- Keep simple conversation concise, but do not hide enabled capabilities from the model."
        ),
    }


def _screen_observation_contract(enabled_tool_packs) -> dict[str, str]:
    return build_pack_aware_screen_observation_contract(enabled_tool_packs)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_interrupt_policy(policy: str) -> str:
    normalized = (policy or "none").strip().lower()
    return normalized if normalized in {"none", "steer_now", "after_tool"} else "none"


def _steering_beta_enabled(session: Any) -> bool:
    env_value = os.getenv(STEERING_BETA_ENV)
    if env_value is not None and env_value.strip():
        return _truthy(env_value)

    workspace = Path(getattr(session, "workspace", Path.cwd()))
    config = get_live_config(workspace / "config.json")
    return bool(config.get("channels.app.steering_beta", False))


def _publish_app_message_sync(
    session: Any,
    *,
    session_id: Optional[str],
    message: Dict[str, Any],
) -> None:
    user_id = getattr(session, "user_id", None)
    if user_id is None or not session_id:
        return

    get_channel_sync_hub().publish(
        user_id=user_id,
        event={
            "type": "user_message",
            "session_id": session_id,
            "origin_channel": message.get("channel"),
            "source_client_id": message.get("source_client_id"),
            "payload": {
                "message": message,
                "text": message.get("content", ""),
            },
        },
    )


async def _request_app_steering(
    session: Any,
    *,
    user_message: str,
    source_format: str,
    interrupt_policy: str,
    source_client_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    policy = _normalize_interrupt_policy(interrupt_policy)
    if policy == "none" or not _steering_beta_enabled(session):
        return None

    async with session.lock:
        if not session.is_processing:
            return None

        timestamp = datetime.now().isoformat()
        display_label = "App Voice Steering" if source_format == "app_voice_transcript" else "App Steering"
        session.last_user_message = user_message
        steering_message = {
            "role": "user",
            "content": user_message,
            "timestamp": timestamp,
            "channel": "app",
            "source_format": source_format,
            "display_label": display_label,
            "interrupt_policy": policy,
            "steering_beta": True,
            "source_client_id": source_client_id,
        }
        session.chat_history.append(steering_message)

        if hasattr(session, "queue_interrupt"):
            session.queue_interrupt(user_message, deferred=(policy == "after_tool"))
        else:
            session.should_interrupt = True
            session.interrupt_message = user_message

        session.save_session()
        current_session_id = session.session_manager.get_current_session_id() if getattr(session, "session_manager", None) else None
        _publish_app_message_sync(
            session,
            session_id=current_session_id,
            message=steering_message,
        )

    return {
        "ok": True,
        "busy": False,
        "steering": True,
        "session_id": current_session_id,
        "assistant_text": "",
        "steering_policy": policy,
        "steering_status": "queued" if policy == "after_tool" else "armed",
        "context_compressed": False,
        "context_compaction": None,
    }


async def run_app_chat_turn(
    session: Any,
    *,
    user_message: str,
    source_format: str = "app_text",
    interrupt_policy: str = "none",
    source_client_id: Optional[str] = None,
    log_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    steering_result = await _request_app_steering(
        session,
        user_message=user_message,
        source_format=source_format,
        interrupt_policy=interrupt_policy,
        source_client_id=source_client_id,
    )
    if steering_result is not None:
        return steering_result

    display_label = "App Voice" if source_format == "app_voice_transcript" else "App"
    reservation = await begin_chat_turn(
        session,
        user_message=user_message,
        user_message_payload={
            "channel": "app",
            "source_format": source_format,
            "display_label": display_label,
            "source_client_id": source_client_id,
        },
    )
    if reservation.busy:
        return {
            "ok": False,
            "busy": True,
            "session_id": reservation.session_id,
            "assistant_text": "",
        }

    screen_observation_turn = is_screen_observation_message(user_message)
    task_like_turn = screen_observation_turn or is_task_like_message(user_message)
    active_tool_packs = list(
        getattr(session, "_active_tool_packs_for_current_run", None)
        or getattr(session, "enabled_tool_packs", [])
        or []
    )
    prelude_messages = []
    if task_like_turn and len(session.chat_history) <= 3:
        prelude_messages.extend(_kickstart_prelude(active_tool_packs))

    system_messages = []
    if screen_observation_turn:
        system_messages.append(_screen_observation_contract(active_tool_packs))
    system_messages.append(_task_execution_contract(session, active_tool_packs))
    if not task_like_turn:
        system_messages.append(_conversational_turn_guard())
    session.current_turn_allowed_tool_names = tools_for_enabled_packs(active_tool_packs)
    session.current_turn_allowed_tool_definitions = filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, active_tool_packs)

    try:
        result = await run_reserved_chat_turn(
            session,
            reservation,
            prompt_builder=build_unified_system_prompt,
            tool_handlers_builder=get_auto_mode_tool_handlers,
            extra_tools_builder=(
                lambda runtime_session: filter_openai_tools_by_enabled_packs(
                    merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS),
                    getattr(runtime_session, "_active_tool_packs_for_current_run", None)
                    or getattr(runtime_session, "enabled_tool_packs", [])
                    or [],
                )
            ),
            system_messages=system_messages,
            prelude_messages=prelude_messages,
            assistant_message_payload={
                "channel": "app",
                "source_format": "app_response",
                "display_label": "App",
                "source_client_id": source_client_id,
            },
            event_sink=log_callback,
            initialize_single_agent=lambda loop: session.init_single_agent(None, loop),
            assistant_content_transform=lambda response: (
                ThinkingModeVisualizer.extract_thinking_content(response)[0]
                if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant)
                else response
            ),
        )
    finally:
        session.current_turn_allowed_tool_names = None
        session.current_turn_allowed_tool_definitions = []
    thinking_content = None
    if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant):
        _, thinking_content = ThinkingModeVisualizer.extract_thinking_content(result.raw_response)

    return {
        "ok": result.ok,
        "busy": result.busy,
        "steering": False,
        "session_id": result.session_id,
        "assistant_text": result.assistant_text,
        "raw_response": result.raw_response,
        "thinking_content": thinking_content,
        "duration_seconds": result.duration_seconds,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "context_compressed": bool(reservation.context_compressed or result.context_compressed),
        "context_compaction": result.context_compaction or reservation.context_compaction,
    }
