from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

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

def _preload_tts_engine() -> Dict[str, Any]:

    from mobile_app.backend.voice_runtime import preload_tts_engine

    return preload_tts_engine()

def _runtime_env_file_path() -> Path:

    home = runtime_home()

    root = home if home is not None else _workspace_root()

    root.mkdir(parents=True, exist_ok=True)

    return root / ".env"

def _write_runtime_env_values(updates: dict[str, str]) -> Path:

    env_path = _runtime_env_file_path()

    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True) if env_path.exists() else []

    pending = dict(updates)

    written_keys: set[str] = set()

    next_lines: list[str] = []

    for line in lines:

        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in line:

            next_lines.append(line)

            continue

        key = line.split("=", 1)[0].strip()

        if key not in updates:

            next_lines.append(line)

            continue

        if key in written_keys:

            continue

        value = str(updates[key]).replace("\r", " ").replace("\n", " ").strip()

        next_lines.append(f"{key}={value}\n")

        written_keys.add(key)

        pending.pop(key, None)

    if next_lines and not next_lines[-1].endswith(("\n", "\r")):

        next_lines[-1] += "\n"

    for key, value in pending.items():

        clean_value = str(value).replace("\r", " ").replace("\n", " ").strip()

        next_lines.append(f"{key}={clean_value}\n")

    env_path.write_text("".join(next_lines), encoding="utf-8")

    return env_path

def _remove_runtime_env_values(keys: set[str]) -> Path:

    env_path = _runtime_env_file_path()

    if not env_path.exists():

        return env_path

    remove_keys = {str(key).strip() for key in keys if str(key).strip()}

    next_lines: list[str] = []

    for line in env_path.read_text(encoding="utf-8").splitlines(keepends=True):

        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in line:

            next_lines.append(line)

            continue

        key = line.split("=", 1)[0].strip()

        if key in remove_keys:

            continue

        next_lines.append(line)

    env_path.write_text("".join(next_lines), encoding="utf-8")

    return env_path

def _restore_env_value(key: str, previous_value: Optional[str]) -> None:

    if previous_value is None:

        os.environ.pop(key, None)

    else:

        os.environ[key] = previous_value

def _configure_tts_backend(backend_value: str) -> dict[str, Any]:

    from mobile_app.backend.voice_runtime import (

        APP_TTS_BACKEND_ENV,

        get_tts_runtime_status,

        normalize_tts_backend,

        reset_tts_runtime_cache,

    )

    backend = normalize_tts_backend(backend_value)

    previous_raw = os.environ.get(APP_TTS_BACKEND_ENV)

    os.environ[APP_TTS_BACKEND_ENV] = backend

    reset_tts_runtime_cache()

    selected_status = get_tts_runtime_status()

    if not bool(selected_status.get("ready")):

        _restore_env_value(APP_TTS_BACKEND_ENV, previous_raw)

        reset_tts_runtime_cache()

        status = _voice_runtime_status()

        status["tts_switch"] = {

            "ok": False,

            "requested_backend": backend,

            "backend": status.get("tts_backend"),

            "issues": list(selected_status.get("issues") or ["Selected TTS backend is not ready."]),

        }

        return status

    try:

        tts_warmup = _preload_tts_engine()

    except Exception as exc:

        _restore_env_value(APP_TTS_BACKEND_ENV, previous_raw)

        reset_tts_runtime_cache()

        status = _voice_runtime_status()

        status["tts_switch"] = {

            "ok": False,

            "requested_backend": backend,

            "backend": status.get("tts_backend"),

            "issues": [f"TTS warmup failed: {exc}"],

        }

        return status

    _write_runtime_env_values({APP_TTS_BACKEND_ENV: backend})

    status = _voice_runtime_status()

    status["tts_warmup"] = tts_warmup

    status["tts_switch"] = {

        "ok": True,

        "backend": backend,

        "requested_backend": backend,

    }

    return status

def _normalize_stt_backend(backend_value: str) -> str:

    backend = str(backend_value or "").strip().lower().replace("-", "_")

    if backend in {"local", "local_whisper", "whisper", "whisper_cpp"}:

        return "local_whisper"

    if backend in {"realtime", "realtime_api", "openai_realtime"}:

        return "openai_realtime"

    if backend in {"openai", "openai_transcribe", "openai_request"}:

        return "openai"

    raise ValueError(f"Unsupported STT backend: {backend_value}")

def _configure_stt_backend(backend_value: str) -> dict[str, Any]:

    from mobile_app.backend.voice_runtime import APP_STT_BACKEND_ENV

    backend = _normalize_stt_backend(backend_value)

    previous_raw = os.environ.get(APP_STT_BACKEND_ENV)

    os.environ[APP_STT_BACKEND_ENV] = backend

    selected_status = _voice_runtime_status()

    if not bool(selected_status.get("input_ok", selected_status.get("ok"))):

        _restore_env_value(APP_STT_BACKEND_ENV, previous_raw)

        status = _voice_runtime_status()

        status["stt_switch"] = {

            "ok": False,

            "requested_backend": backend,

            "backend": status.get("stt_backend"),

            "issues": list(selected_status.get("issues") or ["Selected speech input backend is not ready."]),

        }

        return status

    _write_runtime_env_values({APP_STT_BACKEND_ENV: backend})

    status = _voice_runtime_status()

    status["stt_switch"] = {

        "ok": True,

        "backend": backend,

        "requested_backend": backend,

    }

    return status

