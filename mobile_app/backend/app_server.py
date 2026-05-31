from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from bot_core.ui_helpers import ThinkingModeVisualizer
from cli.tui_constants import AVAILABLE_MODELS, MODEL_CONFIGS, MODEL_CONTEXT_SIZES
from mobile_app.backend.auth_store import AppAuthStore
from mobile_app.backend.models import (
    AgentActionResponse,
    AgentConfigureRequest,
    AgentOverviewView,
    AppUserProfile,
    ArtifactDetailView,
    ArtifactSummaryView,
    ChatSendRequest,
    ConfigEntryView,
    ConfigListResponse,
    ConfigUpdateRequest,
    CronFeedItemView,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    DeviceActionResponse,
    DevicePairCompleteRequest,
    DevicePairCompleteResponse,
    DevicePairStartRequest,
    DevicePairStartResponse,
    JobActionResponse,
    JobCreateRequest,
    JobDetailView,
    HeadlessConfigureRequest,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryNoteRequest,
    RealtimeServerEvent,
    RemoteAccountProfile,
    RemoteAuthLoginRequest,
    RemoteAuthLoginResponse,
    RemoteAuthRegisterRequest,
    RemoteDesktopSocketMessage,
    RemoteDesktopSyncEnvelope,
    RemoteDesktopView,
    RemoteMobileView,
    RemoteMobileSocketMessage,
    RemotePairCompleteRequest,
    RemotePairCompleteResponse,
    RemotePairStartRequest,
    RemotePairStartResponse,
    RemoteUserView,
    ScheduledJobView,
    ScreenCaptureView,
    SessionSearchRequest,
    SessionSearchResponse,
    SessionSearchResultView,
    SessionBotAssignmentRequest,
    SkillActivateRequest,
    SkillListResponse,
    SkillSummaryView,
    SkillValidationView,
    SessionDetailView,
    SessionHeadlessEligibilityRequest,
    SessionSummaryView,
    SubAgentListResponse,
    SubAgentSpawnRequest,
    SubAgentTaskView,
    TaskBoardArmRequest,
    TaskBoardArmResponse,
    TaskBoardResponse,
    TelegramBotConfigCreateRequest,
    TelegramBotConfigUpdateRequest,
    TelegramBotConfigView,
    TimelineEventAppendRequest,
    ToolPackUpdateRequest,
    TrustedDeviceView,
    UploadResponse,
    VoiceClientEvent,
    RuntimeOrchestratorView,
)
from mobile_app.backend.remote_control_runtime import get_remote_desktop_manager
from mobile_app.backend.remote_control_store import (
    REMOTE_PAIRING_TTL_SECONDS,
    REMOTE_SESSION_TTL_SECONDS,
    RemoteControlPlaneStore,
)
from shared.channel_events import publish_current_session_changed, publish_status_update
from shared.channel_sync import get_channel_sync_hub
from shared.live_config import get_live_config
from shared.channel_runtime import compact_session_history
from shared.task_board import (
    archive_active_task_board,
    completed_task_board_views,
    format_task_board_for_user,
    get_active_task_board,
    get_display_task_board,
    get_task_board_armed_next_turn,
    request_task_board_reassessment,
    recover_stale_task_board,
    task_board_view,
)
from single_agent.cron_scheduler import get_scheduler, parse_schedule_with_error
from telegram_bot.restart_runtime import exec_current_process

if TYPE_CHECKING:
    from bot_core.security import SecurityManager
    from mobile_app.backend.session_bridge import AppSessionBridge


APP_SECRET_ENV = "EMPLO_APP_SECRET"
PAIRING_SECRET_ENV = "EMPLO_APP_PAIRING_SECRET"
DEFAULT_PAIR_TTL_SECONDS = 60 * 30
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 180

_auth_store: Optional[AppAuthStore] = None
_remote_control_store: Optional[RemoteControlPlaneStore] = None
_security_manager: Optional[SecurityManager] = None
_security_manager_attempted = False
_server_thread: Optional[threading.Thread] = None
_server_started = False
logger = logging.getLogger(__name__)
_BASE64_KEYS = frozenset({"image_base64", "base64", "image_data", "data", "screenshot"})
_APP_RUNTIME_STATUS: Dict[str, Any] = {
    "startup_state": "idle",
    "startup_error": None,
    "startup_error_detail": None,
    "last_runtime_error": None,
    "last_runtime_error_detail": None,
    "last_runtime_error_at": None,
}
_SESSION_SEARCH_CACHE_LOCK = threading.Lock()
_SESSION_SEARCH_CACHE: Dict[int, Dict[str, Dict[str, Any]]] = {}
_SEARCH_NORMALIZE_RE = re.compile(r"[\W_]+", re.UNICODE)
_SESSION_SEARCH_LIMIT_MAX = 100


def _capture_runtime_status() -> Dict[str, Any]:
    from mobile_app.backend.capture_runtime import get_capture_runtime_status

    return get_capture_runtime_status()


def _capture_screen_snapshot(*, max_width: Optional[int] = None, jpeg_quality: Optional[int] = None):
    from mobile_app.backend.capture_runtime import capture_screen_snapshot

    if max_width is None and jpeg_quality is None:
        return capture_screen_snapshot()
    kwargs: Dict[str, Any] = {}
    if max_width is not None:
        kwargs["max_width"] = max_width
    if jpeg_quality is not None:
        kwargs["jpeg_quality"] = jpeg_quality
    return capture_screen_snapshot(**kwargs)


def _voice_runtime_status() -> Dict[str, Any]:
    from mobile_app.backend.voice_runtime import get_voice_runtime_status

    return get_voice_runtime_status()


def _preload_hebrew_voice_models() -> Dict[str, Any]:
    from mobile_app.backend.voice_runtime import preload_hebrew_models

    return preload_hebrew_models()


def _new_voice_draft_state():
    from mobile_app.backend.voice_runtime import VoiceDraftState

    return VoiceDraftState()


def _synthesize_assistant_audio_sync(text: str):
    from mobile_app.backend.voice_runtime import synthesize_assistant_audio

    return synthesize_assistant_audio(text)


async def _run_app_chat_turn_lazy(*args, **kwargs):
    from mobile_app.backend.runtime import run_app_chat_turn

    return await run_app_chat_turn(*args, **kwargs)


def _set_startup_state(state: str, *, error: Optional[str] = None, detail: Optional[str] = None) -> None:
    _APP_RUNTIME_STATUS["startup_state"] = state
    _APP_RUNTIME_STATUS["startup_error"] = error
    _APP_RUNTIME_STATUS["startup_error_detail"] = detail


def _record_runtime_error(message: str, detail: Optional[str] = None) -> None:
    _APP_RUNTIME_STATUS["last_runtime_error"] = message
    _APP_RUNTIME_STATUS["last_runtime_error_detail"] = detail
    _APP_RUNTIME_STATUS["last_runtime_error_at"] = time.time()


def _dependency_status() -> Dict[str, Any]:
    capture = _capture_runtime_status()
    voice = _voice_runtime_status()
    issues = [*capture.get("issues", []), *voice.get("issues", [])]
    return {
        "capture": capture,
        "voice": voice,
        "issues": issues,
        "degraded": bool(issues),
    }


def _secret() -> str:
    return os.getenv(APP_SECRET_ENV) or os.getenv("TELEGRAM_BOT_TOKEN", "emploai-dev-secret")


def _format_verbose_tool_event(name: str, args: dict[str, Any], result: Any, duration_ms: float) -> dict[str, Any]:
    short_parts = []
    for key, value in list((args or {}).items())[:4]:
        value_str = str(value)
        if key in _BASE64_KEYS and len(value_str) > 100:
            continue
        if len(value_str) > 80:
            value_str = value_str[:77] + "..."
        short_parts.append(f"{key}: {value_str}")

    args_str = ", ".join(short_parts)
    if len(args_str) > 200:
        args_str = args_str[:197] + "..."

    result_text = ""
    level = "info"
    if isinstance(result, dict):
        if "error" in result:
            level = "error"
            result_text = f"❌ {str(result['error'])[:240]}"
        else:
            safe_keys = [key for key in result.keys() if key not in _BASE64_KEYS]
            result_text = f"✅ {', '.join(safe_keys[:4]) or 'ok'}"
    elif isinstance(result, str):
        clean = result[:240]
        if clean.startswith("Error"):
            level = "error"
            result_text = f"❌ {clean}"
        else:
            result_text = f"✅ {clean}"
    else:
        result_text = f"✅ {str(result)[:240]}"

    formatted = f"🔧 {name}({args_str})\n→ {result_text} ({duration_ms:.0f}ms)"
    if len(formatted) > 700:
        formatted = formatted[:697] + "..."

    return {
        "formatted": formatted,
        "level": level,
        "tool_name": name,
        "tool_args": args,
        "tool_result": result,
        "duration_ms": duration_ms,
    }


def _format_runtime_log_entry(message: str) -> dict[str, str]:
    text = str(message or "").strip()
    level = "info"
    if "[ERROR]" in text or "❌" in text:
        level = "error"
    elif "[PAUSED]" in text or "[STOPPED]" in text or "🛑" in text:
        level = "warn"
    return {"message": text, "level": level}


def _format_thinking_for_app(thinking: str) -> str:
    formatted = ThinkingModeVisualizer.format_thinking_for_telegram(thinking)
    return formatted.replace("*", "")


def _normalize_search_text(value: Any) -> str:
    collapsed = _SEARCH_NORMALIZE_RE.sub(" ", str(value or "").casefold())
    return " ".join(collapsed.split())


def _project_name_from_path(project_path: str) -> str:
    normalized = str(project_path or "").strip()
    if not normalized:
        return "Workspace"
    try:
        path = Path(normalized)
        name = path.name.strip()
        if name:
            return name
    except Exception:
        pass
    parts = normalized.rstrip("\\/").split("\\")
    return parts[-1] if parts else normalized


