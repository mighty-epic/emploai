from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

from shared.subprocess_utils import hidden_subprocess_kwargs
from app_backend.automation_sessions import (
    resolve_existing_automation_session,
    resolve_new_automation_session,
)
from app_backend.company_runtime_context import (
    company_record_matches,
    require_company_record,
    selected_company_scope,
)

def _persist_sleep_mode_enabled(user_id, enabled):

    try:

        store = _get_remote_control_store()

        profile = store.get_user_profile(user_id=int(user_id))

        preferences = dict(profile.get("preferences") or {})

        if preferences.get("sleep_mode_enabled") == bool(enabled):

            return

        preferences["sleep_mode_enabled"] = bool(enabled)

        store.update_user_profile(user_id=int(user_id), profile={**profile, "preferences": preferences})

    except Exception:

        logger.exception("[app] failed to persist shared sleep mode preference")

def register_event_routes(app):

    def _company_scope(auth: Dict[str, Any]) -> Dict[str, Any]:
        return selected_company_scope(
            auth=auth,
            company_store=_get_company_store(),
            fleet_store=_get_remote_control_store(),
        )

    def _require_scoped_record(
        auth: Dict[str, Any],
        record: Any,
        *,
        message: str,
    ) -> Dict[str, Any]:
        scope = _company_scope(auth)
        try:
            require_company_record(
                record,
                company_id=scope.get("company_id"),
                include_legacy=bool(scope.get("include_legacy")),
                message=message,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=message) from exc
        return scope

    def _scoped_automation(auth: Dict[str, Any], automation_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        try:
            record = _get_remote_control_store().get_automation(
                user_id=int(auth["user_id"]),
                automation_id=automation_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Automation not found") from exc
        scope = _require_scoped_record(
            auth,
            record,
            message="Automation not found in the selected company",
        )
        return record, scope

    def _scoped_fleet_snapshot(auth: Dict[str, Any], scope: Dict[str, Any]) -> Dict[str, Any]:
        return _get_remote_control_store().get_fleet_snapshot(
            user_id=int(auth["user_id"]),
            desktop_id=scope.get("computer_id"),
            company_id=scope.get("company_id"),
            company_computer_ids=scope.get("company_computer_ids"),
            include_unscoped_company_records=bool(scope.get("include_legacy")),
        )

    def _session_record_matches_company(
        auth: Dict[str, Any],
        record: Dict[str, Any],
    ) -> bool:
        scope = _company_scope(auth)
        metadata_company_id = str(
            dict(record.get("metadata") or {}).get("company_id") or ""
        ).strip()
        if metadata_company_id:
            return metadata_company_id == str(scope.get("company_id") or "")
        session_id = str(record.get("session_id") or "").strip()
        if session_id:
            try:
                session = _bridge_for_user(int(auth["user_id"])).get_session(session_id)
            except Exception:
                return False
            return company_record_matches(
                session,
                company_id=scope.get("company_id"),
                include_legacy=bool(scope.get("include_legacy")),
            )
        return bool(scope.get("include_legacy"))

    def _find_scoped_runtime_record(
        auth: Dict[str, Any],
        records: list[Dict[str, Any]],
        *,
        field: str,
        value: str,
        message: str,
    ) -> Dict[str, Any]:
        record = next(
            (
                item
                for item in records
                if str(item.get(field) or "") == str(value or "")
                and _session_record_matches_company(auth, item)
            ),
            None,
        )
        if not record:
            raise HTTPException(status_code=404, detail=message)
        return record

    def _company_metadata(
        auth: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        company_id = str(_company_scope(auth).get("company_id") or "").strip()
        return {
            **dict(metadata or {}),
            **({"company_id": company_id} if company_id else {}),
        }

    @app.get("/api/app/automations/{job_id}", response_model=JobDetailView)

    @app.get("/api/app/jobs/{job_id}", response_model=JobDetailView)

    async def get_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobDetailView:

        auth = _resolve_token(authorization)

        user_id = int(auth["user_id"])

        durable = None

        try:

            durable = _get_remote_control_store().get_automation(user_id=user_id, automation_id=job_id)
            _require_scoped_record(
                auth,
                durable,
                message="Automation not found in the selected company",
            )

        except KeyError:

            durable = None

        if _is_remote_session_auth(auth):

            if durable:

                return JobDetailView.model_validate(durable)

            state = _remote_shared_state(auth)

            for raw in list(state.get("jobs") or []):

                if str((raw or {}).get("id") or (raw or {}).get("automation_id") or "") == str(job_id):
                    _require_scoped_record(
                        auth,
                        raw,
                        message="Automation not found in the selected company",
                    )

                    return JobDetailView.model_validate(raw)

            raise HTTPException(status_code=404, detail="Job not found")

        bridge = _bridge_for_user(user_id)
        scope = _company_scope(auth)

        try:

            payload = bridge.get_job(job_id)
            if not durable and not bool(scope.get("include_legacy")):
                raise HTTPException(status_code=404, detail="Automation not found")

            if durable:

                payload = {**durable, **payload}

            return JobDetailView(**payload)

        except KeyError as exc:

            if durable:

                return JobDetailView.model_validate(durable)

            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.get("/api/app/events", response_model=list[CronFeedItemView])

    @app.get("/api/app/cron/feed", response_model=list[CronFeedItemView])

    async def cron_feed(authorization: Optional[str] = Header(default=None)) -> list[CronFeedItemView]:

        auth = _resolve_token(authorization)

        user_id = int(auth["user_id"])
        scope = _company_scope(auth)

        durable = [
            item
            for item in _get_remote_control_store().list_automation_events(user_id=user_id)
            if company_record_matches(
                item,
                company_id=scope.get("company_id"),
                include_legacy=bool(scope.get("include_legacy")),
            )
        ]

        seen = {str(item.get("id") or item.get("event_id") or "") for item in durable}

        items = [CronFeedItemView(**item) for item in durable]

        if _is_remote_session_auth(auth):

            return items[:400]

        bridge = _bridge_for_user(user_id)

        for item in bridge.list_cron_feed():
            if not company_record_matches(
                item,
                company_id=scope.get("company_id"),
                include_legacy=bool(scope.get("include_legacy")),
            ):
                continue

            item_id = str(item.get("id") or "")

            if item_id and item_id in seen:

                continue

            items.append(CronFeedItemView(**item))

        return items[:400]

    @app.get("/api/app/events/runs", response_model=list[AutomationEventRunView])

    async def event_runs(authorization: Optional[str] = Header(default=None)) -> list[AutomationEventRunView]:

        auth = _resolve_token(authorization)
        scope = _company_scope(auth)

        return [
            AutomationEventRunView(**item)
            for item in _get_remote_control_store().list_event_runs(user_id=int(auth["user_id"]))
            if company_record_matches(
                item,
                company_id=scope.get("company_id"),
                include_legacy=bool(scope.get("include_legacy")),
            )
        ]

    @app.get("/api/app/events/process-waits", response_model=list[ProcessWaitView])

    async def process_waits(authorization: Optional[str] = Header(default=None)) -> list[ProcessWaitView]:

        auth = _resolve_token(authorization)

        return [
            ProcessWaitView(**item)
            for item in _get_remote_control_store().list_process_waits(
                user_id=int(auth["user_id"])
            )
            if _session_record_matches_company(auth, item)
        ]

    @app.get("/api/app/events/planner-contracts", response_model=list[PlannerContractView])

    async def planner_contracts(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> list[PlannerContractView]:

        auth = _resolve_token(authorization)

        return [

            PlannerContractView(**item)

            for item in _get_remote_control_store().list_planner_contracts(

                user_id=int(auth["user_id"]),

                session_id=session_id,

            )
            if _session_record_matches_company(auth, item)

        ]

    @app.post("/api/app/events/runs/{event_run_id}/cancel", response_model=AutomationEventRunView)

    async def cancel_event_run(

        event_run_id: str,

        request: RuntimeActionRequest,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> AutomationEventRunView:

        auth = _resolve_token(authorization)
        _find_scoped_runtime_record(
            auth,
            _get_remote_control_store().list_event_runs(
                user_id=int(auth["user_id"]),
                limit=1000,
            ),
            field="event_run_id",
            value=event_run_id,
            message="Event run not found in the selected company",
        )

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="automation_event_run_cancel",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"event_run_id": event_run_id, "reason": request.reason},

        )

        try:

            run = _get_remote_control_store().update_event_run_status(

                user_id=int(auth["user_id"]),

                event_run_id=event_run_id,

                status="canceled",

                error=request.reason or "Event run canceled by user.",

                metadata=_company_metadata(
                    auth,
                    {"action_reason": request.reason, **dict(request.metadata or {})},
                ),

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail="Event run not found") from exc

        _get_remote_control_store().append_automation_event(

            user_id=int(auth["user_id"]),

            automation_id=run.get("automation_id"),

            kind="event_run_canceled",

            event_type="event_run_canceled",

            event_source="runtime_control",

            content=f"Event run {event_run_id} was canceled.",

            status="canceled",

            target_identity_id=run.get("target_identity_id"),

            target_chat_id=run.get("target_chat_id"),

            importance="important",

            metadata=_company_metadata(
                auth,
                {"event_run_id": event_run_id, "reason": request.reason},
            ),

        )

        return AutomationEventRunView(**run)

    @app.post("/api/app/events/runs/{event_run_id}/retry", response_model=AutomationEventRunView)

    async def retry_event_run(

        event_run_id: str,

        request: RuntimeActionRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> AutomationEventRunView:

        auth = _resolve_token(authorization)
        _find_scoped_runtime_record(
            auth,
            _get_remote_control_store().list_event_runs(
                user_id=int(auth["user_id"]),
                limit=1000,
            ),
            field="event_run_id",
            value=event_run_id,
            message="Event run not found in the selected company",
        )

        try:

            run = _get_remote_control_store().update_event_run_status(

                user_id=int(auth["user_id"]),

                event_run_id=event_run_id,

                status="retrying",

                result=None,

                error=None,

                metadata=_company_metadata(
                    auth,
                    {
                        "retry_requested_by": str(auth.get("actor_kind") or "app"),
                        "retry_reason": request.reason,
                        **dict(request.metadata or {}),
                    },
                ),

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail="Event run not found") from exc

        _get_remote_control_store().append_automation_event(

            user_id=int(auth["user_id"]),

            automation_id=run.get("automation_id"),

            kind="event_run_retry_requested",

            event_type="event_run_retry_requested",

            event_source="runtime_control",

            content=f"Retry requested for event run {event_run_id}.",

            status="queued",

            target_identity_id=run.get("target_identity_id"),

            target_chat_id=run.get("target_chat_id"),

            importance="important",

            metadata=_company_metadata(
                auth,
                {
                    "event_run_id": event_run_id,
                    "reason": request.reason,
                    "manager_review": "queued_if_busy",
                },
            ),

        )

        return AutomationEventRunView(**run)

    def _stop_exact_process_pid(pid: Optional[int]) -> Dict[str, Any]:

        if not pid or int(pid) <= 0:

            return {"stopped": False, "reason": "missing_pid"}

        try:

            if os.name == "nt":

                completed = subprocess.run(

                    ["taskkill", "/PID", str(int(pid)), "/T", "/F"],

                    capture_output=True,

                    text=True,

                    timeout=8,

                    **hidden_subprocess_kwargs(),

                )

                return {

                    "stopped": completed.returncode == 0,

                    "returncode": completed.returncode,

                    "stdout": (completed.stdout or "")[-1000:],

                    "stderr": (completed.stderr or "")[-1000:],

                }

            os.kill(int(pid), 15)

            return {"stopped": True}

        except Exception as exc:

            return {"stopped": False, "reason": str(exc)}

    @app.post("/api/app/events/process-waits/{process_wait_id}/cancel", response_model=ProcessWaitView)

    async def cancel_process_wait(

        process_wait_id: str,

        request: RuntimeActionRequest,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> ProcessWaitView:

        auth = _resolve_token(authorization)
        _find_scoped_runtime_record(
            auth,
            _get_remote_control_store().list_process_waits(
                user_id=int(auth["user_id"]),
                limit=1000,
            ),
            field="process_wait_id",
            value=process_wait_id,
            message="Process wait not found in the selected company",
        )

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="process_wait_cancel",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"process_wait_id": process_wait_id, "reason": request.reason},

        )

        try:

            wait = _get_remote_control_store().update_process_wait(

                user_id=int(auth["user_id"]),

                process_wait_id=process_wait_id,

                status="canceled",

                metadata=_company_metadata(
                    auth,
                    {"action_reason": request.reason, **dict(request.metadata or {})},
                ),

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail="Process wait not found") from exc

        _get_remote_control_store().append_automation_event(

            user_id=int(auth["user_id"]),

            kind="process_wait_canceled",

            event_type="process_wait_canceled",

            event_source="runtime_control",

            content=f"Process wait {wait.get('command_id') or process_wait_id} was canceled.",

            status="canceled",

            target_chat_id=wait.get("session_id"),

            importance="important",

            metadata=_company_metadata(
                auth,
                {"process_wait_id": process_wait_id, "reason": request.reason},
            ),

        )

        return ProcessWaitView(**wait)

    @app.post("/api/app/events/process-waits/{process_wait_id}/stop", response_model=ProcessWaitView)

    async def stop_process_wait(

        process_wait_id: str,

        request: RuntimeActionRequest,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> ProcessWaitView:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Process control must run on the local desktop backend")

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="process_wait_stop",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"process_wait_id": process_wait_id, "reason": request.reason},

        )

        existing = next(

            (item for item in _get_remote_control_store().list_process_waits(user_id=int(auth["user_id"]), limit=1000) if item.get("process_wait_id") == process_wait_id),

            None,

        )

        if not existing:

            raise HTTPException(status_code=404, detail="Process wait not found")
        if not _session_record_matches_company(auth, existing):
            raise HTTPException(
                status_code=404,
                detail="Process wait not found in the selected company",
            )

        stop_result = _stop_exact_process_pid(existing.get("pid"))

        wait = _get_remote_control_store().update_process_wait(

            user_id=int(auth["user_id"]),

            process_wait_id=process_wait_id,

            status="stopped" if stop_result.get("stopped") else "stop_failed",

            metadata=_company_metadata(
                auth,
                {
                    "stop_result": stop_result,
                    "action_reason": request.reason,
                    **dict(request.metadata or {}),
                },
            ),

        )

        _get_remote_control_store().append_automation_event(

            user_id=int(auth["user_id"]),

            kind="process_wait_stop_requested",

            event_type="process_wait_stop_requested",

            event_source="runtime_control",

            content=f"Stop requested for process wait {wait.get('command_id') or process_wait_id}: {'stopped' if stop_result.get('stopped') else 'not stopped'}.",

            status=wait.get("status"),

            target_chat_id=wait.get("session_id"),

            importance="important",

            metadata=_company_metadata(
                auth,
                {
                    "process_wait_id": process_wait_id,
                    "stop_result": stop_result,
                    "reason": request.reason,
                },
            ),

        )

        return ProcessWaitView(**wait)

    @app.post("/api/app/events/process-waits/{process_wait_id}/persistent", response_model=ProcessWaitView)

    async def set_process_wait_persistent(

        process_wait_id: str,

        request: ProcessWaitUpdateRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> ProcessWaitView:

        auth = _resolve_token(authorization)
        _find_scoped_runtime_record(
            auth,
            _get_remote_control_store().list_process_waits(
                user_id=int(auth["user_id"]),
                limit=1000,
            ),
            field="process_wait_id",
            value=process_wait_id,
            message="Process wait not found in the selected company",
        )

        try:

            wait = _get_remote_control_store().update_process_wait(

                user_id=int(auth["user_id"]),

                process_wait_id=process_wait_id,

                persistent=bool(request.persistent),

                metadata=_company_metadata(
                    auth,
                    {
                        "persistent_reason": request.reason,
                        **dict(request.metadata or {}),
                    },
                ),

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail="Process wait not found") from exc

        return ProcessWaitView(**wait)

    @app.post("/api/app/events/planner-contracts/{contract_id}/status", response_model=PlannerContractView)

    async def update_planner_contract_status(

        contract_id: str,

        request: PlannerContractStatusRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> PlannerContractView:

        auth = _resolve_token(authorization)
        _find_scoped_runtime_record(
            auth,
            _get_remote_control_store().list_planner_contracts(
                user_id=int(auth["user_id"]),
            ),
            field="contract_id",
            value=contract_id,
            message="Planner contract not found in the selected company",
        )

        try:

            contract = _get_remote_control_store().update_planner_contract_status(

                user_id=int(auth["user_id"]),

                contract_id=contract_id,

                status=request.status,

                metadata=request.metadata,

            )

        except KeyError as exc:

            raise HTTPException(status_code=404, detail="Planner contract not found") from exc

        return PlannerContractView(**contract)

    @app.post("/api/app/events/{event_id}/ack", response_model=CronFeedItemView)

    async def acknowledge_event(event_id: str, authorization: Optional[str] = Header(default=None)) -> CronFeedItemView:

        auth = _resolve_token(authorization)
        event = next(
            (
                item
                for item in _get_remote_control_store().list_automation_events(
                    user_id=int(auth["user_id"]),
                    limit=1000,
                )
                if str(item.get("id") or item.get("event_id") or "") == str(event_id)
            ),
            None,
        )
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        _require_scoped_record(
            auth,
            event,
            message="Event not found in the selected company",
        )

        try:

            return CronFeedItemView(**_get_remote_control_store().acknowledge_automation_event(user_id=int(auth["user_id"]), event_id=event_id))

        except KeyError as exc:

            raise HTTPException(status_code=404, detail="Event not found") from exc

    @app.post("/api/app/automations", response_model=JobDetailView)

    @app.post("/api/app/jobs", response_model=JobDetailView)

    async def create_job(request: JobCreateRequest, authorization: Optional[str] = Header(default=None)) -> JobDetailView:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Automation scheduling must run on the local desktop backend")

        user_id = int(auth["user_id"])
        scope = _company_scope(auth)
        company_id = str(scope.get("company_id") or "").strip() or None

        bridge = _bridge_for_user(user_id)

        interval_seconds, error = parse_schedule_with_error(request.schedule)

        if error or not interval_seconds:

            raise HTTPException(status_code=400, detail=error or "Invalid schedule")

        scheduler = get_scheduler()

        origin_session_id = request.session_id or _resolve_target_session_id(bridge, None)

        origin_session = bridge.get_session(origin_session_id)
        try:
            require_company_record(
                origin_session,
                company_id=company_id,
                include_legacy=bool(scope.get("include_legacy")),
                message="The selected chat belongs to a different company",
            )
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        origin_bot = bridge.orchestrator.resolve_telegram_bot_for_session(origin_session)

        metadata_payload = {
            **dict(request.metadata or {}),
            "company_id": company_id,
        }
        if request.target_identity_id:
            visible_identity_ids = {
                str(item.get("identity_id") or "")
                for item in list(_scoped_fleet_snapshot(auth, scope).get("identities") or [])
            }
            if str(request.target_identity_id) not in visible_identity_ids:
                raise HTTPException(
                    status_code=409,
                    detail="The selected entity belongs to a different company or is unavailable",
                )

        requires_confirmation = bool(request.requires_confirmation or metadata_payload.get("agent_created") or metadata_payload.get("agent_proposed"))

        if requires_confirmation:

            durable = _get_remote_control_store().upsert_automation(

                user_id=user_id,

                name=request.name,

                prompt=request.prompt,

                schedule=request.schedule,

                schedule_mode="proposal",

                enabled=False,

                status="needs_confirmation",

                target_kind=request.target_kind or "active_identity",

                target_identity_id=request.target_identity_id,

                target_group_id=request.target_group_id,

                target_chat_id=request.target_chat_id or origin_session.id,

                chat_target=request.chat_target or "existing_or_new",

                permission_mode=request.permission_mode,

                tool_packs=list(request.tool_packs or []),

                metadata={

                    **metadata_payload,

                    "origin_session_id": origin_session.id,

                    "origin_workspace": origin_session.workspace,

                    "origin_model": origin_session.model,

                    "origin_enabled_tool_packs": list(getattr(origin_session, "enabled_tool_packs", []) or []),

                    "proposal_reason": metadata_payload.get("proposal_reason") or "Agent-created persistent automation requires confirmation.",

                },

                requires_confirmation=True,

                confirmation_status=request.confirmation_status or "pending",

                confirmation_expires_at=time.time() + 60 * 60 * 24 * 7,

            )

            _get_remote_control_store().append_automation_event(

                user_id=user_id,

                automation_id=durable.get("automation_id") or durable.get("id"),

                kind="automation_proposed",

                event_type="automation_proposed",

                event_source="agent_proposal",

                content=f"Automation proposal '{request.name}' is waiting for confirmation.",

                status="needs_confirmation",

                target_identity_id=request.target_identity_id,

                target_chat_id=request.target_chat_id or origin_session.id,

                importance="important",

                metadata={"automation": durable, "company_id": company_id},

            )

            return JobDetailView.model_validate(durable)

        requested_chat_target = str(request.chat_target or "").strip().lower()
        resolved_chat_target = request.chat_target or "existing_or_new"
        resolved_target_identity_id = request.target_identity_id
        if requested_chat_target in {"existing", "new"}:
            fleet_snapshot = _scoped_fleet_snapshot(auth, scope)
            identities = [item for item in list(fleet_snapshot.get("identities") or []) if isinstance(item, dict)]
            try:
                if requested_chat_target == "existing":
                    execution = resolve_existing_automation_session(
                        bridge=bridge,
                        identities=identities,
                        session_id=request.target_chat_id or request.session_id,
                        identity_id=request.target_identity_id,
                        company_id=company_id,
                        include_legacy=bool(scope.get("include_legacy")),
                    )
                else:
                    execution = resolve_new_automation_session(
                        bridge=bridge,
                        identities=identities,
                        active_identity_id=fleet_snapshot.get("active_identity_id"),
                        automation_name=request.name,
                        identity_id=request.target_identity_id,
                        model=request.model,
                        variant=request.variant,
                        permission_mode=request.permission_mode,
                        company_id=company_id,
                        include_legacy=bool(scope.get("include_legacy")),
                    )
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            origin_session = execution.session
            resolved_chat_target = execution.chat_target
            resolved_target_identity_id = execution.identity_id

        origin_bot = bridge.orchestrator.resolve_telegram_bot_for_session(origin_session)
        origin_tool_packs = list(getattr(origin_session, "enabled_tool_packs", []) or [])
        origin_permission_mode = str(getattr(origin_session, "security_permission_mode", "") or "").strip() or request.permission_mode

        job_id = scheduler.add_job(

            name=request.name,

            prompt=request.prompt,

            interval_seconds=interval_seconds,

            schedule_text=request.schedule,

            owner_user_id=int(auth["user_id"]),

            origin_session_id=origin_session.id,

            origin_telegram_bot_config_id=str(origin_bot.get("id") or "").strip() or None if origin_bot else None,

            origin_workspace=origin_session.workspace,

            origin_model=origin_session.model,

            origin_variant=getattr(origin_session, "variant", None),

            origin_enabled_tool_packs=origin_tool_packs,

        )

        scheduler_payload: Dict[str, Any] = {}

        try:

            scheduler_payload = bridge.get_job(job_id)

        except KeyError:

            scheduler_payload = {

                "id": job_id,

                "name": request.name,

                "prompt": request.prompt,

                "schedule": request.schedule,

                "enabled": True,

            }

        durable = _get_remote_control_store().upsert_automation(

            user_id=user_id,

            automation_id=job_id,

            name=request.name,

            prompt=request.prompt,

            schedule=request.schedule,

            schedule_mode="delay" if bool(scheduler_payload.get("one_time")) else "schedule",

            enabled=True,

            target_kind="identity" if resolved_target_identity_id else (request.target_kind or "active_identity"),

            target_identity_id=resolved_target_identity_id,

            target_group_id=request.target_group_id,

            target_chat_id=origin_session.id,

            chat_target=resolved_chat_target,

            permission_mode=origin_permission_mode,

            tool_packs=origin_tool_packs,

            metadata={

                **metadata_payload,

                "origin_session_id": origin_session.id,

                "origin_workspace": origin_session.workspace,

                "origin_model": origin_session.model,

                "origin_variant": getattr(origin_session, "variant", None),

                "origin_enabled_tool_packs": origin_tool_packs,

                "automation_managed_chat": resolved_chat_target == "new",

            },

            one_time=bool(scheduler_payload.get("one_time")),

        )

        try:

            return JobDetailView(**{**durable, **scheduler_payload})

        except KeyError:

            return JobDetailView(

                id=job_id,

                automation_id=job_id,

                name=request.name,

                prompt=request.prompt,

                schedule=request.schedule,

                enabled=True,

            )

    @app.put("/api/app/automations/{job_id}", response_model=JobDetailView)

    @app.put("/api/app/jobs/{job_id}", response_model=JobDetailView)

    async def update_job(

        job_id: str,

        request: JobCreateRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> JobDetailView:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Automation changes must run on the local desktop backend")

        user_id = int(auth["user_id"])
        scope = _company_scope(auth)
        company_id = str(scope.get("company_id") or "").strip() or None

        store = _get_remote_control_store()

        existing, scope = _scoped_automation(auth, job_id)
        company_id = str(scope.get("company_id") or "").strip() or None

        interval_seconds, error = parse_schedule_with_error(request.schedule)

        if error or not interval_seconds:

            raise HTTPException(status_code=400, detail=error or "Invalid schedule")

        clean_name = str(request.name or "").strip()

        clean_prompt = str(request.prompt or "").strip()

        if not clean_name or not clean_prompt:

            raise HTTPException(status_code=400, detail="Name and task are required")

        scheduler = get_scheduler()

        bridge = _bridge_for_user(user_id)
        existing_metadata = dict(existing.get("metadata") or {})
        requested_chat_target = str(request.chat_target or existing.get("chat_target") or "").strip().lower()
        resolved_chat_target = requested_chat_target or "existing_or_new"
        resolved_target_identity_id = request.target_identity_id or existing.get("target_identity_id")
        if requested_chat_target in {"existing", "new"}:
            fleet_snapshot = _scoped_fleet_snapshot(auth, scope)
            identities = [item for item in list(fleet_snapshot.get("identities") or []) if isinstance(item, dict)]
            try:
                if requested_chat_target == "existing":
                    execution = resolve_existing_automation_session(
                        bridge=bridge,
                        identities=identities,
                        session_id=request.target_chat_id or request.session_id,
                        identity_id=resolved_target_identity_id,
                        company_id=company_id,
                        include_legacy=bool(scope.get("include_legacy")),
                    )
                else:
                    reusable_session_id = (
                        existing.get("target_chat_id")
                        if str(existing.get("chat_target") or "").lower() == "new"
                        and bool(existing_metadata.get("automation_managed_chat"))
                        and str(existing.get("target_identity_id") or "") == str(resolved_target_identity_id or "")
                        else None
                    )
                    execution = resolve_new_automation_session(
                        bridge=bridge,
                        identities=identities,
                        active_identity_id=fleet_snapshot.get("active_identity_id"),
                        automation_name=clean_name,
                        identity_id=resolved_target_identity_id,
                        model=request.model or existing_metadata.get("origin_model"),
                        variant=request.variant or existing_metadata.get("origin_variant"),
                        permission_mode=request.permission_mode or existing.get("permission_mode"),
                        reusable_session_id=reusable_session_id,
                        company_id=company_id,
                        include_legacy=bool(scope.get("include_legacy")),
                    )
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            origin_session = execution.session
            resolved_chat_target = execution.chat_target
            resolved_target_identity_id = execution.identity_id
        else:
            origin_session_id = str(
                existing_metadata.get("origin_session_id")
                or existing.get("target_chat_id")
                or _resolve_target_session_id(bridge, None)
            )
            origin_session = bridge.get_session(origin_session_id)
            try:
                require_company_record(
                    origin_session,
                    company_id=company_id,
                    include_legacy=bool(scope.get("include_legacy")),
                    message="The automation chat belongs to a different company",
                )
            except LookupError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        origin_bot = bridge.orchestrator.resolve_telegram_bot_for_session(origin_session)
        origin_tool_packs = list(getattr(origin_session, "enabled_tool_packs", []) or [])
        origin_permission_mode = str(getattr(origin_session, "security_permission_mode", "") or "").strip() or request.permission_mode or "standard"

        scheduler_job = scheduler.get_job(job_id)

        if scheduler_job:

            scheduler.update_job(

                job_id,

                name=clean_name,

                prompt=clean_prompt,

                schedule_text=request.schedule,

                interval_seconds=interval_seconds,

                enabled=bool(existing.get("enabled", True)),

                origin_session_id=origin_session.id,

                origin_telegram_bot_config_id=str(origin_bot.get("id") or "").strip() or None if origin_bot else None,

                origin_workspace=origin_session.workspace,

                origin_model=origin_session.model,

                origin_variant=getattr(origin_session, "variant", None),

                origin_enabled_tool_packs=origin_tool_packs,

            )

        else:

            scheduler.add_job(

                name=clean_name,

                prompt=clean_prompt,

                interval_seconds=interval_seconds,

                enabled=bool(existing.get("enabled", True)),

                schedule_text=request.schedule,

                owner_user_id=user_id,

                origin_session_id=origin_session.id,

                origin_telegram_bot_config_id=str(origin_bot.get("id") or "").strip() or None if origin_bot else None,

                origin_workspace=origin_session.workspace,

                origin_model=origin_session.model,

                origin_variant=getattr(origin_session, "variant", None),

                origin_enabled_tool_packs=origin_tool_packs,

                job_id=job_id,

            )

        scheduler_job = scheduler.get_job(job_id)

        scheduler_payload = bridge.get_job(job_id)

        request_metadata = dict(request.metadata or {})

        request_metadata.pop("cloud_mirror_policy", None)
        request_metadata["company_id"] = company_id

        confirmation_expires_at = None

        if existing.get("confirmation_expires_at"):

            try:

                confirmation_expires_at = datetime.fromisoformat(

                    str(existing["confirmation_expires_at"]).replace("Z", "+00:00")

                ).timestamp()

            except (TypeError, ValueError):

                confirmation_expires_at = None

        durable = store.upsert_automation(

            user_id=user_id,

            automation_id=job_id,

            name=clean_name,

            prompt=clean_prompt,

            schedule=request.schedule,

            schedule_mode=str(request_metadata.get("schedule_mode") or existing.get("schedule_mode") or "schedule"),

            enabled=bool(existing.get("enabled", True)),

            status="active" if bool(existing.get("enabled", True)) else "paused",

            target_kind="identity" if resolved_target_identity_id else (request.target_kind or "active_identity"),

            target_identity_id=resolved_target_identity_id,

            target_group_id=request.target_group_id,

            target_chat_id=origin_session.id,

            chat_target=resolved_chat_target,

            permission_mode=origin_permission_mode,

            tool_packs=origin_tool_packs,

            metadata={

                **dict(existing.get("metadata") or {}),

                **request_metadata,

                "updated_from": "desktop_automations",

                "origin_session_id": origin_session.id,

                "origin_workspace": origin_session.workspace,

                "origin_model": origin_session.model,

                "origin_variant": getattr(origin_session, "variant", None),

                "origin_enabled_tool_packs": origin_tool_packs,

                "automation_managed_chat": resolved_chat_target == "new",

            },

            next_run_at=getattr(scheduler_job, "next_run", None),

            one_time=bool(getattr(scheduler_job, "one_time", False)),

            requires_confirmation=bool(existing.get("requires_confirmation", False)),

            confirmation_status=existing.get("confirmation_status"),

            confirmation_expires_at=confirmation_expires_at,

        )

        store.append_automation_event(

            user_id=user_id,

            automation_id=job_id,

            kind="automation_updated",

            event_type="automation_updated",

            event_source="desktop",

            content=f"Automation '{clean_name}' was updated.",

            status="active" if bool(existing.get("enabled", True)) else "paused",

            target_identity_id=resolved_target_identity_id,

            target_chat_id=origin_session.id,

            importance="normal",

            metadata={"schedule": request.schedule, "company_id": company_id},

        )

        return JobDetailView(**{**durable, **scheduler_payload})

    @app.get("/api/app/runtime/orchestrator", response_model=RuntimeOrchestratorView)

    async def runtime_orchestrator_status(authorization: Optional[str] = Header(default=None)) -> RuntimeOrchestratorView:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Runtime orchestration must run on the local desktop backend")

        bridge = _bridge_for_user(int(auth["user_id"]))

        return RuntimeOrchestratorView(**bridge.orchestrator.runtime_status_view())

    @app.post("/api/app/runtime/headless", response_model=RuntimeOrchestratorView)

    async def configure_headless_runtime(

        request: HeadlessConfigureRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> RuntimeOrchestratorView:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Runtime orchestration must run on the local desktop backend")

        bridge = _bridge_for_user(int(auth["user_id"]))

        was_headless_enabled = bridge.orchestrator.headless_mode_enabled

        payload = bridge.orchestrator.configure_headless(

            enabled=request.enabled,

            default_max_concurrent_chats=request.default_max_concurrent_chats,

            default_sleep_session_by_bot=request.default_sleep_session_by_bot,

        )

        if request.enabled is not None:

            _persist_sleep_mode_enabled(int(auth["user_id"]), bool(request.enabled))

        if request.enabled is True and not was_headless_enabled:

            await _notify_sleep_mode_enabled(bridge)

        return RuntimeOrchestratorView(**payload)

    @app.post("/api/app/automations/{job_id}/run", response_model=JobActionResponse)

    @app.post("/api/app/jobs/{job_id}/run", response_model=JobActionResponse)

    async def run_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Automation execution must run on the local desktop backend")
        _automation, scope = _scoped_automation(auth, job_id)
        company_id = str(scope.get("company_id") or "").strip() or None

        scheduler = get_scheduler()

        if not scheduler.run_job_now(job_id):

            raise HTTPException(status_code=404, detail="Job not found")

        try:

            _get_remote_control_store().create_or_update_event_run(

                user_id=int(auth["user_id"]),

                automation_id=job_id,

                status="queued",

                metadata={
                    "manual_run": True,
                    "source": "api",
                    "company_id": company_id,
                },

            )

            _get_remote_control_store().append_automation_event(

                user_id=int(auth["user_id"]),

                automation_id=job_id,

                kind="automation_manual_run",

                event_type="automation_manual_run",

                event_source="manual",

                content=f"Automation {job_id} was manually queued.",

                status="queued",

                importance="normal",

                metadata={"automation_id": job_id, "company_id": company_id},

            )

        except Exception:

            pass

        return JobActionResponse(job_id=job_id, action="run")

    @app.post("/api/app/automations/{job_id}/resume", response_model=JobActionResponse)

    @app.post("/api/app/automations/{job_id}/enable", response_model=JobActionResponse)

    @app.post("/api/app/jobs/{job_id}/enable", response_model=JobActionResponse)

    async def enable(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Automation scheduler changes must run on the local desktop backend")
        durable, scope = _scoped_automation(auth, job_id)

        scheduler = get_scheduler()

        if not scheduler.enable_job(job_id):

            interval_seconds, error = parse_schedule_with_error(str(durable.get("schedule") or ""))

            if error or not interval_seconds:

                raise HTTPException(status_code=400, detail=error or "Invalid schedule")

            metadata = dict(durable.get("metadata") or {})

            scheduler.add_job(

                name=str(durable.get("name") or "Restored automation"),

                prompt=str(durable.get("prompt") or ""),

                interval_seconds=interval_seconds,

                schedule_text=str(durable.get("schedule") or ""),

                owner_user_id=int(auth["user_id"]),

                origin_session_id=str(metadata.get("origin_session_id") or durable.get("target_chat_id") or ""),

                origin_telegram_bot_config_id=None,

                origin_workspace=metadata.get("origin_workspace"),

                origin_model=metadata.get("origin_model"),

                origin_variant=metadata.get("origin_variant"),

                origin_enabled_tool_packs=list(metadata.get("origin_enabled_tool_packs") or durable.get("tool_packs") or []),

                job_id=job_id,

            )

        try:

            _get_remote_control_store().set_automation_enabled(user_id=int(auth["user_id"]), automation_id=job_id, enabled=True)

            existing = _get_remote_control_store().get_automation(user_id=int(auth["user_id"]), automation_id=job_id)

            if existing.get("requires_confirmation"):

                _get_remote_control_store().upsert_automation(

                    user_id=int(auth["user_id"]),

                    automation_id=job_id,

                    name=str(existing.get("name") or "Automation"),

                    prompt=str(existing.get("prompt") or ""),

                    schedule=existing.get("schedule"),

                    schedule_mode=existing.get("schedule_mode"),

                    enabled=True,

                    status="active",

                    target_kind=str(existing.get("target_kind") or "active_identity"),

                    target_identity_id=existing.get("target_identity_id"),

                    target_group_id=existing.get("target_group_id"),

                    target_chat_id=existing.get("target_chat_id"),

                    chat_target=str(existing.get("chat_target") or "existing_or_new"),

                    permission_mode=existing.get("permission_mode"),

                    tool_packs=list(existing.get("tool_packs") or []),

                    metadata=dict(existing.get("metadata") or {}),

                    one_time=bool(existing.get("one_time")),

                    requires_confirmation=False,

                    confirmation_status="confirmed",

                )

        except Exception:

            pass

        return JobActionResponse(job_id=job_id, action="enable")

    @app.post("/api/app/automations/{job_id}/pause", response_model=JobActionResponse)

    @app.post("/api/app/automations/{job_id}/disable", response_model=JobActionResponse)

    @app.post("/api/app/jobs/{job_id}/disable", response_model=JobActionResponse)

    async def disable(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Automation scheduler changes must run on the local desktop backend")
        _scoped_automation(auth, job_id)

        scheduler = get_scheduler()

        if not scheduler.disable_job(job_id):

            raise HTTPException(status_code=404, detail="Job not found")

        try:

            _get_remote_control_store().set_automation_enabled(user_id=int(auth["user_id"]), automation_id=job_id, enabled=False)

        except Exception:

            pass

        return JobActionResponse(job_id=job_id, action="disable")

    @app.delete("/api/app/automations/{job_id}", response_model=JobActionResponse)

    @app.delete("/api/app/jobs/{job_id}", response_model=JobActionResponse)

    async def delete_job(

        job_id: str,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> JobActionResponse:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Automation deletion must run on the local desktop backend")
        _scoped_automation(auth, job_id)

        _consume_approved_confirmation(

            user_id=int(auth["user_id"]),

            confirmation_id=confirmation_id,

            action_kind="automation_delete",

            executed_by_surface=str(auth.get("actor_kind") or "app"),

            metadata={"automation_id": job_id},

        )

        scheduler = get_scheduler()

        if not scheduler.remove_job(job_id):

            deleted = _get_remote_control_store().delete_automation(user_id=int(auth["user_id"]), automation_id=job_id)

            if not deleted:

                raise HTTPException(status_code=404, detail="Job not found")

            return JobActionResponse(job_id=job_id, action="delete")

        try:

            _get_remote_control_store().delete_automation(user_id=int(auth["user_id"]), automation_id=job_id)

        except Exception:

            pass

        return JobActionResponse(job_id=job_id, action="delete")
