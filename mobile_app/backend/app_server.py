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
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bot_core.ui_helpers import ThinkingModeVisualizer
from bot_core.security import SecurityManager
from cli.tui_constants import AVAILABLE_MODELS, MODEL_CONFIGS, MODEL_CONTEXT_SIZES
from mobile_app.backend.auth_store import AppAuthStore
from mobile_app.backend.capture_runtime import capture_screen_snapshot, get_capture_runtime_status
from mobile_app.backend.models import (
    AgentActionResponse,
    AgentConfigureRequest,
    AgentOverviewView,
    AppUserProfile,
    ChatSendRequest,
    ConfigEntryView,
    ConfigListResponse,
    ConfigUpdateRequest,
    CronFeedItemView,
    CreateSessionRequest,
    CreateSessionResponse,
    DeviceActionResponse,
    DevicePairCompleteRequest,
    DevicePairCompleteResponse,
    DevicePairStartRequest,
    DevicePairStartResponse,
    JobActionResponse,
    JobCreateRequest,
    JobDetailView,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryNoteRequest,
    RealtimeServerEvent,
    ScheduledJobView,
    ScreenCaptureView,
    SessionSearchRequest,
    SessionSearchResponse,
    SessionSearchResultView,
    SkillActivateRequest,
    SkillListResponse,
    SkillSummaryView,
    SkillValidationView,
    SessionDetailView,
    SessionSummaryView,
    SubAgentListResponse,
    SubAgentSpawnRequest,
    SubAgentTaskView,
    TaskBoardResponse,
    TimelineEventAppendRequest,
    TrustedDeviceView,
    UploadResponse,
    VoiceClientEvent,
)
from mobile_app.backend.runtime import run_app_chat_turn
from mobile_app.backend.session_bridge import AppSessionBridge
from mobile_app.backend.voice_runtime import VoiceDraftState, get_voice_runtime_status, synthesize_assistant_audio
from shared.channel_sync import get_channel_sync_hub
from shared.live_config import get_live_config
from shared.channel_runtime import compact_session_history
from shared.task_board import (
    completed_task_board_views,
    format_task_board_for_user,
    get_active_task_board,
    get_display_task_board,
    request_task_board_reassessment,
    task_board_view,
)
from single_agent.cron_scheduler import get_scheduler, parse_schedule_with_error
from telegram_bot.restart_runtime import exec_current_process


APP_SECRET_ENV = "EMPLO_APP_SECRET"
PAIRING_SECRET_ENV = "EMPLO_APP_PAIRING_SECRET"
DEFAULT_PAIR_TTL_SECONDS = 60 * 30
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 180

_auth_store: Optional[AppAuthStore] = None
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


def _set_startup_state(state: str, *, error: Optional[str] = None, detail: Optional[str] = None) -> None:
    _APP_RUNTIME_STATUS["startup_state"] = state
    _APP_RUNTIME_STATUS["startup_error"] = error
    _APP_RUNTIME_STATUS["startup_error_detail"] = detail


def _record_runtime_error(message: str, detail: Optional[str] = None) -> None:
    _APP_RUNTIME_STATUS["last_runtime_error"] = message
    _APP_RUNTIME_STATUS["last_runtime_error_detail"] = detail
    _APP_RUNTIME_STATUS["last_runtime_error_at"] = time.time()


