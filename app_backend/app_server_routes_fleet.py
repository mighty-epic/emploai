from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

def register_fleet_routes(app):

    def _require_remote_desktop_auth(authorization: Optional[str]) -> Dict[str, Any]:

        auth = _resolve_token(authorization)

        if not _is_remote_session_auth(auth):
            return _standalone_manager_auth(auth)

        if str(auth.get("actor_kind") or "") != "desktop":

            raise HTTPException(status_code=403, detail="Signed-in desktop session required")

        if not str(auth.get("desktop_id") or "").strip():

            raise HTTPException(status_code=400, detail="No desktop is available for this fleet action")

        return auth

    def _require_fleet_manager_auth(authorization: Optional[str]) -> Dict[str, Any]:

        auth = _resolve_token(authorization)

        if not _is_remote_session_auth(auth):

            return _standalone_manager_auth(auth)

        desktop_id = str(auth.get("desktop_id") or "").strip()

        if not desktop_id:

            desktop_id = _remote_desktop_id_for_command(auth) or ""

        if not desktop_id:

            desktop_id = _get_remote_control_store().paired_desktop_id_for_payload(auth) or ""

        if not desktop_id:

            state = _get_remote_control_store().get_shared_state(user_id=int(auth["user_id"]))

            desktop_id = str(state.get("current_desktop_id") or "").strip()

        if not desktop_id:

            raise HTTPException(status_code=400, detail="No manager desktop is available for this fleet action")

        enriched = dict(auth)

        enriched["desktop_id"] = desktop_id

        return enriched

    def _standalone_manager_auth(auth: Dict[str, Any]) -> Dict[str, Any]:

        user_id = int(auth.get("user_id") or 0)

        device_id = str(auth.get("device_id") or "").strip()

        if not device_id:

            raise HTTPException(status_code=403, detail="Local desktop session required")

        desktop = _get_remote_control_store().ensure_standalone_manager_desktop(

            user_id=user_id,

            display_name=str(auth.get("device_name") or "EmploAI Desktop"),

            device_platform=str(auth.get("device_platform") or "desktop-electron"),

            device_key=f"local-app:{device_id}",

        )

        enriched = dict(auth)

        enriched["auth_kind"] = "local_app"

        enriched["actor_kind"] = "desktop"

        enriched["desktop_id"] = str(desktop.get("desktop_id") or "")

        enriched["desktop_name"] = str(desktop.get("display_name") or "EmploAI Desktop")

        return enriched

    def _fleet_snapshot_desktop_id(auth: Dict[str, Any]) -> Optional[str]:

        desktop_id = str(auth.get("desktop_id") or "").strip()

        if not desktop_id:

            desktop_id = _get_remote_control_store().paired_desktop_id_for_payload(auth) or ""

        if not desktop_id:

            desktop_id = _remote_desktop_id_for_command(auth) or ""

        if not desktop_id:

            state = _get_remote_control_store().get_shared_state(user_id=int(auth["user_id"]))

            desktop_id = str(state.get("current_desktop_id") or "").strip()

        return desktop_id or None

    app.include_router(

        create_fleet_enrollment_router(

            FleetEnrollmentRouterDeps(

                require_fleet_manager_auth=_require_fleet_manager_auth,

                get_store=_get_remote_control_store,

                publish_fleet_delta=_publish_fleet_delta,

                check_rate_limit=_check_remote_auth_rate_limit,

                remote_auth_rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,

                remote_session_ttl_seconds=REMOTE_SESSION_TTL_SECONDS,

            )

        )

    )

    @app.get("/api/fleet/snapshot", response_model=FleetSnapshotResponse)

    async def fleet_snapshot(authorization: Optional[str] = Header(default=None)) -> FleetSnapshotResponse:

        auth = _resolve_token(authorization)

        if not _is_remote_session_auth(auth):

            auth = _standalone_manager_auth(auth)

        snapshot = _get_remote_control_store().get_fleet_snapshot(

            user_id=int(auth["user_id"]),

            desktop_id=_fleet_snapshot_desktop_id(auth),

        )

        return FleetSnapshotResponse.model_validate(snapshot)

    @app.get("/api/fleet/identities", response_model=list[FleetIdentityView])

    async def fleet_identities(authorization: Optional[str] = Header(default=None)) -> list[FleetIdentityView]:

        auth = _resolve_token(authorization)

        if not _is_remote_session_auth(auth):

            auth = _standalone_manager_auth(auth)

        snapshot = _get_remote_control_store().get_fleet_snapshot(

            user_id=int(auth["user_id"]),

            desktop_id=_fleet_snapshot_desktop_id(auth),

        )

        return [FleetIdentityView.model_validate(item) for item in list(snapshot.get("identities") or [])]

    @app.put("/api/fleet/active-identity", response_model=FleetActiveIdentityResponse)

    async def fleet_set_active_identity(

        request: FleetSetActiveIdentityRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetActiveIdentityResponse:

        auth = _resolve_token(authorization)

        if not _is_remote_session_auth(auth):

            auth = _standalone_manager_auth(auth)

        try:

            result = _get_remote_control_store().set_active_fleet_identity(

                user_id=int(auth["user_id"]),

                identity_id=request.identity_id,

                selected_chat_id=request.selected_chat_id,

                source=request.source or str(auth.get("actor_kind") or "app"),

                desktop_id=_fleet_snapshot_desktop_id(auth),

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_identity_changed",

            payload=result,

            origin_channel=request.source or str(auth.get("actor_kind") or "app"),

        )

        return FleetActiveIdentityResponse.model_validate(result)

    @app.put("/api/fleet/identities/{identity_id}/active-chat", response_model=FleetActiveIdentityResponse)

    async def fleet_set_identity_active_chat(

        identity_id: str,

        request: FleetSetActiveChatRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetActiveIdentityResponse:

        auth = _resolve_token(authorization)

        if not _is_remote_session_auth(auth):

            auth = _standalone_manager_auth(auth)

        try:

            result = _get_remote_control_store().set_active_chat_for_fleet_identity(

                user_id=int(auth["user_id"]),

                identity_id=identity_id,

                chat_id=request.chat_id,

                source=request.source or str(auth.get("actor_kind") or "app"),

                desktop_id=_fleet_snapshot_desktop_id(auth),

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_identity_changed",

            payload=result,

            origin_channel=request.source or str(auth.get("actor_kind") or "app"),

        )

        return FleetActiveIdentityResponse.model_validate(result)

    @app.post("/api/fleet/groups")

    async def fleet_create_group(

        request: FleetGroupRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        try:

            group = _get_remote_control_store().create_or_update_group(

                user_id=int(auth["user_id"]),

                display_name=request.display_name,

                description=request.description,

                worker_ids=request.worker_ids,

                metadata=request.metadata,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_group_changed",

            payload={"group": group},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return group

    @app.put("/api/fleet/groups/{group_id}")

    async def fleet_update_group(

        group_id: str,

        request: FleetGroupRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        try:

            group = _get_remote_control_store().create_or_update_group(

                user_id=int(auth["user_id"]),

                group_id=group_id,

                display_name=request.display_name,

                description=request.description,

                worker_ids=request.worker_ids,

                metadata=request.metadata,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_group_changed",

            payload={"group": group},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return group

    @app.put("/api/fleet/groups/{group_id}/workers")

    async def fleet_set_group_workers(

        group_id: str,

        request: FleetGroupMembershipRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        try:

            group = _get_remote_control_store().set_group_workers(

                user_id=int(auth["user_id"]),

                group_id=group_id,

                worker_ids=request.worker_ids,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_group_changed",

            payload={"group": group},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return group

    @app.delete("/api/fleet/groups/{group_id}")

    async def fleet_delete_group(

        group_id: str,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="fleet_group_delete",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"group_id": group_id},

        )

        try:

            result = _get_remote_control_store().delete_group(user_id=int(auth["user_id"]), group_id=group_id)

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_group_changed",

            payload={"deleted_group_id": group_id, "result": result},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return result

    @app.post("/api/fleet/workers/local", response_model=FleetWorkerView)

    async def fleet_create_local_worker(

        request: FleetCreateLocalWorkerRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetWorkerView:

        auth = _require_fleet_manager_auth(authorization)

        try:

            worker = _get_remote_control_store().create_local_worker(

                user_id=int(auth["user_id"]),

                desktop_id=str(auth["desktop_id"]),

                display_name=request.display_name,

                metadata=request.metadata,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_worker_presence",

            payload={"worker": worker, "reason": "created"},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return FleetWorkerView.model_validate(worker)

    @app.put("/api/fleet/workers/{worker_id}", response_model=FleetWorkerView)

    async def fleet_update_worker(

        worker_id: str,

        request: FleetWorkerUpdateRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetWorkerView:

        auth = _require_fleet_manager_auth(authorization)

        if not request.display_name and request.queue_policy is None:

            try:

                worker = _get_remote_control_store().get_worker(user_id=int(auth["user_id"]), worker_id=worker_id)

            except KeyError as exc:

                raise HTTPException(status_code=404, detail=str(exc)) from exc

            return FleetWorkerView.model_validate(worker)

        try:

            store = _get_remote_control_store()

            worker = (

                store.rename_worker(

                    user_id=int(auth["user_id"]),

                    worker_id=worker_id,

                    display_name=request.display_name,

                )

                if request.display_name

                else store.get_worker(user_id=int(auth["user_id"]), worker_id=worker_id)

            )

            if request.queue_policy is not None:

                worker = store.set_worker_queue_policy(

                    user_id=int(auth["user_id"]),

                    worker_id=worker_id,

                    queue_policy=request.queue_policy,

                )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_worker_presence",

            payload={

                "worker": worker,

                "reason": "queue_policy_updated" if request.queue_policy is not None else "renamed",

            },

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return FleetWorkerView.model_validate(worker)

    @app.post("/api/fleet/workers/{worker_id}/stop")

    async def fleet_stop_worker(

        worker_id: str,

        request: FleetStopWorkerRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        try:

            result = await _stop_fleet_worker_active_task(

                user_id=int(auth["user_id"]),

                worker_id=worker_id,

                reason=request.reason,

                metadata=request.metadata,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_task_status",

            payload=result,

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return result

    @app.post("/api/fleet/workers/{worker_id}/preview")

    async def fleet_request_worker_preview(worker_id: str, authorization: Optional[str] = Header(default=None)) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        store = _get_remote_control_store()

        try:

            worker = store.get_worker(user_id=int(auth["user_id"]), worker_id=worker_id)

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        payload = await request_fleet_worker_preview(

            store=store,

            remote_desktop_manager=get_remote_desktop_manager(),

            user_id=int(auth["user_id"]),

            worker=worker,

            requested_by=str(auth.get("actor_kind") or "app"),

            is_remote_session_active=_remote_desktop_connection_session_is_active,

            is_desktop_unavailable_error=_command_error_implies_desktop_unavailable,

            mark_desktop_offline=_mark_remote_desktop_offline_if_no_live_connection,

            capture_local_preview=capture_local_worker_preview,

        )

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_preview_request",

            payload=payload,

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return payload

    @app.post("/api/fleet/stop-all")

    async def fleet_stop_all(

        request: FleetStopWorkerRequest,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="fleet_stop_all",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"reason": request.reason, **dict(request.metadata or {})},

        )

        snapshot = _get_remote_control_store().get_fleet_snapshot(

            user_id=int(auth["user_id"]),

            desktop_id=str(auth.get("desktop_id") or "").strip() or None,

        )

        results = []

        for worker in list(snapshot.get("workers") or []):

            active_task = _fleet_active_task_for_worker(

                snapshot=snapshot,

                worker=dict(worker or {}),

                metadata=None,

            )

            active_task_id = str((active_task or {}).get("task_id") or "").strip()

            if not active_task_id:

                continue

            try:

                results.append(

                    await _stop_fleet_worker_active_task(

                        user_id=int(auth["user_id"]),

                        worker_id=str(worker.get("worker_id") or ""),

                        reason=request.reason or "Fleet stop all",

                        metadata={**dict(request.metadata or {}), "stop_all": True, "task_id": active_task_id},

                    )

                )

            except Exception:

                logger.exception("[fleet] failed stopping worker during stop-all")

                results.append({"worker_id": worker.get("worker_id"), "stopped": False, "error": "stop_failed"})

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_task_status",

            payload={"stop_all": True, "results": results},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return {"ok": True, "stopped_count": sum(1 for item in results if item.get("stopped")), "results": results}

    @app.post("/api/fleet/workers/{worker_id}/reset", response_model=FleetDeleteWorkerResponse)

    async def fleet_reset_worker(

        worker_id: str,

        request: FleetStopWorkerRequest,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> FleetDeleteWorkerResponse:

        auth = _require_fleet_manager_auth(authorization)

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="fleet_worker_reset",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"worker_id": worker_id, "reason": request.reason, **dict(request.metadata or {})},

        )

        try:

            await _stop_fleet_worker_active_task(

                user_id=int(auth["user_id"]),

                worker_id=worker_id,

                reason=request.reason or "Worker reset by manager",

                metadata={**dict(request.metadata or {}), "reset": True},

            )

            result = _get_remote_control_store().delete_worker(

                user_id=int(auth["user_id"]),

                worker_id=worker_id,

                wipe_state=True,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_worker_presence",

            payload={"worker_id": worker_id, "reason": "reset", "result": result},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return FleetDeleteWorkerResponse.model_validate(result)

    @app.delete("/api/fleet/workers/{worker_id}", response_model=FleetDeleteWorkerResponse)

    async def fleet_delete_worker(

        worker_id: str,

        wipe_state: bool = True,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> FleetDeleteWorkerResponse:

        auth = _require_fleet_manager_auth(authorization)

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="fleet_worker_delete",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"worker_id": worker_id, "wipe_state": bool(wipe_state)},

        )

        try:

            await _stop_fleet_worker_active_task(

                user_id=int(auth["user_id"]),

                worker_id=worker_id,

                reason="Worker deleted by manager",

                metadata={"delete_worker": True},

            )

            result = _get_remote_control_store().delete_worker(

                user_id=int(auth["user_id"]),

                worker_id=worker_id,

                wipe_state=wipe_state,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_worker_presence",

            payload={"worker_id": worker_id, "reason": "deleted", "result": result},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return FleetDeleteWorkerResponse.model_validate(result)

    @app.post("/api/fleet/workers/{worker_id}/tasks", response_model=FleetTaskView)

    async def fleet_assign_task(

        worker_id: str,

        request: FleetAssignTaskRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetTaskView:

        auth = _require_fleet_manager_auth(authorization)

        store = _get_remote_control_store()

        try:

            worker = store.get_worker(user_id=int(auth["user_id"]), worker_id=worker_id)

            snapshot = store.get_fleet_snapshot(user_id=int(auth["user_id"]), desktop_id=str(auth.get("desktop_id") or ""))

            target_session_id = _fleet_task_target_session_id(

                snapshot=snapshot,

                worker=worker,

                request=request,

            )

            task = store.assign_worker_task(

                user_id=int(auth["user_id"]),

                worker_id=worker_id,

                prompt=request.prompt,

                source=request.source,

                target_session_id=target_session_id,

                target_mode=request.target_mode,

                metadata=request.metadata,

            )

            blocker = _workspace_binding_blocker_for_task(

                user_id=int(auth["user_id"]),

                worker=worker,

                request=request,

            )

            if blocker:

                task = store.update_worker_task_status(

                    user_id=int(auth["user_id"]),

                    task_id=str(task.get("task_id") or ""),

                    status="blocked",

                    metadata={

                        **dict(request.metadata or {}),

                        "workspace_binding_blocker": blocker,

                        "blocked_before_dispatch": True,

                    },

                )

            else:

                task = await _try_dispatch_fleet_worker_task(

                    user_id=int(auth["user_id"]),

                    worker=worker,

                    task=task,

                )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except RuntimeError:

            logger.exception("[fleet] failed dispatching worker task; task remains queued")

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_task_assigned",

            payload={"task": task, "worker_id": worker_id},

            origin_channel=request.source or str(auth.get("actor_kind") or "app"),

        )

        return FleetTaskView.model_validate(task)

    @app.post("/api/fleet/groups/{group_id}/tasks", response_model=list[FleetTaskView])

    async def fleet_assign_group_task(

        group_id: str,

        request: FleetAssignTaskRequest,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> list[FleetTaskView]:

        auth = _require_fleet_manager_auth(authorization)

        store = _get_remote_control_store()

        snapshot = store.get_fleet_snapshot(user_id=int(auth["user_id"]), desktop_id=str(auth.get("desktop_id") or ""))

        group = next((item for item in list(snapshot.get("groups") or []) if str(item.get("group_id") or "") == str(group_id)), None)

        if not group:

            raise HTTPException(status_code=404, detail="Unknown group")

        workers = [

            worker

            for worker in list(snapshot.get("workers") or [])

            if str(worker.get("group_id") or "") == str(group_id)

        ]

        if not workers:

            raise HTTPException(status_code=400, detail="Group has no workers")

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="fleet_group_dispatch",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={

                "group_id": group_id,

                "worker_count": len(workers),

                "requires_workspace_write": bool(request.requires_workspace_write),

                **dict(request.metadata or {}),

            },

        )

        tasks: list[dict] = []

        for worker in workers:

            task = store.assign_worker_task(

                user_id=int(auth["user_id"]),

                worker_id=str(worker.get("worker_id") or ""),

                prompt=request.prompt,

                source=request.source,

                target_session_id=_fleet_task_target_session_id(

                    snapshot=snapshot,

                    worker=worker,

                    request=request,

                ),

                target_mode=request.target_mode,

                metadata={

                    **dict(request.metadata or {}),

                    "group_id": group_id,

                    "bulk_dispatch_confirmed": bool((request.metadata or {}).get("bulk_dispatch_confirmed")),

                },

            )

            blocker = _workspace_binding_blocker_for_task(

                user_id=int(auth["user_id"]),

                worker=worker,

                request=request,

            )

            if blocker:

                dispatched = store.update_worker_task_status(

                    user_id=int(auth["user_id"]),

                    task_id=str(task.get("task_id") or ""),

                    status="blocked",

                    metadata={

                        **dict(request.metadata or {}),

                        "group_id": group_id,

                        "workspace_binding_blocker": blocker,

                        "blocked_before_dispatch": True,

                    },

                )

            else:

                dispatched = await _try_dispatch_fleet_worker_task(

                    user_id=int(auth["user_id"]),

                    worker=worker,

                    task=task,

                )

            tasks.append(dispatched)

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_task_assigned",

            payload={"tasks": tasks, "group_id": group_id},

            origin_channel=request.source or str(auth.get("actor_kind") or "app"),

        )

        return [FleetTaskView.model_validate(item) for item in tasks]

    @app.put("/api/fleet/tasks/reorder", response_model=list[FleetTaskView])

    async def fleet_reorder_tasks(

        request: FleetTaskReorderRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> list[FleetTaskView]:

        auth = _require_fleet_manager_auth(authorization)

        try:

            tasks = _get_remote_control_store().reorder_worker_tasks(

                user_id=int(auth["user_id"]),

                worker_id=request.worker_id,

                task_ids=request.task_ids,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_queue_updated",

            payload={"worker_id": request.worker_id, "tasks": tasks},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return [FleetTaskView.model_validate(item) for item in tasks]

    @app.post("/api/fleet/workers/{worker_id}/queue/continue")

    async def fleet_continue_worker_queue(

        worker_id: str,

        request: FleetContinueWorkerQueueRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict:

        auth = _require_fleet_manager_auth(authorization)

        store = _get_remote_control_store()

        try:

            worker = store.get_worker(user_id=int(auth["user_id"]), worker_id=worker_id)

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if str(worker.get("active_task_id") or "").strip():

            raise HTTPException(status_code=409, detail="Worker still has an active task; stop, redirect, or wait before continuing the queue")

        snapshot = store.get_fleet_snapshot(

            user_id=int(auth["user_id"]),

            desktop_id=str(auth.get("desktop_id") or "").strip() or None,

        )

        latest_report = next(

            (

                report

                for report in list(snapshot.get("reports") or [])

                if str(report.get("worker_id") or "") == str(worker.get("worker_id") or "")

            ),

            None,

        )

        if latest_report:

            report_status = str(latest_report.get("status") or "").strip().lower()

            report_confidence = str(latest_report.get("confidence") or "").strip().lower()

            if report_status != "completed" or report_confidence == "low":

                raise HTTPException(

                    status_code=409,

                    detail="Latest worker report requires manager review before queued work can continue",

                )

            try:

                worker = store.mark_worker_queue_reviewed(

                    user_id=int(auth["user_id"]),

                    worker_id=worker_id,

                    reviewed_report_id=request.reviewed_report_id or latest_report.get("report_id"),

                    source=request.source,

                    metadata=request.metadata,

                )

            except ValueError as exc:

                raise HTTPException(status_code=409, detail=str(exc)) from exc

        next_task = store.get_next_queued_worker_task(user_id=int(auth["user_id"]), worker_id=worker_id)

        if not next_task:

            return {"ok": True, "continued": False, "worker_id": worker_id, "reason": "queue_empty"}

        dispatched = await _try_dispatch_fleet_worker_task(

            user_id=int(auth["user_id"]),

            worker=worker,

            task={

                **next_task,

                "metadata": {

                    **dict(next_task.get("metadata") or {}),

                    **dict(request.metadata or {}),

                    "continued_by": request.source,

                    "reviewed_report_id": request.reviewed_report_id,

                },

            },

        )

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_queue_updated",

            payload={"worker_id": worker_id, "continued": True, "task": dispatched},

            origin_channel=request.source or str(auth.get("actor_kind") or "app"),

        )

        return {"ok": True, "continued": str(dispatched.get("status") or "") == "running", "task": dispatched}

    @app.post("/api/fleet/tasks/{task_id}/redirect", response_model=FleetTaskView)

    async def fleet_redirect_task(

        task_id: str,

        request: FleetTaskRedirectRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetTaskView:

        auth = _require_fleet_manager_auth(authorization)

        try:

            task = _get_remote_control_store().redirect_worker_task(

                user_id=int(auth["user_id"]),

                task_id=task_id,

                direction=request.direction,

                source=request.source,

                metadata=request.metadata,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_task_redirect",

            payload={"task": task, "direction": request.direction},

            origin_channel=request.source or str(auth.get("actor_kind") or "app"),

        )

        return FleetTaskView.model_validate(task)

    @app.put("/api/fleet/tasks/{task_id}/status", response_model=FleetTaskView)

    async def fleet_update_task_status(

        task_id: str,

        request: FleetTaskStatusRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetTaskView:

        auth = _require_fleet_manager_auth(authorization)

        try:

            task = _get_remote_control_store().update_worker_task_status(

                user_id=int(auth["user_id"]),

                task_id=task_id,

                status=request.status,

                metadata=request.metadata,

            )

            live_stop_sent = False

            if str(request.status or "") == "stopped":

                live_stop_sent = await _try_stop_fleet_worker_task(

                    user_id=int(auth["user_id"]),

                    task=task,

                )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_task_status",

            payload={"task": task},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        try:

            from shared.proactive_runtime import append_fleet_status_event

            append_fleet_status_event(user_id=int(auth["user_id"]), task=task)

        except Exception:

            logger.exception("[fleet] failed appending proactive task status event")

        return FleetTaskView.model_validate(task)

    @app.post("/api/fleet/tasks/{task_id}/report", response_model=FleetReportView)

    async def fleet_create_task_report(

        task_id: str,

        request: FleetReportRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetReportView:

        auth = _require_fleet_manager_auth(authorization)

        try:

            report = _get_remote_control_store().complete_worker_task_report(

                user_id=int(auth["user_id"]),

                task_id=task_id,

                status=request.status,

                summary=request.summary,

                evidence=request.evidence,

                artifacts=request.artifacts,

                blockers=request.blockers,

                confidence=request.confidence,

                next_suggested_action=request.next_suggested_action,

                raw=request.raw,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        except ValueError as exc:

            raise HTTPException(status_code=409, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_task_report",

            payload={"report": report},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        await _try_dispatch_next_fleet_worker_task(

            user_id=int(auth["user_id"]),

            worker_id=str(report.get("worker_id") or ""),

        )

        try:

            from shared.proactive_runtime import append_fleet_report_event

            append_fleet_report_event(user_id=int(auth["user_id"]), report=report)

        except Exception:

            logger.exception("[fleet] failed appending proactive report event")

        return FleetReportView.model_validate(report)

    @app.post("/api/fleet/reports/search")

    async def fleet_search_reports(

        request: FleetReportSearchRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict:

        auth = _resolve_token(authorization)

        if not _is_remote_session_auth(auth):

            auth = _standalone_manager_auth(auth)

        try:

            return _get_remote_control_store().search_fleet_reports(

                user_id=int(auth["user_id"]),

                query=request.query,

                worker=request.worker,

                status=request.status,

                limit=request.limit,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/fleet/workspace-bindings", response_model=FleetWorkspaceBindingView)

    async def fleet_upsert_workspace_binding(

        request: FleetWorkspaceBindingRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetWorkspaceBindingView:

        auth = _require_fleet_manager_auth(authorization)

        try:

            binding = _get_remote_control_store().upsert_workspace_binding(

                user_id=int(auth["user_id"]),

                workspace_id=request.workspace_id,

                machine_id=request.machine_id,

                local_path=request.local_path,

                label=request.label,

                status=request.status,

                metadata=request.metadata,

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_workspace_binding_changed",

            payload={"workspace_binding": binding},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return FleetWorkspaceBindingView.model_validate(binding)

    @app.post("/api/fleet/tool-grants", response_model=FleetToolGrantView)

    async def fleet_request_tool_grant(

        request: FleetToolGrantRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetToolGrantView:

        auth = _require_fleet_manager_auth(authorization)

        grant = _get_remote_control_store().request_tool_grant(

            user_id=int(auth["user_id"]),

            target_kind=request.target_kind,

            target_id=request.target_id,

            tool_pack_id=request.tool_pack_id,

            reason=request.reason,

            task_id=request.task_id,

            requested_turns=request.requested_turns,

            requested_by=request.requested_by or str(auth.get("desktop_id") or ""),

        )

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_grant_requested",

            payload={"tool_grant": grant},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return FleetToolGrantView.model_validate(grant)

    @app.post("/api/fleet/tool-grants/{grant_id}/decision", response_model=FleetToolGrantView)

    async def fleet_decide_tool_grant(

        grant_id: str,

        request: FleetToolGrantDecisionRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> FleetToolGrantView:

        auth = _require_fleet_manager_auth(authorization)

        try:

            grant = _get_remote_control_store().decide_tool_grant(

                user_id=int(auth["user_id"]),

                grant_id=grant_id,

                approved=request.approved,

                approved_turns=request.approved_turns,

                approved_by=request.approved_by or str(auth.get("desktop_id") or ""),

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _publish_fleet_delta(

            user_id=int(auth["user_id"]),

            event_type="fleet_grant_decided",

            payload={"tool_grant": grant},

            origin_channel=str(auth.get("actor_kind") or "app"),

        )

        return FleetToolGrantView.model_validate(grant)
