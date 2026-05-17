from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic

from bot_core.hooks import HookEvent, HookType
from cli.agent_tools.loop import LoopResult, run_tool_loop
from cli.tui_constants import MODEL_CONFIGS
from shared.channel_sync import get_channel_sync_hub
from shared.session_timeline import (
    append_timeline_event,
    build_log_timeline_event,
    build_tool_timeline_event,
    create_timeline_event,
)
from shared.task_board import (
    TASK_BOARD_FAILURE_REPORT_TOOL,
    TASK_BOARD_INTERNAL_TOOL_NAME,
    apply_task_board_failure_report,
    before_model_turn_messages,
    completed_task_board_views,
    finalize_task_board_turn,
    get_active_task_board,
    get_display_task_board,
    handle_tool_result,
    note_user_turn,
    task_board_view,
)


EventSink = Callable[[Dict[str, Any]], Any]
PromptBuilder = Callable[[Any, str, str, str], str]
ToolHandlersBuilder = Callable[[Any], Dict[str, Callable[[Dict[str, Any]], Any]]]
ExtraToolsBuilder = Callable[[Any], List[Dict[str, Any]]]
SingleAgentInitializer = Callable[[asyncio.AbstractEventLoop], None]
AssistantContentTransform = Callable[[str], str]


@dataclass
class TurnReservation:
    busy: bool = False
    task_id: int = 0
    session_id: Optional[str] = None
    is_session_start: bool = False
    context_compressed: bool = False
    context_compaction: Optional[Dict[str, Any]] = None
    event_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedTurnResult:
    ok: bool = False
    busy: bool = False
    abandoned: bool = False
    session_id: Optional[str] = None
    assistant_text: str = ""
    raw_response: str = ""
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    context_compressed: bool = False
    context_compaction: Optional[Dict[str, Any]] = None


