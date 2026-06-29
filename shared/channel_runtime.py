from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic

from bot_core.hooks import HookEvent, HookType
from cli.agent_tools.loop import LoopResult, run_tool_loop
from cli.tui_constants import MODEL_CONFIGS
from shared.channel_sync import get_channel_sync_hub
from shared.proactive_planner_contract import (
    build_pending_planner_contract,
    contract_system_message,
    record_planner_contract,
)
from shared.proactive_runtime import install_background_process_hooks
from shared.security_policy import redact_json, redact_text
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
    archive_active_task_board,
    before_model_turn_messages,
    completed_task_board_views,
    finalize_task_board_turn,
    get_active_task_board,
    get_display_task_board,
    handle_tool_result,
    note_user_turn,
    task_board_view,
)
from shared.workspace_recovery import ensure_session_workspace_ready_for_task


EventSink = Callable[[Dict[str, Any]], Any]
PromptBuilder = Callable[[Any, str, str, str], str]
ToolHandlersBuilder = Callable[[Any], Dict[str, Callable[[Dict[str, Any]], Any]]]
ExtraToolsBuilder = Callable[[Any], List[Dict[str, Any]]]
SingleAgentInitializer = Callable[[asyncio.AbstractEventLoop], None]
AssistantContentTransform = Callable[[str], str]

try:
    from shared import channel_artifacts as _channel_artifacts
    from shared import channel_planner as _channel_planner
    from shared import channel_runtime_events as _channel_events
except ImportError:
    import channel_artifacts as _channel_artifacts
    import channel_planner as _channel_planner
    import channel_runtime_events as _channel_events

_CHANNEL_PLANNER_NAMES = (
    "_collapse_for_verifier",
    "_extract_json_object",
    "_desktop_window_context_message",
    "_task_contract_context_message",
    "_planner_verifier_system_prompt",
    "_planner_verifier_payload",
    "_coding_task_requires_strict_retry",
    "_preserved_task_objective",
    "_planner_model_for_final_verifier",
    "_planner_final_completion",
    "_planner_contract_completion",
    "_run_parallel_planner_contract",
    "_planner_final_verdict",
)
for _channel_name in _CHANNEL_PLANNER_NAMES:
    globals()[_channel_name] = getattr(_channel_planner, _channel_name)
_channel_planner._planner_final_completion = lambda *args, **kwargs: _planner_final_completion(*args, **kwargs)

_CHANNEL_EVENT_NAMES = (
    "merge_openai_tools",
    "current_session_id",
    "compact_session_history",
    "_publish_compaction_status",
    "_compaction_metadata",
    "_emit_event",
    "_publish_sync_event",
    "_message_sync_event",
    "_turn_sync_event",
    "_task_board_sync_event",
    "_timeline_sync_event",
    "_append_and_publish_timeline_event",
    "_memory_context",
    "_build_file_context",
)
for _channel_name in _CHANNEL_EVENT_NAMES:
    globals()[_channel_name] = getattr(_channel_events, _channel_name)
_channel_events.get_channel_sync_hub = lambda: get_channel_sync_hub()

_CHANNEL_ARTIFACT_NAMES = (
    "_artifact_store_for_session",
    "_sanitize_artifact_metadata",
    "_sanitize_runtime_event_value",
    "_artifact_summary_payload",
    "_publish_artifact_created",
    "_workspace_relative_text",
    "_resolve_workspace_path",
    "_track_mutated_file_path",
    "_track_used_file_if_already_mirrored",
    "_command_output_text",
    "_artifact_preview_for_command",
    "_safe_slug",
    "_preview_text",
    "_serialize_search_text",
    "_artifact_text_for_browser_observation",
    "_artifact_text_for_ocr",
    "_capture_tool_artifact_ids",
    "_safe_command_filename",
    "_snapshot_touched_file_artifact_ids",
)
for _channel_name in _CHANNEL_ARTIFACT_NAMES:
    globals()[_channel_name] = getattr(_channel_artifacts, _channel_name)