def _safe_datetime_value(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _session_file_signature(session_file: Path) -> Optional[tuple[int, int]]:
    try:
        stat = session_file.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _name_match_reason(kind: str, query: str, candidate: str) -> Optional[tuple[str, float]]:
    if not query or not candidate:
        return None
    if candidate == query:
        return (f"{kind}_exact", 300.0 if kind == "project" else 270.0)
    if candidate.startswith(query):
        return (f"{kind}_prefix", 290.0 if kind == "project" else 260.0)
    if query in candidate:
        return (f"{kind}_substring", 280.0 if kind == "project" else 250.0)
    return None


def _build_message_snippet(content: str, query: str, query_tokens: list[str]) -> str:
    normalized_content = " ".join(str(content or "").split())
    if not normalized_content:
        return ""
    lowered = normalized_content.casefold()
    search_needles = [query.casefold(), *[token.casefold() for token in query_tokens if token]]
    match_index = -1
    match_length = 0
    for needle in search_needles:
        if not needle:
            continue
        match_index = lowered.find(needle)
        if match_index >= 0:
            match_length = len(needle)
            break
    if match_index < 0:
        return normalized_content[:180]
    start = max(0, match_index - 60)
    end = min(len(normalized_content), match_index + max(match_length, 1) + 120)
    snippet = normalized_content[start:end]
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(normalized_content):
        snippet = f"{snippet}..."
    return snippet


def _user_session_search_cache(user_id: int) -> Dict[str, Dict[str, Any]]:
    with _SESSION_SEARCH_CACHE_LOCK:
        user_cache = _SESSION_SEARCH_CACHE.setdefault(user_id, {})
    return user_cache


def _load_session_search_entry(
    *,
    cache: Dict[str, Dict[str, Any]],
    session_file: Path,
    session_summary: Any,
) -> Optional[Dict[str, Any]]:
    signature = _session_file_signature(session_file)
    if signature is None:
        cache.pop(str(session_file), None)
        return None

    cached = cache.get(str(session_file))
    if cached and tuple(cached.get("signature") or ()) == signature:
        return cached

    try:
        payload = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        cache.pop(str(session_file), None)
        return None

    workspace = str(getattr(session_summary, "workspace", "") or payload.get("workspace", "") or "")
    entry = {
        "signature": signature,
        "session_id": str(getattr(session_summary, "id", "") or payload.get("id", "")),
        "session_name": str(getattr(session_summary, "name", "") or payload.get("name", "")),
        "workspace": workspace,
        "updated_at": str(getattr(session_summary, "updated_at", "") or payload.get("updated_at", "")),
        "messages": [
            {
                "index": index,
                "role": str(item.get("role", "user")),
                "content": str(item.get("content", "")),
                "normalized": _normalize_search_text(item.get("content", "")),
                "timestamp": item.get("timestamp"),
            }
            for index, item in enumerate(payload.get("chat_history", []))
            if str(item.get("content", "")).strip()
        ],
    }
    cache[str(session_file)] = entry
    return entry


def _search_sessions_in_manager(
    *,
    user_id: int,
    session_manager: Any,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return []

    normalized_limit = max(1, min(int(limit or 40), _SESSION_SEARCH_LIMIT_MAX))
    query_tokens = [token for token in normalized_query.split(" ") if token]
    summaries = sorted(
        session_manager.list_sessions(),
        key=lambda item: str(getattr(item, "updated_at", "") or ""),
        reverse=True,
    )
    session_cache = _user_session_search_cache(user_id)
    active_file_keys: set[str] = set()

    session_exact: list[dict[str, Any]] = []
    session_prefix: list[dict[str, Any]] = []
    session_substring: list[dict[str, Any]] = []
    message_phrase: list[dict[str, Any]] = []
    message_token: list[dict[str, Any]] = []
    remaining_message_limit = normalized_limit

    for summary in summaries:
        project_path = str(getattr(summary, "workspace", "") or "")
        project_name = _project_name_from_path(project_path)
        session_name = str(getattr(summary, "name", "") or "")
        normalized_session_name = _normalize_search_text(session_name)
        session_reason = _name_match_reason("session", normalized_query, normalized_session_name)
        if session_reason:
            target_bucket = (
                session_exact
                if session_reason[0].endswith("exact")
                else session_prefix
                if session_reason[0].endswith("prefix")
                else session_substring
            )
            target_bucket.append({
                "kind": "session",
                "project_path": project_path,
                "project_name": project_name,
                "session_id": str(getattr(summary, "id", "")),
                "session_name": session_name,
                "message_index": None,
                "message_role": None,
                "timestamp": getattr(summary, "updated_at", None),
                "snippet": "Chat name match",
                "match_reason": session_reason[0],
                "score": session_reason[1],
            })

    remaining_message_limit = max(
        0,
        normalized_limit - len(session_exact) - len(session_prefix) - len(session_substring),
    )
    if remaining_message_limit <= 0:
        return (
            session_exact
            + session_prefix
            + session_substring
        )[:normalized_limit]

    for summary in summaries:
        if len(message_phrase) >= remaining_message_limit and len(message_token) >= remaining_message_limit:
            break
        session_file = session_manager.sessions_dir / f"{getattr(summary, 'id', '')}.json"
        active_file_keys.add(str(session_file))
        search_entry = _load_session_search_entry(cache=session_cache, session_file=session_file, session_summary=summary)
        if not search_entry:
            continue

        project_path = str(search_entry.get("workspace", "") or "")
        project_name = _project_name_from_path(project_path)
        for message in reversed(search_entry.get("messages", [])):
            message_text = str(message.get("content", "") or "")
            normalized_message = str(message.get("normalized", "") or "")
            if not normalized_message:
                continue

            if normalized_query in normalized_message:
                if len(message_phrase) >= remaining_message_limit:
                    continue
                reason = "message_phrase"
                score = 240.0 + min(_safe_datetime_value(message.get("timestamp")) / 10_000_000_000, 0.999999)
                target_bucket = message_phrase
            elif query_tokens and all(token in normalized_message for token in query_tokens):
                if len(message_token) >= remaining_message_limit:
                    continue
                reason = "message_tokens"
                score = 230.0 + min(_safe_datetime_value(message.get("timestamp")) / 10_000_000_000, 0.999999)
                target_bucket = message_token
            else:
                continue

            target_bucket.append({
                "kind": "message",
                "project_path": project_path,
                "project_name": project_name,
                "session_id": str(search_entry.get("session_id", "")),
                "session_name": str(search_entry.get("session_name", "")),
                "message_index": int(message.get("index", 0)),
                "message_role": str(message.get("role", "user")),
                "timestamp": message.get("timestamp"),
                "snippet": _build_message_snippet(message_text, normalized_query, query_tokens),
                "match_reason": reason,
                "score": score,
            })

    stale_files = [key for key in list(session_cache.keys()) if key not in active_file_keys]
    for stale_file in stale_files:
        session_cache.pop(stale_file, None)

    return (
        session_exact
        + session_prefix
        + session_substring
        + message_phrase
        + message_token
    )[:normalized_limit]


def _sync_event_to_realtime_event(
    event: Dict[str, Any],
    *,
    active_session_id: Optional[str],
    client_id: Optional[str],
    verbose_mode: bool,
) -> Optional[RealtimeServerEvent]:
    event_session_id = str(event.get("session_id") or "").strip()
    payload = dict(event.get("payload") or {})
    event_type = str(event.get("type") or "").strip()

    if event_type == "current_session_changed":
        if not active_session_id:
            return None
        current_session_id = str(payload.get("current_session_id") or "").strip()
        previous_session_id = str(payload.get("previous_session_id") or "").strip()
        if active_session_id not in {session_id for session_id in (current_session_id, previous_session_id) if session_id}:
            return None
        if client_id and str(event.get("source_client_id") or "").strip() == client_id:
            return None
        return RealtimeServerEvent(
            type="current_session_changed",
            session_id=current_session_id or previous_session_id or active_session_id,
            payload=payload,
        )

    if not active_session_id or not event_session_id or event_session_id != active_session_id:
        return None

    if client_id and str(event.get("source_client_id") or "").strip() == client_id:
        return None

    if event_type == "user_message":
        message = payload.get("message")
        if not isinstance(message, dict):
            return None
        return RealtimeServerEvent(
            type="user_message",
            session_id=event_session_id,
            payload={"message": message},
        )

    if event_type == "assistant_delta":
        return RealtimeServerEvent(
            type="assistant_delta",
            session_id=event_session_id,
            payload={"delta": payload.get("delta", "")},
        )

    if event_type == "assistant_final":
        return RealtimeServerEvent(
            type="assistant_final",
            session_id=event_session_id,
            payload=payload,
        )

    if event_type == "artifact_created":
        return RealtimeServerEvent(
            type="artifact_created",
            session_id=event_session_id,
            payload={"artifacts": payload.get("artifacts") or []},
        )

    if event_type == "tool_use":
        if not verbose_mode:
            return None
        return RealtimeServerEvent(
            type="tool_event",
            session_id=event_session_id,
            payload=_format_verbose_tool_event(
                str(payload.get("tool_name", "")),
                payload.get("tool_args") or {},
                payload.get("tool_result"),
                float(payload.get("duration_ms") or 0.0),
            ),
        )

    if event_type == "tool_event":
        if not verbose_mode:
            return None
        return RealtimeServerEvent(
            type="tool_event",
            session_id=event_session_id,
            payload=payload,
        )

    if event_type == "log":
        if not verbose_mode:
            return None
        return RealtimeServerEvent(
            type="log",
            session_id=event_session_id,
            payload=_format_runtime_log_entry(str(payload.get("message", ""))),
        )

    if event_type == "status":
        return RealtimeServerEvent(
            type="status",
            session_id=event_session_id,
            payload=payload,
        )

    if event_type == "warning":
        return RealtimeServerEvent(
            type="warning",
            session_id=event_session_id,
            payload=payload,
        )

    if event_type == "error":
        return RealtimeServerEvent(
            type="error",
            session_id=event_session_id,
            payload=payload,
        )

    if event_type == "task_board":
        return RealtimeServerEvent(
            type="task_board",
            session_id=event_session_id,
            payload={
                "board": payload.get("board"),
                "completed_task_boards": payload.get("completed_task_boards") or [],
                "summary": payload.get("summary"),
            },
        )

    if event_type == "timeline_event":
        return RealtimeServerEvent(
            type="timeline_event",
            session_id=event_session_id,
            payload={"event": payload.get("event")},
        )

    return None


def _resolve_external_current_session_id(
    bridge: Any,
    *,
    active_session_id: Optional[str],
    event: Dict[str, Any],
) -> Optional[str]:
    event_session_id = str(event.get("session_id") or "").strip()
    if not event_session_id or event_session_id == active_session_id:
        return None

    try:
        current = bridge.get_current_session()
    except Exception:
        return None

    current_session_id = str(getattr(current, "id", "") or "").strip()
    if current_session_id == event_session_id:
        return current_session_id
    return None


async def _handle_remote_chat_ws(websocket: WebSocket, auth: Dict[str, Any]) -> None:
    send_lock = asyncio.Lock()
    watch_task: Optional[asyncio.Task[None]] = None
    sync_subscription_id: Optional[str] = None
    client_id = str(websocket.query_params.get("client_id") or secrets.token_hex(8))
    requested_session_id = str(websocket.query_params.get("session_id") or "").strip() or None
    effective_session_id = requested_session_id or _remote_current_session_id(auth)
    last_sync_version = -1

    async def send_model(event: RealtimeServerEvent) -> None:
        async with send_lock:
            await websocket.send_json(event.model_dump())

    async def send_session_sync(reason: str) -> None:
        nonlocal effective_session_id, last_sync_version
        state = _remote_shared_state(auth)
        last_sync_version = int(state.get("sync_version", 0) or 0)
        next_session_id = requested_session_id or str(state.get("current_session_id") or "").strip() or effective_session_id
        if not next_session_id:
            return
        effective_session_id = next_session_id
        try:
            detail = _remote_session_detail_view(auth, next_session_id)
        except HTTPException:
            return
        await send_model(
            RealtimeServerEvent(
                type="session_sync",
                session_id=next_session_id,
                payload={
                    "reason": reason,
                    "session": detail.model_dump(),
                    "sessions": [item.model_dump() for item in _remote_session_summary_views(auth)],
                    "shared_state": state,
                },
            )
        )

    async def handle_sync_event(event: Dict[str, Any]) -> None:
        nonlocal effective_session_id
        event_type = str(event.get("type") or "").strip()
        if event_type == "current_session_changed":
            next_session_id = str((event.get("payload") or {}).get("current_session_id") or event.get("session_id") or "").strip()
            if next_session_id:
                effective_session_id = next_session_id
                await send_session_sync("remote_current_session")
            return
        live_event = _sync_event_to_realtime_event(
            event,
            active_session_id=effective_session_id,
            client_id=client_id,
            verbose_mode=True,
        )
        if live_event is None:
            return
        await send_model(live_event)

    sync_subscription_id = get_channel_sync_hub().subscribe(
        user_id=int(auth["user_id"]),
        channel="remote_mobile",
        callback=handle_sync_event,
        loop=asyncio.get_running_loop(),
    )

    async def watch_remote_state() -> None:
        nonlocal effective_session_id, last_sync_version
        try:
            while True:
                await asyncio.sleep(0.8)
                state = _remote_shared_state(auth)
                current_sync_version = int(state.get("sync_version", 0) or 0)
                current_session_id = str(state.get("current_session_id") or "").strip() or effective_session_id
                if current_sync_version != last_sync_version:
                    effective_session_id = current_session_id
                    await send_session_sync("remote_sync")
        except asyncio.CancelledError:
            return

    await send_model(
        RealtimeServerEvent(
            type="session_snapshot",
            session_id=effective_session_id,
            payload={"connected": True, "mode": "remote"},
        )
    )
    await send_session_sync("connected")
    watch_task = asyncio.create_task(watch_remote_state())

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            text = str(data.get("text", "")).strip()
            if not text:
                await send_model(RealtimeServerEvent(type="warning", payload={"message": "Empty message ignored"}))
                continue
            target_session_id = str(data.get("session_id") or effective_session_id or "").strip() or None
            await _remote_dispatch_command(
                auth,
                command_name="chat_send",
                payload={
                    "text": text,
                    "session_id": target_session_id,
                    "source_format": str(data.get("source_format") or "app_text"),
                    "interrupt_policy": str(data.get("interrupt_policy") or "none"),
                    "source_client_id": client_id,
                },
            )
            await send_model(
                RealtimeServerEvent(
                    type="status",
                    session_id=target_session_id,
                    payload={"message": "dispatched to desktop"},
                )
            )
    finally:
        if watch_task:
            watch_task.cancel()
        if sync_subscription_id:
            get_channel_sync_hub().unsubscribe(sync_subscription_id)


async def _handle_remote_desktop_ws(websocket: WebSocket, auth: Dict[str, Any]) -> None:
    if not _is_remote_session_auth(auth) or str(auth.get("actor_kind") or "") != "desktop":
        raise WebSocketDisconnect(code=4403)

    desktop_id = str(auth.get("desktop_id") or "").strip()
    if not desktop_id:
        raise WebSocketDisconnect(code=4400)

    user_id = int(auth["user_id"])
    manager = get_remote_desktop_manager()
    store = _get_remote_control_store()
    connection = manager.register(
        user_id=user_id,
        desktop_id=desktop_id,
        websocket=websocket,
        loop=asyncio.get_running_loop(),
    )
    store.mark_desktop_connection(user_id=user_id, desktop_id=desktop_id, status="connected", detail="desktop websocket connected")
    get_channel_sync_hub().publish(
        user_id=user_id,
        event={
            "type": "status",
            "session_id": None,
            "origin_channel": "app",
            "payload": {"message": "paired desktop connected"},
        },
    )

    try:
        while True:
            raw = await websocket.receive_text()
            message = RemoteDesktopSocketMessage.model_validate_json(raw)
            if message.type == "heartbeat":
                store.heartbeat_desktop(
                    user_id=user_id,
                    desktop_id=desktop_id,
                    detail=str((message.payload or {}).get("detail") or "desktop heartbeat"),
                )
                continue

            if message.type == "state_snapshot":
                snapshot = RemoteDesktopSyncEnvelope.model_validate(message.payload or {})
                before_state = store.get_shared_state(user_id=user_id)
                store.update_shared_snapshot(
                    user_id=user_id,
                    desktop_id=desktop_id,
                    snapshot=snapshot.model_dump(),
                )
                previous_session_id = str(before_state.get("current_session_id") or "").strip() or None
                current_session_id = str(snapshot.current_session_id or "").strip() or None
                if current_session_id != previous_session_id:
                    publish_current_session_changed(
                        user_id=user_id,
                        session_id=current_session_id,
                        previous_session_id=previous_session_id,
                        origin_channel="app",
                        reason="remote_snapshot",
                    )
                continue

            if message.type == "sync_event":
                payload = dict(message.payload or {})
                payload.setdefault("origin_channel", "app")
                get_channel_sync_hub().publish(user_id=user_id, event=payload)
                continue

            if message.type == "status":
                get_channel_sync_hub().publish(
                    user_id=user_id,
                    event={
                        "type": "status",
                        "session_id": (message.payload or {}).get("session_id"),
                        "origin_channel": "app",
                        "payload": {"message": str((message.payload or {}).get("message") or "")},
                    },
                )
                continue
    finally:
        manager.unregister(connection.desktop_id)
        store.mark_desktop_connection(
            user_id=user_id,
            desktop_id=desktop_id,
            status="offline",
            detail="desktop websocket disconnected",
        )


def _sign(value: str) -> str:
    return hmac.new(_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _get_auth_store() -> AppAuthStore:
    global _auth_store
    if _auth_store is None:
        _auth_store = AppAuthStore()
    return _auth_store


def _get_remote_control_store() -> RemoteControlPlaneStore:
    global _remote_control_store
    if _remote_control_store is None:
        _remote_control_store = RemoteControlPlaneStore()
    return _remote_control_store


def _bearer_token_from_header(auth_header: Optional[str]) -> str:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return auth_header.split(" ", 1)[1].strip()


def _resolve_token(auth_header: Optional[str]) -> Dict[str, object]:
    token = _bearer_token_from_header(auth_header)
    payload = _get_auth_store().resolve_access_token(token)
    if not payload:
        payload = _get_remote_control_store().resolve_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def _resolve_ws_token(token: Optional[str]) -> Dict[str, object]:
    payload = _get_auth_store().resolve_access_token(token or "")
    if not payload:
        payload = _get_remote_control_store().resolve_session_token(token or "")
    if not payload:
        raise WebSocketDisconnect(code=4401)
    return payload


def _authorize_pair_start(auth_header: Optional[str], pair_secret: Optional[str]) -> int:
    if auth_header:
        return int(_resolve_token(auth_header)["user_id"])

    configured_secret = os.getenv(PAIRING_SECRET_ENV, "").strip()
    provided_secret = (pair_secret or "").strip()
    if configured_secret and provided_secret and hmac.compare_digest(provided_secret, configured_secret):
        return _default_user_id()

    raise HTTPException(
        status_code=401,
        detail="Pair start requires an existing device token or X-App-Pair-Secret",
    )


def _bridge_for_user(user_id: int) -> AppSessionBridge:
    workspace = _workspace_root()
    from mobile_app.backend.session_bridge import AppSessionBridge

    return AppSessionBridge(user_id=user_id, workspace=workspace)


def _path_signature(path: Path) -> Optional[tuple[int, int]]:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (int(stat.st_mtime_ns), int(stat.st_size))


def _resolve_pairing_user_id(pairing_id: str) -> int:
    pairing = _get_auth_store().get_pairing(pairing_id)
    if not pairing:
        raise HTTPException(status_code=404, detail="Unknown pairing")

    created_by = str(pairing.get("created_by") or "").strip()
    if created_by.startswith("user:"):
        try:
            return int(created_by.split(":", 1)[1])
        except ValueError:
            pass
    return _default_user_id()


def _is_remote_session_auth(payload: Dict[str, Any]) -> bool:
    return str(payload.get("auth_kind") or "").strip() == "remote_session"


def _remote_shared_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _get_remote_control_store().get_shared_state(user_id=int(payload["user_id"]))


def _remote_current_session_id(payload: Dict[str, Any]) -> Optional[str]:
    state = _remote_shared_state(payload)
    current_session_id = str(state.get("current_session_id") or "").strip()
    return current_session_id or None


def _remote_profile_view(payload: Dict[str, Any]) -> AppUserProfile:
    state = _remote_shared_state(payload)
    return AppUserProfile(
        user_id=int(payload["user_id"]),
        current_session_id=str(state.get("current_session_id") or "").strip() or None,
        current_model=str(state.get("current_model") or "").strip() or None,
        current_variant=str(state.get("current_variant") or "").strip() or None,
        device_id=str(payload.get("mobile_id") or payload.get("desktop_id") or "").strip() or None,
        device_name=str(payload.get("device_name") or payload.get("desktop_name") or "").strip() or None,
        device_platform=str(payload.get("device_platform") or payload.get("actor_kind") or "").strip() or None,
    )


def _remote_session_summary_views(payload: Dict[str, Any]) -> list[SessionSummaryView]:
    state = _remote_shared_state(payload)
    items = []
    for raw in list(state.get("sessions") or []):
        try:
            items.append(SessionSummaryView.model_validate(raw))
        except Exception:
            continue
    return items


def _remote_session_detail_view(payload: Dict[str, Any], session_id: Optional[str]) -> SessionDetailView:
    state = _remote_shared_state(payload)
    target_session_id = str(session_id or state.get("current_session_id") or "").strip()
    if not target_session_id:
        raise HTTPException(status_code=404, detail="No current session")
    details = dict(state.get("session_details") or {})
    raw = details.get(target_session_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Session detail is not available yet")
    try:
        return SessionDetailView.model_validate(raw)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Remote session detail is malformed: {exc}") from exc


async def _remote_wait_for_sync_version(user_id: int, baseline: int, *, timeout_seconds: float = 8.0) -> Dict[str, Any]:
    deadline = time.monotonic() + max(0.5, timeout_seconds)
    store = _get_remote_control_store()
    while time.monotonic() < deadline:
        state = store.get_shared_state(user_id=user_id)
        if int(state.get("sync_version", 0) or 0) > int(baseline):
            return state
        await asyncio.sleep(0.2)
    return store.get_shared_state(user_id=user_id)


async def _remote_dispatch_command(
    auth: Dict[str, Any],
    *,
    command_name: str,
    payload: Dict[str, Any],
) -> str:
    desktop_id = _get_remote_control_store().paired_desktop_id_for_payload(auth)
    if not desktop_id:
        raise HTTPException(status_code=409, detail="No paired desktop is available for this account")
    try:
        return await get_remote_desktop_manager().send_command(
            desktop_id=desktop_id,
            command_type=command_name,
            payload=payload,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _workspace_root() -> Path:
    runtime_home = os.getenv("EMPLOAI_HOME", "").strip()
    if runtime_home:
        return Path(runtime_home).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _default_user_id() -> int:
    allowed = os.getenv("ALLOWED_USER_IDS", "").split(",")
    for item in allowed:
        item = item.strip()
        if item:
            try:
                return int(item)
            except ValueError:
                continue
    return 0


def _get_security_manager() -> Optional[SecurityManager]:
    global _security_manager, _security_manager_attempted
    if _security_manager_attempted:
        return _security_manager

    _security_manager_attempted = True
    try:
        from bot_core.security import SecurityManager

        _security_manager = SecurityManager(
            max_requests_per_minute=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),
            max_requests_per_hour=int(os.getenv("MAX_REQUESTS_PER_HOUR", "200")),
        )
    except Exception:
        _security_manager = None
    return _security_manager


def _resolve_target_session_id(bridge: "AppSessionBridge", session_id: Optional[str] = None) -> str:
    target_session_id = str(session_id or "").strip()
    if target_session_id:
        return target_session_id
    current = bridge.get_current_session()
    if not current:
        raise HTTPException(status_code=404, detail="No current session")
    return str(current.id)


def _load_runtime_session_or_409(bridge: AppSessionBridge, session_id: Optional[str] = None):
    try:
        target_session_id = _resolve_target_session_id(bridge, session_id)
        return bridge.orchestrator.get_worker(target_session_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _current_headless_mode() -> str:
    return "headless" if os.getenv("HEADLESS", "true").strip().lower() in {"true", "1", "yes", "on"} else "headed"


def _model_groups(runtime) -> list[dict[str, Any]]:
    return runtime.get_available_model_groups(AVAILABLE_MODELS)


def _estimate_message_tokens(message: Dict[str, Any]) -> int:
    content = message.get("content", "")
    if isinstance(content, str):
        return len(content) // 4
    if isinstance(content, list):
        return len(json.dumps(content)) // 4
    return len(str(content)) // 4


def _context_usage(runtime) -> dict[str, Any]:
    context_manager = getattr(runtime, "context_manager", None)
    if context_manager:
        return context_manager.get_usage_snapshot(
            runtime.chat_history,
            runtime.current_model,
            last_compaction=getattr(runtime, "last_context_compaction", None),
        )

    max_tokens = int(MODEL_CONTEXT_SIZES.get(runtime.current_model, 128000))
    estimated_tokens = sum(_estimate_message_tokens(message) for message in runtime.chat_history)
    usage_percent = (estimated_tokens / max_tokens) * 100 if max_tokens else 0.0
    threshold_percent = 40.0
    return {
        "model": runtime.current_model,
        "max_tokens": max_tokens,
        "estimated_tokens": estimated_tokens,
        "usage_percent": round(usage_percent, 2),
        "message_count": len(runtime.chat_history),
        "threshold_percent": threshold_percent,
        "needs_compaction": usage_percent >= threshold_percent,
        "compaction_state": "needs_compaction" if usage_percent >= threshold_percent else "ok",
        "token_strategy": "rough",
        "last_compaction": getattr(runtime, "last_context_compaction", None),
    }


def _history_preview(runtime, count: int) -> list[dict[str, Any]]:
    preview_items: list[dict[str, Any]] = []
    for message in runtime.chat_history[-count:]:
        content = message.get("content", "")
        if isinstance(content, list):
            preview = json.dumps(content)
        else:
            preview = str(content)
        preview = preview.replace("\n", " ").strip()
        if len(preview) > 180:
            preview = preview[:180] + "..."
        preview_items.append(
            {
                "role": message.get("role", "user"),
                "timestamp": message.get("timestamp"),
                "preview": preview,
                "display_label": message.get("display_label"),
            }
        )
    return list(reversed(preview_items))


def _pending_files(runtime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for pending in runtime.pending_files:
        items.append(
            {
                "filename": str(pending.get("filename", "upload")),
                "mime_type": pending.get("mime_type"),
                "size": pending.get("size"),
                "source_format": pending.get("source_format"),
                "uploaded_at": pending.get("uploaded_at"),
            }
        )
    return items


def _memory_summary(runtime) -> dict[str, Any]:
    if not runtime.memory_manager:
        return {
            "memory_file_exists": False,
            "daily_log_count": 0,
            "oldest_log": None,
            "newest_log": None,
        }
    return runtime.memory_manager.export_memory_summary()


def _analytics_summary(runtime, days: int) -> dict[str, Any]:
    if not runtime.analytics_tracker:
        return {
            "period_days": days,
            "total_events": 0,
            "total_messages": 0,
            "total_commands": 0,
            "total_tokens": 0,
            "avg_tokens_per_message": 0.0,
            "top_skills": {},
            "top_commands": {},
            "model_usage": {},
            "daily_activity": {},
        }
    return runtime.analytics_tracker.get_summary(days)


def _security_summary() -> dict[str, Any]:
    manager = _get_security_manager()
    if not manager:
        return {
            "allowed_users_count": len([item for item in os.getenv("ALLOWED_USER_IDS", "").split(",") if item.strip()]),
            "rate_limited_users": 0,
            "security_events_24h": 0,
            "warning_events_24h": 0,
            "error_events_24h": 0,
            "max_requests_per_minute": int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),
            "max_requests_per_hour": int(os.getenv("MAX_REQUESTS_PER_HOUR", "200")),
        }

    summary = manager.get_security_summary()
    summary["max_requests_per_minute"] = manager.max_requests_per_minute
    summary["max_requests_per_hour"] = manager.max_requests_per_hour
    return summary


def _config_preview(runtime, limit: int = 18) -> list[dict[str, Any]]:
    if not runtime.live_config:
        return []
    items = runtime.live_config.list_all()
    return [{"key": key, "value": value} for key, value in sorted(items.items())[:limit]]


def _agent_overview(runtime, bridge: "AppSessionBridge", *, history_count: int = 12, analytics_days: int = 7) -> dict[str, Any]:
    runtime.ensure_current_model_available(AVAILABLE_MODELS)
    heartbeat = (
        runtime.heartbeat_manager.get_status()
        if runtime.heartbeat_manager
        else {
            "enabled": bool(runtime.live_config.get("heartbeat.enabled", False)) if runtime.live_config else False,
            "running": False,
            "interval_seconds": int(runtime.live_config.get("heartbeat.interval_seconds", 1800)) if runtime.live_config else 1800,
            "check_count": 0,
            "last_heartbeat": None,
        }
    )

    get_supported_planner_models = getattr(runtime, "get_supported_planner_models", None)
    planner_models = list(get_supported_planner_models(AVAILABLE_MODELS)) if callable(get_supported_planner_models) else []

    return {
        "session_id": runtime.session_manager.get_current_session_id() if runtime.session_manager else None,
        "current_model": runtime.current_model,
        "current_variant": runtime.current_variant,
        "planner_model": getattr(runtime, "planner_model", None),
        "available_planner_models": planner_models,
        "available_variants": runtime.get_available_variants(),
        "model_groups": _model_groups(runtime),
        "max_turns": runtime.max_turns,
        "workspace": str(runtime.workspace),
        "auto_reply_enabled": bool(runtime.auto_reply_enabled),
        "verbose_mode": bool(runtime.verbose_mode),
        "bridge_enabled": bool(runtime.live_config.get("browser.use_extension", True)) if runtime.live_config else False,
        "headless_mode": _current_headless_mode(),
        "heartbeat": heartbeat,
        "context_usage": _context_usage(runtime),
        "history": _history_preview(runtime, max(1, min(history_count, 25))),
        "pending_files": _pending_files(runtime),
        "memory_summary": _memory_summary(runtime),
        "analytics": _analytics_summary(runtime, max(1, min(analytics_days, 30))),
        "security": _security_summary(),
        "config_preview": _config_preview(runtime),
        "run_state": "running" if bool(getattr(runtime, "is_processing", False)) else "idle",
        "task_board": task_board_view(get_display_task_board(runtime)),
        "completed_task_boards": completed_task_board_views(runtime),
        "task_board_armed_next_turn": get_task_board_armed_next_turn(runtime),
        "available_tool_packs": bridge.orchestrator.available_tool_packs_for_session_obj(runtime.session),
        "enabled_tool_packs": list(getattr(runtime, "enabled_tool_packs", []) or []),
        "lock_status": bridge.orchestrator.lock_status_for_session_obj(runtime.session),
    }


def _coerce_config_value(raw_value: Any) -> Any:
    if not isinstance(raw_value, str):
        return raw_value

    value = raw_value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("{") or value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _resolve_workspace_path(requested: str, *, user_id: int) -> Path:
    requested_value = (requested or "").strip()
    if not requested_value:
        raise HTTPException(status_code=400, detail="Workspace is required")

    manager = _get_security_manager()
    resolved_path: Optional[Path] = None
    if manager:
        valid, resolved_path, error = manager.validate_path(requested_value, user_id)
        if not valid or not resolved_path:
            raise HTTPException(status_code=400, detail=error or "Invalid workspace path")
    else:
        resolved_path = Path(requested_value).expanduser().resolve()

    if not resolved_path.exists() or not resolved_path.is_dir():
        raise HTTPException(status_code=400, detail="Workspace path does not exist or is not a directory")

    return resolved_path


def _set_workspace(runtime, workspace_value: str) -> None:
    resolved_path = _resolve_workspace_path(workspace_value, user_id=runtime.user_id)

    try:
        runtime.set_workspace(resolved_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    runtime.save_session()


def _configure_runtime(runtime, request: AgentConfigureRequest) -> None:
    runtime.ensure_current_model_available(AVAILABLE_MODELS)
    should_save_session = False

    if request.model is not None:
        if request.model not in runtime.get_available_models(AVAILABLE_MODELS):
            raise HTTPException(status_code=400, detail="Model is unavailable for configured providers")
        runtime.current_model = request.model
        should_save_session = True

    available_variants = runtime.get_available_variants()
    if runtime.current_variant not in available_variants:
        runtime.current_variant = available_variants[0] if available_variants else "standard"

    if request.variant is not None:
        available_variants = runtime.get_available_variants()
        if request.variant not in available_variants:
            raise HTTPException(status_code=400, detail="Variant is not available for the current model")
        runtime.current_variant = request.variant
        should_save_session = True

    if request.planner_model is not None:
        planner_value = str(request.planner_model).strip() or None
        get_supported_planner_models = getattr(runtime, "get_supported_planner_models", None)
        supported_planner_models = (
            set(get_supported_planner_models(AVAILABLE_MODELS))
            if callable(get_supported_planner_models)
            else set(runtime.get_available_models(AVAILABLE_MODELS))
        )
        if planner_value and planner_value not in supported_planner_models:
            raise HTTPException(status_code=400, detail="Planner model is unavailable for the lightweight planner runtime")
        runtime.planner_model = planner_value
        should_save_session = True

    if request.max_turns is not None:
        max_turns = int(request.max_turns)
        if max_turns < 10 or max_turns > 1000:
            raise HTTPException(status_code=400, detail="Max turns must be between 10 and 1000")
        runtime.max_turns = max_turns

    if request.workspace is not None:
        _set_workspace(runtime, request.workspace)
        should_save_session = True

    if request.auto_reply_enabled is not None:
        runtime.auto_reply_enabled = bool(request.auto_reply_enabled)
        if runtime.auto_reply_enabled:
            runtime.auto_reply_notice_sent = False

    if request.verbose_mode is not None:
        runtime.verbose_mode = bool(request.verbose_mode)

    if request.bridge_enabled is not None and runtime.live_config:
        runtime.live_config.set("browser.use_extension", bool(request.bridge_enabled), runtime.user_id)
        runtime.live_config.save_config()
        runtime.reset_browser_task_context(runtime.current_task_id)
        if request.bridge_enabled:
            try:
                from telegram_bot.telegram_unified_agent import ensure_extension_bridge
                ensure_extension_bridge(runtime)
            except Exception:
                logger.exception("[app] failed to enable browser bridge")

    if request.heartbeat_interval_seconds is not None:
        seconds = int(request.heartbeat_interval_seconds)
        if seconds < 60 or seconds > 86400:
            raise HTTPException(status_code=400, detail="Heartbeat interval must be between 60 and 86400 seconds")
        if runtime.live_config:
            runtime.live_config.set("heartbeat.interval_seconds", seconds, runtime.user_id)
            runtime.live_config.save_config()
        if runtime.heartbeat_manager:
            runtime.heartbeat_manager.set_interval(seconds)

    if request.heartbeat_enabled is not None:
        enabled = bool(request.heartbeat_enabled)
        if runtime.live_config:
            runtime.live_config.set("heartbeat.enabled", enabled, runtime.user_id)
            runtime.live_config.save_config()
        if runtime.heartbeat_manager:
            if enabled:
                runtime.heartbeat_manager.start()
            else:
                runtime.heartbeat_manager.stop()

    if request.headless_mode is not None:
        os.environ["HEADLESS"] = "true" if request.headless_mode == "headless" else "false"
        if runtime.refined_agent:
            runtime.refined_agent.browser.headless = request.headless_mode == "headless"

    if should_save_session:
        runtime.save_session()


def _publish_runtime_config_sync(runtime, *, user_id: int, origin_channel: str) -> None:
    try:
        session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "").strip()
        if not session_id and runtime.session_manager:
            session_id = runtime.session_manager.get_current_session_id()
        if not session_id:
            return
        get_channel_sync_hub().publish(
            user_id=user_id,
            event={
                "type": "session_config",
                "session_id": session_id,
                "origin_channel": origin_channel,
                "payload": {
                    "model": runtime.current_model,
                    "variant": runtime.current_variant,
                    "planner_model": getattr(runtime, "planner_model", None),
                    "max_turns": runtime.max_turns,
                    "auto_reply_enabled": bool(runtime.auto_reply_enabled),
                    "verbose_mode": bool(runtime.verbose_mode),
                    "bridge_enabled": bool(runtime.live_config.get("browser.use_extension", True)) if runtime.live_config else False,
                    "headless_mode": _current_headless_mode(),
                    "enabled_tool_packs": list(getattr(runtime, "enabled_tool_packs", []) or []),
                    "telegram_bot_config_id": getattr(runtime, "telegram_bot_config_id", None),
                    "headless_eligible": bool(getattr(runtime, "headless_eligible", False)),
                },
            },
        )
    except Exception:
        logger.exception("[app] failed to publish runtime config sync")


def _active_task_agents(runtime) -> list[Any]:
    agents = []
    for attr in ("unified_agent", "refined_agent", "single_agent"):
        agent = getattr(runtime, attr, None)
        if agent and getattr(agent, "current_task", None):
            agents.append(agent)
    return agents


def _prepare_runtime_restart(runtime) -> None:
    runtime.should_interrupt = True
    runtime.is_processing = False
    for agent in _active_task_agents(runtime):
        try:
            agent.stop()
        except Exception:
            logger.exception("[app] failed stopping agent during restart prep")
    if getattr(runtime, "heartbeat_manager", None):
        try:
            runtime.heartbeat_manager.stop()
        except Exception:
            logger.exception("[app] failed stopping heartbeat during restart prep")
    runtime.save_session()


def _ensure_background_runtime(runtime) -> None:
    if getattr(runtime, "spawn_tool", None):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:  # pragma: no cover - app routes always have a loop
        raise HTTPException(status_code=503, detail="No event loop is available") from exc
    runtime.init_single_agent(None, loop)


def _skill_items(runtime) -> list[dict[str, Any]]:
    registry = getattr(runtime, "skill_registry", None)
    if not registry:
        return []

    gating = getattr(registry, "gating", None)
    available_skills = gating.list_available_skills() if gating else []
    unavailable = getattr(gating, "_unavailable_skills", {}) if gating else {}
    active = set(getattr(runtime, "active_skills", []) or [])

    items: list[dict[str, Any]] = []
    for skill in available_skills:
        items.append(
            {
                "name": skill.name,
                "description": skill.description,
                "user_invocable": bool(getattr(skill.metadata, "user_invocable", False)),
                "available": True,
                "active": skill.name in active,
                "unavailable_reason": None,
            }
        )

    for name, reason in sorted((unavailable or {}).items()):
        items.append(
            {
                "name": name,
                "description": str(reason),
                "user_invocable": False,
                "available": False,
                "active": False,
                "unavailable_reason": str(reason),
            }
        )

    items.sort(key=lambda item: (not item["active"], not item["available"], item["name"].lower()))
    return items


def create_app() -> FastAPI:
    app = FastAPI(title="EmploAI App Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_http_requests(request, call_next):
        started_at = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.exception("[app] %s %s from %s failed after %sms", request.method, request.url.path, client_host, duration_ms)
            _record_runtime_error(
                f"{request.method} {request.url.path} failed",
                traceback.format_exc(),
            )
            raise

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("[app] %s %s from %s -> %s (%sms)", request.method, request.url.path, client_host, response.status_code, duration_ms)
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):  # type: ignore[override]
        detail = traceback.format_exc()
        _record_runtime_error(
            f"{request.method} {request.url.path} crashed: {type(exc).__name__}: {exc}",
            detail,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"{type(exc).__name__}: {exc}",
                "traceback": detail,
            },
        )

    @app.get("/api/app/health")
    async def health(shallow: bool = False) -> dict:
        config = get_live_config(_workspace_root() / "config.json")
        forced_app_server = os.getenv("EMPLOAI_DESKTOP_FORCE_APP_SERVER", "").strip().lower() in {"1", "true", "yes", "on"}
        payload = {
            "ok": True,
            "channel": "app",
            "process_id": os.getpid(),
            "enabled": bool(forced_app_server or config.get("channels.app.enabled", False)),
            "pairing_bootstrap_enabled": bool(os.getenv(PAIRING_SECRET_ENV, "").strip()),
            "pairing_token_ttl_seconds": DEFAULT_PAIR_TTL_SECONDS,
            "access_token_ttl_seconds": TOKEN_TTL_SECONDS,
            "steering_beta_enabled": bool(
                os.getenv("EMPLO_APP_STEERING_BETA_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
                or config.get("channels.app.steering_beta", False)
            ),
            "startup_state": _APP_RUNTIME_STATUS["startup_state"],
            "startup_error": _APP_RUNTIME_STATUS["startup_error"],
            "startup_error_detail": _APP_RUNTIME_STATUS["startup_error_detail"],
            "last_runtime_error": _APP_RUNTIME_STATUS["last_runtime_error"],
            "last_runtime_error_detail": _APP_RUNTIME_STATUS["last_runtime_error_detail"],
            "last_runtime_error_at": _APP_RUNTIME_STATUS["last_runtime_error_at"],
            "readiness_scope": "app_api" if shallow else "full",
        }
        if shallow:
            return payload
        payload["dependency_status"] = _dependency_status()
        return payload

    @app.post("/api/remote/auth/register", response_model=RemoteUserView)
    async def remote_register(request: RemoteAuthRegisterRequest) -> RemoteUserView:
        try:
            user = _get_remote_control_store().register_user(
                email=request.email,
                password=request.password,
                display_name=request.display_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RemoteUserView.model_validate(user)

    @app.post("/api/remote/auth/login", response_model=RemoteAuthLoginResponse)
    async def remote_login(request: RemoteAuthLoginRequest) -> RemoteAuthLoginResponse:
        try:
            result = _get_remote_control_store().login(
                email=request.email,
                password=request.password,
                actor_kind=request.actor_kind,
                device_name=request.device_name,
                device_platform=request.device_platform,
                device_key=request.device_key,
                token_ttl_seconds=REMOTE_SESSION_TTL_SECONDS,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        expires_at = float(result.get("expires_at") or time.time())
        expires_in_seconds = max(0, int(expires_at - time.time()))
        return RemoteAuthLoginResponse(
            session_token=str(result.get("session_token") or ""),
            expires_in_seconds=expires_in_seconds,
            actor_kind=request.actor_kind,
            user=RemoteUserView.model_validate(result.get("user") or {}),
            desktop=RemoteDesktopView.model_validate(result["desktop"]) if result.get("desktop") else None,
            mobile=RemoteMobileView.model_validate(result["mobile"]) if result.get("mobile") else None,
        )

    @app.get("/api/remote/account/me", response_model=RemoteAccountProfile)
    async def remote_account_me(authorization: Optional[str] = Header(default=None)) -> RemoteAccountProfile:
        auth = _resolve_token(authorization)
        if not _is_remote_session_auth(auth):
            raise HTTPException(status_code=403, detail="Remote account access requires a remote session token")
        user = _get_remote_control_store().get_user(int(auth["user_id"]))
        if not user:
            raise HTTPException(status_code=404, detail="Unknown account")
        desktops = _get_remote_control_store().list_desktops(user_id=int(auth["user_id"]))
        desktop = None
        if auth.get("desktop_id"):
            for item in desktops:
                if str(item.get("desktop_id") or "") == str(auth.get("desktop_id") or ""):
                    desktop = item
                    break
        mobile = None
        if auth.get("mobile_id"):
            mobile = {
                "mobile_id": auth.get("mobile_id"),
                "device_name": auth.get("device_name"),
                "device_platform": auth.get("device_platform"),
                "paired_desktop_id": _get_remote_control_store().paired_desktop_id_for_payload(auth),
                "created_at": None,
                "last_used_at": None,
            }
        return RemoteAccountProfile(
            user=RemoteUserView.model_validate(user),
            actor_kind=str(auth.get("actor_kind") or "mobile"),
            desktop=RemoteDesktopView.model_validate(desktop) if desktop else None,
            mobile=RemoteMobileView.model_validate(mobile) if mobile else None,
            shared_state=_remote_shared_state(auth),
        )

    @app.get("/api/remote/desktops", response_model=list[RemoteDesktopView])
    async def remote_list_desktops(authorization: Optional[str] = Header(default=None)) -> list[RemoteDesktopView]:
        auth = _resolve_token(authorization)
        if not _is_remote_session_auth(auth):
            raise HTTPException(status_code=403, detail="Remote desktop access requires a remote session token")
        items = _get_remote_control_store().list_desktops(user_id=int(auth["user_id"]))
        return [RemoteDesktopView.model_validate(item) for item in items]

    @app.post("/api/remote/pair/start", response_model=RemotePairStartResponse)
    async def remote_pair_start(
        request: RemotePairStartRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> RemotePairStartResponse:
        auth = _resolve_token(authorization)
        if not _is_remote_session_auth(auth) or str(auth.get("actor_kind") or "") != "desktop":
            raise HTTPException(status_code=403, detail="Desktop login required to start pairing")
        desktop_id = str(request.desktop_id or auth.get("desktop_id") or "").strip()
        if not desktop_id:
            raise HTTPException(status_code=400, detail="No desktop is available for pairing")
        try:
            pairing = _get_remote_control_store().create_pairing(
                user_id=int(auth["user_id"]),
                desktop_id=desktop_id,
                ttl_seconds=REMOTE_PAIRING_TTL_SECONDS,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown desktop") from exc
        return RemotePairStartResponse.model_validate(pairing)

    @app.post("/api/remote/pair/complete", response_model=RemotePairCompleteResponse)
    async def remote_pair_complete(
        request: RemotePairCompleteRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> RemotePairCompleteResponse:
        auth = _resolve_token(authorization)
        if not _is_remote_session_auth(auth) or str(auth.get("actor_kind") or "") != "mobile":
            raise HTTPException(status_code=403, detail="Mobile login required to complete pairing")
        mobile_id = str(auth.get("mobile_id") or "").strip()
        if not mobile_id:
            raise HTTPException(status_code=400, detail="Mobile device is unavailable")
        try:
            result = _get_remote_control_store().complete_pairing(
                user_id=int(auth["user_id"]),
                pairing_token=request.pairing_token,
                mobile_id=mobile_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown pairing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RemotePairCompleteResponse(
            desktop=RemoteDesktopView.model_validate(result["desktop"]),
            mobile=RemoteMobileView.model_validate(result["mobile"]),
            shared_state=result.get("shared_state") or {},
        )

    @app.post("/api/app/pair/start", response_model=DevicePairStartResponse)
    async def pair_start(
        request: DevicePairStartRequest,
        authorization: Optional[str] = Header(default=None),
        x_app_pair_secret: Optional[str] = Header(default=None),
    ) -> DevicePairStartResponse:
        created_by_user = _authorize_pair_start(authorization, x_app_pair_secret)
        record = _get_auth_store().create_pairing(
            device_name=request.device_name,
            created_by=f"user:{created_by_user}",
            ttl_seconds=DEFAULT_PAIR_TTL_SECONDS,
        )
        pairing_id = str(record["pairing_id"])
        issued_at = int(record["issued_at"])
        payload = f"{pairing_id}:{issued_at}"
        token = f"{payload}:{_sign(payload)}"
        return DevicePairStartResponse(
            pairing_id=pairing_id,
            pairing_token=token,
            expires_in_seconds=DEFAULT_PAIR_TTL_SECONDS,
        )

    @app.post("/api/app/pair/complete", response_model=DevicePairCompleteResponse)
    async def pair_complete(request: DevicePairCompleteRequest) -> DevicePairCompleteResponse:
        try:
            pairing_id, issued_at, signature = request.pairing_token.split(":", 2)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Malformed pairing token") from exc
        payload = f"{pairing_id}:{issued_at}"
        if not hmac.compare_digest(signature, _sign(payload)):
            raise HTTPException(status_code=400, detail="Invalid pairing token")
        user_id = _resolve_pairing_user_id(pairing_id)
        try:
            result = _get_auth_store().complete_pairing(
                pairing_id=pairing_id,
                user_id=user_id,
                device_name=request.device_name,
                device_platform=request.device_platform,
                token_ttl_seconds=TOKEN_TTL_SECONDS,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown pairing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DevicePairCompleteResponse(
            access_token=result["access_token"],
            device_id=result["device_id"],
            expires_in_seconds=TOKEN_TTL_SECONDS,
        )

    @app.get("/api/app/me", response_model=AppUserProfile)
    async def me(authorization: Optional[str] = Header(default=None)) -> AppUserProfile:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            return _remote_profile_view(auth)
        user_id = int(auth["user_id"])
        bridge = _bridge_for_user(user_id)
        current = bridge.get_current_session()
        return AppUserProfile(
            user_id=user_id,
            current_session_id=current.id if current else None,
            current_model=current.model if current else None,
            current_variant=current.variant if current else None,
            device_id=auth.get("device_id"),
            device_name=auth.get("device_name"),
            device_platform=auth.get("device_platform"),
        )

    @app.get("/api/app/voice/status")
    async def voice_status(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            return {
                "ok": True,
                "input_ok": False,
                "issues": ["Mobile voice is disabled in remote mode for v1."],
                "selected_engine": "none",
                "selected_engine_state": "disabled",
                "selected_engine_ready": False,
            }
        return _voice_runtime_status()

    @app.post("/api/app/voice/warm")
    async def warm_voice_engine(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
        _resolve_token(authorization)
        status = _voice_runtime_status()
        selected_engine = str(status.get("selected_engine") or "").strip().lower()
        if selected_engine == "hebrew_local":
            try:
                timings = _preload_hebrew_voice_models()
                status = _voice_runtime_status()
                status["warmup"] = {
                    "ok": True,
                    "engine": selected_engine,
                    "timings": timings,
                }
            except Exception as exc:
                status = _voice_runtime_status()
                issues = list(status.get("issues") or [])
                issues.insert(0, f"Hebrew voice warmup failed: {exc}")
                status["issues"] = issues
                status["ok"] = False
                status["input_ok"] = False
                status["selected_engine_state"] = "error"
                status["selected_engine_ready"] = False
                status["warmup"] = {
                    "ok": False,
                    "engine": selected_engine,
                    "error": str(exc),
                }
        else:
            status["warmup"] = {
                "ok": True,
                "engine": selected_engine or "none",
                "timings": None,
            }
        return status

    @app.get("/api/app/agent/overview", response_model=AgentOverviewView)
    async def agent_overview(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
        history_count: int = 12,
        analytics_days: int = 7,
    ) -> AgentOverviewView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        return AgentOverviewView(**_agent_overview(runtime, bridge, history_count=history_count, analytics_days=analytics_days))

    @app.get("/api/app/agent/task-board", response_model=TaskBoardResponse)
    async def agent_task_board(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> TaskBoardResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        return TaskBoardResponse(task_board=task_board_view(get_display_task_board(runtime)))

    @app.post("/api/app/agent/task-board/arm", response_model=TaskBoardArmResponse)
    async def agent_task_board_arm(
        request: TaskBoardArmRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> TaskBoardArmResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        target_session_id = session_id
        if not target_session_id:
            current = bridge.get_current_session()
            target_session_id = current.id if current else None
        if not target_session_id:
            raise HTTPException(status_code=404, detail="No current session to arm")
        result = bridge.set_task_board_armed_next_turn(target_session_id, request.armed)
        return TaskBoardArmResponse(**result)

    @app.post("/api/app/agent/task-board/reassess", response_model=AgentActionResponse)
    async def agent_task_board_reassess(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)

        board = request_task_board_reassessment(runtime, "Manual reassessment requested by the user.")
        if not board:
            return AgentActionResponse(action="reassess", message="No active managed task.")

        runtime.save_session()
        get_channel_sync_hub().publish(
            user_id=int(auth["user_id"]),
            event={
                "type": "task_board",
                "session_id": runtime.session_manager.get_current_session_id() if runtime.session_manager else session_id,
                "origin_channel": "app",
                "payload": {
                    "board": board,
                    "completed_task_boards": completed_task_board_views(runtime),
                    "summary": "Manual reassessment completed. The active task board was revised immediately.",
                },
            },
        )
        return AgentActionResponse(
            action="reassess",
            message="Manual reassessment completed. The active task board was revised immediately.",
        )

    @app.post("/api/app/agent/configure", response_model=AgentActionResponse)
    async def configure_agent(
        request: AgentConfigureRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        _configure_runtime(runtime, request)
        _publish_runtime_config_sync(runtime, user_id=int(auth["user_id"]), origin_channel="app")
        return AgentActionResponse(action="configure", message="Agent controls updated")

    @app.get("/api/app/agent/bridge-status")
    async def bridge_status(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        try:
            from telegram_bot.telegram_unified_agent import get_browser_bridge_status
        except ImportError:
            from telegram_unified_agent import get_browser_bridge_status
        return dict(get_browser_bridge_status(runtime) or {})

    @app.get("/api/app/agent/config", response_model=ConfigListResponse)
    async def list_agent_config(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
        key: Optional[str] = None,
    ) -> ConfigListResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        if not runtime.live_config:
            return ConfigListResponse(items=[])

        if key:
            return ConfigListResponse(items=[ConfigEntryView(key=key, value=runtime.live_config.get(key))])

        items = runtime.live_config.list_all()
        return ConfigListResponse(
            items=[ConfigEntryView(key=entry_key, value=value) for entry_key, value in sorted(items.items())]
        )

    @app.post("/api/app/agent/config", response_model=ConfigEntryView)
    async def update_agent_config(
        request: ConfigUpdateRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> ConfigEntryView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        if not runtime.live_config:
            raise HTTPException(status_code=503, detail="Live config is unavailable")

        parsed_value = _coerce_config_value(request.value)
        runtime.live_config.set(request.key, parsed_value, runtime.user_id)
        runtime.live_config.save_config()
        return ConfigEntryView(key=request.key, value=runtime.live_config.get(request.key))

    @app.post("/api/app/agent/memory/search", response_model=MemorySearchResponse)
    async def search_agent_memory(
        request: MemorySearchRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> MemorySearchResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        if not runtime.memory_manager:
            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        query = request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        results = runtime.memory_manager.search_memory(query, max_results=8)
        return MemorySearchResponse(query=query, results=results)

    @app.post("/api/app/agent/memory/note", response_model=AgentActionResponse)
    async def append_agent_memory_note(
        request: MemoryNoteRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        if not runtime.memory_manager:
            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        note = request.note.strip()
        if not note:
            raise HTTPException(status_code=400, detail="Note is required")

        stored = runtime.memory_manager.append_to_memory("User Notes", f"- {note}")
        runtime.memory_manager.append_to_daily_log(note, "user_note")
        message = "Note saved to memory" if stored else "Note was already present in memory"
        return AgentActionResponse(action="memory_note", message=message)

    @app.post("/api/app/agent/files/clear", response_model=AgentActionResponse)
    async def clear_pending_files(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        runtime.pending_files = []
        runtime.save_session()
        return AgentActionResponse(action="clear_files", message="Pending files cleared")

    @app.post("/api/app/agent/forget-last", response_model=AgentActionResponse)
    async def forget_last_user_message(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)

        removed = False
        for index in range(len(runtime.chat_history) - 1, -1, -1):
            if runtime.chat_history[index].get("role") == "user":
                del runtime.chat_history[index]
                removed = True
                break

        if removed:
            runtime.save_session()
            return AgentActionResponse(action="forget_last", message="Last user message removed from context")
        return AgentActionResponse(action="forget_last", message="No user message found to remove")

    @app.post("/api/app/agent/reset", response_model=AgentActionResponse)
    async def reset_agent_context(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)

        runtime.chat_history = []
        runtime.pending_files = []
        runtime.message_id_map = {}
        if runtime.single_agent:
            runtime.single_agent.messages = []
        if runtime.unified_agent:
            runtime.unified_agent.conversation_history = []
        runtime.save_session()
        return AgentActionResponse(action="reset", message="Chat history cleared")

    @app.post("/api/app/agent/compact", response_model=AgentActionResponse)
    async def compact_agent_context(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)

        async with runtime.lock:
            if getattr(runtime, "is_processing", False):
                raise HTTPException(status_code=409, detail="Session is busy")

            result = compact_session_history(runtime, reason="manual", announce=True)
            if not result:
                raise HTTPException(status_code=503, detail="Context manager is unavailable")

            runtime.save_session()
        return AgentActionResponse(action="compact", message=result.message)

    @app.get("/api/app/agent/skills", response_model=SkillListResponse)
    async def list_agent_skills(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> SkillListResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        return SkillListResponse(items=[SkillSummaryView(**item) for item in _skill_items(runtime)])

    @app.post("/api/app/agent/skills/activate", response_model=AgentActionResponse)
    async def activate_agent_skill(
        request: SkillActivateRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        registry = getattr(runtime, "skill_registry", None)
        if not registry:
            raise HTTPException(status_code=503, detail="Skill system is unavailable")

        skill_name = request.name.strip()
        if not skill_name:
            raise HTTPException(status_code=400, detail="Skill name is required")

        if request.active:
            skill = registry.loader.get_skill(skill_name)
            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")
            if not registry.gating.is_available(skill_name):
                reason = registry.gating.get_unavailable_reason(skill_name)
                raise HTTPException(status_code=400, detail=reason or "Skill is unavailable")
            runtime.active_skills = [skill_name]
            message = f"{skill_name} will be active for your next messages"
        else:
            runtime.active_skills = [name for name in runtime.active_skills if name != skill_name]
            message = f"{skill_name} removed from active skills"

        runtime.save_session()
        return AgentActionResponse(action="skill_activate", message=message)

    @app.post("/api/app/agent/skills/validate", response_model=SkillValidationView)
    async def validate_agent_skill(
        request: SkillActivateRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> SkillValidationView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        registry = getattr(runtime, "skill_registry", None)
        if not registry:
            raise HTTPException(status_code=503, detail="Skill system is unavailable")

        skill_name = request.name.strip()
        if not skill_name:
            raise HTTPException(status_code=400, detail="Skill name is required")

        result = registry.validate_skill(skill_name)
        resources = result.get("resources", {}) or {}
        return SkillValidationView(
            name=skill_name,
            valid=bool(result.get("valid")),
            errors=[str(item) for item in result.get("errors", [])],
            warnings=[str(item) for item in result.get("warnings", [])],
            scripts_count=len(resources.get("scripts", [])),
            references_count=len(resources.get("references", [])),
            assets_count=len(resources.get("assets", [])),
        )

    @app.get("/api/app/agent/subagents", response_model=SubAgentListResponse)
    async def list_agent_subagents(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> SubAgentListResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        spawn_tool = getattr(runtime, "spawn_tool", None)
        if not spawn_tool:
            return SubAgentListResponse()

        status = spawn_tool.get_status()
        tasks = [SubAgentTaskView(**task) for task in status.get("tasks", [])]
        return SubAgentListResponse(
            total_tasks=int(status.get("total_tasks", 0)),
            running=int(status.get("running", 0)),
            completed=int(status.get("completed", 0)),
            failed=int(status.get("failed", 0)),
            tasks=tasks,
        )

    @app.post("/api/app/agent/subagents", response_model=AgentActionResponse)
    async def spawn_agent_subtask(
        request: SubAgentSpawnRequest,
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)

        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        _ensure_background_runtime(runtime)
        task_id = await runtime.spawn_tool.spawn(
            prompt=prompt,
            headless=bool(request.headless),
            max_turns=int(request.max_turns),
            announce_on_complete=False,
        )
        return AgentActionResponse(action="spawn", message=f"Sub-agent {task_id} started")

    @app.post("/api/app/agent/control/pause", response_model=AgentActionResponse)
    async def pause_agent_run(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            await _remote_dispatch_command(
                auth,
                command_name="pause_run",
                payload={"session_id": session_id},
            )
            return AgentActionResponse(action="pause", message="Pause requested for the paired desktop")
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        agents = _active_task_agents(runtime)
        if not agents:
            return AgentActionResponse(action="pause", message="No task is currently running")

        for agent in agents:
            agent.pause()
        return AgentActionResponse(action="pause", message="Pause requested for the current task")

    @app.post("/api/app/agent/control/stop", response_model=AgentActionResponse)
    async def stop_agent_run(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            await _remote_dispatch_command(
                auth,
                command_name="stop_run",
                payload={"session_id": session_id},
            )
            return AgentActionResponse(action="stop", message="Stop requested for the paired desktop")
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        agents = _active_task_agents(runtime)
        if not agents:
            return AgentActionResponse(action="stop", message="No task is currently running")

        for agent in agents:
            agent.stop()
        archived_board = archive_active_task_board(
            runtime,
            status="interrupted",
            summary="The current managed task was stopped by the user.",
        )
        runtime.is_processing = False
        runtime.should_interrupt = True
        runtime.save_session()
        current_runtime_session_id = runtime.session_manager.get_current_session_id() if runtime.session_manager else session_id
        publish_status_update(
            user_id=int(auth["user_id"]),
            session_id=current_runtime_session_id,
            origin_channel="app",
            message="ready",
            run_state="idle",
        )
        get_channel_sync_hub().publish(
            user_id=int(auth["user_id"]),
            event={
                "type": "task_board",
                "session_id": current_runtime_session_id,
                "origin_channel": "app",
                "payload": {
                    "board": task_board_view(get_display_task_board(runtime)),
                    "completed_task_boards": completed_task_board_views(runtime),
                    "summary": (archived_board or {}).get("completion_summary") if archived_board else "Managed task stopped.",
                },
            },
        )
        return AgentActionResponse(action="stop", message="Stopped the current task")

    @app.post("/api/app/agent/control/restart", response_model=AgentActionResponse)
    async def restart_agent_process(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            await _remote_dispatch_command(
                auth,
                command_name="restart_runtime",
                payload={"session_id": session_id},
            )
            return AgentActionResponse(action="restart", message="Restart requested for the paired desktop")
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)

        async def _restart_later() -> None:
            await asyncio.sleep(1.0)
            exec_current_process(
                script_path_fallback=str(Path(__file__).resolve().parents[2] / "telegram_bot" / "telegram_agent.py")
            )

        _prepare_runtime_restart(runtime)
        asyncio.create_task(_restart_later())
        return AgentActionResponse(action="restart", message="Restart scheduled")

    @app.get("/api/app/devices", response_model=list[TrustedDeviceView])
    async def list_devices(authorization: Optional[str] = Header(default=None)) -> list[TrustedDeviceView]:
        auth = _resolve_token(authorization)
        user_id = int(auth["user_id"])
        return [TrustedDeviceView(**item) for item in _get_auth_store().list_devices(user_id=user_id)]

    @app.post("/api/app/devices/{device_id}/revoke", response_model=DeviceActionResponse)
    async def revoke_device(device_id: str, authorization: Optional[str] = Header(default=None)) -> DeviceActionResponse:
        auth = _resolve_token(authorization)
        user_id = int(auth["user_id"])
        if not _get_auth_store().revoke_device(user_id=user_id, device_id=device_id):
            raise HTTPException(status_code=404, detail="Device not found")
        return DeviceActionResponse(device_id=device_id, action="revoke")

    @app.get("/api/app/sessions", response_model=list[SessionSummaryView])
    async def list_sessions(authorization: Optional[str] = Header(default=None)) -> list[SessionSummaryView]:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            return _remote_session_summary_views(auth)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return [SessionSummaryView(**bridge.summarize_session_summary(s)) for s in bridge.list_session_summaries()]

    @app.post("/api/app/sessions/search", response_model=SessionSearchResponse)
    async def search_sessions(request: SessionSearchRequest, authorization: Optional[str] = Header(default=None)) -> SessionSearchResponse:
        auth = _resolve_token(authorization)
        user_id = int(auth["user_id"])
        bridge = _bridge_for_user(user_id)
        results = _search_sessions_in_manager(
            user_id=user_id,
            session_manager=bridge.session_manager,
            query=request.query,
            limit=request.limit,
        )
        return SessionSearchResponse(results=[SessionSearchResultView(**item) for item in results])

    @app.post("/api/app/sessions", response_model=CreateSessionResponse)
    async def create_session(request: CreateSessionRequest, authorization: Optional[str] = Header(default=None)) -> CreateSessionResponse:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            before = _remote_shared_state(auth)
            await _remote_dispatch_command(
                auth,
                command_name="create_session",
                payload={
                    "name": request.name,
                    "workspace": request.workspace,
                    "telegram_bot_config_id": request.telegram_bot_config_id,
                    "enabled_tool_packs": list(request.enabled_tool_packs or []),
                    "headless_eligible": bool(request.headless_eligible),
                },
            )
            await _remote_wait_for_sync_version(
                int(auth["user_id"]),
                int(before.get("sync_version", 0) or 0),
            )
            return CreateSessionResponse(session=_remote_session_detail_view(auth, _remote_current_session_id(auth)))
        user_id = int(auth["user_id"])
        bridge = _bridge_for_user(user_id)
        workspace = _resolve_workspace_path(request.workspace, user_id=user_id) if request.workspace else None
        previous = bridge.get_current_session()
        try:
            session = bridge.create_session(
                request.name,
                workspace=workspace,
                telegram_bot_config_id=request.telegram_bot_config_id,
                enabled_tool_packs=request.enabled_tool_packs,
                headless_eligible=request.headless_eligible,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        publish_current_session_changed(
            user_id=user_id,
            session_id=session.id,
            previous_session_id=previous.id if previous else None,
            origin_channel="app",
            reason="session_created",
        )
        detail = SessionDetailView(**bridge.detailed_session_view(session))
        return CreateSessionResponse(session=detail)

    @app.post("/api/app/sessions/{session_id}/activate", response_model=SessionDetailView)
    async def activate_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            before = _remote_shared_state(auth)
            await _remote_dispatch_command(
                auth,
                command_name="activate_session",
                payload={"session_id": session_id},
            )
            await _remote_wait_for_sync_version(
                int(auth["user_id"]),
                int(before.get("sync_version", 0) or 0),
            )
            return _remote_session_detail_view(auth, session_id)
        user_id = int(auth["user_id"])
        bridge = _bridge_for_user(user_id)
        previous = bridge.get_current_session()
        try:
            session = bridge.activate_session(session_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        publish_current_session_changed(
            user_id=user_id,
            session_id=session.id,
            previous_session_id=previous.id if previous else None,
            origin_channel="app",
            reason="session_activated",
        )
        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.delete("/api/app/sessions/{session_id}", response_model=DeleteSessionResponse)
    async def delete_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> DeleteSessionResponse:
        auth = _resolve_token(authorization)
        user_id = int(auth["user_id"])
        bridge = _bridge_for_user(user_id)
        previous = bridge.get_current_session()
        try:
            result = bridge.delete_session(session_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        publish_current_session_changed(
            user_id=user_id,
            session_id=result.get("current_session_id"),
            previous_session_id=previous.id if previous else session_id,
            origin_channel="app",
            reason="session_deleted",
        )
        return DeleteSessionResponse(**result)

    @app.get("/api/app/sessions/{session_id}", response_model=SessionDetailView)
    async def get_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            return _remote_session_detail_view(auth, session_id)
        bridge = _bridge_for_user(int(auth["user_id"]))
        session = bridge.get_session(session_id)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.get("/api/app/sessions/{session_id}/artifacts", response_model=list[ArtifactSummaryView])
    async def list_session_artifacts(
        session_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> list[ArtifactSummaryView]:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            bridge.get_session(session_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        return [ArtifactSummaryView(**item) for item in bridge.list_session_artifacts(session_id)]

    @app.get("/api/app/sessions/{session_id}/artifacts/{artifact_id}", response_model=ArtifactDetailView)
    async def get_session_artifact(
        session_id: str,
        artifact_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> ArtifactDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            detail = bridge.get_session_artifact(session_id, artifact_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
        return ArtifactDetailView(**detail)

    @app.get("/api/app/sessions/{session_id}/artifacts/{artifact_id}/download")
    async def download_session_artifact(
        session_id: str,
        artifact_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> FileResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            detail = bridge.get_session_artifact(session_id, artifact_id)
            path = bridge.session_artifact_download_path(session_id, artifact_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
        return FileResponse(
            path,
            media_type=str(detail.get("mime_type") or "application/octet-stream"),
            filename=str(detail.get("payload_file_name") or path.name),
        )

    @app.post("/api/app/sessions/{session_id}/tool-packs", response_model=SessionDetailView)
    async def update_session_tool_packs(
        session_id: str,
        request: ToolPackUpdateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        session = bridge.update_session_tool_packs(session_id, request.enabled_tool_packs)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.post("/api/app/sessions/{session_id}/telegram-bot", response_model=SessionDetailView)
    async def update_session_telegram_bot(
        session_id: str,
        request: SessionBotAssignmentRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        session = bridge.update_session_telegram_bot_config(session_id, request.telegram_bot_config_id)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.post("/api/app/sessions/{session_id}/headless-eligibility", response_model=SessionDetailView)
    async def update_session_headless_eligibility(
        session_id: str,
        request: SessionHeadlessEligibilityRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        session = bridge.update_session_headless_eligible(session_id, request.headless_eligible)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.get("/api/app/telegram-bots", response_model=list[TelegramBotConfigView])
    async def list_telegram_bot_configs(authorization: Optional[str] = Header(default=None)) -> list[TelegramBotConfigView]:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return [TelegramBotConfigView(**item) for item in bridge.list_telegram_bot_configs()]

    @app.post("/api/app/telegram-bots", response_model=TelegramBotConfigView)
    async def create_telegram_bot_config(
        request: TelegramBotConfigCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> TelegramBotConfigView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return TelegramBotConfigView(**bridge.create_telegram_bot_config(label=request.label, bot_token=request.bot_token))

    @app.post("/api/app/telegram-bots/{bot_config_id}", response_model=TelegramBotConfigView)
    async def update_telegram_bot_config(
        bot_config_id: str,
        request: TelegramBotConfigUpdateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> TelegramBotConfigView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            item = bridge.update_telegram_bot_config(
                bot_config_id,
                label=request.label,
                bot_token=request.bot_token,
                is_default=request.is_default,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Telegram bot config not found") from exc
        return TelegramBotConfigView(**item)

    @app.delete("/api/app/telegram-bots/{bot_config_id}")
    async def delete_telegram_bot_config(
        bot_config_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return bridge.delete_telegram_bot_config(bot_config_id)

    @app.post("/api/app/sessions/{session_id}/timeline")
    async def append_session_timeline(
        session_id: str,
        request: TimelineEventAppendRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> dict:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        event = bridge.append_timeline_event(
            session_id=session_id,
            kind=request.kind,
            title=request.title,
            content=request.content,
            tone=request.tone,
            channel=request.channel,
            source_format=request.source_format,
            metadata=request.metadata,
        )
        get_channel_sync_hub().publish(
            user_id=int(auth["user_id"]),
            event={
                "type": "timeline_event",
                "session_id": session_id,
                "origin_channel": request.channel,
                "source_client_id": request.source_client_id,
                "payload": {"event": event},
            },
        )
        return {"event": event}

    @app.post("/api/app/chat/send")
    async def send_chat(request: ChatSendRequest, authorization: Optional[str] = Header(default=None)) -> dict:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, request.session_id)
        lease = await bridge.orchestrator.prepare_turn(str(runtime.session.id))
        if lease.busy:
            raise HTTPException(status_code=409, detail=lease.error or "Session is already processing another message")
        try:
            result = await _run_app_chat_turn_lazy(
                runtime,
                user_message=request.text,
                source_format=request.source_format,
                interrupt_policy=request.interrupt_policy,
            )
        finally:
            await bridge.orchestrator.complete_turn(lease)
        if result.get("busy"):
            raise HTTPException(status_code=409, detail="Session is already processing another message")
        return result

    @app.get("/api/app/jobs", response_model=list[ScheduledJobView])
    async def list_jobs(authorization: Optional[str] = Header(default=None)) -> list[ScheduledJobView]:
        auth = _resolve_token(authorization)
        if _is_remote_session_auth(auth):
            state = _remote_shared_state(auth)
            items: list[ScheduledJobView] = []
            for raw in list(state.get("jobs") or []):
                try:
                    items.append(ScheduledJobView.model_validate(raw))
                except Exception:
                    continue
            return items
        bridge = _bridge_for_user(int(auth["user_id"]))
        return [ScheduledJobView(**job) for job in bridge.list_jobs()]

    @app.get("/api/app/jobs/{job_id}", response_model=JobDetailView)
    async def get_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            return JobDetailView(**bridge.get_job(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.get("/api/app/cron/feed", response_model=list[CronFeedItemView])
    async def cron_feed(authorization: Optional[str] = Header(default=None)) -> list[CronFeedItemView]:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return [CronFeedItemView(**item) for item in bridge.list_cron_feed()]

    @app.post("/api/app/jobs", response_model=JobDetailView)
    async def create_job(request: JobCreateRequest, authorization: Optional[str] = Header(default=None)) -> JobDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        interval_seconds, error = parse_schedule_with_error(request.schedule)
        if error or not interval_seconds:
            raise HTTPException(status_code=400, detail=error or "Invalid schedule")
        scheduler = get_scheduler()
        origin_session_id = request.session_id or _resolve_target_session_id(bridge, None)
        origin_session = bridge.get_session(origin_session_id)
        origin_bot = bridge.orchestrator.resolve_telegram_bot_for_session(origin_session)
        job_id = scheduler.add_job(
            name=request.name,
            prompt=request.prompt,
            interval_seconds=interval_seconds,
            schedule_text=request.schedule,
            owner_user_id=int(auth["user_id"]),
            origin_session_id=origin_session.id,
            origin_telegram_bot_config_id=str(origin_bot.get("id") or "").strip() or None if origin_bot else None,
            origin_workspace=origin_session.workspace,
            origin_model=origin_session.model,
            origin_enabled_tool_packs=list(getattr(origin_session, "enabled_tool_packs", []) or []),
        )
        try:
            return JobDetailView(**bridge.get_job(job_id))
        except KeyError:
            return JobDetailView(
                id=job_id,
                name=request.name,
                prompt=request.prompt,
                schedule=request.schedule,
                enabled=True,
            )

    @app.get("/api/app/runtime/orchestrator", response_model=RuntimeOrchestratorView)
    async def runtime_orchestrator_status(authorization: Optional[str] = Header(default=None)) -> RuntimeOrchestratorView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return RuntimeOrchestratorView(**bridge.orchestrator.runtime_status_view())

    @app.post("/api/app/runtime/headless", response_model=RuntimeOrchestratorView)
    async def configure_headless_runtime(
        request: HeadlessConfigureRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> RuntimeOrchestratorView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return RuntimeOrchestratorView(
            **bridge.orchestrator.configure_headless(
                enabled=request.enabled,
                default_max_concurrent_chats=request.default_max_concurrent_chats,
                default_sleep_session_by_bot=request.default_sleep_session_by_bot,
            )
        )

    @app.post("/api/app/jobs/{job_id}/run", response_model=JobActionResponse)
    async def run_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.run_job_now(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="run")

    @app.post("/api/app/jobs/{job_id}/enable", response_model=JobActionResponse)
    async def enable(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.enable_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="enable")

    @app.post("/api/app/jobs/{job_id}/disable", response_model=JobActionResponse)
    async def disable(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.disable_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="disable")

    @app.delete("/api/app/jobs/{job_id}", response_model=JobActionResponse)
    async def delete_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.remove_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="delete")

    @app.post("/api/app/upload", response_model=UploadResponse)
    async def upload(
        file: UploadFile = File(...),
        session_id: Optional[str] = None,
        authorization: Optional[str] = Header(default=None),
    ) -> UploadResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        upload_id = secrets.token_hex(10)
        data = await file.read()
        effective_session_id = runtime.session_manager.get_current_session_id()
        bridge.attach_pending_file(
            runtime=runtime,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
        )
        return UploadResponse(
            upload_id=upload_id,
            filename=file.filename or "upload",
            session_id=effective_session_id,
            attached=True,
        )

    @app.get("/api/app/screenshot/current", response_model=ScreenCaptureView)
    async def current_screenshot(authorization: Optional[str] = Header(default=None)) -> ScreenCaptureView:
        _resolve_token(authorization)
        try:
            capture = _capture_screen_snapshot()
        except Exception as exc:
            _record_runtime_error(
                f"Screenshot capture failed: {exc}",
                traceback.format_exc(),
            )
            raise HTTPException(status_code=503, detail=f"Screenshot capture failed: {str(exc)}") from exc
        return ScreenCaptureView(**capture)

    @app.websocket("/ws/app/screen")
    async def screen_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("[app] websocket /ws/app/screen connected from %s", websocket.client.host if websocket.client else "unknown")
        send_lock = asyncio.Lock()

        async def send_model(event: RealtimeServerEvent) -> None:
            async with send_lock:
                await websocket.send_json(event.model_dump())

        try:
            token = websocket.query_params.get("token")
            _resolve_ws_token(token)

            try:
                fps = float(websocket.query_params.get("fps", "1.0") or "1.0")
            except ValueError:
                fps = 1.0
            fps = max(0.4, min(fps, 3.0))
            interval_seconds = 1.0 / fps

            try:
                max_width = int(websocket.query_params.get("max_width", "960") or "960")
            except ValueError:
                max_width = 960

            try:
                jpeg_quality = int(websocket.query_params.get("quality", "55") or "55")
            except ValueError:
                jpeg_quality = 55
            jpeg_quality = max(30, min(jpeg_quality, 85))

            await send_model(
                RealtimeServerEvent(
                    type="screen_state",
                    payload={
                        "state": "connected",
                        "fps": fps,
                        "max_width": max_width,
                        "quality": jpeg_quality,
                    },
                )
            )

            announced_streaming = False
            loop = asyncio.get_running_loop()
            while True:
                capture = await loop.run_in_executor(
                    None,
                    lambda: _capture_screen_snapshot(max_width=max_width, jpeg_quality=jpeg_quality),
                )
                if not announced_streaming:
                    await send_model(
                        RealtimeServerEvent(
                            type="screen_state",
                            payload={"state": "streaming", "fps": fps},
                        )
                    )
                    announced_streaming = True
                await send_model(
                    RealtimeServerEvent(
                        type="screen_frame",
                        payload=capture,
                    )
                )
                await asyncio.sleep(interval_seconds)
        except WebSocketDisconnect:
            logger.info("[app] websocket /ws/app/screen disconnected")
            return
        except Exception as exc:
            try:
                _record_runtime_error(
                    f"Screen feed failed: {exc}",
                    traceback.format_exc(),
                )
                await send_model(
                    RealtimeServerEvent(
                        type="error",
                        payload={"message": f"Screen feed failed: {str(exc)}"},
                    )
                )
            except Exception:
                pass
            return

    @app.websocket("/ws/remote/desktop")
    async def remote_desktop_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            auth = _resolve_ws_token(websocket.query_params.get("token"))
            await _handle_remote_desktop_ws(websocket, auth)
        except WebSocketDisconnect:
            logger.info("[remote] desktop websocket disconnected")
            return
        except Exception:
            logger.exception("[remote] desktop websocket failed")
            try:
                await websocket.send_json(
                    RealtimeServerEvent(
                        type="error",
                        payload={"message": "Remote desktop websocket failed"},
                    ).model_dump()
                )
            except Exception:
                pass
            return

    @app.websocket("/ws/remote/mobile")
    async def remote_mobile_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            auth = _resolve_ws_token(websocket.query_params.get("token"))
            if not _is_remote_session_auth(auth):
                raise WebSocketDisconnect(code=4403)
            await _handle_remote_chat_ws(websocket, auth)
        except WebSocketDisconnect:
            logger.info("[remote] mobile websocket disconnected")
            return
        except Exception:
            logger.exception("[remote] mobile websocket failed")
            try:
                await websocket.send_json(
                    RealtimeServerEvent(
                        type="error",
                        payload={"message": "Remote mobile websocket failed"},
                    ).model_dump()
                )
            except Exception:
                pass
            return

    @app.websocket("/ws/app/chat")
    async def chat_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("[app] websocket /ws/app/chat connected from %s", websocket.client.host if websocket.client else "unknown")
        send_lock = asyncio.Lock()
        watch_task: Optional[asyncio.Task[None]] = None
        sync_subscription_id: Optional[str] = None
        effective_session_id: Optional[str] = None

        async def send_model(event: RealtimeServerEvent) -> None:
            async with send_lock:
                await websocket.send_json(event.model_dump())

        try:
            token = websocket.query_params.get("token")
            session_id = websocket.query_params.get("session_id")
            auth = _resolve_ws_token(token)
            if _is_remote_session_auth(auth):
                await _handle_remote_chat_ws(websocket, auth)
                return
            bridge = _bridge_for_user(int(auth["user_id"]))
            client_id = str(websocket.query_params.get("client_id") or secrets.token_hex(8))

            last_session_signature: Optional[tuple[int, int]] = None
            last_index_signature: Optional[tuple[int, int]] = None

            async def send_session_sync(target_session_id: Optional[str], reason: str) -> None:
                nonlocal last_session_signature, last_index_signature
                if not target_session_id:
                    return
                try:
                    payload = bridge.build_session_sync_payload(target_session_id)
                except Exception:
                    return

                payload["reason"] = reason
                last_session_signature = _path_signature(bridge.session_file_path(target_session_id))
                last_index_signature = _path_signature(bridge.session_index_path())
                await send_model(
                    RealtimeServerEvent(
                        type="session_sync",
                        session_id=target_session_id,
                        payload=payload,
                    )
                )

            try:
                runtime = _load_runtime_session_or_409(bridge, session_id)
            except RuntimeError as exc:
                await send_model(
                    RealtimeServerEvent(
                        type="error",
                        session_id=session_id,
                        payload={"message": str(exc)},
                    )
                )
                return
            effective_session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "").strip() or session_id
            await send_model(
                RealtimeServerEvent(
                    type="session_snapshot",
                    session_id=effective_session_id,
                    payload={"connected": True},
                )
            )
            await send_session_sync(effective_session_id, "connected")

            async def handle_sync_event(event: Dict[str, Any]) -> None:
                nonlocal effective_session_id
                event_type = str(event.get("type") or "").strip()
                event_session_id = str(event.get("session_id") or "").strip()
                if event_type == "session_config":
                    if event_session_id and event_session_id == effective_session_id:
                        payload = event.get("payload") or {}
                        setting = str(payload.get("setting") or "external_config")
                        await send_session_sync(effective_session_id, setting)
                    return

                if event_type == "current_session_changed":
                    next_session_id = event_session_id or str((event.get("payload") or {}).get("current_session_id") or "").strip()
                    if next_session_id and next_session_id != effective_session_id:
                        effective_session_id = next_session_id
                        await send_session_sync(next_session_id, "external_current_session")
                    return

                live_event = _sync_event_to_realtime_event(
                    event,
                    active_session_id=effective_session_id,
                    client_id=client_id,
                    verbose_mode=runtime.verbose_mode,
                )
                if live_event is None:
                    return
                await send_model(live_event)

            sync_subscription_id = get_channel_sync_hub().subscribe(
                user_id=int(auth["user_id"]),
                channel="app",
                callback=handle_sync_event,
                loop=asyncio.get_running_loop(),
            )

            async def watch_session_updates() -> None:
                nonlocal effective_session_id
                try:
                    while True:
                        await asyncio.sleep(1.0)
                        current = bridge.get_current_session()
                        current_session_id = str(getattr(current, "id", "") or "").strip() or effective_session_id
                        if current_session_id != effective_session_id:
                            effective_session_id = current_session_id
                            await send_session_sync(current_session_id, "external_current_session")
                            continue

                        tracked_session_id = effective_session_id
                        if not tracked_session_id:
                            continue

                        session_signature = _path_signature(bridge.session_file_path(tracked_session_id))
                        index_signature = _path_signature(bridge.session_index_path())
                        if (
                            session_signature != last_session_signature
                            or index_signature != last_index_signature
                        ):
                            await send_session_sync(tracked_session_id, "external_change")
                except asyncio.CancelledError:
                    return

            watch_task = asyncio.create_task(watch_session_updates())

            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                text = str(data.get("text", "")).strip()
                req_session_id = data.get("session_id") or effective_session_id
                source_format = str(data.get("source_format") or "app_text")
                if not text:
                    await send_model(RealtimeServerEvent(type="warning", message="Empty message ignored"))
                    continue

                try:
                    runtime = _load_runtime_session_or_409(bridge, req_session_id)
                    effective_session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "").strip() or req_session_id
                except RuntimeError as exc:
                    await send_model(
                        RealtimeServerEvent(
                            type="warning",
                            session_id=req_session_id,
                            payload={"message": str(exc)},
                        )
                    )
                    continue

                async def emit(event: dict) -> None:
                    kind = event.get("type")
                    if kind == "assistant_delta":
                        await send_model(
                            RealtimeServerEvent(
                                type="assistant_delta",
                                session_id=req_session_id,
                                payload={"delta": event.get("delta", "")},
                            )
                        )
                    elif kind == "tool_use":
                        if not runtime.verbose_mode:
                            return
                        tool_payload = _format_verbose_tool_event(
                            str(event.get("tool_name", "")),
                            event.get("tool_args") or {},
                            event.get("tool_result"),
                            float(event.get("duration_ms") or 0.0),
                        )
                        await send_model(
                            RealtimeServerEvent(
                                type="tool_event",
                                session_id=req_session_id,
                                payload=tool_payload,
                            )
                        )
                    elif kind == "log":
                        if not runtime.verbose_mode:
                            return
                        log_payload = _format_runtime_log_entry(str(event.get("message", "")))
                        await send_model(
                            RealtimeServerEvent(
                                type="log",
                                session_id=req_session_id,
                                payload=log_payload,
                            )
                        )
                    elif kind == "status":
                        await send_model(
                            RealtimeServerEvent(
                                type="status",
                                session_id=req_session_id,
                                payload={"message": event.get("message", "")},
                            )
                        )
                    elif kind == "task_board":
                        await send_model(
                            RealtimeServerEvent(
                                type="task_board",
                                session_id=req_session_id,
                                payload={
                                    "board": event.get("board"),
                                    "summary": event.get("summary"),
                                },
                            )
                        )

                lease = await bridge.orchestrator.prepare_turn(str(getattr(getattr(runtime, "session", None), "id", "") or req_session_id or ""))
                if lease.busy:
                    await send_model(
                        RealtimeServerEvent(
                            type="warning",
                            session_id=req_session_id,
                            payload={"message": lease.error or "Session is already processing another message"},
                        )
                    )
                    continue
                try:
                    result = await _run_app_chat_turn_lazy(
                        runtime,
                        user_message=text,
                        source_format=source_format,
                        interrupt_policy=str(data.get("interrupt_policy", "none")),
                        source_client_id=client_id,
                        log_callback=emit,
                    )
                finally:
                    await bridge.orchestrator.complete_turn(lease)
                if result.get("busy"):
                    await send_model(
                        RealtimeServerEvent(
                            type="warning",
                            session_id=req_session_id,
                            payload={"message": "Session is already processing another message"},
                        )
                    )
                    continue
                if result.get("steering"):
                    await send_model(
                        RealtimeServerEvent(
                            type="status",
                            session_id=req_session_id,
                            payload={
                                "message": (
                                    "Beta steering accepted"
                                    if result.get("steering_status") == "armed"
                                    else "Beta steering queued for next safe boundary"
                                )
                            },
                        )
                    )
                    continue
                final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or req_session_id
                thinking_content = str(result.get("thinking_content") or "").strip()
                if thinking_content:
                    await send_model(
                        RealtimeServerEvent(
                            type="thinking",
                            session_id=final_session_id,
                            payload={
                                "text": thinking_content,
                                "formatted": _format_thinking_for_app(thinking_content),
                            },
                        )
                    )
                await send_model(
                    RealtimeServerEvent(
                        type="assistant_final",
                        session_id=final_session_id,
                        payload={
                            "text": result.get("assistant_text", ""),
                            "duration_seconds": result.get("duration_seconds"),
                            "input_tokens": result.get("input_tokens"),
                            "output_tokens": result.get("output_tokens"),
                            "total_tokens": result.get("total_tokens"),
                        },
                    )
                )
                if runtime.verbose_mode:
                    await send_model(
                        RealtimeServerEvent(
                            type="log",
                            session_id=final_session_id,
                            payload={
                                "message": (
                                    f"[COMPLETE] {result.get('duration_seconds', 0):.2f}s · "
                                    f"in {result.get('input_tokens', 0)} · out {result.get('output_tokens', 0)} · "
                                    f"total {result.get('total_tokens', 0)} tokens"
                                ),
                                "level": "info",
                            },
                        )
                    )
                effective_session_id = final_session_id
                await send_session_sync(final_session_id, "turn_complete")
        except WebSocketDisconnect:
            logger.info("[app] websocket /ws/app/chat disconnected")
            return
        except Exception as exc:
            try:
                logger.exception("[app] chat websocket failed")
                _record_runtime_error(
                    f"Chat websocket failed: {exc}",
                    traceback.format_exc(),
                )
                await send_model(
                    RealtimeServerEvent(
                        type="error",
                        session_id=effective_session_id,
                        payload={
                            "message": f"Chat websocket failed: {str(exc)}",
                            "detail": traceback.format_exc(),
                        },
                    )
                )
            except Exception:
                pass
            return
        finally:
            if watch_task:
                watch_task.cancel()
            if sync_subscription_id:
                get_channel_sync_hub().unsubscribe(sync_subscription_id)

    @app.websocket("/ws/app/voice")
    async def voice_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("[app] websocket /ws/app/voice connected from %s", websocket.client.host if websocket.client else "unknown")
        send_lock = asyncio.Lock()

        async def send_model(event: RealtimeServerEvent) -> None:
            async with send_lock:
                await websocket.send_json(event.model_dump())

        try:
            token = websocket.query_params.get("token")
            auth = _resolve_ws_token(token)
            if _is_remote_session_auth(auth):
                await send_model(
                    RealtimeServerEvent(
                        type="error",
                        session_id=websocket.query_params.get("session_id"),
                        payload={"message": "Mobile voice is disabled in remote mode for v1"},
                    )
                )
                return
            bridge = _bridge_for_user(int(auth["user_id"]))
            client_id = str(websocket.query_params.get("client_id") or secrets.token_hex(8))
            draft = _new_voice_draft_state()
            active_session_id = websocket.query_params.get("session_id")
            await send_model(
                RealtimeServerEvent(
                    type="voice_state",
                    session_id=active_session_id,
                    payload={"state": "connected"},
                )
            )
            while True:
                raw = await websocket.receive_text()
                event = VoiceClientEvent.model_validate_json(raw)
                if event.session_id:
                    active_session_id = event.session_id

                async def send_voice_event(event_type: str, payload: Optional[dict] = None) -> None:
                    await send_model(
                        RealtimeServerEvent(
                            type=event_type,
                            session_id=active_session_id,
                            payload=payload or {},
                        )
                    )

                if event.type == "voice_start":
                    draft.reset()
                    draft.state = "listening"
                    await send_voice_event("voice_state", {"state": "listening"})
                elif event.type == "voice_chunk":
                    revision = draft.revision
                    session_for_chunk = active_session_id
                    chunk_audio_base64 = event.audio_base64
                    chunk_mime_type = event.mime_type
                    chunk_sequence = event.sequence

                    async def process_chunk() -> None:
                        try:
                            partial_text = await draft.transcribe_chunk(
                                audio_base64=chunk_audio_base64,
                                mime_type=chunk_mime_type,
                                sequence=chunk_sequence,
                                revision=revision,
                            )
                            if revision != draft.revision:
                                return
                            draft.state = "listening"
                            await send_model(
                                RealtimeServerEvent(
                                    type="voice_partial",
                                    session_id=session_for_chunk,
                                    payload={"text": partial_text},
                                )
                            )
                        except Exception as exc:
                            if revision != draft.revision:
                                return
                            draft.state = "error"
                            await send_model(
                                RealtimeServerEvent(
                                    type="error",
                                    session_id=session_for_chunk,
                                    payload={"message": f"Voice transcription failed: {str(exc)}"},
                                )
                            )

                    task = asyncio.create_task(process_chunk())
                    draft.register_task(task)
                elif event.type in {"voice_pause", "voice_resume"}:
                    draft.state = event.type.replace("voice_", "")
                    await send_voice_event("voice_state", {"state": draft.state})
                elif event.type == "voice_commit":
                    draft.state = "finalizing"
                    await send_voice_event("voice_state", {"state": "finalizing"})
                    await draft.wait_for_pending()
                    draft_text = (await draft.final_transcript()).strip()
                    if not draft_text:
                        draft.reset()
                        await send_voice_event("warning", {"message": "No speech detected"})
                        await send_voice_event("voice_state", {"state": "idle"})
                        continue
                    if event.auto_send is False:
                        await send_model(
                            RealtimeServerEvent(
                                type="voice_transcript",
                                session_id=active_session_id,
                                payload={"text": draft_text, "auto_sent": False},
                            )
                        )
                        await send_voice_event("voice_state", {"state": "idle"})
                        draft.reset()
                        continue
                    try:
                        runtime = bridge.load_runtime_session(active_session_id)
                    except RuntimeError as exc:
                        await send_voice_event("warning", {"message": str(exc)})
                        await send_voice_event("voice_state", {"state": "idle"})
                        draft.reset()
                        continue
                    await send_voice_event("voice_state", {"state": "generating"})

                    async def emit(event_data: dict) -> None:
                        kind = event_data.get("type")
                        if kind == "assistant_delta":
                            await send_model(
                                RealtimeServerEvent(
                                    type="assistant_delta",
                                    session_id=active_session_id,
                                    payload={"delta": event_data.get("delta", "")},
                                )
                            )
                        elif kind == "tool_use":
                            if not runtime.verbose_mode:
                                return
                            tool_payload = _format_verbose_tool_event(
                                str(event_data.get("tool_name", "")),
                                event_data.get("tool_args") or {},
                                event_data.get("tool_result"),
                                float(event_data.get("duration_ms") or 0.0),
                            )
                            await send_model(
                                RealtimeServerEvent(
                                    type="tool_event",
                                    session_id=active_session_id,
                                    payload=tool_payload,
                                )
                            )
                        elif kind == "log":
                            if not runtime.verbose_mode:
                                return
                            log_payload = _format_runtime_log_entry(str(event_data.get("message", "")))
                            await send_model(
                                RealtimeServerEvent(
                                    type="log",
                                    session_id=active_session_id,
                                    payload=log_payload,
                                )
                            )
                        elif kind == "status":
                            await send_model(
                                RealtimeServerEvent(
                                    type="status",
                                    session_id=active_session_id,
                                    payload={"message": event_data.get("message", "")},
                                )
                            )

                    result = await _run_app_chat_turn_lazy(
                        runtime,
                        user_message=draft_text,
                        source_format="app_voice_transcript",
                        interrupt_policy=event.interrupt_policy or "none",
                        source_client_id=client_id,
                        log_callback=emit,
                    )
                    if result.get("busy"):
                        await send_voice_event("warning", {"message": "Session is already processing another message"})
                        continue
                    if result.get("steering"):
                        await send_model(
                            RealtimeServerEvent(
                                type="voice_final",
                                session_id=active_session_id,
                                payload={"text": draft_text},
                            )
                        )
                        await send_voice_event(
                            "status",
                            {
                                "message": (
                                    "Beta steering accepted"
                                    if result.get("steering_status") == "armed"
                                    else "Beta steering queued for next safe boundary"
                                )
                            },
                        )
                        draft.reset()
                        continue
                    final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or active_session_id
                    await send_model(
                        RealtimeServerEvent(
                            type="voice_final",
                            session_id=final_session_id,
                            payload={"text": draft_text},
                        )
                    )
                    thinking_content = str(result.get("thinking_content") or "").strip()
                    if thinking_content:
                        await send_model(
                            RealtimeServerEvent(
                                type="thinking",
                                session_id=final_session_id,
                                payload={
                                    "text": thinking_content,
                                    "formatted": _format_thinking_for_app(thinking_content),
                                },
                            )
                        )
                    await send_model(
                        RealtimeServerEvent(
                            type="assistant_final",
                            session_id=final_session_id,
                            payload={
                                "text": result.get("assistant_text", ""),
                                "duration_seconds": result.get("duration_seconds"),
                                "input_tokens": result.get("input_tokens"),
                                "output_tokens": result.get("output_tokens"),
                                "total_tokens": result.get("total_tokens"),
                            },
                        )
                    )
                    if runtime.verbose_mode:
                        await send_model(
                            RealtimeServerEvent(
                                type="log",
                                session_id=final_session_id,
                                payload={
                                    "message": (
                                        f"[COMPLETE] {result.get('duration_seconds', 0):.2f}s · "
                                        f"in {result.get('input_tokens', 0)} · out {result.get('output_tokens', 0)} · "
                                        f"total {result.get('total_tokens', 0)} tokens"
                                    ),
                                    "level": "info",
                                },
                            )
                        )
                    assistant_audio = None
                    assistant_text = str(result.get("assistant_text", "") or "").strip()
                    if assistant_text:
                        await send_voice_event("voice_state", {"state": "synthesizing"})
                        loop = asyncio.get_running_loop()
                        try:
                            assistant_audio = await loop.run_in_executor(None, _synthesize_assistant_audio_sync, assistant_text)
                        except Exception as exc:
                            await send_voice_event("warning", {"message": f"Assistant audio unavailable: {str(exc)}"})

                    if assistant_audio:
                        await send_voice_event("voice_state", {"state": "speaking"})
                        await send_model(
                            RealtimeServerEvent(
                                type="assistant_audio",
                                session_id=final_session_id,
                                payload=assistant_audio,
                            )
                        )
                    await send_voice_event("voice_state", {"state": "idle"})
                    draft.reset()
                elif event.type == "voice_cancel":
                    draft.reset()
                    await send_voice_event("voice_state", {"state": "cancelled"})
        except WebSocketDisconnect:
            logger.info("[app] websocket /ws/app/voice disconnected")
            return
        except Exception as exc:
            try:
                logger.exception("[app] voice websocket failed")
                _record_runtime_error(
                    f"Voice websocket failed: {exc}",
                    traceback.format_exc(),
                )
                await send_model(
                    RealtimeServerEvent(
                        type="error",
                        session_id=active_session_id,
                        payload={
                            "message": f"Voice websocket failed: {str(exc)}",
                            "detail": traceback.format_exc(),
                        },
                    )
                )
            except Exception:
                pass
            return


    return app


def start_embedded_app_server_if_enabled(*, force: bool = False) -> None:
    global _server_thread, _server_started
    if _server_started:
        return

    workspace = _workspace_root()
    config = get_live_config(workspace / "config.json")
    if not force and not bool(config.get("channels.app.enabled", False)):
        return

    host = str(config.get("channels.app.host", "0.0.0.0"))
    port = int(config.get("channels.app.port", 8787))
    _set_startup_state("starting")

    def _run() -> None:
        try:
            import uvicorn

            _set_startup_state("ready")
            uvicorn.run(
                create_app(),
                host=host,
                port=port,
                log_level="info",
                loop="asyncio",
                http="h11",
                ws="websockets",
            )
        except Exception as exc:
            detail = traceback.format_exc()
            logger.exception("[app] embedded app server failed to start")
            _set_startup_state(
                "error",
                error=f"Embedded app server failed to start: {exc}",
                detail=detail,
            )

    _server_thread = threading.Thread(target=_run, name="emploai-app-server", daemon=True)
    _server_thread.start()
    _server_started = True
