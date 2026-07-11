from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

async def _send_realtime_event(

    websocket: WebSocket,

    send_lock: asyncio.Lock,

    event: "RealtimeServerEvent",

) -> None:

    async with send_lock:

        if (

            websocket.client_state is WebSocketState.DISCONNECTED

            or websocket.application_state is WebSocketState.DISCONNECTED

        ):

            raise WebSocketDisconnect(code=1000)

        try:

            await websocket.send_json(event.model_dump())

        except Exception as exc:

            if _is_expected_websocket_close_error(exc):

                raise WebSocketDisconnect(code=1000) from exc

            raise

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

def _production_mode_enabled() -> bool:

    return os.getenv(DEPLOYMENT_ENV_ENV, "").strip().lower() in _PRODUCTION_ENV_VALUES

def _secret() -> str:

    configured_secret = os.getenv(APP_SECRET_ENV, "").strip()

    if configured_secret:

        return configured_secret

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if telegram_token:

        return telegram_token

    if _production_mode_enabled():

        raise RuntimeError(f"{APP_SECRET_ENV} is required when {DEPLOYMENT_ENV_ENV}=production")

    return "emploai-dev-secret"

def _debug_error_responses_enabled() -> bool:

    return os.getenv(DEBUG_ERROR_RESPONSES_ENV, "").strip().lower() in _TRUE_ENV_VALUES

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

            if str(item.get("content", "")).strip() and not bool(item.get("hidden_from_app"))

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

    if event_type.startswith("fleet_"):

        return RealtimeServerEvent(

            type=event_type,

            session_id=active_session_id,

            payload=payload,

        )

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

    if event_type == "run_failed":

        return RealtimeServerEvent(

            type="run_failed",

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

        message = str(payload.get("message", ""))

        if not _runtime_message_is_user_visible(message):

            return None

        return RealtimeServerEvent(

            type="log",

            session_id=event_session_id,

            payload=_format_runtime_log_entry(message),

        )

    if event_type == "status":

        message = str(payload.get("message", ""))

        if message and not _runtime_message_is_user_visible(message):

            return None

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

        event_payload = payload.get("event")

        if not _timeline_event_is_user_visible(event_payload):

            return None

        return RealtimeServerEvent(

            type="timeline_event",

            session_id=event_session_id,

            payload={"event": event_payload},

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