def _new_voice_draft_state():

    from mobile_app.backend.voice_runtime import new_voice_draft_state

    return new_voice_draft_state()

def _jarvis_fast_final_enabled() -> bool:

    from mobile_app.backend.voice_runtime import jarvis_fast_final_enabled

    return jarvis_fast_final_enabled()

def _jarvis_pending_wait_seconds() -> float:

    from mobile_app.backend.voice_runtime import jarvis_pending_wait_seconds

    return jarvis_pending_wait_seconds()

def _synthesize_assistant_audio_sync(text: str):

    from mobile_app.backend.voice_runtime import synthesize_assistant_audio

    return synthesize_assistant_audio(text)

async def _run_app_chat_turn_lazy(*args, **kwargs):

    from mobile_app.backend.runtime import run_app_chat_turn

    return await run_app_chat_turn(*args, **kwargs)

async def _try_start_manager_review_turn(

    *,

    user_id: int,

    event_run_id: str,

    prompt: str,

    target_chat_id: Optional[str] = None,

) -> Dict[str, Any]:

    bridge = _bridge_for_user(int(user_id))

    try:

        runtime = bridge.load_runtime_session(target_chat_id)

    except Exception:

        runtime = bridge.load_runtime_session(None)

    session_id = str(getattr(getattr(runtime, "session", None), "id", None) or "")

    if not session_id:

        return {"started": False, "reason": "missing_manager_session"}

    if bool(getattr(runtime, "is_processing", False)):

        return {"started": False, "reason": "manager_busy"}

    lease = await bridge.orchestrator.prepare_turn(session_id, origin_channel="proactive_manager_review")

    if lease.busy:

        return {"started": False, "reason": lease.error or "manager_busy"}

    _get_remote_control_store().update_event_run_status(

        user_id=int(user_id),

        event_run_id=event_run_id,

        status="running",

        metadata={"manager_review_started_at": time.time(), "manager_session_id": session_id},

    )

    try:

        result = await _run_app_chat_turn_lazy(

            runtime,

            user_message=prompt,

            source_format="app_system",

            interrupt_policy="none",

            source_client_id="proactive_manager_review",

        )

        _get_remote_control_store().update_event_run_status(

            user_id=int(user_id),

            event_run_id=event_run_id,

            status="completed",

            result=json.dumps(result, ensure_ascii=False, default=str)[:20_000],

            metadata={"manager_review_completed_at": time.time(), "manager_session_id": session_id},

        )

        return {"started": True, "completed": True}

    except Exception as exc:

        _get_remote_control_store().update_event_run_status(

            user_id=int(user_id),

            event_run_id=event_run_id,

            status="failed",

            error=str(exc),

            metadata={"manager_review_failed_at": time.time(), "manager_session_id": session_id},

        )

        return {"started": True, "completed": False, "error": str(exc)}

    finally:

        await bridge.orchestrator.complete_turn(lease)

def _is_active_steering_request(runtime: Any, interrupt_policy: str | None) -> bool:

    policy = str(interrupt_policy or "none").strip().lower()

    return policy in {"steer_now", "after_tool"} and bool(getattr(runtime, "is_processing", False))

def _set_startup_state(state: str, *, error: Optional[str] = None, detail: Optional[str] = None) -> None:

    _APP_RUNTIME_STATUS["startup_state"] = state

    _APP_RUNTIME_STATUS["startup_error"] = error

    _APP_RUNTIME_STATUS["startup_error_detail"] = detail

def _record_runtime_error(message: str, detail: Optional[str] = None) -> None:

    _APP_RUNTIME_STATUS["last_runtime_error"] = message

    _APP_RUNTIME_STATUS["last_runtime_error_detail"] = detail

    _APP_RUNTIME_STATUS["last_runtime_error_at"] = time.time()

def _chat_turn_failure_payload(exc: BaseException) -> dict[str, Any]:

    fallback_message = str(exc).strip() or type(exc).__name__

    payload: dict[str, Any] = {

        "message": fallback_message,

        "code": "chat_turn_failed",

        "retryable": False,

    }

    try:

        from shared.provider_errors import PROVIDER_ERROR, normalize_provider_error

        info = normalize_provider_error(exc, payload_kind="chat")

    except Exception:

        return payload

    if info.error_type == PROVIDER_ERROR and info.status_code is None:

        return payload

    payload.update(

        {

            "message": info.message,

            "code": info.error_type,

            "retryable": bool(info.retryable),

        }

    )

    if info.status_code is not None:

        payload["provider_status_code"] = int(info.status_code)

    return payload

def _record_chat_turn_failure(exc: BaseException) -> dict[str, Any]:

    payload = _chat_turn_failure_payload(exc)

    _record_runtime_error(

        f"Chat turn failed: {payload.get('message') or type(exc).__name__}",

        traceback.format_exc(),

    )

    return payload

def _is_expected_websocket_close_error(exc: BaseException) -> bool:

    if not isinstance(exc, RuntimeError):

        return False

    message = str(exc or "").strip().lower()

    return (

        "close message has been sent" in message

        or "websocket is not connected" in message

    )