def _dependency_status() -> Dict[str, Any]:
    capture = get_capture_runtime_status()
    voice = get_voice_runtime_status()
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

    project_exact: list[dict[str, Any]] = []
    project_prefix: list[dict[str, Any]] = []
    project_substring: list[dict[str, Any]] = []
    session_exact: list[dict[str, Any]] = []
    session_prefix: list[dict[str, Any]] = []
    session_substring: list[dict[str, Any]] = []
    message_phrase: list[dict[str, Any]] = []
    message_token: list[dict[str, Any]] = []
    seen_project_paths: set[str] = set()
    remaining_message_limit = normalized_limit

    for summary in summaries:
        project_path = str(getattr(summary, "workspace", "") or "")
        project_name = _project_name_from_path(project_path)
        normalized_project_name = _normalize_search_text(project_name)
        normalized_project_path = _normalize_search_text(project_path)
        project_reason = _name_match_reason("project", normalized_query, normalized_project_name)
        if project_reason is None and normalized_project_path:
            project_reason = _name_match_reason("project", normalized_query, normalized_project_path)
        if project_reason and project_path not in seen_project_paths:
            seen_project_paths.add(project_path)
            target_bucket = (
                project_exact
                if project_reason[0].endswith("exact")
                else project_prefix
                if project_reason[0].endswith("prefix")
                else project_substring
            )
            target_bucket.append({
                "kind": "project",
                "project_path": project_path,
                "project_name": project_name,
                "session_id": None,
                "session_name": None,
                "message_index": None,
                "message_role": None,
                "timestamp": None,
                "snippet": "Project name match",
                "match_reason": project_reason[0],
                "score": project_reason[1],
            })

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
        normalized_limit - len(project_exact) - len(project_prefix) - len(project_substring) - len(session_exact) - len(session_prefix) - len(session_substring),
    )
    if remaining_message_limit <= 0:
        return (
            project_exact
            + project_prefix
            + project_substring
            + session_exact
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
        project_exact
        + project_prefix
        + project_substring
        + session_exact
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
    if not active_session_id or not event_session_id or event_session_id != active_session_id:
        return None

    if client_id and str(event.get("source_client_id") or "").strip() == client_id:
        return None

    payload = dict(event.get("payload") or {})
    event_type = str(event.get("type") or "").strip()

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
            payload={"message": payload.get("message", "")},
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


def _sign(value: str) -> str:
    return hmac.new(_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _get_auth_store() -> AppAuthStore:
    global _auth_store
    if _auth_store is None:
        _auth_store = AppAuthStore()
    return _auth_store


def _bearer_token_from_header(auth_header: Optional[str]) -> str:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return auth_header.split(" ", 1)[1].strip()


def _resolve_token(auth_header: Optional[str]) -> Dict[str, object]:
    token = _bearer_token_from_header(auth_header)
    payload = _get_auth_store().resolve_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def _resolve_ws_token(token: Optional[str]) -> Dict[str, object]:
    payload = _get_auth_store().resolve_access_token(token or "")
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
        _security_manager = SecurityManager(
            max_requests_per_minute=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),
            max_requests_per_hour=int(os.getenv("MAX_REQUESTS_PER_HOUR", "200")),
        )
    except Exception:
        _security_manager = None
    return _security_manager


def _load_runtime_session_or_409(bridge: AppSessionBridge, session_id: Optional[str] = None):
    try:
        return bridge.load_runtime_session(session_id)
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


def _agent_overview(runtime, *, history_count: int = 12, analytics_days: int = 7) -> dict[str, Any]:
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
        "task_board": task_board_view(get_display_task_board(runtime)),
        "completed_task_boards": completed_task_board_views(runtime),
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
        session_id = runtime.session_manager.get_current_session_id() if runtime.session_manager else None
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
    async def health() -> dict:
        config = get_live_config(_workspace_root() / "config.json")
        dependency_status = _dependency_status()
        forced_app_server = os.getenv("EMPLOAI_DESKTOP_FORCE_APP_SERVER", "").strip().lower() in {"1", "true", "yes", "on"}
        return {
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
            "dependency_status": dependency_status,
        }

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
        return AgentOverviewView(**_agent_overview(runtime, history_count=history_count, analytics_days=analytics_days))

    @app.get("/api/app/agent/task-board", response_model=TaskBoardResponse)
    async def agent_task_board(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> TaskBoardResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        return TaskBoardResponse(task_board=task_board_view(get_display_task_board(runtime)))

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
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = _load_runtime_session_or_409(bridge, session_id)
        agents = _active_task_agents(runtime)
        if not agents:
            return AgentActionResponse(action="stop", message="No task is currently running")

        for agent in agents:
            agent.stop()
        runtime.is_processing = False
        runtime.should_interrupt = True
        runtime.save_session()
        return AgentActionResponse(action="stop", message="Stopped the current task")

    @app.post("/api/app/agent/control/restart", response_model=AgentActionResponse)
    async def restart_agent_process(
        authorization: Optional[str] = Header(default=None),
        session_id: Optional[str] = None,
    ) -> AgentActionResponse:
        auth = _resolve_token(authorization)
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
        bridge = _bridge_for_user(int(auth["user_id"]))
        return [SessionSummaryView(**bridge.summarize_session(s)) for s in bridge.list_sessions()]

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
        bridge = _bridge_for_user(int(auth["user_id"]))
        workspace = _resolve_workspace_path(request.workspace, user_id=int(auth["user_id"])) if request.workspace else None
        try:
            session = bridge.create_session(request.name, workspace=workspace)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        detail = SessionDetailView(**bridge.detailed_session_view(session))
        return CreateSessionResponse(session=detail)

    @app.post("/api/app/sessions/{session_id}/activate", response_model=SessionDetailView)
    async def activate_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            session = bridge.activate_session(session_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.get("/api/app/sessions/{session_id}", response_model=SessionDetailView)
    async def get_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        session = bridge.get_session(session_id)
        return SessionDetailView(**bridge.detailed_session_view(session))

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
        result = await run_app_chat_turn(
            runtime,
            user_message=request.text,
            source_format=request.source_format,
            interrupt_policy=request.interrupt_policy,
        )
        if result.get("busy"):
            raise HTTPException(status_code=409, detail="Session is already processing another message")
        return result

    @app.get("/api/app/jobs", response_model=list[ScheduledJobView])
    async def list_jobs(authorization: Optional[str] = Header(default=None)) -> list[ScheduledJobView]:
        auth = _resolve_token(authorization)
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
        interval_seconds, error = parse_schedule_with_error(request.schedule)
        if error or not interval_seconds:
            raise HTTPException(status_code=400, detail=error or "Invalid schedule")
        scheduler = get_scheduler()
        job_id = scheduler.add_job(
            name=request.name,
            prompt=request.prompt,
            interval_seconds=interval_seconds,
            schedule_text=request.schedule,
            owner_user_id=int(auth["user_id"]),
        )
        bridge = _bridge_for_user(int(auth["user_id"]))
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
            capture = capture_screen_snapshot()
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
                    lambda: capture_screen_snapshot(max_width=max_width, jpeg_quality=jpeg_quality),
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
                runtime = bridge.load_runtime_session(session_id)
            except RuntimeError as exc:
                await send_model(
                    RealtimeServerEvent(
                        type="error",
                        session_id=session_id,
                        payload={"message": str(exc)},
                    )
                )
                return
            effective_session_id = runtime.session_manager.get_current_session_id()
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

                switched_session_id = _resolve_external_current_session_id(
                    bridge,
                    active_session_id=effective_session_id,
                    event=event,
                )
                if switched_session_id:
                    effective_session_id = switched_session_id
                    await send_session_sync(switched_session_id, "external_current_session")
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
                    runtime = bridge.load_runtime_session(req_session_id)
                    effective_session_id = runtime.session_manager.get_current_session_id() or req_session_id
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

                result = await run_app_chat_turn(
                    runtime,
                    user_message=text,
                    source_format=source_format,
                    interrupt_policy=str(data.get("interrupt_policy", "none")),
                    source_client_id=client_id,
                    log_callback=emit,
                )
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
            bridge = _bridge_for_user(int(auth["user_id"]))
            client_id = str(websocket.query_params.get("client_id") or secrets.token_hex(8))
            draft = VoiceDraftState()
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

                    result = await run_app_chat_turn(
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
                            assistant_audio = await loop.run_in_executor(None, synthesize_assistant_audio, assistant_text)
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
            uvicorn.run(create_app(), host=host, port=port, log_level="info")
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
