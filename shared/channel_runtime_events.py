from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from shared.channel_sync import get_channel_sync_hub
from shared.security_policy import redact_json
from shared.session_timeline import append_timeline_event, create_timeline_event
from shared.task_board import task_board_view

EventSink = Callable[[Dict[str, Any]], Any]

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
    user_id = getattr(session, "sync_user_id", None)
    if user_id is None:
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
    live_config = getattr(session, "live_config", None)
    if live_config and live_config.get("memory.prompt_context_enabled", True) is False:
        return ""
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
        safe_item = redact_json(dict(item))
        if "image_base64" in safe_item:
            safe_item["image_base64"] = "[omitted - stored]"
        safe_files.append(safe_item)

    file_context = json.dumps(safe_files, indent=2)
    if len(file_context) > 8000:
        file_context = file_context[:7800] + "\n... [truncated]"
    return file_context
