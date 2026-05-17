from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from bot_core.ui_helpers import ThinkingModeVisualizer
from single_agent.tool_manifest import AGENT_TOOLS
from shared.channel_sync import get_channel_sync_hub
from telegram_bot.telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME

from shared import begin_chat_turn, merge_openai_tools, run_reserved_chat_turn
from shared.live_config import get_live_config


STEERING_BETA_ENV = "EMPLO_APP_STEERING_BETA_ENABLED"


def _kickstart_prelude() -> list[dict[str, str]]:
    return [
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


def _task_execution_contract() -> dict[str, str]:
    return {
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

    prelude_messages = []
    if len(session.chat_history) <= 3:
        prelude_messages.extend(_kickstart_prelude())

    system_messages = [_task_execution_contract()]

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
