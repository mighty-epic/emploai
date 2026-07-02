from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

async def _handle_remote_chat_ws(websocket: WebSocket, auth: Dict[str, Any]) -> None:

    send_lock = asyncio.Lock()

    watch_task: Optional[asyncio.Task[None]] = None

    sync_subscription_id: Optional[str] = None

    client_id = str(websocket.query_params.get("client_id") or secrets.token_hex(8))

    requested_session_id = str(websocket.query_params.get("session_id") or "").strip() or None

    effective_session_id = requested_session_id or _remote_current_session_id(auth)

    explicit_target_session_id: Optional[str] = None

    last_sync_version = -1

    async def send_model(event: RealtimeServerEvent) -> None:

        await _send_realtime_event(websocket, send_lock, event)

    def subscribed_session_id() -> Optional[str]:

        return explicit_target_session_id or effective_session_id or requested_session_id or _remote_current_session_id(auth)

    async def send_session_sync(reason: str) -> None:

        nonlocal effective_session_id, last_sync_version

        state = _remote_shared_state(auth)

        last_sync_version = int(state.get("sync_version", 0) or 0)

        next_session_id = subscribed_session_id()

        detail = None

        if next_session_id:

            effective_session_id = next_session_id

            try:

                detail = _remote_session_detail_view(auth, next_session_id)

            except HTTPException:

                detail = None

        sync_payload = {

            "reason": reason,

            "sessions": [item.model_dump() for item in _remote_session_summary_views(auth)],

            "shared_state": state,

        }

        if detail is not None:

            sync_payload["session"] = detail.model_dump()

        await send_model(

            RealtimeServerEvent(

                type="session_sync",

                session_id=next_session_id,

                payload=sync_payload,

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

        if event_type == "session_sync":

            payload = dict(event.get("payload") or {})

            detail = payload.get("session") if isinstance(payload.get("session"), dict) else {}

            next_session_id = str(

                detail.get("id")

                or event.get("session_id")

                or effective_session_id

                or ""

            ).strip()

            target_session_id = subscribed_session_id()

            if next_session_id and target_session_id and next_session_id != target_session_id:

                return

            if next_session_id:

                effective_session_id = next_session_id

                await send_model(

                    RealtimeServerEvent(

                        type="session_sync",

                        session_id=next_session_id,

                        payload=payload,

                    )

                )

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

                if not _remote_ws_session_is_active(auth):

                    try:

                        await websocket.close(code=4401)

                    except Exception:

                        pass

                    return

                state = _remote_shared_state(auth)

                current_sync_version = int(state.get("sync_version", 0) or 0)

                current_session_id = explicit_target_session_id or _remote_current_session_id(auth) or effective_session_id

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

            raw = await _receive_remote_ws_text(websocket)

            await _ensure_remote_ws_session_active(websocket, auth)

            try:

                data = _remote_ws_json_object(raw)

            except ValueError:

                await _close_remote_ws_protocol_error(websocket)

            text = str(data.get("text", "")).strip()

            if len(text) > REMOTE_CHAT_MAX_TEXT_CHARS:

                await _close_remote_ws_protocol_error(websocket, code=4409)

            if not text:

                await send_model(RealtimeServerEvent(type="warning", payload={"message": "Empty message ignored"}))

                continue

            target_session_id = str(data.get("session_id") or effective_session_id or "").strip() or None

            if target_session_id:

                explicit_target_session_id = target_session_id

                effective_session_id = target_session_id

            if target_session_id:

                await send_model(

                    RealtimeServerEvent(

                        type="user_message",

                        session_id=target_session_id,

                        payload={

                            "message": {

                                "role": "user",

                                "content": text,

                                "timestamp": datetime.now(timezone.utc).isoformat(),

                                "display_label": "You",

                                "channel": "app",

                                "pending": True,

                            }

                        },

                    )

                )

            try:

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

            except HTTPException as exc:

                await send_model(

                    RealtimeServerEvent(

                        type="error",

                        session_id=target_session_id,

                        payload={"message": str(exc.detail or "Unable to send message to the paired desktop")},

                    )

                )

                continue

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

    try:

        connection = manager.register(

            user_id=user_id,

            desktop_id=desktop_id,

            websocket=websocket,

            loop=asyncio.get_running_loop(),

            session_token_hash=str(auth.get("session_token_hash") or "").strip() or None,

        )

    except RuntimeError:

        logger.exception("[remote] refused desktop websocket registration for %s", desktop_id)

        await websocket.close(code=4403)

        return

    store.mark_desktop_connection(user_id=user_id, desktop_id=desktop_id, status="connected", detail="desktop websocket connected")

    _publish_fleet_delta(

        user_id=user_id,

        event_type="fleet_worker_presence",

        payload={"desktop_id": desktop_id, "status": "connected"},

        origin_channel="desktop",

    )

    get_channel_sync_hub().publish(

        user_id=user_id,

        event={

            "type": "status",

            "session_id": None,

            "origin_channel": "app",

            "payload": {"message": "paired desktop connected"},

        },

    )

    broker_task = asyncio.create_task(

        pump_remote_desktop_command_broker(

            store=store,

            user_id=user_id,

            desktop_id=desktop_id,

            connection=connection,

            manager=manager,

        )

    )

    try:

        while True:

            raw = await _receive_remote_ws_text(websocket)

            await _ensure_remote_ws_session_active(websocket, auth)

            try:

                message = RemoteDesktopSocketMessage.model_validate_json(raw)

            except Exception:

                await _close_remote_ws_protocol_error(websocket)

            if not manager.is_active_connection(desktop_id, connection.connection_id):

                logger.info("[remote] ignoring stale desktop websocket message for %s", desktop_id)

                break

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

            if message.type == "fleet_task_status":

                payload = dict(message.payload or {})

                task_id = str(payload.get("task_id") or "").strip()

                status = str(payload.get("status") or "").strip()

                if task_id and status:

                    try:

                        task = store.update_worker_task_status(

                            user_id=user_id,

                            task_id=task_id,

                            status=status,

                            metadata=dict(payload.get("metadata") or {}),

                        )

                        get_channel_sync_hub().publish(

                            user_id=user_id,

                            event={

                                "type": "status",

                                "session_id": None,

                                "origin_channel": "app",

                                "payload": {

                                    "message": f"Fleet task {task.get('task_id')} is {task.get('status')}",

                                    "fleet_task": task,

                                },

                            },

                        )

                        _publish_fleet_delta(

                            user_id=user_id,

                            event_type="fleet_task_status",

                            payload={"task": task},

                            origin_channel="worker",

                        )

                        try:

                            from shared.proactive_runtime import append_fleet_status_event

                            append_fleet_status_event(user_id=user_id, task=task)

                        except Exception:

                            logger.exception("[fleet] failed appending proactive task status event")

                    except Exception:

                        logger.exception("[fleet] failed applying worker task status")

                continue

            if message.type == "fleet_task_report":

                payload = dict(message.payload or {})

                task_id = str(payload.get("task_id") or "").strip()

                if task_id:

                    try:

                        report = store.complete_worker_task_report(

                            user_id=user_id,

                            task_id=task_id,

                            status=str(payload.get("status") or "completed"),

                            summary=str(payload.get("summary") or "Task completed."),

                            evidence=list(payload.get("evidence") or []),

                            artifacts=list(payload.get("artifacts") or []),

                            blockers=list(payload.get("blockers") or []),

                            confidence=payload.get("confidence"),

                            next_suggested_action=payload.get("next_suggested_action"),

                            raw=dict(payload.get("raw") or {}),

                        )

                        get_channel_sync_hub().publish(

                            user_id=user_id,

                            event={

                                "type": "status",

                                "session_id": None,

                                "origin_channel": "app",

                                "payload": {

                                    "message": f"Fleet task report completed: {report.get('status')}",

                                    "fleet_report": report,

                                },

                            },

                        )

                        _publish_fleet_delta(

                            user_id=user_id,

                            event_type="fleet_task_report",

                            payload={"report": report},

                            origin_channel="worker",

                        )

                        try:

                            from shared.proactive_runtime import append_fleet_report_event

                            append_fleet_report_event(user_id=user_id, report=report)

                        except Exception:

                            logger.exception("[fleet] failed appending proactive report event")

                    except Exception:

                        logger.exception("[fleet] failed applying worker task report")

                continue

            if message.type == "command_result":

                get_remote_desktop_manager().resolve_command_reply(

                    desktop_id=desktop_id,

                    connection_id=connection.connection_id,

                    command_id=message.command_id,

                    payload=message.payload or {},

                )

                store.complete_remote_desktop_command(

                    command_id=str(message.command_id or ""),

                    user_id=user_id,

                    desktop_id=desktop_id,

                    ok=bool((message.payload or {}).get("ok", True)),

                    payload=message.payload or {},

                )

                continue

            if message.type == "status":

                status_payload = dict(message.payload or {})

                status_payload["message"] = str(status_payload.get("message") or "")

                get_channel_sync_hub().publish(

                    user_id=user_id,

                    event={

                        "type": "status",

                        "session_id": status_payload.get("session_id"),

                        "origin_channel": "app",

                        "payload": status_payload,

                    },

                )

                continue

    finally:

        broker_task.cancel()

        try:

            await broker_task

        except asyncio.CancelledError:

            pass

        if manager.unregister(connection.desktop_id, connection_id=connection.connection_id):

            store.mark_desktop_connection(

                user_id=user_id,

                desktop_id=desktop_id,

                status="offline",

                detail="desktop websocket disconnected",

            )

            _publish_fleet_delta(

                user_id=user_id,

                event_type="fleet_worker_presence",

                payload={"desktop_id": desktop_id, "status": "offline"},

                origin_channel="desktop",

            )
