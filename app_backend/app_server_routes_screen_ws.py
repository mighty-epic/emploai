from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.
from shared.provider_failures import get_failed_turn
from shared.provider_availability import active_provider_block, provider_failure_from_block

def register_screen_ws_routes(app):

    @app.get("/api/app/screenshot/current", response_model=ScreenCaptureView)

    async def current_screenshot(

        authorization: Optional[str] = Header(default=None),

        max_width: Optional[int] = None,

        quality: Optional[int] = None,

    ) -> ScreenCaptureView:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Screenshot capture must run on the local desktop backend")

        try:

            safe_quality = max(30, min(int(quality), 85)) if quality is not None else None

            safe_width = max(160, min(int(max_width), 2560)) if max_width is not None else None

            capture = _capture_screen_snapshot(max_width=safe_width, jpeg_quality=safe_quality)

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

        if not await _ensure_websocket_origin_allowed(websocket):

            return

        logger.info("[app] websocket /ws/app/screen connected from %s", websocket.client.host if websocket.client else "unknown")

        send_lock = asyncio.Lock()

        async def send_model(event: RealtimeServerEvent) -> None:

            await _send_realtime_event(websocket, send_lock, event)

        try:

            auth = await _resolve_ws_token_or_close(websocket)

            if auth is None:

                return

            if _is_remote_session_auth(auth):

                await websocket.close(code=4403)

                return

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

        if not await _ensure_websocket_origin_allowed(websocket):

            return

        try:

            auth = await _resolve_ws_token_or_close(websocket)

            if auth is None:

                return

            if not _is_remote_desktop_session_auth(auth):

                await websocket.close(code=4403)

                return

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

    @app.websocket("/ws/app/chat")

    async def chat_ws(websocket: WebSocket) -> None:

        await websocket.accept()

        if not await _ensure_websocket_origin_allowed(websocket):

            return

        logger.info("[app] websocket /ws/app/chat connected from %s", websocket.client.host if websocket.client else "unknown")

        send_lock = asyncio.Lock()

        watch_task: Optional[asyncio.Task[None]] = None

        receive_task: Optional[asyncio.Task[None]] = None

        sync_subscription_id: Optional[str] = None

        effective_session_id: Optional[str] = None

        connection_open = True

        async def send_model(event: RealtimeServerEvent) -> None:

            nonlocal connection_open

            if not connection_open:

                return

            try:

                await _send_realtime_event(websocket, send_lock, event)

            except Exception as exc:

                if _is_expected_websocket_close_error(exc):

                    connection_open = False

                    return

                raise

        try:

            session_id = websocket.query_params.get("session_id")

            requested_session_id = str(session_id or "").strip() or None

            auth = await _resolve_ws_token_or_close(websocket)

            if auth is None:

                return

            if _is_remote_session_auth(auth):

                await websocket.close(code=4403)

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

                runtime = _load_runtime_session_or_409(bridge, requested_session_id)

            except (HTTPException, RuntimeError) as exc:

                detail = getattr(exc, "detail", str(exc))

                await send_model(

                    RealtimeServerEvent(

                        type="error",

                    session_id=requested_session_id,

                        payload={"message": str(detail), "code": "session_unavailable"},

                    )

                )

                return

            try:

                runtime.session.account_user_id = int(auth["user_id"])

            except Exception:

                pass

            effective_session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "").strip() or requested_session_id

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

                    if requested_session_id:

                        return

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

                        if not requested_session_id:

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

            incoming_messages: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=64)

            async def receive_chat_messages() -> None:

                nonlocal connection_open

                try:

                    while True:

                        raw_message = await websocket.receive_text()

                        try:

                            preview = json.loads(raw_message)

                        except json.JSONDecodeError:

                            preview = None

                        if isinstance(preview, dict):

                            preview_text = str(preview.get("text") or "").strip()

                            preview_policy = str(preview.get("interrupt_policy") or "none")

                            preview_session_id = preview.get("session_id") or effective_session_id

                            session_target_valid = (

                                not requested_session_id

                                or str(preview_session_id or "").strip() == requested_session_id

                            )

                            if preview_text and len(preview_text) <= 200_000 and session_target_valid:

                                try:

                                    steering_runtime = _load_runtime_session_or_409(bridge, preview_session_id)

                                except (HTTPException, RuntimeError):

                                    steering_runtime = None

                                steering_enabled = False

                                if steering_runtime is not None:

                                    try:

                                        from app_backend.runtime import _steering_beta_enabled

                                        steering_enabled = _steering_beta_enabled(steering_runtime)

                                    except Exception:

                                        steering_enabled = False

                                if (

                                    steering_runtime is not None

                                    and steering_enabled

                                    and _is_active_steering_request(steering_runtime, preview_policy)

                                ):

                                    steering_client_message_id = str(

                                        preview.get("client_message_id") or ""

                                    ).strip()[:128]

                                    if steering_client_message_id and any(

                                        str(item.get("client_message_id") or "").strip()

                                        == steering_client_message_id

                                        for item in list(getattr(steering_runtime, "chat_history", []) or [])

                                        if isinstance(item, dict)

                                    ):

                                        await send_model(

                                            RealtimeServerEvent(

                                                type="message_ack",

                                                session_id=preview_session_id,

                                                payload={

                                                    "client_message_id": steering_client_message_id,

                                                    "status": "duplicate",

                                                    "retryable": False,

                                                },

                                            )

                                        )

                                        continue



                                    async def acknowledge_steering(payload: Dict[str, Any]) -> None:

                                        if not steering_client_message_id:

                                            return

                                        await send_model(

                                            RealtimeServerEvent(

                                                type="message_ack",

                                                session_id=preview_session_id,

                                                payload={

                                                    "client_message_id": steering_client_message_id,

                                                    "status": str(payload.get("status") or "steering"),

                                                    "retryable": bool(payload.get("retryable", False)),

                                                },

                                            )

                                        )



                                    try:

                                        steering_result = await _run_app_chat_turn_lazy(

                                            steering_runtime,

                                            user_message=preview_text,

                                            source_format=str(preview.get("source_format") or "app_text"),

                                            interrupt_policy=preview_policy,

                                            source_client_id=str(preview.get("source_client_id") or client_id),

                                            client_message_id=steering_client_message_id or None,

                                            message_accepted_callback=acknowledge_steering,

                                            run_mode=preview.get("run_mode"),

                                            plan_action=preview.get("plan_action"),

                                            plan_answer=(

                                                preview.get("plan_answer")

                                                if isinstance(preview.get("plan_answer"), dict)

                                                else None

                                            ),

                                        )

                                    except Exception as exc:

                                        failure_payload = _record_chat_turn_failure(exc)

                                        await acknowledge_steering(

                                            {

                                                "status": "rejected",

                                                "retryable": bool(failure_payload.get("retryable", False)),

                                            }

                                        )

                                        await send_model(

                                            RealtimeServerEvent(

                                                type="error",

                                                session_id=preview_session_id,

                                                payload=failure_payload,

                                            )

                                        )

                                        continue

                                    if steering_result.get("steering"):

                                        try:

                                            steering_runtime.session.account_user_id = int(auth["user_id"])

                                            _mirror_session_snapshot(

                                                user_id=int(auth["user_id"]),

                                                bridge=bridge,

                                                session=steering_runtime.session,

                                                reason="chat_ws_steering",

                                            )

                                        except Exception:

                                            logger.exception("[recovery] failed mirroring chat websocket steering")

                                        await send_model(

                                            RealtimeServerEvent(

                                                type="status",

                                                session_id=preview_session_id,

                                                payload={

                                                    "message": (

                                                        "Beta steering accepted"

                                                        if steering_result.get("steering_status") == "armed"

                                                        else "Beta steering queued for next safe boundary"

                                                    )

                                                },

                                            )

                                        )

                                        continue

                        await incoming_messages.put(raw_message)

                except WebSocketDisconnect:

                    connection_open = False

                except Exception as exc:

                    connection_open = False

                    if not _is_expected_websocket_close_error(exc):

                        logger.exception("[app] chat websocket receive loop failed")

                finally:

                    await incoming_messages.put(None)

            receive_task = asyncio.create_task(receive_chat_messages())

            while True:

                raw = await incoming_messages.get()

                if raw is None:

                    break

                try:

                    data = json.loads(raw)

                except json.JSONDecodeError:

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=effective_session_id,

                            payload={"message": "Malformed chat message ignored", "code": "invalid_message"},

                        )

                    )

                    continue

                if not isinstance(data, dict):

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=effective_session_id,

                            payload={"message": "Chat message must be a JSON object", "code": "invalid_message"},

                        )

                    )

                    continue

                message_type = str(data.get("type") or "chat_message").strip().lower()
                retry_run_id = str(data.get("run_id") or "").strip() if message_type == "retry_failed_turn" else ""
                text = str(data.get("text", "")).strip()
                if retry_run_id:
                    text = "[retry failed turn]"

                req_session_id = data.get("session_id") or effective_session_id

                if requested_session_id and str(req_session_id or "").strip() != requested_session_id:

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=requested_session_id,

                            payload={

                                "message": "Chat socket cannot target a different session",

                                "code": "invalid_session_target",

                            },

                        )

                    )

                    continue

                source_format = str(data.get("source_format") or "app_text")

                message_client_id = str(data.get("source_client_id") or client_id)
                client_message_id = str(data.get("client_message_id") or "").strip()[:128]
                run_mode = data.get("run_mode")
                plan_action = data.get("plan_action")
                plan_answer = data.get("plan_answer") if isinstance(data.get("plan_answer"), dict) else None

                async def send_message_ack(
                    status: str,
                    *,
                    retryable: bool = False,
                    extra: Optional[Dict[str, Any]] = None,
                ) -> None:
                    if not client_message_id:
                        return
                    await send_model(
                        RealtimeServerEvent(
                            type="message_ack",
                            session_id=req_session_id,
                            payload={
                                "client_message_id": client_message_id,
                                "status": status,
                                "retryable": bool(retryable),
                                **dict(extra or {}),
                            },
                        )
                    )

                delivery_kwargs = (
                    {
                        "client_message_id": client_message_id,
                        "message_accepted_callback": lambda payload: send_message_ack(
                            str(payload.get("status") or "accepted"),
                            retryable=bool(payload.get("retryable", False)),
                            extra={
                                key: value
                                for key, value in dict(payload or {}).items()
                                if key not in {"status", "retryable", "client_message_id"}
                            },
                        ),
                    }
                    if client_message_id
                    else {}
                )

                if not text:

                    await send_message_ack("rejected", retryable=False)

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=req_session_id,

                            payload={"message": "Empty message ignored"},

                        )

                    )

                    continue

                try:

                    runtime = _load_runtime_session_or_409(bridge, req_session_id)

                    effective_session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "").strip() or req_session_id

                    try:

                        runtime.session.account_user_id = int(auth["user_id"])

                    except Exception:

                        pass

                    if retry_run_id:
                        failed_turn = get_failed_turn(runtime, retry_run_id)
                        if not failed_turn:
                            raise RuntimeError("The failed turn is no longer available to retry.")
                        if bool(failed_turn.get("retry_consumed")):
                            raise RuntimeError("This failed turn has already been retried.")
                        selected_model = str(data.get("model_id") or "").strip()
                        selected_provider = str(data.get("provider_id") or "").strip().lower()
                        model_key = next(
                            (
                                key
                                for key, config in MODEL_CONFIGS.items()
                                if key == selected_model or str(config.get("id") or "") == selected_model
                            ),
                            None,
                        )
                        if not model_key:
                            raise RuntimeError("Choose a configured model before retrying this turn.")
                        model_provider = str(MODEL_CONFIGS.get(model_key, {}).get("provider") or "").strip().lower()
                        if selected_provider and selected_provider != model_provider:
                            raise RuntimeError("The selected provider does not match the selected model.")
                        provider_model_id = str(MODEL_CONFIGS.get(model_key, {}).get("id") or model_key)
                        provider_block = active_provider_block(model_provider, provider_model_id)
                        if provider_block:
                            await send_model(
                                RealtimeServerEvent(
                                    type="run_failed",
                                    session_id=req_session_id,
                                    payload=provider_failure_from_block(provider_block, run_id=retry_run_id),
                                )
                            )
                            continue
                        runtime.current_model = model_key
                        text = str(failed_turn.get("user_message") or "").strip()
                        if not text:
                            raise RuntimeError("The failed turn no longer contains a request to retry.")

                except (HTTPException, RuntimeError) as exc:

                    detail = getattr(exc, "detail", str(exc))

                    await send_message_ack("rejected", retryable=False)

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=req_session_id,

                            payload={"message": str(detail), "code": "session_unavailable"},

                        )

                    )

                    continue

                if len(text) > 200_000:

                    await send_message_ack("rejected", retryable=False, extra={"message": "Message is too large"})

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=req_session_id,

                            payload={"message": "Message is too large", "code": "message_too_large"},

                        )

                    )

                    continue

                if client_message_id and any(
                    str(item.get("client_message_id") or "").strip() == client_message_id
                    for item in list(getattr(runtime, "chat_history", []) or [])
                    if isinstance(item, dict)
                ):

                    await send_message_ack("duplicate", retryable=False)

                    await send_session_sync(req_session_id, "duplicate_message")

                    continue

                missing_key_payload = _missing_provider_api_key_payload(runtime)

                if missing_key_payload:

                    await send_message_ack("rejected", retryable=False)

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=req_session_id,

                            payload=missing_key_payload,

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

                        message = str(event.get("message", ""))

                        if not _runtime_message_is_user_visible(message):

                            return

                        log_payload = _format_runtime_log_entry(message)

                        await send_model(

                            RealtimeServerEvent(

                                type="log",

                                session_id=req_session_id,

                                payload=log_payload,

                            )

                        )

                    elif kind == "status":

                        message = str(event.get("message", ""))

                        if message and not _runtime_message_is_user_visible(message):

                            return

                        await send_model(

                            RealtimeServerEvent(

                                type="status",

                                session_id=req_session_id,

                                payload={"message": message},

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

                    elif kind == "run_failed":

                        await send_model(

                            RealtimeServerEvent(

                                type="run_failed",

                                session_id=req_session_id,

                                payload={

                                    key: value

                                    for key, value in event.items()

                                    if key != "type"

                                },

                            )

                        )

                interrupt_policy = str(data.get("interrupt_policy", "none"))

                if _is_active_steering_request(runtime, interrupt_policy):

                    try:

                        result = await _run_app_chat_turn_lazy(

                            runtime,

                            user_message=text,

                            source_format=source_format,

                            interrupt_policy=interrupt_policy,

                            source_client_id=message_client_id,
                            **delivery_kwargs,
                            run_mode=run_mode,
                            plan_action=plan_action,
                            plan_answer=plan_answer,

                            log_callback=emit,
                            retry_run_id=retry_run_id or None,

                        )

                    except Exception as exc:

                        payload = _record_chat_turn_failure(exc)

                        await send_message_ack("rejected", retryable=bool(payload.get("retryable", False)))

                        await send_model(

                            RealtimeServerEvent(

                                type="error",

                                session_id=req_session_id,

                                payload=payload,

                            )

                        )

                        continue

                    if result.get("steering"):

                        try:

                            runtime.session.account_user_id = int(auth["user_id"])

                            _mirror_session_snapshot(user_id=int(auth["user_id"]), bridge=bridge, session=runtime.session, reason="chat_ws_steering")

                        except Exception:

                            logger.exception("[recovery] failed mirroring chat websocket steering")

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

                    if result.get("busy"):

                        await send_message_ack("rejected", retryable=True)

                        await send_model(

                            RealtimeServerEvent(

                                type="warning",

                                session_id=req_session_id,

                                payload={"message": "Session is already processing another message"},

                            )

                        )

                        continue

                lease = await bridge.orchestrator.prepare_turn(

                    str(getattr(getattr(runtime, "session", None), "id", "") or req_session_id or ""),

                    origin_channel="app",

                )

                if lease.busy:

                    await send_message_ack("rejected", retryable=True)

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=req_session_id,

                            payload={"message": lease.error or "Session is already processing another message"},

                        )

                    )

                    continue

                try:

                    try:

                        result = await _run_app_chat_turn_lazy(

                            runtime,

                            user_message=text,

                            source_format=source_format,

                            interrupt_policy=interrupt_policy,

                            source_client_id=message_client_id,
                            **delivery_kwargs,
                            run_mode=run_mode,
                            plan_action=plan_action,
                            plan_answer=plan_answer,

                            log_callback=emit,
                            retry_run_id=retry_run_id or None,

                        )

                    except Exception as exc:

                        payload = _record_chat_turn_failure(exc)

                        await send_message_ack("rejected", retryable=bool(payload.get("retryable", False)))

                        await send_model(

                            RealtimeServerEvent(

                                type="error",

                                session_id=req_session_id,

                                payload=payload,

                            )

                        )

                        continue

                finally:

                    await bridge.orchestrator.complete_turn(lease)

                if result.get("busy"):

                    await send_message_ack("rejected", retryable=True)

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=req_session_id,

                            payload={"message": "Session is already processing another message"},

                        )

                    )

                    continue

                if result.get("steering"):

                    try:

                        runtime.session.account_user_id = int(auth["user_id"])

                        _mirror_session_snapshot(user_id=int(auth["user_id"]), bridge=bridge, session=runtime.session, reason="chat_ws_steering")

                    except Exception:

                        logger.exception("[recovery] failed mirroring chat websocket steering")

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

                if result.get("failure"):

                    continue

                final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or req_session_id

                try:

                    runtime.session.account_user_id = int(auth["user_id"])

                    _sync_session_workspace_binding(user_id=int(auth["user_id"]), auth=auth, session=runtime.session)

                    _mirror_session_snapshot(user_id=int(auth["user_id"]), bridge=bridge, session=runtime.session, reason="chat_ws_turn")

                except Exception:

                    logger.exception("[recovery] failed syncing chat websocket session")

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

                            "message": "Chat websocket failed. Reconnect and try again.",

                            "code": "chat_websocket_error",

                        },

                    )

                )

            except Exception:

                pass

            return

        finally:

            if receive_task:

                receive_task.cancel()

            if watch_task:

                watch_task.cancel()

            if sync_subscription_id:

                get_channel_sync_hub().unsubscribe(sync_subscription_id)