def _stringify_tool_result_for_fallback(tool_result: Any, *, limit: int = 700) -> str:
    if isinstance(tool_result, dict):
        for key in (
            "description",
            "vision_summary",
            "summary",
            "plain_text",
            "text",
            "stdout",
            "output",
            "message",
            "error",
        ):
            value = str(tool_result.get(key) or "").strip()
            if value:
                return value[:limit]
        items = tool_result.get("items")
        if isinstance(items, list):
            if not items:
                return "No items were returned."
            labels: List[str] = []
            for item in items[:12]:
                if isinstance(item, dict):
                    labels.append(str(item.get("name") or item.get("path") or item.get("id") or item).strip())
                else:
                    labels.append(str(item).strip())
            labels = [item for item in labels if item]
            suffix = "" if len(items) <= len(labels) else f" and {len(items) - len(labels)} more"
            return f"Items: {', '.join(labels)}{suffix}."[:limit]
        try:
            return json.dumps(tool_result, ensure_ascii=False, default=str)[:limit]
        except Exception:
            return str(tool_result)[:limit]
    return str(tool_result or "").strip()[:limit]


def _fallback_final_from_tool_events(tool_events: List[Dict[str, Any]]) -> str:
    visible_events = [
        event
        for event in tool_events
        if str(event.get("tool_name") or "").strip()
    ]
    if not visible_events:
        return ""
    last = visible_events[-1]
    tool_name = str(last.get("tool_name") or "tool").strip()
    result_text = _stringify_tool_result_for_fallback(last.get("tool_result")).strip()
    if result_text:
        return f"I ran `{tool_name}`. {result_text}"
    return f"I ran `{tool_name}`, but it did not return any displayable output."


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

        user_id = int(getattr(session, "sync_user_id", None) or getattr(session, "user_id", 0) or 0)
        if user_id:
            workspace_preflight = ensure_session_workspace_ready_for_task(
                session=session,
                user_id=user_id,
                user_message=user_message,
                metadata={
                    "channel": payload.get("channel"),
                    "source_format": payload.get("source_format"),
                    "display_label": payload.get("display_label"),
                    "source_client_id": payload.get("source_client_id"),
                    "requires_workspace_write": payload.get("requires_workspace_write"),
                    "requires_workspace_access": payload.get("requires_workspace_access"),
                },
            )
            if not workspace_preflight.ok:
                append_timeline_event(
                    session,
                    event=create_timeline_event(
                        kind="workspace_reconnect_required",
                        title="Workspace Needs Reconnection",
                        content=workspace_preflight.message,
                        tone="warning",
                        metadata=workspace_preflight.to_dict(),
                    ),
                )
                session.save_session()
                _publish_sync_event(
                    session,
                    {
                        "type": "workspace_reconnect_required",
                        "session_id": current_session_id(session),
                        "payload": workspace_preflight.to_dict(),
                    },
                )
                raise RuntimeError(workspace_preflight.message)
            if workspace_preflight.action == "restored_managed_workspace":
                append_timeline_event(
                    session,
                    event=create_timeline_event(
                        kind="workspace_restored",
                        title="Workspace Restored",
                        content=f"Restored cloud-known workspace files to {workspace_preflight.restored_path}.",
                        tone="info",
                        metadata=workspace_preflight.to_dict(),
                    ),
                )

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
        planner_contract = build_pending_planner_contract(user_message)
        if planner_contract.get("action") in {"pending", "inject"}:
            setattr(session, "proactive_planner_contract", planner_contract)
            setattr(session, "proactive_planner_contract_injected", False)
            setattr(session, "proactive_planner_contract_version", 0)
            setattr(session, "proactive_planner_contract_user_message", user_message)
        else:
            setattr(session, "proactive_planner_contract", None)
            setattr(session, "proactive_planner_contract_injected", True)
            setattr(session, "proactive_planner_contract_version", 0)
            setattr(session, "proactive_planner_contract_user_message", user_message)

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
        artifact_store = _artifact_store_for_session(session, session_id=reservation.session_id)
        touched_file_paths: set[Path] = set()
        turn_artifact_ids: List[str] = []
        tool_events_this_turn: List[Dict[str, Any]] = []
        file_snapshots_flushed = False

        def _schedule_emit(event: Dict[str, Any]) -> None:
            if not event_sink:
                return
            try:
                asyncio.run_coroutine_threadsafe(_emit_event(event_sink, event), running_loop)
            except RuntimeError:
                pass

        planner_contract_task: Optional[asyncio.Task[None]] = None
        planner_user_message = str(getattr(session, "proactive_planner_contract_user_message", "") or getattr(session, "last_user_message", "") or "")
        pending_planner_contract = getattr(session, "proactive_planner_contract", None)
        if isinstance(pending_planner_contract, dict) and pending_planner_contract.get("action") == "pending":
            planner_contract_task = asyncio.create_task(
                _run_parallel_planner_contract(
                    session,
                    user_message=planner_user_message,
                    session_id=reservation.session_id,
                    turn_id=str(reservation.task_id),
                    schedule_emit=_schedule_emit,
                )
            )

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
                    save_session=True,
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
                response_buffer.append(redact_text(text))

        def begin_stream_func() -> None:
            response_buffer.clear()

        def append_stream_func(text: str) -> None:
            safe_text = redact_text(text)
            response_buffer.append(safe_text)
            _schedule_emit({"type": "assistant_delta", "delta": safe_text})

        def append_reasoning_func(text: str) -> None:
            if not str(text or "").strip():
                return
            _schedule_emit({"type": "reasoning_delta", "delta": text})

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
            task_messages = list(before_model_turn_messages(session))
            task_contract_context = _task_contract_context_message(session)
            desktop_context = _desktop_window_context_message(session)
            planner_context_messages: List[Dict[str, str]] = []
            planner_contract = getattr(session, "proactive_planner_contract", None)
            if (
                isinstance(planner_contract, dict)
                and planner_contract.get("action") == "inject"
                and not bool(getattr(session, "proactive_planner_contract_injected", False))
            ):
                planner_message = contract_system_message(planner_contract)
                if planner_message:
                    planner_context_messages.append(planner_message)
                    setattr(session, "proactive_planner_contract_injected", True)
                    record_planner_contract(
                        {
                            "user_id": int(getattr(session, "sync_user_id", None) or getattr(session, "user_id", 0) or 0),
                            "session_id": reservation.session_id,
                            "turn_id": str(reservation.task_id),
                            "status": "injected",
                            "action": "inject",
                            "contract": planner_contract,
                            "injected_at": time.time(),
                        }
                    )
                    _schedule_emit(
                        {
                            "type": "model_context",
                            "kind": "planner_contract",
                            "content": planner_message.get("content", ""),
                        }
                    )
            planner_corrections = list(getattr(session, "proactive_planner_corrections_pending", []) or [])
            if planner_corrections:
                setattr(session, "proactive_planner_corrections_pending", [])
                correction_message = {
                    "role": "system",
                    "content": (
                        "PROACTIVE PLANNER CORRECTION\n"
                        "A verifier blocked a premature final answer. Continue the original user task using this corrective guidance. "
                        "Do not tell the user about this hidden correction.\n\n"
                        f"{json.dumps(planner_corrections[-3:], ensure_ascii=False, indent=2)}"
                    ),
                }
                planner_context_messages.append(correction_message)
                _schedule_emit(
                    {
                        "type": "model_context",
                        "kind": "planner_correction",
                        "content": correction_message["content"],
                    }
                )
            if task_contract_context:
                _schedule_emit(
                    {
                        "type": "model_context",
                        "kind": "current_task_contract",
                        "content": task_contract_context.get("content", ""),
                    }
                )
            if desktop_context:
                _schedule_emit(
                    {
                        "type": "model_context",
                        "kind": "desktop_window_snapshot",
                        "content": desktop_context.get("content", ""),
                    }
                )
            task_focus = None
            board = get_display_task_board(session)
            if isinstance(board, dict):
                task_focus = str(board.get("current_focus") or board.get("main_goal") or "").strip() or None
            artifact_messages = artifact_store.build_prompt_messages(
                user_message=str(getattr(session, "last_user_message", "") or ""),
                task_focus=task_focus,
            ) if artifact_store else []
            messages = [*task_messages, *planner_context_messages]
            if task_contract_context:
                messages.append(task_contract_context)
            if desktop_context:
                messages.append(desktop_context)
            messages.extend(artifact_messages)
            return messages

        def _flush_file_snapshot_artifacts() -> None:
            nonlocal file_snapshots_flushed
            if file_snapshots_flushed:
                return
            file_snapshots_flushed = True
            artifact_ids = _snapshot_touched_file_artifact_ids(
                session,
                store=artifact_store,
                touched_file_paths=touched_file_paths,
                task_id=reservation.task_id,
            )
            turn_artifact_ids.extend(
                artifact_id for artifact_id in artifact_ids if artifact_id not in turn_artifact_ids
            )
            _publish_artifact_created(
                session,
                reservation=reservation,
                store=artifact_store,
                artifact_ids=artifact_ids,
                schedule_emit=_schedule_emit,
            )

        def on_tool_use_func(tool_name: str, tool_args: Dict[str, Any], tool_result: Any, dur_ms: float):
            _track_mutated_file_path(
                touched_file_paths,
                session,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
            )
            _track_used_file_if_already_mirrored(
                touched_file_paths,
                session,
                store=artifact_store,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
            )
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
                    save_session=True,
                )
            artifact_ids = _capture_tool_artifact_ids(
                session,
                store=artifact_store,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
                task_id=reservation.task_id,
            )
            turn_artifact_ids.extend(
                artifact_id for artifact_id in artifact_ids if artifact_id not in turn_artifact_ids
            )
            event_tool_args = _sanitize_runtime_event_value(tool_args)
            event_tool_result = _sanitize_runtime_event_value(tool_result)
            tool_events_this_turn.append(
                {
                    "tool_name": tool_name,
                    "tool_args": event_tool_args,
                    "tool_result": event_tool_result,
                    "duration_ms": dur_ms,
                }
            )
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="tool_use",
                    session_id=reservation.session_id,
                    payload={
                        "tool_name": tool_name,
                        "tool_args": event_tool_args,
                        "tool_result": event_tool_result,
                        "duration_ms": dur_ms,
                        "artifact_ids": artifact_ids,
                    },
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit(
                {
                    "type": "tool_use",
                    "tool_name": tool_name,
                    "tool_args": event_tool_args,
                    "tool_result": event_tool_result,
                    "duration_ms": dur_ms,
                    "artifact_ids": artifact_ids,
                }
            )
            _publish_artifact_created(
                session,
                reservation=reservation,
                store=artifact_store,
                artifact_ids=artifact_ids,
                schedule_emit=_schedule_emit,
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

        def on_auto_continue_func(payload: Dict[str, Any]) -> None:
            safe_payload = dict(payload or {})
            safe_payload["internal"] = True
            safe_payload["visibility"] = "internal"
            action = str(safe_payload.get("action") or "allow")
            reason = str(safe_payload.get("reason") or "planner_verdict")
            preview = str(safe_payload.get("candidate_final_preview") or "").strip()
            event_content = f"{action}: {reason}"
            if preview:
                event_content = f"{event_content}\nCandidate final: {_collapse_for_verifier(preview, limit=700)}"
            _append_and_publish_timeline_event(
                session,
                event=create_timeline_event(
                    kind="runtime",
                    title="Planner verifier",
                    content=event_content,
                    tone="warn" if action == "continue" else "neutral",
                    channel=reservation.event_meta.get("channel"),
                    source_format=reservation.event_meta.get("source_format"),
                    metadata=safe_payload,
                ),
                event_meta=reservation.event_meta,
                save_session=True,
            )
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="auto_continue",
                    session_id=reservation.session_id,
                    payload=safe_payload,
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit({"type": "auto_continue", **safe_payload})
            if action == "continue":
                correction = {
                    "reason": reason,
                    "failed_obligation": safe_payload.get("failed_obligation"),
                    "evidence_gap": safe_payload.get("evidence_gap"),
                    "retry_instruction": safe_payload.get("retry_instruction"),
                    "continuation_instruction": safe_payload.get("continuation_instruction"),
                    "must_use_tool": bool(safe_payload.get("must_use_tool")),
                }
                pending = list(getattr(session, "proactive_planner_corrections_pending", []) or [])
                pending.append({key: value for key, value in correction.items() if value not in (None, "")})
                setattr(session, "proactive_planner_corrections_pending", pending[-5:])
                all_corrections = list(getattr(session, "proactive_planner_corrections", []) or [])
                all_corrections.append(pending[-1])
                setattr(session, "proactive_planner_corrections", all_corrections[-20:])
                record_planner_contract(
                    {
                        "user_id": int(getattr(session, "sync_user_id", None) or getattr(session, "user_id", 0) or 0),
                        "session_id": reservation.session_id,
                        "turn_id": str(reservation.task_id),
                        "status": "correction_added",
                        "action": "inject",
                        "contract": getattr(session, "proactive_planner_contract", None) or {},
                        "corrections": all_corrections[-20:],
                    }
                )

        def judge_final_candidate_func(payload: Dict[str, Any]) -> Dict[str, Any]:
            payload = dict(payload or {})
            planner_contract = getattr(session, "proactive_planner_contract", None) or {}
            if isinstance(planner_contract, dict) and planner_contract.get("action") == "pending":
                planner_contract = planner_contract.get("fallback_contract") or planner_contract
            payload.setdefault("planner_contract", planner_contract)
            return _planner_final_verdict(session, payload)

        callbacks = {
            "log": log_func,
            "log_inline": log_inline_func,
            "begin_stream": begin_stream_func,
            "append_stream": append_stream_func,
            "append_reasoning": append_reasoning_func,
            "finish_stream": finish_stream_func,
            "update_status": update_status_func,
            "before_model_turn": before_model_turn_func,
            "on_tool_use": on_tool_use_func,
            "on_auto_continue": on_auto_continue_func,
            "judge_final_candidate": judge_final_candidate_func,
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

        active_task_board = get_active_task_board(session)
        if getattr(session, "tool_executor", None) and tool_handlers_builder:
            handlers = dict(tool_handlers_builder(session))
            if active_task_board:
                handlers[TASK_BOARD_INTERNAL_TOOL_NAME] = lambda args: apply_task_board_failure_report(session, args)
            session.tool_executor.custom_tool_handlers = handlers
        elif getattr(session, "tool_executor", None):
            session.tool_executor.custom_tool_handlers = (
                {TASK_BOARD_INTERNAL_TOOL_NAME: lambda args: apply_task_board_failure_report(session, args)}
                if active_task_board
                else {}
            )

        extra_tools = extra_tools_builder(session) if extra_tools_builder else None
        if active_task_board:
            extra_tools = merge_openai_tools(extra_tools, [TASK_BOARD_FAILURE_REPORT_TOOL])
        base_tools = list(getattr(session, "current_turn_allowed_tool_definitions", []) or [])

        _publish_sync_event(
            session,
            _turn_sync_event(
                event_type="status",
                session_id=reservation.session_id,
                payload={"message": "running", "run_state": "running"},
                event_meta=reservation.event_meta,
            ),
        )
        await _emit_event(event_sink, {"type": "status", "message": "running"})
        start_time = time.time()
        loop = asyncio.get_running_loop()
        if getattr(session, "tool_executor", None):
            workspace_for_security = str(getattr(session, "workspace", "") or "")
            session.tool_executor.security_context_provider = lambda: {
                "permission_mode": getattr(session, "security_permission_mode", "standard"),
                "workspace_path": workspace_for_security,
                "workspace_binding_status": getattr(session, "workspace_binding_status", None),
                "workspace_write_enabled": (
                    None
                    if not workspace_for_security
                    else Path(workspace_for_security).expanduser().exists()
                ),
                "surface": reservation.event_meta.get("channel") or "app",
                "session_id": current_session_id(session),
                "identity_id": getattr(session, "fleet_identity_id", None),
            }
            install_background_process_hooks(session, event_loop=loop)
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
                base_tools=base_tools,
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
        assistant_text = redact_text(assistant_text)
        if not assistant_text.strip() and tool_events_this_turn:
            assistant_text = redact_text(_fallback_final_from_tool_events(tool_events_this_turn))
        finalized_task_board = finalize_task_board_turn(session, assistant_text or "")
        post_compaction_result = None
        _flush_file_snapshot_artifacts()
        if assistant_text:
            assistant_message = {
                "role": "assistant",
                "content": assistant_text,
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "artifact_ids": list(turn_artifact_ids),
                    **({"generated_from_tool_result": True} if not str(raw_response or "").strip() and tool_events_this_turn else {}),
                },
            }
            assistant_message.update(assistant_message_payload or {})
            if isinstance(assistant_message.get("metadata"), dict):
                merged_ids = list(assistant_message["metadata"].get("artifact_ids") or [])
                for artifact_id in turn_artifact_ids:
                    if artifact_id not in merged_ids:
                        merged_ids.append(artifact_id)
                assistant_message["metadata"]["artifact_ids"] = merged_ids
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
                        "artifact_ids": list(turn_artifact_ids),
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
            raw_response=redact_text(raw_response),
            duration_seconds=duration,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            context_compressed=bool(post_compaction_result and post_compaction_result.applied),
            context_compaction=_compaction_metadata(post_compaction_result) if post_compaction_result and post_compaction_result.applied else None,
        )
    except Exception:
        _flush_file_snapshot_artifacts()
        interrupted_board = archive_active_task_board(
            session,
            status="interrupted",
            summary="The managed task stopped unexpectedly before it could finish.",
        )
        if interrupted_board:
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=current_session_id(session),
                    board=None,
                    completed_boards=completed_task_board_views(session),
                    summary=interrupted_board.get("completion_summary"),
                    event_meta=reservation.event_meta,
                ),
            )
        raise
    finally:
        _flush_file_snapshot_artifacts()
        async with session.lock:
            if session.current_task_id == task_id:
                session.is_processing = False
                session.save_session()
        _publish_sync_event(
            session,
            _turn_sync_event(
                event_type="status",
                session_id=current_session_id(session),
                payload={"message": "ready", "run_state": "idle"},
                event_meta=reservation.event_meta,
            ),
        )