def merge_openai_tools(*tool_groups: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for group in tool_groups:
        for tool in group or []:
            func = tool.get("function", {})
            name = func.get("name")
            if not name or name in seen:
                continue
            merged.append(tool)
            seen.add(name)
    return merged


def current_session_id(session: Any) -> Optional[str]:
    if not getattr(session, "session_manager", None):
        return None
    return session.session_manager.get_current_session_id()


def compact_session_history(
    session: Any,
    *,
    reason: str = "manual",
    announce: bool = False,
    event_meta: Optional[Dict[str, Any]] = None,
):
    context_manager = getattr(session, "context_manager", None)
    if not context_manager:
        return None

    model_id = session.current_model or "claude-sonnet-4-5"
    result = context_manager.compact(
        session.chat_history,
        model_id,
        reason=reason,
    )
    if result.applied:
        session.chat_history = result.messages
        if hasattr(session, "message_id_map"):
            rebuilt_map: Dict[int, int] = {}
            for index, message in enumerate(session.chat_history):
                message_id = message.get("message_id")
                if message_id is not None:
                    rebuilt_map[message_id] = index
            session.message_id_map = rebuilt_map
        session.last_context_compaction = _compaction_metadata(result)
        if announce:
            _publish_compaction_status(session, result, event_meta=event_meta)
    return result


def _publish_compaction_status(session: Any, result: Any, *, event_meta: Optional[Dict[str, Any]] = None) -> None:
    if not result:
        return

    _append_and_publish_timeline_event(
        session,
        event=create_timeline_event(
            kind="compaction",
            title="Context Compaction",
            content=result.message,
            tone="accent",
            channel=(event_meta or {}).get("channel"),
            source_format=(event_meta or {}).get("source_format"),
            metadata=_compaction_metadata(result),
        ),
        event_meta=event_meta,
    )
    _publish_sync_event(
        session,
        _turn_sync_event(
            event_type="status",
            session_id=current_session_id(session),
            payload={"message": result.message},
            event_meta=event_meta or {},
        ),
    )


def _compaction_metadata(result: Any) -> Dict[str, Any]:
    payload = dict(result.to_dict())
    payload.pop("messages", None)
    return payload


async def _emit_event(event_sink: Optional[EventSink], event: Dict[str, Any]) -> None:
    if not event_sink:
        return
    maybe = event_sink(event)
    if asyncio.iscoroutine(maybe):
        await maybe


def _publish_sync_event(session: Any, event: Dict[str, Any]) -> None:
    user_id = getattr(session, "user_id", None)
    if user_id is None:
        return
    get_channel_sync_hub().publish(user_id=user_id, event=event)


def _message_sync_event(
    *,
    event_type: str,
    session_id: Optional[str],
    message: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "type": event_type,
        "session_id": session_id,
        "origin_channel": message.get("channel"),
        "source_client_id": message.get("source_client_id"),
        "payload": {
            "message": message,
            "text": message.get("content", ""),
        },
    }


def _turn_sync_event(
    *,
    event_type: str,
    session_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    event_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = dict(event_meta or {})
    return {
        "type": event_type,
        "session_id": session_id,
        "origin_channel": meta.get("channel"),
        "source_client_id": meta.get("source_client_id"),
        "payload": payload or {},
    }


def _task_board_sync_event(
    *,
    session_id: Optional[str],
    board: Optional[Dict[str, Any]],
    completed_boards: Optional[List[Dict[str, Any]]] = None,
    summary: Optional[str],
    event_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _turn_sync_event(
        event_type="task_board",
        session_id=session_id,
        payload={
            "board": task_board_view(board),
            "completed_task_boards": list(completed_boards or []),
            "summary": summary or (board or {}).get("latest_summary"),
        },
        event_meta=event_meta,
    )


def _timeline_sync_event(
    *,
    session_id: Optional[str],
    event: Dict[str, Any],
    event_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _turn_sync_event(
        event_type="timeline_event",
        session_id=session_id,
        payload={"event": event},
        event_meta=event_meta,
    )


def _append_and_publish_timeline_event(
    session: Any,
    *,
    event: Dict[str, Any],
    event_meta: Optional[Dict[str, Any]] = None,
    save_session: bool = False,
) -> Dict[str, Any]:
    stored = append_timeline_event(session, event=event)
    if save_session:
        session.save_session()
    _publish_sync_event(
        session,
        _timeline_sync_event(
            session_id=current_session_id(session),
            event=stored,
            event_meta=event_meta,
        ),
    )
    return stored


def _memory_context(session: Any) -> str:
    if not getattr(session, "session_context", None):
        return ""
    if not getattr(session.session_context, "can_access_memory", False):
        return ""
    memory_manager = getattr(session, "memory_manager", None)
    if not memory_manager:
        return ""

    session_id = current_session_id(session)
    build_prompt_context = getattr(memory_manager, "build_prompt_context", None)
    if callable(build_prompt_context):
        return build_prompt_context(
            session_id=session_id,
            recent_days=7,
            recent_chars=3000,
            long_term_chars=4000,
        )

    get_long_term_context = getattr(memory_manager, "get_long_term_context", None)
    if callable(get_long_term_context):
        return get_long_term_context()
    return ""


def _build_file_context(pending_files: List[Dict[str, Any]]) -> str:
    if not pending_files:
        return ""

    safe_files: List[Dict[str, Any]] = []
    for item in pending_files:
        safe_item = dict(item)
        if "image_base64" in safe_item:
            safe_item["image_base64"] = "[omitted - stored]"
        safe_files.append(safe_item)

    file_context = json.dumps(safe_files, indent=2)
    if len(file_context) > 8000:
        file_context = file_context[:7800] + "\n... [truncated]"
    return file_context


async def begin_chat_turn(
    session: Any,
    *,
    user_message: str,
    user_message_payload: Optional[Dict[str, Any]] = None,
) -> TurnReservation:
    payload = dict(user_message_payload or {})

    async with session.lock:
        if session.is_processing:
            return TurnReservation(busy=True, session_id=current_session_id(session))

        session.current_task_id += 1
        task_id = session.current_task_id
        session.start_browser_task(task_id, user_message)
        session.should_interrupt = False
        session.is_processing = True

        timestamp = datetime.now().isoformat()
        message = {
            "role": "user",
            "content": user_message,
            "timestamp": timestamp,
        }
        message.update(payload)

        session.last_user_message = user_message
        session.chat_history.append(message)
        task_board_summary = note_user_turn(session, user_message)

        message_id = payload.get("message_id")
        if message_id is not None and hasattr(session, "message_id_map"):
            session.message_id_map[message_id] = len(session.chat_history) - 1

        is_session_start = len(session.chat_history) == 1
        if is_session_start:
            session.refresh_system_info()

        context_compressed = False
        context_compaction: Optional[Dict[str, Any]] = None
        if getattr(session, "context_manager", None):
            model_id = session.current_model or "claude-sonnet-4-5"
            if session.context_manager.needs_compression(session.chat_history, model_id):
                compaction_result = compact_session_history(session, reason="auto_pre_turn")
                if compaction_result and compaction_result.applied:
                    context_compressed = True
                    context_compaction = _compaction_metadata(compaction_result)
                    _publish_compaction_status(session, compaction_result)

        session.save_session()
        _publish_sync_event(
            session,
            _message_sync_event(
                event_type="user_message",
                session_id=current_session_id(session),
                message=message,
            ),
        )
        if task_board_summary:
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=current_session_id(session),
                    board=get_active_task_board(session),
                    completed_boards=completed_task_board_views(session),
                    summary=task_board_summary,
                    event_meta={
                        "channel": payload.get("channel"),
                        "source_format": payload.get("source_format"),
                        "display_label": payload.get("display_label"),
                        "source_client_id": payload.get("source_client_id"),
                    },
                ),
            )
        return TurnReservation(
            busy=False,
            task_id=task_id,
            session_id=current_session_id(session),
            is_session_start=is_session_start,
            context_compressed=context_compressed,
            context_compaction=context_compaction,
            event_meta={
                "channel": payload.get("channel"),
                "source_format": payload.get("source_format"),
                "display_label": payload.get("display_label"),
                "source_client_id": payload.get("source_client_id"),
            },
        )


async def run_reserved_chat_turn(
    session: Any,
    reservation: TurnReservation,
    *,
    prompt_builder: PromptBuilder,
    tool_handlers_builder: Optional[ToolHandlersBuilder] = None,
    extra_tools_builder: Optional[ExtraToolsBuilder] = None,
    system_messages: Optional[List[Dict[str, Any]]] = None,
    prelude_messages: Optional[List[Dict[str, Any]]] = None,
    assistant_message_payload: Optional[Dict[str, Any]] = None,
    event_sink: Optional[EventSink] = None,
    initialize_single_agent: Optional[SingleAgentInitializer] = None,
    assistant_content_transform: Optional[AssistantContentTransform] = None,
) -> SharedTurnResult:
    task_id = reservation.task_id
    raw_response = ""
    response_buffer: List[str] = []

    try:
        client, provider = session.get_client_for_model()
        if not client:
            raise RuntimeError(f"No API key configured for provider: {provider}")

        async with session.lock:
            pending_files = list(getattr(session, "pending_files", []))
            session.pending_files = []

        file_context = _build_file_context(pending_files)
        skills_index = ""
        active_skills_context = ""
        if getattr(session, "skill_registry", None):
            skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
            if getattr(session, "active_skills", None):
                active_skills_context = (
                    "\n\n# LOADED SPECIALIZED SKILLS\n"
                    f"{session.skill_registry.get_active_skills_context(session.active_skills)}"
                )

        memory_context = _memory_context(session)
        custom_system_prompt = prompt_builder(
            session,
            memory_context=memory_context,
            skills_index=skills_index,
            active_skills_context=active_skills_context,
        )

        messages: List[Dict[str, Any]] = [{"role": "system", "content": custom_system_prompt}]
        injected_messages = list(system_messages or [])
        if file_context:
            injected_messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"USER ATTACHMENTS (structured data):\n{file_context}",
                },
            )
        messages.extend(injected_messages)
        messages.extend(prelude_messages or [])
        messages.extend(
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in session.chat_history
        )

        running_loop = asyncio.get_running_loop()

        def _schedule_emit(event: Dict[str, Any]) -> None:
            if not event_sink:
                return
            try:
                asyncio.run_coroutine_threadsafe(_emit_event(event_sink, event), running_loop)
            except RuntimeError:
                pass

        def log_func(text: str) -> None:
            if text.strip() and getattr(session, "verbose_mode", False):
                _append_and_publish_timeline_event(
                    session,
                    event=build_log_timeline_event(
                        message=text,
                        channel=reservation.event_meta.get("channel"),
                        source_format=reservation.event_meta.get("source_format"),
                    ),
                    event_meta=reservation.event_meta,
                )
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="log",
                    session_id=reservation.session_id,
                    payload={"message": text},
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit({"type": "log", "message": text})

        def log_inline_func(text: str) -> None:
            if text.strip():
                response_buffer.append(text)

        def begin_stream_func() -> None:
            response_buffer.clear()

        def append_stream_func(text: str) -> None:
            response_buffer.append(text)
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="assistant_delta",
                    session_id=reservation.session_id,
                    payload={"delta": text},
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit({"type": "assistant_delta", "delta": text})

        def finish_stream_func() -> None:
            return None

        def update_status_func() -> None:
            return None

        def _emit_task_board(summary: Optional[str], board: Optional[Dict[str, Any]]) -> None:
            if not board and not summary:
                return
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=reservation.session_id,
                    board=board,
                    completed_boards=completed_task_board_views(session),
                    summary=summary,
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit(
                {
                    "type": "task_board",
                    "board": task_board_view(board),
                    "completed_task_boards": completed_task_board_views(session),
                    "summary": summary or (board or {}).get("latest_summary"),
                }
            )

        def before_model_turn_func(_turn_number: int, _messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
            return before_model_turn_messages(session)

        def on_tool_use_func(tool_name: str, tool_args: Dict[str, Any], tool_result: Any, dur_ms: float):
            if getattr(session, "verbose_mode", False):
                _append_and_publish_timeline_event(
                    session,
                    event=build_tool_timeline_event(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tool_result=tool_result,
                        duration_ms=dur_ms,
                        channel=reservation.event_meta.get("channel"),
                        source_format=reservation.event_meta.get("source_format"),
                    ),
                    event_meta=reservation.event_meta,
                )
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="tool_use",
                    session_id=reservation.session_id,
                    payload={
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_result": tool_result,
                        "duration_ms": dur_ms,
                    },
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit(
                {
                    "type": "tool_use",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_result": tool_result,
                    "duration_ms": dur_ms,
                }
            )
            prompt_messages: List[Dict[str, Any]] = []
            if tool_name == TASK_BOARD_INTERNAL_TOOL_NAME and isinstance(tool_result, dict):
                _emit_task_board(tool_result.get("summary"), get_display_task_board(session))
                prompt_messages = list(tool_result.get("prompt_messages") or [])
            else:
                task_effect = handle_tool_result(
                    session,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_result=tool_result,
                    channel=reservation.event_meta.get("channel"),
                )
                if task_effect.get("summary") or task_effect.get("created"):
                    _emit_task_board(task_effect.get("summary"), task_effect.get("board"))
                prompt_messages = list(task_effect.get("prompt_messages") or [])
            return prompt_messages

        callbacks = {
            "log": log_func,
            "log_inline": log_inline_func,
            "begin_stream": begin_stream_func,
            "append_stream": append_stream_func,
            "finish_stream": finish_stream_func,
            "update_status": update_status_func,
            "before_model_turn": before_model_turn_func,
            "on_tool_use": on_tool_use_func,
        }

        model_config = MODEL_CONFIGS.get(session.current_model, {})
        auto_provider = model_config.get("provider", "openai")
        auto_model_id = model_config.get("id", session.current_model)
        api_type = model_config.get("api", "chat")

        auto_client = client
        if auto_provider == "anthropic" and not getattr(session, "anthropic_client", None):
            api_key = session.config_manager.get_api_key("anthropic") or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("Claude requires API key")
            session.anthropic_client = Anthropic(api_key=api_key)
            auto_client = session.anthropic_client

        if not getattr(session, "single_agent", None):
            init = initialize_single_agent or (lambda loop: session.init_single_agent(None, loop))
            init(running_loop)

        if getattr(session, "tool_executor", None) and tool_handlers_builder:
            session.tool_executor.custom_tool_handlers = {
                **tool_handlers_builder(session),
                TASK_BOARD_INTERNAL_TOOL_NAME: lambda args: apply_task_board_failure_report(session, args),
            }
        elif getattr(session, "tool_executor", None):
            session.tool_executor.custom_tool_handlers = {
                TASK_BOARD_INTERNAL_TOOL_NAME: lambda args: apply_task_board_failure_report(session, args),
            }

        extra_tools = extra_tools_builder(session) if extra_tools_builder else None
        extra_tools = merge_openai_tools(extra_tools, [TASK_BOARD_FAILURE_REPORT_TOOL])

        _publish_sync_event(
            session,
            _turn_sync_event(
                event_type="status",
                session_id=reservation.session_id,
                payload={"message": "running"},
                event_meta=reservation.event_meta,
            ),
        )
        await _emit_event(event_sink, {"type": "status", "message": "running"})
        start_time = time.time()
        loop = asyncio.get_running_loop()
        result: LoopResult = await loop.run_in_executor(
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

        if session.current_task_id != task_id:
            return SharedTurnResult(
                ok=False,
                abandoned=True,
                session_id=current_session_id(session),
            )

        raw_response = result.content or "".join(response_buffer)
        assistant_text = assistant_content_transform(raw_response) if assistant_content_transform else raw_response
        finalized_task_board = finalize_task_board_turn(session, assistant_text or "")
        post_compaction_result = None
        if assistant_text:
            assistant_message = {
                "role": "assistant",
                "content": assistant_text,
                "timestamp": datetime.now().isoformat(),
            }
            assistant_message.update(assistant_message_payload or {})
            async with session.lock:
                session.chat_history.append(assistant_message)
                if getattr(session, "context_manager", None):
                    model_id = session.current_model or "claude-sonnet-4-5"
                    if session.context_manager.needs_compression(session.chat_history, model_id):
                        post_compaction_result = compact_session_history(session, reason="auto_post_turn")
                        if post_compaction_result and post_compaction_result.applied:
                            _publish_compaction_status(session, post_compaction_result)
                session.save_session()
            _publish_sync_event(
                session,
                {
                    **_message_sync_event(
                        event_type="assistant_final",
                        session_id=current_session_id(session),
                        message=assistant_message,
                    ),
                    "payload": {
                        "message": assistant_message,
                        "text": assistant_text,
                        "duration_seconds": time.time() - start_time,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "total_tokens": result.total_tokens,
                    },
                },
            )
        if finalized_task_board:
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=current_session_id(session),
                    board=finalized_task_board.get("board"),
                    completed_boards=finalized_task_board.get("completed_boards") or completed_task_board_views(session),
                    summary=finalized_task_board.get("summary"),
                    event_meta=reservation.event_meta,
                ),
            )
            await _emit_event(
                event_sink,
                {
                    "type": "task_board",
                    "board": task_board_view(finalized_task_board.get("board")),
                    "completed_task_boards": finalized_task_board.get("completed_boards") or completed_task_board_views(session),
                    "summary": finalized_task_board.get("summary"),
                },
            )

        duration = time.time() - start_time
        if assistant_text and getattr(session, "memory_manager", None):
            session.memory_manager.append_to_daily_log(
                f"User: {session.last_user_message[:200]}...\n\nAssistant: {assistant_text[:200]}...",
                "chat",
                session_id=current_session_id(session),
            )

        if assistant_text and getattr(session, "hook_manager", None):
            session.hook_manager.trigger(
                HookType.MESSAGE_PROCESSED,
                HookEvent.create(HookType.MESSAGE_PROCESSED, session.user_id, response=assistant_text),
            )

        if getattr(session, "analytics_tracker", None):
            session.analytics_tracker.track_llm_request(
                session.user_id,
                session.current_model,
                result.input_tokens,
                result.output_tokens,
                duration,
            )

        asyncio.get_running_loop().run_in_executor(None, session.auto_rename_session)

        return SharedTurnResult(
            ok=True,
            session_id=current_session_id(session),
            assistant_text=assistant_text,
            raw_response=raw_response,
            duration_seconds=duration,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            context_compressed=bool(post_compaction_result and post_compaction_result.applied),
            context_compaction=_compaction_metadata(post_compaction_result) if post_compaction_result and post_compaction_result.applied else None,
        )
    finally:
        async with session.lock:
            if session.current_task_id == task_id:
                session.is_processing = False
                session.save_session()
