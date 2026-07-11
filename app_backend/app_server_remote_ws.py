from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

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
