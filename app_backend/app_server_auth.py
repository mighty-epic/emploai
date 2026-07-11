from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS = 20

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

def _remote_auth_rate_limit_key(request: Request, *, email: str, action: str) -> str:

    client_host = request.client.host if request.client else "unknown"

    return f"{action}:{client_host}:{email.strip().casefold()}"

def _remote_auth_rate_limit_keys(

    request: Request,

    *,

    email: str,

    action: str,

    include_client_bucket: bool,

) -> list[str]:

    client_host = request.client.host if request.client else "unknown"

    keys = [_remote_auth_rate_limit_key(request, email=email, action=action)]

    if include_client_bucket:

        keys.append(f"{action}:{client_host}:*")

    return list(dict.fromkeys(keys))

def _check_remote_auth_rate_limit(

    request: Request,

    *,

    email: str,

    action: str,

    max_attempts: int = REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,

    include_client_bucket: bool = True,

) -> None:

    keys = _remote_auth_rate_limit_keys(

        request,

        email=email,

        action=action,

        include_client_bucket=include_client_bucket,

    )

    _record_remote_auth_rate_limit_attempt(keys, max_attempts=max_attempts)

def _record_remote_auth_rate_limit_attempt(keys: list[str], *, max_attempts: int) -> None:

    now = time.time()

    cutoff = now - REMOTE_AUTH_RATE_LIMIT_WINDOW_SECONDS

    with _REMOTE_AUTH_RATE_LIMIT_LOCK:

        if len(_REMOTE_AUTH_RATE_LIMIT) > REMOTE_AUTH_RATE_LIMIT_MAX_KEYS:

            stale_keys = [

                item_key

                for item_key, item_attempts in _REMOTE_AUTH_RATE_LIMIT.items()

                if not item_attempts or max(item_attempts) < cutoff

            ]

            for item_key in stale_keys:

                _REMOTE_AUTH_RATE_LIMIT.pop(item_key, None)

            if len(_REMOTE_AUTH_RATE_LIMIT) > REMOTE_AUTH_RATE_LIMIT_MAX_KEYS:

                oldest_keys = sorted(

                    _REMOTE_AUTH_RATE_LIMIT,

                    key=lambda item_key: max(_REMOTE_AUTH_RATE_LIMIT.get(item_key) or [0]),

                )

                for item_key in oldest_keys[: max(1, len(_REMOTE_AUTH_RATE_LIMIT) - REMOTE_AUTH_RATE_LIMIT_MAX_KEYS)]:

                    _REMOTE_AUTH_RATE_LIMIT.pop(item_key, None)

        attempts_by_key = {

            key: [item for item in _REMOTE_AUTH_RATE_LIMIT.get(key, []) if item >= cutoff]

            for key in keys

        }

        for key, attempts in attempts_by_key.items():

            if len(attempts) >= max(1, int(max_attempts)):

                _REMOTE_AUTH_RATE_LIMIT[key] = attempts

                raise HTTPException(status_code=429, detail="Too many auth attempts. Try again in a few minutes.")

        for key, attempts in attempts_by_key.items():

            attempts.append(now)

            _REMOTE_AUTH_RATE_LIMIT[key] = attempts

def _remote_ws_auth_rate_limit_keys(websocket: WebSocket, token: Optional[str]) -> list[str]:

    client_host = websocket.client.host if websocket.client else "unknown"

    token_label = _token_hash_prefix(str(token or "")) or "missing"

    return list(dict.fromkeys([f"ws_auth:{client_host}:{token_label}", f"ws_auth:{client_host}:*"]))

def _empty_sidebar_state() -> Dict[str, Any]:

    return {

        "version": 1,

        "projectOrder": [],

        "projects": {},

        "sessionMeta": {},

        "selectedProjectPath": None,

        "lastSelectedProjectPath": None,

    }

def _sidebar_state_path() -> Path:

    home = runtime_home()

    root = home if home is not None else _workspace_root()

    root.mkdir(parents=True, exist_ok=True)

    return root / "desktop-sidebar-state.json"

def _read_local_sidebar_state() -> Dict[str, Any]:

    path = _sidebar_state_path()

    try:

        if not path.exists():

            return _empty_sidebar_state()

        payload = json.loads(path.read_text(encoding="utf-8"))

        return payload if isinstance(payload, dict) else _empty_sidebar_state()

    except Exception:

        return _empty_sidebar_state()

def _write_local_sidebar_state(state: Dict[str, Any]) -> Dict[str, Any]:

    payload = dict(state or _empty_sidebar_state())

    path = _sidebar_state_path()

    temp_path = path.with_suffix(".tmp")

    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    temp_path.replace(path)

    return payload

