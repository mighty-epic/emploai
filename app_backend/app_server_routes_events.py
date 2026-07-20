from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

from shared.subprocess_utils import hidden_subprocess_kwargs

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

    @app.get("/api/app/automations/{job_id}", response_model=JobDetailView)

    @app.get("/api/app/jobs/{job_id}", response_model=JobDetailView)

    async def get_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobDetailView:

        auth = _resolve_token(authorization)

        user_id = int(auth["user_id"])

        durable = None

        try:

            durable = _get_remote_control_store().get_automation(user_id=user_id, automation_id=job_id)

        except KeyError:

            durable = None

        if _is_remote_session_auth(auth):

            if durable:

                return JobDetailView.model_validate(durable)

            state = _remote_shared_state(auth)

            for raw in list(state.get("jobs") or []):

                if str((raw or {}).get("id") or (raw or {}).get("automation_id") or "") == str(job_id):

                    return JobDetailView.model_validate(raw)

            raise HTTPException(status_code=404, detail="Job not found")

        bridge = _bridge_for_user(user_id)

        try:

            payload = bridge.get_job(job_id)

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

        durable = _get_remote_control_store().list_automation_events(user_id=user_id)

        seen = {str(item.get("id") or item.get("event_id") or "") for item in durable}

        items = [CronFeedItemView(**item) for item in durable]

        if _is_remote_session_auth(auth):

            return items[:400]

        bridge = _bridge_for_user(user_id)

        for item in bridge.list_cron_feed():

            item_id = str(item.get("id") or "")

            if item_id and item_id in seen:

                continue

            items.append(CronFeedItemView(**item))

        return items[:400]

    @app.get("/api/app/events/runs", response_model=list[AutomationEventRunView])

    async def event_runs(authorization: Optional[str] = Header(default=None)) -> list[AutomationEventRunView]:

        auth = _resolve_token(authorization)

        return [AutomationEventRunView(**item) for item in _get_remote_control_store().list_event_runs(user_id=int(auth["user_id"]))]

    @app.get("/api/app/events/process-waits", response_model=list[ProcessWaitView])

    async def process_waits(authorization: Optional[str] = Header(default=None)) -> list[ProcessWaitView]:

        auth = _resolve_token(authorization)

        return [ProcessWaitView(**item) for item in _get_remote_control_store().list_process_waits(user_id=int(auth["user_id"]))]

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

        ]

    @app.post("/api/app/events/runs/{event_run_id}/cancel", response_model=AutomationEventRunView)

    async def cancel_event_run(

        event_run_id: str,

        request: RuntimeActionRequest,

        authorization: Optional[str] = Header(default=None),

        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),

    ) -> AutomationEventRunView:

        auth = _resolve_token(authorization)

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

                metadata={"action_reason": request.reason, **dict(request.metadata or {})},

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

            metadata={"event_run_id": event_run_id, "reason": request.reason},

        )

        return AutomationEventRunView(**run)

    @app.post("/api/app/events/runs/{event_run_id}/retry", response_model=AutomationEventRunView)

    async def retry_event_run(

        event_run_id: str,

        request: RuntimeActionRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> AutomationEventRunView:

        auth = _resolve_token(authorization)

        try:

            run = _get_remote_control_store().update_event_run_status(

                user_id=int(auth["user_id"]),

                event_run_id=event_run_id,

                status="retrying",

                result=None,

                error=None,

                metadata={"retry_requested_by": str(auth.get("actor_kind") or "app"), "retry_reason": request.reason, **dict(request.metadata or {})},

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

            metadata={"event_run_id": event_run_id, "reason": request.reason, "manager_review": "queued_if_busy"},

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

                metadata={"action_reason": request.reason, **dict(request.metadata or {})},

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

            metadata={"process_wait_id": process_wait_id, "reason": request.reason},

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

        stop_result = _stop_exact_process_pid(existing.get("pid"))

        wait = _get_remote_control_store().update_process_wait(

            user_id=int(auth["user_id"]),

            process_wait_id=process_wait_id,

            status="stopped" if stop_result.get("stopped") else "stop_failed",

            metadata={"stop_result": stop_result, "action_reason": request.reason, **dict(request.metadata or {})},

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

            metadata={"process_wait_id": process_wait_id, "stop_result": stop_result, "reason": request.reason},

        )

        return ProcessWaitView(**wait)

    @app.post("/api/app/events/process-waits/{process_wait_id}/persistent", response_model=ProcessWaitView)

    async def set_process_wait_persistent(

        process_wait_id: str,

        request: ProcessWaitUpdateRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> ProcessWaitView:

        auth = _resolve_token(authorization)

        try:

            wait = _get_remote_control_store().update_process_wait(

                user_id=int(auth["user_id"]),

                process_wait_id=process_wait_id,

                persistent=bool(request.persistent),

                metadata={"persistent_reason": request.reason, **dict(request.metadata or {})},

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

        bridge = _bridge_for_user(user_id)

        interval_seconds, error = parse_schedule_with_error(request.schedule)

        if error or not interval_seconds:

            raise HTTPException(status_code=400, detail=error or "Invalid schedule")

        scheduler = get_scheduler()

        origin_session_id = request.session_id or _resolve_target_session_id(bridge, None)

        origin_session = bridge.get_session(origin_session_id)

        origin_bot = bridge.orchestrator.resolve_telegram_bot_for_session(origin_session)

        metadata_payload = dict(request.metadata or {})

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

                metadata={"automation": durable},

            )

            return JobDetailView.model_validate(durable)

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

            origin_enabled_tool_packs=list(getattr(origin_session, "enabled_tool_packs", []) or []),

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

        store = _get_remote_control_store()

        try:

            existing = store.get_automation(user_id=user_id, automation_id=job_id)

        except KeyError as exc:

            raise HTTPException(status_code=404, detail="Automation not found") from exc

        interval_seconds, error = parse_schedule_with_error(request.schedule)

        if error or not interval_seconds:

            raise HTTPException(status_code=400, detail=error or "Invalid schedule")

        clean_name = str(request.name or "").strip()

        clean_prompt = str(request.prompt or "").strip()

        if not clean_name or not clean_prompt:

            raise HTTPException(status_code=400, detail="Name and task are required")

        scheduler = get_scheduler()

        scheduler_job = scheduler.get_job(job_id)

        if scheduler_job:

            scheduler.update_job(

                job_id,

                name=clean_name,

                prompt=clean_prompt,

                schedule_text=request.schedule,

                interval_seconds=interval_seconds,

                enabled=bool(existing.get("enabled", True)),

            )

        else:

            scheduler.add_job(

                name=clean_name,

                prompt=clean_prompt,

                interval_seconds=interval_seconds,

                enabled=bool(existing.get("enabled", True)),

                schedule_text=request.schedule,

                owner_user_id=user_id,

                origin_session_id=existing.get("origin_session_id"),

                origin_telegram_bot_config_id=existing.get("origin_telegram_bot_config_id"),

                origin_workspace=existing.get("origin_workspace"),

                origin_model=existing.get("origin_model"),

                origin_enabled_tool_packs=list(existing.get("origin_enabled_tool_packs") or []),

                job_id=job_id,

            )

        scheduler_job = scheduler.get_job(job_id)

        scheduler_payload = _bridge_for_user(user_id).get_job(job_id)

        request_metadata = dict(request.metadata or {})

        request_metadata.pop("cloud_mirror_policy", None)

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

            target_kind=request.target_kind or "active_identity",

            target_identity_id=request.target_identity_id,

            target_group_id=request.target_group_id,

            target_chat_id=request.target_chat_id or existing.get("origin_session_id"),

            chat_target=request.chat_target or "existing_or_new",

            permission_mode=request.permission_mode or "standard",

            tool_packs=list(request.tool_packs or []),

            metadata={

                **dict(existing.get("metadata") or {}),

                **request_metadata,

                "updated_from": "desktop_automations",

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

            target_identity_id=request.target_identity_id,

            target_chat_id=request.target_chat_id or existing.get("origin_session_id"),

            importance="normal",

            metadata={"schedule": request.schedule},

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

        scheduler = get_scheduler()

        if not scheduler.run_job_now(job_id):

            raise HTTPException(status_code=404, detail="Job not found")

        try:

            _get_remote_control_store().create_or_update_event_run(

                user_id=int(auth["user_id"]),

                automation_id=job_id,

                status="queued",

                metadata={"manual_run": True, "source": "api"},

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

                metadata={"automation_id": job_id},

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

        scheduler = get_scheduler()

        if not scheduler.enable_job(job_id):

            durable = None

            try:

                durable = _get_remote_control_store().get_automation(user_id=int(auth["user_id"]), automation_id=job_id)

            except Exception:

                durable = None

            if not durable:

                raise HTTPException(status_code=404, detail="Job not found")

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
