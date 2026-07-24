from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

from shared.project_onboarding import ProjectOnboardingStore, merge_tool_packs
from app_backend.company_runtime_context import (
    company_record_matches,
    resolve_local_company_runtime,
    selected_company_scope,
)


def _project_onboarding_tool_packs(*, user_id: int, workspace: str, current_tool_packs: list[str] | None = None) -> list[str]:
    try:
        profile = ProjectOnboardingStore(user_id=user_id).get_by_workspace(workspace)
    except Exception:
        return []
    if not profile.get("enabled"):
        return []
    return merge_tool_packs(current_tool_packs or [], profile.get("desired_tool_packs") or [])


def register_session_routes(app):

    def _company_scope(auth: Dict[str, Any]) -> tuple[Optional[str], bool]:
        if _is_remote_session_auth(auth):
            computer_id = str(auth.get("desktop_id") or "").strip()
            company_id = (
                _get_company_store().active_company_id(computer_id=computer_id)
                if computer_id
                else None
            )
            if not company_id:
                return None, True
            company = _get_company_store().get_company(company_id)
        else:
            fleet_store = _get_remote_control_store()
            if not callable(
                getattr(fleet_store, "ensure_standalone_manager_desktop", None)
            ):
                # Legacy/local bridge adapters predate Company membership. They
                # remain unscoped and eligible for the default migration path.
                return None, True
            runtime = resolve_local_company_runtime(
                auth=auth,
                company_store=_get_company_store(),
                fleet_store=fleet_store,
            )
            if not runtime:
                return None, True
            company_id = str(runtime["company_id"])
            company = runtime["company"]
        include_legacy = str((company.get("migration") or {}).get("state") or "") == "legacy_compatibility"
        return str(company_id), include_legacy

    def _require_session_company(
        session: Any,
        *,
        company_id: Optional[str],
        include_legacy: bool,
    ) -> None:
        raw_value = (
            session.get("company_id")
            if isinstance(session, dict)
            else getattr(session, "company_id", None)
        )
        value = str(raw_value or "").strip()
        if company_id and value != company_id and not (include_legacy and not value):
            raise HTTPException(status_code=404, detail="Session not found in the selected company")

    @app.get("/api/app/sidebar-state", response_model=SidebarStateResponse)

    async def get_sidebar_state(authorization: Optional[str] = Header(default=None)) -> SidebarStateResponse:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            shared_state = _remote_shared_state(auth)

            state = shared_state.get("sidebar_state")

            return SidebarStateResponse(

                state=state if isinstance(state, dict) else _empty_sidebar_state(),

                shared_state=shared_state,

            )

        return SidebarStateResponse(state=_read_local_sidebar_state())

    @app.put("/api/app/sidebar-state", response_model=SidebarStateResponse)

    async def put_sidebar_state(request: SidebarStateRequest, authorization: Optional[str] = Header(default=None)) -> SidebarStateResponse:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            before = _remote_shared_state(auth)

            await _remote_dispatch_command(

                auth,

                command_name="update_sidebar_state",

                payload={"state": request.state},

            )

            shared_state = await _remote_wait_for_sync_version(

                int(auth["user_id"]),

                int(before.get("sync_version", 0) or 0),

            )

            state = shared_state.get("sidebar_state")

            return SidebarStateResponse(

                state=state if isinstance(state, dict) else _empty_sidebar_state(),

                shared_state=shared_state,

            )

        state = _write_local_sidebar_state(request.state)

        return SidebarStateResponse(state=state)

    @app.post("/api/app/sessions", response_model=CreateSessionResponse)

    async def create_session(request: CreateSessionRequest, authorization: Optional[str] = Header(default=None)) -> CreateSessionResponse:

        auth = _resolve_token(authorization)
        company_id, _include_legacy = _company_scope(auth)

        if _is_remote_session_auth(auth):
            if request.fleet_identity_id:
                scope = selected_company_scope(
                    auth=auth,
                    company_store=_get_company_store(),
                    fleet_store=_get_remote_control_store(),
                )
                snapshot = _get_remote_control_store().get_fleet_snapshot(
                    user_id=int(auth["user_id"]),
                    desktop_id=scope.get("computer_id"),
                    company_id=scope.get("company_id"),
                    company_computer_ids=scope.get("company_computer_ids"),
                    include_unscoped_company_records=bool(scope.get("include_legacy")),
                )
                if not any(
                    str(item.get("identity_id") or "")
                    == str(request.fleet_identity_id)
                    for item in list(snapshot.get("identities") or [])
                ):
                    raise HTTPException(
                        status_code=404,
                        detail="Identity not found in the selected company",
                    )

            before = _remote_shared_state(auth)

            result = await _remote_request_desktop_command(

                auth,

                command_name="create_session",

                payload={

                    "name": request.name,

                    "workspace": request.workspace,

                    "workspace_id": request.workspace_id,

                    "workspace_binding_status": request.workspace_binding_status,

                    "telegram_bot_config_id": request.telegram_bot_config_id,

                    "enabled_tool_packs": list(request.enabled_tool_packs or []),

                    "security_permission_mode": request.security_permission_mode,

                    "headless_eligible": bool(request.headless_eligible),

                    "fleet_identity_id": request.fleet_identity_id,

                    "fleet_identity_role": request.fleet_identity_role,

                    "fleet_worker_id": request.fleet_worker_id,

                    "fleet_task_mode": request.fleet_task_mode,

                    "fleet_task_id": request.fleet_task_id,
                    "company_id": company_id,

                },

                timeout_seconds=30.0,

            )

            if isinstance(result.get("session"), dict):

                detail = SessionDetailView.model_validate(result["session"])

                if request.fleet_identity_id:

                    try:

                        _get_remote_control_store().set_active_chat_for_fleet_identity(

                            user_id=int(auth["user_id"]),

                            identity_id=request.fleet_identity_id,

                            chat_id=detail.id,

                            source=str(auth.get("actor_kind") or "app"),
                            company_id=company_id,
                            include_unscoped_company_records=_include_legacy,

                        )

                        _publish_fleet_delta(

                            user_id=int(auth["user_id"]),

                            event_type="fleet_identity_chat_selected",

                            payload={"identity_id": request.fleet_identity_id, "selected_chat_id": detail.id},

                            origin_channel=str(auth.get("actor_kind") or "app"),

                        )

                    except Exception:

                        logger.exception("[fleet] failed selecting remote-created identity chat")

                return CreateSessionResponse(session=detail)

            await _remote_wait_for_sync_version(

                int(auth["user_id"]),

                int(before.get("sync_version", 0) or 0),

            )

            detail = _remote_session_detail_view(auth, _remote_current_session_id(auth))

            if request.fleet_identity_id:

                try:

                    _get_remote_control_store().set_active_chat_for_fleet_identity(

                        user_id=int(auth["user_id"]),

                        identity_id=request.fleet_identity_id,

                        chat_id=detail.id,

                        source=str(auth.get("actor_kind") or "app"),
                        company_id=company_id,
                        include_unscoped_company_records=_include_legacy,

                    )

                    _publish_fleet_delta(

                        user_id=int(auth["user_id"]),

                        event_type="fleet_identity_chat_selected",

                        payload={"identity_id": request.fleet_identity_id, "selected_chat_id": detail.id},

                        origin_channel=str(auth.get("actor_kind") or "app"),

                    )

                except Exception:

                    logger.exception("[fleet] failed selecting remote-created identity chat")

            return CreateSessionResponse(session=detail)

        user_id = int(auth["user_id"])

        bridge = _bridge_for_user(user_id)

        workspace = _resolve_workspace_path(request.workspace, user_id=user_id) if request.workspace else None
        enabled_tool_packs = list(request.enabled_tool_packs or [])

        previous = bridge.get_current_session()

        activate_created_session = str(request.fleet_task_mode or "").strip().lower() != "delegated"

        fleet_identity_metadata = None

        if request.fleet_identity_id:

            try:

                company_runtime = resolve_local_company_runtime(
                    auth=auth,
                    company_store=_get_company_store(),
                    fleet_store=_get_remote_control_store(),
                )
                fleet_snapshot = _get_remote_control_store().get_fleet_snapshot(
                    user_id=user_id,
                    desktop_id=(company_runtime or {}).get("computer_id"),
                    company_id=company_id,
                    company_computer_ids=[
                        str(item.get("computer_id") or "")
                        for item in list(((company_runtime or {}).get("company") or {}).get("memberships") or [])
                    ] if company_runtime else None,
                    include_unscoped_company_records=bool(
                        company_runtime
                        and str((((company_runtime or {}).get("company") or {}).get("migration") or {}).get("state") or "")
                        == "legacy_compatibility"
                    ),
                )

                fleet_identity = next(

                    (

                        item for item in list(fleet_snapshot.get("identities") or [])

                        if str(item.get("identity_id") or "") == str(request.fleet_identity_id)

                    ),

                    None,

                )

                fleet_identity_metadata = dict((fleet_identity or {}).get("metadata") or {})
                if request.fleet_identity_id and fleet_identity is None:
                    raise HTTPException(status_code=404, detail="Identity not found in the selected company")

            except HTTPException:
                raise

            except Exception:

                logger.exception("[fleet] failed resolving identity tool profile")

        try:

            session = bridge.create_session(

                request.name,

                workspace=workspace,

                workspace_id=request.workspace_id,

                workspace_binding_status=request.workspace_binding_status,

                telegram_bot_config_id=request.telegram_bot_config_id,

                enabled_tool_packs=enabled_tool_packs,

                security_permission_mode=request.security_permission_mode,

                headless_eligible=request.headless_eligible,

                fleet_identity_id=request.fleet_identity_id,

                fleet_identity_role=request.fleet_identity_role,

                fleet_worker_id=request.fleet_worker_id,

                fleet_task_mode=request.fleet_task_mode,

                fleet_task_id=request.fleet_task_id,
                company_id=company_id,

                fleet_identity_metadata=fleet_identity_metadata,

                activate=activate_created_session,

            )

        except RuntimeError as exc:

            raise HTTPException(status_code=409, detail=str(exc)) from exc

        if not request.enabled_tool_packs and getattr(session, "workspace", None):

            next_tool_packs = _project_onboarding_tool_packs(

                user_id=user_id,

                workspace=str(getattr(session, "workspace", "")),

                current_tool_packs=list(getattr(session, "enabled_tool_packs", []) or []),

            )

            if next_tool_packs and set(next_tool_packs) != set(getattr(session, "enabled_tool_packs", []) or []):

                session = bridge.update_session_tool_packs(session.id, next_tool_packs)

        _sync_session_workspace_binding(user_id=user_id, auth=auth, session=session)

        try:

            bridge.session_manager.save_session(session)

        except Exception:

            logger.exception("[workspace] failed saving session workspace binding status")

        _mirror_session_snapshot_later(user_id=user_id, bridge=bridge, session=session, reason="session_created")

        if activate_created_session:

            publish_current_session_changed(

                user_id=user_id,

                session_id=session.id,

                previous_session_id=previous.id if previous else None,

                origin_channel="app",

                reason="session_created",

            )

        if request.fleet_identity_id:

            try:

                _get_remote_control_store().set_active_chat_for_fleet_identity(

                    user_id=user_id,

                    identity_id=request.fleet_identity_id,

                    chat_id=session.id,

                    source="app",
                    company_id=company_id,
                    include_unscoped_company_records=_include_legacy,

                )

                _publish_fleet_delta(

                    user_id=user_id,

                    event_type="fleet_identity_chat_selected",

                    payload={"identity_id": request.fleet_identity_id, "selected_chat_id": session.id},

                    origin_channel="app",

                )

            except Exception:

                logger.exception("[fleet] failed selecting local-created identity chat")

        detail = SessionDetailView(**bridge.detailed_session_view(session))

        return CreateSessionResponse(session=detail)

    @app.post("/api/app/sessions/{session_id}/activate", response_model=SessionDetailView)

    async def activate_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:

        auth = _resolve_token(authorization)
        company_id, include_legacy = _company_scope(auth)

        if _is_remote_session_auth(auth):
            _require_session_company(
                _remote_session_detail_view(auth, session_id),
                company_id=company_id,
                include_legacy=include_legacy,
            )

            before = _remote_shared_state(auth)

            result = await _remote_request_desktop_command(

                auth,

                command_name="activate_session",

                payload={"session_id": session_id},

                timeout_seconds=30.0,

            )

            if result:

                detail = SessionDetailView.model_validate(result)
                _require_session_company(
                    detail,
                    company_id=company_id,
                    include_legacy=include_legacy,
                )

                if detail.fleet_identity_id:

                    try:

                        _get_remote_control_store().set_active_chat_for_fleet_identity(

                            user_id=int(auth["user_id"]),

                            identity_id=detail.fleet_identity_id,

                            chat_id=detail.id,

                            source=str(auth.get("actor_kind") or "app"),
                            company_id=company_id,
                            include_unscoped_company_records=include_legacy,

                        )

                        _publish_fleet_delta(

                            user_id=int(auth["user_id"]),

                            event_type="fleet_identity_chat_selected",

                            payload={"identity_id": detail.fleet_identity_id, "selected_chat_id": detail.id},

                            origin_channel=str(auth.get("actor_kind") or "app"),

                        )

                    except Exception:

                        logger.exception("[fleet] failed remembering remote-activated identity chat")

                return detail

            await _remote_wait_for_sync_version(

                int(auth["user_id"]),

                int(before.get("sync_version", 0) or 0),

            )

            detail = _remote_session_detail_view(auth, session_id)
            _require_session_company(
                detail,
                company_id=company_id,
                include_legacy=include_legacy,
            )

            if detail.fleet_identity_id:

                try:

                    _get_remote_control_store().set_active_chat_for_fleet_identity(

                        user_id=int(auth["user_id"]),

                        identity_id=detail.fleet_identity_id,

                        chat_id=detail.id,

                        source=str(auth.get("actor_kind") or "app"),
                        company_id=company_id,
                        include_unscoped_company_records=include_legacy,

                    )

                    _publish_fleet_delta(

                        user_id=int(auth["user_id"]),

                        event_type="fleet_identity_chat_selected",

                        payload={"identity_id": detail.fleet_identity_id, "selected_chat_id": detail.id},

                        origin_channel=str(auth.get("actor_kind") or "app"),

                    )

                except Exception:

                    logger.exception("[fleet] failed remembering remote-activated identity chat")

            return detail

        user_id = int(auth["user_id"])

        bridge = _bridge_for_user(user_id)

        previous = bridge.get_current_session()

        try:
            _require_session_company(
                bridge.get_session(session_id),
                company_id=company_id,
                include_legacy=include_legacy,
            )

            session = bridge.activate_session(session_id)

        except RuntimeError as exc:

            raise HTTPException(status_code=409, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=404, detail="Session not found") from exc

        publish_current_session_changed(

            user_id=user_id,

            session_id=session.id,

            previous_session_id=previous.id if previous else None,

            origin_channel="app",

            reason="session_activated",

        )

        if getattr(session, "fleet_identity_id", None):

            try:

                _get_remote_control_store().set_active_chat_for_fleet_identity(

                    user_id=user_id,

                    identity_id=str(session.fleet_identity_id),

                    chat_id=session.id,

                    source="app",
                    company_id=company_id,
                    include_unscoped_company_records=include_legacy,

                )

                _publish_fleet_delta(

                    user_id=user_id,

                    event_type="fleet_identity_chat_selected",

                    payload={"identity_id": str(session.fleet_identity_id), "selected_chat_id": session.id},

                    origin_channel="app",

                )

            except Exception:

                logger.exception("[fleet] failed remembering local-activated identity chat")

        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.put("/api/app/sessions/{session_id}", response_model=SessionDetailView)

    async def rename_session(session_id: str, request: RenameSessionRequest, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:

        auth = _resolve_token(authorization)
        company_id, include_legacy = _company_scope(auth)

        if _is_remote_session_auth(auth):
            _require_session_company(
                _remote_session_detail_view(auth, session_id),
                company_id=company_id,
                include_legacy=include_legacy,
            )

            before = _remote_shared_state(auth)

            result = await _remote_request_desktop_command(

                auth,

                command_name="rename_session",

                payload={"session_id": session_id, "name": request.name},

                timeout_seconds=30.0,

            )

            detail_payload = result.get("session") if isinstance(result, dict) and isinstance(result.get("session"), dict) else result

            if isinstance(detail_payload, dict) and detail_payload.get("id"):
                detail = SessionDetailView.model_validate(detail_payload)
                _require_session_company(
                    detail,
                    company_id=company_id,
                    include_legacy=include_legacy,
                )
                return detail

            await _remote_wait_for_sync_version(

                int(auth["user_id"]),

                int(before.get("sync_version", 0) or 0),

            )

            detail = _remote_session_detail_view(auth, session_id)
            _require_session_company(
                detail,
                company_id=company_id,
                include_legacy=include_legacy,
            )
            return detail

        user_id = int(auth["user_id"])

        bridge = _bridge_for_user(user_id)

        try:
            _require_session_company(
                bridge.get_session(session_id),
                company_id=company_id,
                include_legacy=include_legacy,
            )

            session = bridge.rename_session(session_id, request.name)

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=404, detail="Session not found") from exc

        _mirror_session_snapshot_later(user_id=user_id, bridge=bridge, session=session, reason="session_renamed")

        publish_current_session_changed(

            user_id=user_id,

            session_id=session.id,

            previous_session_id=session.id,

            origin_channel="app",

            reason="session_renamed",

        )

        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.delete(

        "/api/app/sessions/{session_id}",

        response_model=DeleteSessionResponse,

    )

    async def delete_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> DeleteSessionResponse:

        auth = _resolve_token(authorization)
        company_id, include_legacy = _company_scope(auth)

        if _is_remote_session_auth(auth):
            _require_session_company(
                _remote_session_detail_view(auth, session_id),
                company_id=company_id,
                include_legacy=include_legacy,
            )

            before = _remote_shared_state(auth)

            result = await _remote_request_desktop_command(

                auth,

                command_name="delete_session",

                payload={"session_id": session_id},

                timeout_seconds=30.0,

            )

            shared_state = await _remote_wait_for_sync_version(

                int(auth["user_id"]),

                int(before.get("sync_version", 0) or 0),

            )

            deleted_session_id = str((result or {}).get("deleted_session_id") or session_id).strip()

            current_session_id = str((result or {}).get("current_session_id") or shared_state.get("current_session_id") or "").strip() or None

            archive_id = str((result or {}).get("archive_id") or "").strip() or None

            if archive_id is None:

                return JSONResponse(content={

                    "deleted_session_id": deleted_session_id,

                    "current_session_id": current_session_id,

                })

            return DeleteSessionResponse(

                deleted_session_id=deleted_session_id,

                current_session_id=current_session_id,

                archive_id=archive_id,

            )

        user_id = int(auth["user_id"])

        bridge = _bridge_for_user(user_id)

        try:
            _require_session_company(
                bridge.get_session(session_id),
                company_id=company_id,
                include_legacy=include_legacy,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

        previous = bridge.get_current_session()

        archive_payload: Optional[Dict[str, Any]] = None

        archive_id: Optional[str] = None

        try:

            archive_session = bridge.get_session(session_id)

            archive_payload = {"session": bridge.detailed_session_view(archive_session)}

            try:

                archive_payload["session"]["artifacts"] = bridge.list_session_artifacts(session_id)

            except Exception:

                archive_payload["session"]["artifacts"] = []

        except Exception:

            archive_payload = None

        try:

            result = bridge.delete_session(session_id)

        except RuntimeError as exc:

            raise HTTPException(status_code=409, detail=str(exc)) from exc

        except Exception as exc:

            raise HTTPException(status_code=404, detail="Session not found") from exc

        if archive_payload:

            try:

                session_payload = dict(archive_payload.get("session") or {})

                archived_item = _get_remote_control_store().archive_item(

                    user_id=user_id,

                    object_kind="chat",

                    object_id=session_id,

                    display_name=str(session_payload.get("name") or session_id),

                    payload=archive_payload,

                    metadata={"archive_reason": "chat_delete", "workspace": session_payload.get("workspace")},

                )

                archive_id = str(archived_item.get("archive_id") or "").strip() or None
            except Exception:

                logger.exception("[recovery] failed archiving deleted chat")

        publish_current_session_changed(

            user_id=user_id,

            session_id=result.get("current_session_id"),

            previous_session_id=previous.id if previous else session_id,

            origin_channel="app",

            reason="session_deleted",

        )

        return DeleteSessionResponse(**result, archive_id=archive_id)

    @app.post("/api/app/chat/send")

    async def send_chat(request: ChatSendRequest, authorization: Optional[str] = Header(default=None)) -> dict:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Chat turns must run on the local desktop backend")

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, request.session_id)

        try:

            runtime.session.account_user_id = int(auth["user_id"])

        except Exception:

            pass

        missing_key_payload = _missing_provider_api_key_payload(runtime)

        if missing_key_payload:

            raise HTTPException(status_code=409, detail=str(missing_key_payload["message"]))

        if _is_active_steering_request(runtime, request.interrupt_policy):

            try:

                result = await _run_app_chat_turn_lazy(

                    runtime,

                    user_message=request.text,

                    source_format=request.source_format,

                    interrupt_policy=request.interrupt_policy,

                    source_client_id=request.source_client_id,

                )

            except Exception as exc:

                payload = _record_chat_turn_failure(exc)

                raise HTTPException(status_code=409, detail=str(payload["message"])) from exc

            if result.get("steering"):

                _mirror_session_snapshot(user_id=int(auth["user_id"]), bridge=bridge, session=runtime.session, reason="chat_steering")

                return result

            if result.get("busy"):

                raise HTTPException(status_code=409, detail="Session is already processing another message")

        lease = await bridge.orchestrator.prepare_turn(str(runtime.session.id), origin_channel=request.channel or "app")

        if lease.busy:

            raise HTTPException(status_code=409, detail=lease.error or "Session is already processing another message")

        try:

            try:

                result = await _run_app_chat_turn_lazy(

                    runtime,

                    user_message=request.text,

                    source_format=request.source_format,

                    interrupt_policy=request.interrupt_policy,

                    source_client_id=request.source_client_id,

                )

            except Exception as exc:

                payload = _record_chat_turn_failure(exc)

                raise HTTPException(status_code=409, detail=str(payload["message"])) from exc

        finally:

            await bridge.orchestrator.complete_turn(lease)

        if result.get("busy"):

            raise HTTPException(status_code=409, detail="Session is already processing another message")

        _sync_session_workspace_binding(user_id=int(auth["user_id"]), auth=auth, session=runtime.session)

        _mirror_session_snapshot(user_id=int(auth["user_id"]), bridge=bridge, session=runtime.session, reason="chat_turn")

        return result

    @app.get("/api/app/automations", response_model=list[ScheduledJobView])

    @app.get("/api/app/jobs", response_model=list[ScheduledJobView])

    async def list_jobs(authorization: Optional[str] = Header(default=None)) -> list[ScheduledJobView]:

        auth = _resolve_token(authorization)
        company_id, include_legacy = _company_scope(auth)

        user_id = int(auth["user_id"])

        if _is_remote_session_auth(auth):

            state = _remote_shared_state(auth)

            items: list[ScheduledJobView] = []

            for raw in list(state.get("jobs") or []):
                if not company_record_matches(
                    raw,
                    company_id=company_id,
                    include_legacy=include_legacy,
                ):
                    continue

                try:

                    items.append(ScheduledJobView.model_validate(raw))

                except Exception:

                    continue

            for raw in _get_remote_control_store().list_automations(user_id=user_id):
                if not company_record_matches(
                    raw,
                    company_id=company_id,
                    include_legacy=include_legacy,
                ):
                    continue

                if not any(item.id == raw.get("id") for item in items):

                    try:

                        items.append(ScheduledJobView.model_validate(raw))

                    except Exception:

                        continue

            return items

        bridge = _bridge_for_user(user_id)

        durable_by_id = {
            str(item.get("id")): item
            for item in _get_remote_control_store().list_automations(user_id=user_id)
            if company_record_matches(
                item,
                company_id=company_id,
                include_legacy=include_legacy,
            )
        }

        merged: list[ScheduledJobView] = []

        seen: set[str] = set()

        for job in bridge.list_jobs():

            job_id = str(job.get("id") or "")

            durable = dict(durable_by_id.get(job_id) or {})
            if not durable and not include_legacy:
                continue

            payload = {**durable, **job}

            if durable:

                payload.setdefault("automation_id", durable.get("automation_id") or job_id)

                for key in (

                    "target_kind",

                    "target_identity_id",

                    "target_group_id",

                    "target_chat_id",

                    "chat_target",

                    "permission_mode",

                    "tool_packs",

                    "metadata",

                    "requires_confirmation",

                    "confirmation_status",

                    "confirmation_expires_at",

                ):

                    if key in durable and key not in job:

                        payload[key] = durable[key]

            merged.append(ScheduledJobView(**payload))

            seen.add(job_id)

        for job_id, durable in durable_by_id.items():

            if job_id not in seen:

                merged.append(ScheduledJobView.model_validate(durable))

        return merged