def _auth_debug_enabled() -> bool:

    return os.getenv("EMPLOAI_AUTH_DEBUG", "").strip() == "1"

def _token_hash_prefix(token: str) -> str:

    if not token:

        return ""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

def _log_invalid_token_debug(token: str) -> None:

    if not _auth_debug_enabled():

        return

    auth_store = _get_auth_store()

    known_hashes = []

    try:

        loaded = auth_store._load()  # noqa: SLF001 - debug-only local auth trace

        known_hashes = sorted(str(key)[:12] for key in loaded.get("tokens", {}).keys())

    except Exception as exc:

        known_hashes = [f"<load-error:{type(exc).__name__}>"]

    logging.warning(

        "[auth-debug] invalid token_hash=%s auth_store=%s known_token_hashes=%s",

        _token_hash_prefix(token) or "<empty>",

        getattr(auth_store, "file_path", "<unknown>"),

        ",".join(known_hashes) or "<none>",

    )

def _resolve_token(auth_header: Optional[str]) -> Dict[str, object]:

    token = _bearer_token_from_header(auth_header)

    payload = _get_auth_store().resolve_access_token(token)

    if not payload:

        payload = _get_remote_control_store().resolve_session_token(token)

    if not payload:

        _log_invalid_token_debug(token)

        raise HTTPException(status_code=401, detail="Invalid token")

    return payload

def _resolve_ws_token(token: Optional[str]) -> Dict[str, object]:

    payload = _get_auth_store().resolve_access_token(token or "")

    if not payload:

        payload = _get_remote_control_store().resolve_session_token(token or "")

    if not payload:

        _log_invalid_token_debug(token or "")

        raise WebSocketDisconnect(code=4401)

    return payload

def _remote_ws_session_is_active(auth: Dict[str, Any]) -> bool:

    if not _is_remote_session_auth(auth):

        return True

    token_hash = str(auth.get("session_token_hash") or "").strip()

    if not token_hash:

        return False

    try:

        user_id = int(auth["user_id"])

    except Exception:

        return False

    actor_kind = str(auth.get("actor_kind") or "").strip()

    desktop_id = str(auth.get("desktop_id") or "").strip() or None

    return _get_remote_control_store().is_session_token_hash_active(

        token_hash=token_hash,

        user_id=user_id,

        actor_kind=actor_kind or None,

        desktop_id=desktop_id if actor_kind == "desktop" else None,

    )

def _remote_desktop_connection_session_is_active(*, desktop_id: str, user_id: int) -> bool:

    clean_desktop_id = str(desktop_id or "").strip()

    if not clean_desktop_id:

        return False

    manager = get_remote_desktop_manager()

    if not hasattr(manager, "get"):

        return True

    connection = manager.get(clean_desktop_id)

    if connection is None or int(connection.user_id) != int(user_id):

        return True

    token_hash = str(getattr(connection, "session_token_hash", "") or "").strip()

    if not token_hash:

        if manager.unregister(

            clean_desktop_id,

            connection_id=connection.connection_id,

            reason="The paired desktop session is not authorized",

        ):

            _mark_remote_desktop_offline(

                user_id=int(user_id),

                desktop_id=clean_desktop_id,

                reason="The paired desktop session is not authorized",

            )

        return False

    if _get_remote_control_store().is_session_token_hash_active(

        token_hash=token_hash,

        user_id=int(user_id),

        actor_kind="desktop",

        desktop_id=clean_desktop_id,

    ):

        return True

    if manager.unregister(

        clean_desktop_id,

        connection_id=connection.connection_id,

        reason="The paired desktop session expired",

    ):

        _mark_remote_desktop_offline(

            user_id=int(user_id),

            desktop_id=clean_desktop_id,

            reason="The paired desktop session expired",

        )

    return False

def _mark_remote_desktop_offline(*, user_id: int, desktop_id: str, reason: str) -> None:

    try:

        _get_remote_control_store().mark_desktop_connection(

            user_id=int(user_id),

            desktop_id=str(desktop_id),

            status="offline",

            detail=reason,

        )

        _publish_fleet_delta(

            user_id=int(user_id),

            event_type="fleet_worker_presence",

            payload={"desktop_id": str(desktop_id), "status": "offline"},

            origin_channel="desktop",

        )

    except Exception:

        logger.exception("[remote] failed marking desktop offline")

