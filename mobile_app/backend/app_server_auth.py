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

def _remote_auth_login_response_from_result(result: Dict[str, Any], *, actor_kind: str) -> RemoteAuthLoginResponse:

    expires_at = float(result.get("expires_at") or time.time())

    expires_in_seconds = max(0, int(expires_at - time.time()))

    return RemoteAuthLoginResponse(

        session_token=str(result.get("session_token") or ""),

        expires_in_seconds=expires_in_seconds,

        actor_kind=actor_kind,

        user=RemoteUserView.model_validate(result.get("user") or {}),

        desktop=RemoteDesktopView.model_validate(result["desktop"]) if result.get("desktop") else None,

        mobile=RemoteMobileView.model_validate(result["mobile"]) if result.get("mobile") else None,

        remember_me=bool(result.get("remember_me")),

    )

def _remote_auth_challenge_response(challenge: Dict[str, Any]) -> RemoteAuthOtpChallengeResponse:

    return RemoteAuthOtpChallengeResponse(

        challenge_id=str(challenge.get("challenge_id") or ""),

        email=str(challenge.get("email") or ""),

        purpose=str(challenge.get("purpose") or "login_verify"),

        expires_in_seconds=max(0, int(challenge.get("expires_in_seconds") or 0)),

        resend_available_in_seconds=max(0, int(challenge.get("resend_available_in_seconds") or 0)),

    )

def _invalidate_remote_auth_challenge(challenge: Dict[str, Any]) -> None:

    challenge_id = str((challenge or {}).get("challenge_id") or "").strip()

    if not challenge_id:

        return

    try:

        _get_remote_control_store().invalidate_auth_otp_challenge(challenge_id=challenge_id)

    except Exception:

        logger.exception("[auth] failed invalidating undelivered OTP challenge")

