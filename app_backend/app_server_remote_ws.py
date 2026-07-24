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
    last_company_membership_sync_revision = 0

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

            if message.type == "fleet_permission_state":

                try:

                    permission_state = store.record_connection_permission_state(

                        user_id=user_id,

                        desktop_id=desktop_id,

                        policy=dict(message.payload or {}),

                        source="paired_desktop",

                    )

                    capability_payload = dict(
                        dict(message.payload or {}).get("capabilities") or {}
                    )

                    company_id = str(
                        (message.payload or {}).get("company_id")
                        or capability_payload.get("company_id")
                        or ""
                    ).strip()

                    if company_id:

                        try:

                            _get_company_store().sync_published_membership_identities(

                                company_id=company_id,

                                child_computer_id=desktop_id,

                                membership_id=str(
                                    (message.payload or {}).get(
                                        "company_membership_id"
                                    )
                                    or capability_payload.get(
                                        "company_membership_id"
                                    )
                                    or ""
                                ).strip()
                                or None,

                                identities=[

                                    dict(item)

                                    for item in list(
                                        capability_payload.get("targets") or []
                                    )

                                    if isinstance(item, dict)

                                ],

                            )

                        except Exception:

                            logger.exception(

                                "[company] failed syncing child identity directory"

                            )
                        try:
                            bundle = (
                                _get_company_store().issue_child_membership_bundle(
                                    company_id=company_id,
                                    child_computer_id=desktop_id,
                                )
                            )
                            bundle_revision = int(
                                dict(bundle.get("payload") or {}).get(
                                    "company_revision"
                                )
                                or 0
                            )
                            reported_revision = int(
                                (message.payload or {}).get(
                                    "company_revision"
                                )
                                or capability_payload.get(
                                    "company_revision"
                                )
                                or 0
                            )
                            if (
                                bundle_revision > reported_revision
                                and bundle_revision
                                > last_company_membership_sync_revision
                            ):
                                await manager.send_command(
                                    desktop_id=desktop_id,
                                    user_id=user_id,
                                    command_type=(
                                        "fleet_company_membership_sync"
                                    ),
                                    payload={"bundle": bundle},
                                )
                                last_company_membership_sync_revision = (
                                    bundle_revision
                                )
                        except Exception:
                            logger.exception(
                                "[company] failed refreshing child membership cache"
                            )

                    _publish_fleet_delta(

                        user_id=user_id,

                        event_type="fleet_permission_state",

                        payload={"desktop_id": desktop_id, "permission_state": permission_state},

                        origin_channel="worker",

                    )

                except Exception:

                    logger.exception("[fleet] failed applying paired-computer permission state")

                continue

            if message.type == "fleet_upstream_request":

                payload = dict(message.payload or {})

                try:

                    upstream_request = store.record_upstream_request(

                        user_id=user_id,

                        desktop_id=desktop_id,

                        request_id=str(payload.get("request_id") or "").strip(),

                        request_kind=str(payload.get("request_kind") or "").strip(),

                        message=str(payload.get("message") or "").strip(),

                        identity_id=str(payload.get("identity_id") or "").strip() or None,

                        identity_label=str(payload.get("identity_label") or "").strip() or None,

                        task_id=str(payload.get("task_id") or "").strip() or None,

                    )

                    _publish_fleet_delta(

                        user_id=user_id,

                        event_type="fleet_upstream_request",

                        payload={"request": upstream_request},

                        origin_channel="worker",

                    )

                except Exception:

                    logger.exception("[fleet] failed applying upstream request")

                continue

            if message.type == "fleet_delegation_status":

                payload = dict(message.payload or {})

                delegation_id = str(payload.get("delegation_id") or "").strip()

                if delegation_id:

                    try:

                        delegation = store.update_computer_delegation(

                            user_id=user_id,

                            delegation_id=delegation_id,

                            status=str(payload.get("status") or "running"),

                            desktop_id=desktop_id,

                        )

                        _publish_fleet_delta(

                            user_id=user_id,

                            event_type="fleet_delegation_status",

                            payload={"delegation": delegation},

                            origin_channel="worker",

                        )

                    except Exception:

                        logger.exception("[fleet] failed applying computer delegation status")

                continue

            if message.type == "fleet_delegation_report":

                payload = dict(message.payload or {})

                delegation_id = str(payload.get("delegation_id") or "").strip()

                if delegation_id:

                    try:

                        delegation = store.update_computer_delegation(

                            user_id=user_id,

                            delegation_id=delegation_id,

                            status=str(payload.get("status") or "completed"),

                            report=payload,

                            desktop_id=desktop_id,

                        )

                        try:

                            from app_backend.company_runtime_reports import (
                                record_linked_company_report,
                            )

                            delegation_metadata = dict(
                                delegation.get("metadata") or {}
                            )

                            company_id = str(
                                delegation_metadata.get("company_id") or ""
                            ).strip()

                            company = (
                                _get_company_store().get_company(company_id)
                                if company_id
                                else {}
                            )

                            root_computer_id = str(
                                dict(company.get("manifest") or {}).get(
                                    "root_computer_id"
                                )
                                or ""
                            ).strip()

                            record_linked_company_report(

                                company_store=_get_company_store(),

                                company_id=company_id,

                                computer_id=root_computer_id,

                                report=payload,

                                route_metadata=delegation_metadata,

                                delegation_id=delegation_id,

                            )

                        except Exception:

                            logger.exception(

                                "[company] failed linking remote delegation report %s",

                                delegation_id,

                            )

                        _publish_fleet_delta(

                            user_id=user_id,

                            event_type="fleet_delegation_report",

                            payload={"delegation": delegation},

                            origin_channel="worker",

                        )

                        try:

                            from shared.proactive_runtime import append_fleet_report_event

                            delegation_metadata = dict(delegation.get("metadata") or {})

                            append_fleet_report_event(

                                user_id=user_id,

                                report={

                                    **payload,

                                    "delegation_id": delegation_id,

                                    "origin": {

                                        key: delegation_metadata.get(key)

                                        for key in ("origin_manager_session_id", "origin_manager_message_id", "origin_run_id")

                                        if delegation_metadata.get(key)

                                    },

                                },

                            )

                        except Exception:

                            logger.exception("[fleet] failed appending delegation report event")

                    except Exception:

                        logger.exception("[fleet] failed applying computer delegation report")

                continue

            if message.type == "state_snapshot":

                logger.warning("[fleet] ignored legacy paired-computer state snapshot from %s", desktop_id)

                continue

            if message.type == "sync_event":

                logger.warning("[fleet] ignored legacy paired-computer sync event from %s", desktop_id)

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

                        current_task = store.get_worker_task(user_id=user_id, task_id=task_id)

                        task_metadata = dict(current_task.get("metadata") or {})

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

                            raw={

                                **dict(payload.get("raw") or {}),

                                "origin": {

                                    key: task_metadata.get(key)

                                    for key in ("origin_manager_session_id", "origin_manager_message_id", "origin_run_id")

                                    if task_metadata.get(key)

                                },

                            },

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

                        await _try_dispatch_next_fleet_worker_task(

                            user_id=user_id,

                            worker_id=str(report.get("worker_id") or ""),

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
