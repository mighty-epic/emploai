from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from single_agent.agent import AGENT_TOOLS
from telegram_bot.telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)

from shared import begin_chat_turn, merge_openai_tools, run_reserved_chat_turn
from shared.live_config import get_live_config


STEERING_BETA_ENV = "EMPLO_APP_STEERING_BETA_ENABLED"


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


async def _request_app_steering(
    session: Any,
    *,
    user_message: str,
    source_format: str,
    interrupt_policy: str,
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
        session.chat_history.append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": timestamp,
                "channel": "app",
                "source_format": source_format,
                "display_label": display_label,
                "interrupt_policy": policy,
                "steering_beta": True,
            }
        )

        if hasattr(session, "queue_interrupt"):
            session.queue_interrupt(user_message, deferred=(policy == "after_tool"))
        else:
            session.should_interrupt = True
            session.interrupt_message = user_message

        session.save_session()

    return {
        "ok": True,
        "busy": False,
        "steering": True,
        "session_id": session.session_manager.get_current_session_id() if getattr(session, "session_manager", None) else None,
        "assistant_text": "",
        "steering_policy": policy,
        "steering_status": "queued" if policy == "after_tool" else "armed",
    }


async def run_app_chat_turn(
    session: Any,
    *,
    user_message: str,
    source_format: str = "app_text",
    interrupt_policy: str = "none",
    log_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    steering_result = await _request_app_steering(
        session,
        user_message=user_message,
        source_format=source_format,
        interrupt_policy=interrupt_policy,
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
        },
    )
    if reservation.busy:
        return {
            "ok": False,
            "busy": True,
            "session_id": reservation.session_id,
            "assistant_text": "",
        }

    system_messages = [
        {
            "role": "system",
            "content": (
                "You are operating through the EmploAI mobile app channel. "
                "Prefer concise, stream-friendly replies and status updates that fit a phone UI."
            ),
        }
    ]

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
        assistant_message_payload={
            "channel": "app",
            "source_format": "app_system",
            "display_label": "App",
        },
        event_sink=log_callback,
        initialize_single_agent=lambda loop: session.init_single_agent(None, loop),
    )
    return {
        "ok": result.ok,
        "busy": result.busy,
        "steering": False,
        "session_id": result.session_id,
        "assistant_text": result.assistant_text,
        "duration_seconds": result.duration_seconds,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
    }
