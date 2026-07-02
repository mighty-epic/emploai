from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.
from shared.standalone_policy import mobile_connection_enabled

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

                await _handle_remote_screen_ws(websocket, auth, send_lock)

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

    @app.websocket("/ws/remote/mobile")

    async def remote_mobile_ws(websocket: WebSocket) -> None:

        await websocket.accept()

        if not mobile_connection_enabled():

            await websocket.close(code=4404)

            return

        if not await _ensure_websocket_origin_allowed(websocket):

            return

        try:

            auth = await _resolve_ws_token_or_close(websocket)

            if auth is None:

                return

            if not _is_remote_mobile_session_auth(auth):

                await websocket.close(code=4403)

                return

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

        if not await _ensure_websocket_origin_allowed(websocket):

            return

        logger.info("[app] websocket /ws/app/chat connected from %s", websocket.client.host if websocket.client else "unknown")

        send_lock = asyncio.Lock()

        watch_task: Optional[asyncio.Task[None]] = None

        sync_subscription_id: Optional[str] = None

        effective_session_id: Optional[str] = None

        async def send_model(event: RealtimeServerEvent) -> None:

            await _send_realtime_event(websocket, send_lock, event)

        try:

            session_id = websocket.query_params.get("session_id")

            requested_session_id = str(session_id or "").strip() or None

            auth = await _resolve_ws_token_or_close(websocket)

            if auth is None:

                return

            if _is_remote_session_auth(auth):

                if not _is_remote_mobile_session_auth(auth):

                    await websocket.close(code=4403)

                    return

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

            while True:

                raw = await websocket.receive_text()

                data = json.loads(raw)

                text = str(data.get("text", "")).strip()

                req_session_id = data.get("session_id") or effective_session_id

                source_format = str(data.get("source_format") or "app_text")

                message_client_id = str(data.get("source_client_id") or client_id)

                if not text:

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

                except (HTTPException, RuntimeError) as exc:

                    detail = getattr(exc, "detail", str(exc))

                    await send_model(

                        RealtimeServerEvent(

                            type="warning",

                            session_id=req_session_id,

                            payload={"message": str(detail), "code": "session_unavailable"},

                        )

                    )

                    continue

                missing_key_payload = _missing_provider_api_key_payload(runtime)

                if missing_key_payload:

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

                interrupt_policy = str(data.get("interrupt_policy", "none"))

                if _is_active_steering_request(runtime, interrupt_policy):

                    try:

                        result = await _run_app_chat_turn_lazy(

                            runtime,

                            user_message=text,

                            source_format=source_format,

                            interrupt_policy=interrupt_policy,

                            source_client_id=message_client_id,

                            log_callback=emit,

                        )

                    except Exception as exc:

                        payload = _record_chat_turn_failure(exc)

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

                            log_callback=emit,

                        )

                    except Exception as exc:

                        payload = _record_chat_turn_failure(exc)

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