def _mark_remote_desktop_offline_if_no_live_connection(*, user_id: int, desktop_id: str, reason: str) -> None:

    manager = get_remote_desktop_manager()

    try:

        if hasattr(manager, "is_connected_for_user"):

            if manager.is_connected_for_user(desktop_id, int(user_id)):

                return

        elif hasattr(manager, "is_connected") and manager.is_connected(desktop_id):

            return

    except Exception:

        logger.exception("[remote] failed checking desktop connection before marking offline")

    _mark_remote_desktop_offline(user_id=int(user_id), desktop_id=str(desktop_id), reason=reason)

def _command_error_implies_desktop_unavailable(detail: str) -> bool:

    normalized = str(detail or "").strip().lower()

    return (

        "offline" in normalized

        or "connection failed" in normalized

        or ("connection" in normalized and "failed" in normalized)

        or "disconnected" in normalized

    )

async def _disconnect_remote_desktops_for_user(user_id: int, *, reason: str) -> int:

    manager = get_remote_desktop_manager()

    if not hasattr(manager, "connected_desktop_ids_for_user"):

        return 0

    disconnected = 0

    for desktop_id in list(manager.connected_desktop_ids_for_user(int(user_id))):

        connection = manager.get(desktop_id) if hasattr(manager, "get") else None

        if manager.unregister(desktop_id, reason=reason):

            disconnected += 1

            if connection is not None:

                try:

                    await connection.websocket.close(code=4401)

                except Exception:

                    pass

    return disconnected

async def _disconnect_remote_desktop_for_session(auth: Dict[str, Any], *, reason: str) -> bool:

    if not _is_remote_desktop_session_auth(auth):

        return False

    desktop_id = str(auth.get("desktop_id") or "").strip()

    if not desktop_id:

        return False

    manager = get_remote_desktop_manager()

    if not hasattr(manager, "get"):

        return False

    connection = manager.get(desktop_id)

    if connection is None or int(connection.user_id) != int(auth["user_id"]):

        return False

    auth_hash = str(auth.get("session_token_hash") or "").strip()

    connection_hash = str(getattr(connection, "session_token_hash", "") or "").strip()

    if auth_hash and connection_hash and not hmac.compare_digest(auth_hash, connection_hash):

        return False

    if not manager.unregister(desktop_id, connection_id=connection.connection_id, reason=reason):

        return False

    try:

        await connection.websocket.close(code=4401)

    except Exception:

        pass

    _mark_remote_desktop_offline(user_id=int(auth["user_id"]), desktop_id=desktop_id, reason=reason)

    return True

async def _ensure_remote_ws_session_active(websocket: WebSocket, auth: Dict[str, Any]) -> None:

    if _remote_ws_session_is_active(auth):

        return

    try:

        await websocket.close(code=4401)

    except Exception:

        pass

    raise WebSocketDisconnect(code=4401)

async def _close_remote_ws_protocol_error(websocket: WebSocket, *, code: int = 4400) -> None:

    try:

        await websocket.close(code=code)

    except Exception:

        pass

    raise WebSocketDisconnect(code=code)

async def _receive_remote_ws_text(websocket: WebSocket) -> str:

    raw = await websocket.receive_text()

    if len(raw.encode("utf-8")) > REMOTE_WS_MAX_MESSAGE_BYTES:

        await _close_remote_ws_protocol_error(websocket, code=4409)

    return raw

def _remote_ws_json_object(raw: str) -> Dict[str, Any]:

    try:

        data = json.loads(raw)

    except json.JSONDecodeError as exc:

        raise ValueError("Malformed remote websocket JSON") from exc

    if not isinstance(data, dict):

        raise ValueError("Remote websocket message must be a JSON object")

    return data

def _websocket_origin_allowed(websocket: WebSocket) -> bool:

    origin = str(websocket.headers.get("origin") or "").strip().rstrip("/")

    if not origin:

        return True

    allowed_origins = {str(item or "").strip().rstrip("/") for item in _cors_allow_origins()}

    return origin in allowed_origins

async def _ensure_websocket_origin_allowed(websocket: WebSocket) -> bool:

    if _websocket_origin_allowed(websocket):

        return True

    try:

        await websocket.close(code=4403)

    except Exception:

        pass

    return False

async def _resolve_ws_token_or_close(websocket: WebSocket) -> Optional[Dict[str, object]]:

    token = websocket.query_params.get("token")

    try:

        return _resolve_ws_token(token)

    except WebSocketDisconnect as exc:

        close_code = int(exc.code or 4401)

        if close_code == 4401:

            try:

                _record_remote_auth_rate_limit_attempt(

                    _remote_ws_auth_rate_limit_keys(websocket, token),

                    max_attempts=REMOTE_WS_AUTH_RATE_LIMIT_MAX_ATTEMPTS,

                )

            except HTTPException:

                close_code = 4408

        await websocket.close(code=close_code)

        return None
