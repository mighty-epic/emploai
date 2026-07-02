from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

def _install_proactive_event_store_callback() -> None:

    try:

        from shared.proactive_runtime import set_event_store_callback

        from shared.proactive_planner_contract import set_planner_contract_store_callback

    except Exception:

        return

    def _callback(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:

        user_id = int(payload.get("user_id") or 0)

        metadata = dict(payload.get("metadata") or {})

        store = _get_remote_control_store()

        event_source = str(payload.get("event_source") or "").strip()

        event_type = str(payload.get("event_type") or payload.get("status") or payload.get("kind") or "").strip()

        event_kind = str(payload.get("kind") or "event").strip()

        if event_source != "loop_guard" and event_kind not in {"event_rate_limited", "repeated_failure_paused"}:

            guard = store.record_loop_guard_event(

                user_id=user_id,

                guard_key="global",

                metadata={"event_source": event_source, "event_type": event_type},

            )

            if not bool(guard.get("allowed", True)):

                return store.append_automation_event(

                    user_id=user_id,

                    kind="event_rate_limited",

                    event_type="event_rate_limited",

                    event_source="loop_guard",

                    content="Automation events were paused because too many events fired in the last hour.",

                    status="blocked",

                    automation_id=payload.get("automation_id"),

                    target_identity_id=metadata.get("target_identity_id") or metadata.get("fleet_identity_id"),

                    target_chat_id=metadata.get("target_chat_id") or metadata.get("session_id"),

                    dedupe_key=f"loop_guard:rate:{user_id}:{int(time.time() // 3600)}",

                    importance="important",

                    metadata={**metadata, "loop_guard": guard},

                )

            normalized_status = str(payload.get("status") or "").strip().lower()

            normalized_type = event_type.lower()

            if normalized_status in {"failed", "blocked"} or normalized_type.endswith("_failed"):

                failure_basis = json.dumps(

                    {

                        "automation_id": payload.get("automation_id"),

                        "event_source": event_source,

                        "event_type": event_type,

                        "content": str(payload.get("content") or "")[:300],

                    },

                    sort_keys=True,

                    default=str,

                )

                failure_key = hashlib.sha256(failure_basis.encode("utf-8")).hexdigest()

                failure_guard = store.record_loop_guard_event(

                    user_id=user_id,

                    guard_key=f"failure:{failure_key}",

                    failed=True,

                    metadata={"failure_basis": failure_basis},

                )

                if not bool(failure_guard.get("allowed", True)):

                    return store.append_automation_event(

                        user_id=user_id,

                        kind="repeated_failure_paused",

                        event_type="repeated_failure_paused",

                        event_source="loop_guard",

                        content="A repeated failure was paused by the runtime cooldown instead of looping.",

                        status="blocked",

                        automation_id=payload.get("automation_id"),

                        target_identity_id=metadata.get("target_identity_id") or metadata.get("fleet_identity_id"),

                        target_chat_id=metadata.get("target_chat_id") or metadata.get("session_id"),

                        dedupe_key=f"loop_guard:failure:{user_id}:{failure_key}",

                        importance="important",

                        metadata={**metadata, "loop_guard": failure_guard},

                    )

        if payload.get("session_id"):

            metadata.setdefault("session_id", payload.get("session_id"))

        if payload.get("session_name"):

            metadata.setdefault("session_name", payload.get("session_name"))

        if payload.get("automation_name"):

            metadata.setdefault("automation_name", payload.get("automation_name"))

            metadata.setdefault("job_name", payload.get("automation_name"))

        event = store.append_automation_event(

            user_id=user_id,

            kind=str(payload.get("kind") or "event"),

            content=str(payload.get("content") or ""),

            event_type=payload.get("event_type"),

            event_source=payload.get("event_source"),

            status=payload.get("status"),

            automation_id=payload.get("automation_id"),

            target_identity_id=metadata.get("target_identity_id") or metadata.get("fleet_identity_id"),

            target_chat_id=metadata.get("target_chat_id") or metadata.get("session_id"),

            dedupe_key=metadata.get("dedupe_key"),

            importance=str(payload.get("importance") or "normal"),

            metadata=metadata,

            scheduled_for=metadata.get("scheduled_for") if isinstance(metadata.get("scheduled_for"), (int, float)) else None,

        )

        command_id = str(metadata.get("command_id") or "").strip()

        if event_source == "background_process" and command_id:

            completed_at = time.time() if event_type in {"process_completed", "process_failed"} else None

            started_at = metadata.get("started_at") if isinstance(metadata.get("started_at"), (int, float)) else None

            store.upsert_process_wait(

                user_id=user_id,

                session_id=metadata.get("session_id") or payload.get("session_id"),

                command_id=command_id,

                pid=metadata.get("pid") if isinstance(metadata.get("pid"), int) else None,

                command=metadata.get("command"),

                cwd=metadata.get("cwd"),

                shell=metadata.get("shell"),

                status=event_type or str(payload.get("status") or "waiting_on_process"),

                resume_policy=metadata.get("resume_policy"),

                persistent=bool(metadata.get("persistent")),

                ready_patterns=list(metadata.get("ready_patterns") or []),

                meaningful_output_patterns=list(metadata.get("meaningful_output_patterns") or []),

                failure_patterns=list(metadata.get("failure_patterns") or []),

                metadata=metadata,

                started_at=started_at,

                completed_at=completed_at,

            )

        automation_id = str(payload.get("automation_id") or "").strip()

        if automation_id and event_type in {"automation_started", "automation_completed", "automation_failed", "process_continuation_result"}:

            run_status = {

                "automation_started": "running",

                "automation_completed": "completed",

                "automation_failed": "failed",

                "process_continuation_result": "completed",

            }.get(event_type, str(payload.get("status") or "queued"))

            active_run = store.find_active_event_run(user_id=user_id, automation_id=automation_id)

            store.create_or_update_event_run(

                user_id=user_id,

                event_run_id=active_run.get("event_run_id") if active_run else None,

                event_id=event.get("event_id") or event.get("id"),

                automation_id=automation_id,

                status=run_status,

                target_identity_id=metadata.get("target_identity_id") or metadata.get("fleet_identity_id"),

                target_chat_id=metadata.get("target_chat_id") or metadata.get("session_id"),

                started_at=time.time() if run_status == "running" else None,

                completed_at=time.time() if run_status in {"completed", "failed", "stopped", "canceled"} else None,

                error=str(payload.get("content") or "")[:4000] if run_status == "failed" else None,

                result=str(payload.get("content") or "")[:20_000] if run_status == "completed" else None,

                metadata=metadata,

            )

            if run_status == "failed":

                review = store.append_automation_event(

                    user_id=user_id,

                    automation_id=automation_id,

                    kind="manager_review_needed",

                    event_type="manager_review_needed",

                    event_source="proactive_runtime",

                    content=(

                        "A proactive run failed and needs manager review. "

                        "The manager agent should assess whether to continue, redirect, or stop."

                    ),

                    status="needs_review",

                    target_identity_id=metadata.get("manager_identity_id") or metadata.get("target_identity_id"),

                    target_chat_id=metadata.get("manager_chat_id") or metadata.get("target_chat_id") or metadata.get("session_id"),

                    dedupe_key=f"manager_review:{automation_id}:{event.get('event_id') or event.get('id')}",

                    importance="important",

                    metadata={

                        **metadata,

                        "failed_event_id": event.get("event_id") or event.get("id"),

                        "automation_id": automation_id,

                        "manager_review_policy": "start_if_idle_else_queue",

                    },

                )

                review_run = store.create_or_update_event_run(

                    user_id=user_id,

                    event_id=review.get("event_id") or review.get("id"),

                    automation_id=f"manager_review:{automation_id}",

                    status="queued",

                    target_identity_id=review.get("target_identity_id"),

                    target_chat_id=review.get("target_chat_id"),

                    max_attempts=1,

                    metadata={"review_event": review, "policy": "start_if_idle_else_queue"},

                )

                review_prompt = (

                    "A proactive event failed while the user was not necessarily watching. "

                    "Review the failure, decide whether the work should continue, stop, or ask the user, "

                    "and produce a short manager-facing recommendation.\n\n"

                    f"Failed event:\n{json.dumps(event, ensure_ascii=False, indent=2, default=str)[:6000]}"

                )

                try:

                    loop = asyncio.get_running_loop()

                    loop.create_task(

                        _try_start_manager_review_turn(

                            user_id=user_id,

                            event_run_id=str(review_run.get("event_run_id") or ""),

                            prompt=review_prompt,

                            target_chat_id=review.get("target_chat_id"),

                        )

                    )

                except RuntimeError:

                    pass

        return event

    set_event_store_callback(_callback)

    def _planner_callback(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:

        user_id = int(payload.get("user_id") or 0)

        return _get_remote_control_store().upsert_planner_contract(

            user_id=user_id,

            session_id=payload.get("session_id"),

            turn_id=payload.get("turn_id"),

            status=str(payload.get("status") or "pending"),

            action=payload.get("action"),

            contract=payload.get("contract") if isinstance(payload.get("contract"), dict) else {},

            corrections=list(payload.get("corrections") or []),

            injected_at=payload.get("injected_at") if isinstance(payload.get("injected_at"), (int, float)) else None,

        )

    set_planner_contract_store_callback(_planner_callback)

def _restore_scheduler_job_from_durable(*, user_id: int, automation_id: str) -> tuple[bool, str]:

    clean_id = str(automation_id or "").strip()

    if not clean_id:

        return False, "missing_automation_id"

    store = _get_remote_control_store()

    try:

        durable = store.get_automation(user_id=int(user_id), automation_id=clean_id)

    except KeyError:

        return False, "automation_not_found"

    if durable.get("requires_confirmation") or str(durable.get("status") or "").strip() == "needs_confirmation":

        return False, "automation_needs_confirmation"

    if not bool(durable.get("enabled", True)):

        return False, "automation_disabled"

    interval_seconds, error = parse_schedule_with_error(str(durable.get("schedule") or ""))

    if error or not interval_seconds:

        return False, error or "invalid_schedule"

    metadata = dict(durable.get("metadata") or {})

    try:

        get_scheduler().add_job(

            name=str(durable.get("name") or "Restored automation"),

            prompt=str(durable.get("prompt") or ""),

            interval_seconds=interval_seconds,

            schedule_text=str(durable.get("schedule") or ""),

            owner_user_id=int(user_id),

            origin_session_id=str(metadata.get("origin_session_id") or durable.get("target_chat_id") or ""),

            origin_telegram_bot_config_id=str(metadata.get("origin_telegram_bot_config_id") or "").strip() or None,

            origin_workspace=metadata.get("origin_workspace"),

            origin_model=metadata.get("origin_model"),

            origin_enabled_tool_packs=list(metadata.get("origin_enabled_tool_packs") or durable.get("tool_packs") or []),

            job_id=clean_id,

        )

    except Exception as exc:

        logger.exception("[automation] failed restoring scheduler job from durable store")

        return False, str(exc)

    return True, "restored"

def _queue_manager_review_for_event_run(*, user_id: int, run: Dict[str, Any], reason: str) -> Dict[str, Any]:

    store = _get_remote_control_store()

    event = store.append_automation_event(

        user_id=int(user_id),

        automation_id=str(run.get("automation_id") or "").strip() or None,

        kind="manager_review_needed",

        event_type="manager_review_needed",

        event_source="event_run_reconciler",

        content=(

            "A proactive event run could not continue automatically and needs manager review. "

            f"Reason: {reason}"

        ),

        status="needs_review",

        target_identity_id=run.get("target_identity_id"),

        target_chat_id=run.get("target_chat_id"),

        dedupe_key=f"manager_review:event_run:{run.get('event_run_id')}",

        importance="important",

        metadata={"event_run": run, "reason": reason},

    )

    review_run = store.create_or_update_event_run(

        user_id=int(user_id),

        event_id=event.get("event_id") or event.get("id"),

        automation_id=f"manager_review:{run.get('event_run_id')}",

        status="queued",

        target_identity_id=run.get("target_identity_id"),

        target_chat_id=run.get("target_chat_id"),

        max_attempts=3,

        metadata={"review_event": event, "failed_event_run": run, "reason": reason},

    )

    return review_run

async def _dispatch_claimed_event_run(run: Dict[str, Any]) -> None:

    store = _get_remote_control_store()

    user_id = int(run.get("user_id") or 0)

    event_run_id = str(run.get("event_run_id") or "").strip()

    automation_id = str(run.get("automation_id") or "").strip()

    if not event_run_id:

        return

    if not automation_id:

        store.update_event_run_status(

            user_id=user_id,

            event_run_id=event_run_id,

            status="failed",

            error="Event run has no automation_id",

        )

        return

    if automation_id.startswith("manager_review:"):

        metadata = dict(run.get("metadata") or {})

        review_event = metadata.get("review_event") if isinstance(metadata.get("review_event"), dict) else {}

        failed_run = metadata.get("failed_event_run") if isinstance(metadata.get("failed_event_run"), dict) else {}

        prompt = str(metadata.get("prompt") or "").strip()

        if not prompt:

            prompt = (

                "Review this proactive runtime issue. Decide whether to continue, stop, or ask the user, "

                "then produce a short recommendation.\n\n"

                f"Review event:\n{json.dumps(review_event or {}, ensure_ascii=False, default=str)[:3000]}\n\n"

                f"Event run:\n{json.dumps(failed_run or run, ensure_ascii=False, default=str)[:4000]}"

            )

        result = await _try_start_manager_review_turn(

            user_id=user_id,

            event_run_id=event_run_id,

            prompt=prompt,

            target_chat_id=run.get("target_chat_id"),

        )

        if not result.get("started"):

            store.create_or_update_event_run(

                user_id=user_id,

                event_run_id=event_run_id,

                event_id=run.get("event_id"),

                automation_id=automation_id,

                status="queued",

                target_identity_id=run.get("target_identity_id"),

                target_chat_id=run.get("target_chat_id"),

                attempt=int(run.get("attempt") or 1),

                max_attempts=int(run.get("max_attempts") or 3),

                next_attempt_at=time.time() + 30,

                metadata={**metadata, "last_dispatch_reason": result.get("reason") or "manager_busy"},

            )

        return

    scheduler = get_scheduler()

    if not scheduler.get_job(automation_id):

        restored, reason = _restore_scheduler_job_from_durable(user_id=user_id, automation_id=automation_id)

        if not restored:

            store.update_event_run_status(

                user_id=user_id,

                event_run_id=event_run_id,

                status="failed",

                error=f"Automation could not be restored: {reason}",

                metadata={"restore_failed": reason},

            )

            _queue_manager_review_for_event_run(user_id=user_id, run=run, reason=reason)

            return

    if not scheduler.run_job_now(automation_id):

        store.update_event_run_status(

            user_id=user_id,

            event_run_id=event_run_id,

            status="failed",

            error="Scheduler refused the automation run request",

        )

        _queue_manager_review_for_event_run(user_id=user_id, run=run, reason="scheduler_run_failed")

        return

    store.update_event_run_status(

        user_id=user_id,

        event_run_id=event_run_id,

        status="running",

        metadata={"dispatched_at": time.time(), "reconciled": True},

    )

async def _event_run_reconciler(stop_event: asyncio.Event) -> None:

    while not stop_event.is_set():

        try:

            claimed = _get_remote_control_store().claim_due_event_runs(limit=20)

            for run in claimed:

                try:

                    await _dispatch_claimed_event_run(run)

                except Exception as exc:

                    logger.exception("[automation] failed dispatching event run")

                    user_id = int(run.get("user_id") or 0)

                    event_run_id = str(run.get("event_run_id") or "").strip()

                    attempt = int(run.get("attempt") or 1)

                    max_attempts = int(run.get("max_attempts") or 3)

                    if attempt < max_attempts:

                        _get_remote_control_store().update_event_run_status(

                            user_id=user_id,

                            event_run_id=event_run_id,

                            status="retrying",

                            error=str(exc),

                            next_attempt_at=time.time() + 30,

                            metadata={"transient_dispatch_error": str(exc), "retry_after_seconds": 30},

                        )

                    else:

                        failed = _get_remote_control_store().update_event_run_status(

                            user_id=user_id,

                            event_run_id=event_run_id,

                            status="failed",

                            error=str(exc),

                            metadata={"dispatch_error": str(exc)},

                        )

                        _queue_manager_review_for_event_run(user_id=user_id, run=failed, reason=str(exc))

        except Exception:

            logger.exception("[automation] event-run reconciler tick failed")

        try:

            await asyncio.wait_for(stop_event.wait(), timeout=5.0)

        except asyncio.TimeoutError:

            continue

async def _start_proactive_runtime_services(app: FastAPI) -> None:

    try:

        from app_backend.cron_runtime import ensure_global_cron_scheduler_started

        await ensure_global_cron_scheduler_started()

    except Exception:

        logger.exception("[automation] failed starting global scheduler")

    stop_event = asyncio.Event()

    app.state.event_run_reconciler_stop = stop_event

    app.state.event_run_reconciler_task = asyncio.create_task(_event_run_reconciler(stop_event))

async def _stop_proactive_runtime_services(app: FastAPI) -> None:

    stop_event = getattr(app.state, "event_run_reconciler_stop", None)

    if isinstance(stop_event, asyncio.Event):

        stop_event.set()

    task = getattr(app.state, "event_run_reconciler_task", None)

    if isinstance(task, asyncio.Task):

        task.cancel()

        try:

            await task

        except asyncio.CancelledError:

            pass

    app.state.event_run_reconciler_stop = None

    app.state.event_run_reconciler_task = None