async def _send_remote_auth_otp_email(*, email: str, code: str, purpose: str) -> None:

    clean_email = str(email or "").strip()

    clean_code = re.sub(r"\D+", "", str(code or ""))

    if not clean_email or len(clean_code) != 6:

        raise ValueError("Verification email is invalid")

    configured_backend = os.getenv(AUTH_EMAIL_BACKEND_ENV, "").strip().casefold()
    resend_api_key_configured = bool(os.getenv(RESEND_API_KEY_ENV, "").strip())
    if configured_backend:
        backend = configured_backend
    elif resend_api_key_configured:
        backend = "resend"
    else:
        raise RuntimeError("Verification email delivery is not configured. Try Google sign-in or contact support.")

    if _production_mode_enabled() and backend == "console":

        raise RuntimeError(f"{AUTH_EMAIL_BACKEND_ENV}=resend is required when {DEPLOYMENT_ENV_ENV}=production")

    sender = os.getenv(AUTH_EMAIL_FROM_ENV, AUTH_EMAIL_DEFAULT_FROM).strip() or AUTH_EMAIL_DEFAULT_FROM

    purpose_text = "finish creating your EmploAI account" if purpose == "signup_verify" else "sign in to EmploAI"

    subject = "Your EmploAI verification code"

    text = (

        f"Use this verification code to {purpose_text}: {clean_code}\n\n"

        "This code expires in 10 minutes. If you did not request it, you can ignore this email."

    )

    html = (

        "<div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#111827\">"

        "<h2>Your EmploAI verification code</h2>"

        f"<p>Use this code to {html_escape(purpose_text)}:</p>"

        f"<p style=\"font-size:28px;font-weight:700;letter-spacing:6px\">{html_escape(clean_code)}</p>"

        "<p>This code expires in 10 minutes. If you did not request it, you can ignore this email.</p>"

        "</div>"

    )

    if backend == "console":

        logger.warning("Auth OTP for %s: %s", clean_email, clean_code)

        return

    if backend != "resend":

        raise RuntimeError(f"Unsupported email backend: {backend}")

    api_key = os.getenv(RESEND_API_KEY_ENV, "").strip()

    if not api_key:

        raise RuntimeError("Resend email backend is not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:

        response = await client.post(

            "https://api.resend.com/emails",

            headers={

                "Authorization": f"Bearer {api_key}",

                "Content-Type": "application/json",

            },

            json={

                "from": sender,

                "to": [clean_email],

                "subject": subject,

                "text": text,

                "html": html,

            },

        )

    if response.status_code >= 400:

        detail = response.text[:500]

        logger.warning("Resend auth OTP email failed status=%s detail=%s", response.status_code, detail)

        raise RuntimeError("Verification email could not be sent. Try again later.")

def _google_oauth_client_id() -> str:

    return os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()

def _google_oauth_client_secret() -> str:

    return os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

def _google_oauth_redirect_uri() -> str:

    return os.getenv("GOOGLE_OAUTH_REDIRECT_URI", GOOGLE_OAUTH_DEFAULT_REDIRECT_URI).strip() or GOOGLE_OAUTH_DEFAULT_REDIRECT_URI

def _google_oauth_configured() -> bool:

    return bool(_google_oauth_client_id() and _google_oauth_client_secret())

def _google_oauth_auth_url(*, state: str) -> str:

    query = urlencode(

        {

            "client_id": _google_oauth_client_id(),

            "redirect_uri": _google_oauth_redirect_uri(),

            "response_type": "code",

            "scope": "openid email profile",

            "state": state,

            "access_type": "online",

            "prompt": "select_account",

        }

    )

    return f"{GOOGLE_OAUTH_AUTH_URL}?{query}"

async def _exchange_google_oauth_code(code: str) -> Dict[str, Any]:

    async with httpx.AsyncClient(timeout=30.0) as client:

        response = await client.post(

            GOOGLE_OAUTH_TOKEN_URL,

            data={

                "code": code,

                "client_id": _google_oauth_client_id(),

                "client_secret": _google_oauth_client_secret(),

                "redirect_uri": _google_oauth_redirect_uri(),

                "grant_type": "authorization_code",

            },

            headers={"Accept": "application/json"},

        )

    try:

        payload = response.json()

    except Exception:

        payload = {"error_description": response.text}

    if response.status_code >= 400:

        detail = payload.get("error_description") or payload.get("error") or "Google token exchange failed"

        raise ValueError(str(detail))

    return payload if isinstance(payload, dict) else {}

def _verify_google_id_token(id_token_value: str) -> Dict[str, Any]:

    if not id_token_value:

        raise ValueError("Google did not return an ID token")

    from google.auth.transport import requests as google_requests

    from google.oauth2 import id_token as google_id_token

    claims = google_id_token.verify_oauth2_token(

        id_token_value,

        google_requests.Request(),

        _google_oauth_client_id(),

    )

    issuer = str(claims.get("iss") or "")

    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:

        raise ValueError("Google ID token issuer is invalid")

    return claims

def _google_callback_page(*, title: str, message: str, is_error: bool = False) -> Response:

    accent = "#ef4444" if is_error else "#22c55e"

    body = f"""<!doctype html>

<html lang=\"en\">

<head>

  <meta charset=\"utf-8\" />

  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />

  <title>{html_escape(title)}</title>

  <style>

    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0b1020; color: #e8f0ff; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}

    main {{ width: min(520px, calc(100vw - 40px)); }}

    .mark {{ width: 48px; height: 48px; border-radius: 12px; background: {accent}; margin-bottom: 18px; }}

    h1 {{ font-size: 28px; margin: 0 0 10px; }}

    p {{ color: #b8c7e6; line-height: 1.55; margin: 0; }}

  </style>

</head>

<body>

  <main>

    <div class=\"mark\"></div>

    <h1>{html_escape(title)}</h1>

    <p>{html_escape(message)}</p>

  </main>

</body>

</html>"""

    return Response(content=body, media_type="text/html")

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

    mobile_id = str(auth.get("mobile_id") or "").strip() or None

    return _get_remote_control_store().is_session_token_hash_active(

        token_hash=token_hash,

        user_id=user_id,

        actor_kind=actor_kind or None,

        desktop_id=desktop_id if actor_kind == "desktop" else None,

        mobile_id=mobile_id if actor_kind == "mobile" else None,

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
