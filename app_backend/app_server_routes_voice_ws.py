from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

def register_voice_ws_routes(app):

    @app.websocket("/ws/app/voice")

    async def voice_ws(websocket: WebSocket) -> None:

        await websocket.accept()

        if not await _ensure_websocket_origin_allowed(websocket):

            return

        logger.info("[app] websocket /ws/app/voice connected from %s", websocket.client.host if websocket.client else "unknown")

        send_lock = asyncio.Lock()

        async def send_model(event: RealtimeServerEvent) -> None:

            await _send_realtime_event(websocket, send_lock, event)

        background_tasks: set[asyncio.Task] = set()

        try:

            auth = await _resolve_ws_token_or_close(websocket)

            if auth is None:

                return

            if _is_remote_session_auth(auth):

                await send_model(

                    RealtimeServerEvent(

                        type="error",

                        session_id=websocket.query_params.get("session_id"),

                        payload={"message": "Mobile voice is disabled in remote mode for v1"},

                    )

                )

                return

            bridge = _bridge_for_user(int(auth["user_id"]))

            client_id = str(websocket.query_params.get("client_id") or secrets.token_hex(8))

            draft = _new_voice_draft_state()

            active_session_id = websocket.query_params.get("session_id")

            active_surface_mode = str(websocket.query_params.get("surface_mode") or "").strip().lower()

            active_utterance_id: Optional[str] = None

            voice_agent_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            pending_jarvis_confirmations: Dict[str, Dict[str, Any]] = {}

            def track_background_task(task: asyncio.Task) -> None:

                background_tasks.add(task)

                task.add_done_callback(lambda finished: background_tasks.discard(finished))

            async def send_voice_event(

                event_type: str,

                payload: Optional[dict] = None,

                *,

                session_id: Optional[str] = None,

            ) -> None:

                await send_model(

                    RealtimeServerEvent(

                        type=event_type,

                        session_id=session_id if session_id is not None else active_session_id,

                        payload=payload or {},

                    )

                )

            async def run_voice_agent_turn(turn: dict[str, Any]) -> None:

                turn_id = str(turn.get("turn_id") or "").strip()

                turn_session_id = str(turn.get("session_id") or "").strip() or active_session_id

                turn_text = str(turn.get("text") or "").strip()

                if not turn_text:

                    return

                await send_voice_event(

                    "voice_state",

                    {"state": "generating", "turn_id": turn_id},

                    session_id=turn_session_id,

                )

                try:

                    runtime = bridge.load_runtime_session(turn_session_id)

                except (RuntimeError, ValueError) as exc:

                    logger.warning("[app] voice turn could not load session %s: %s", turn_session_id or "<current>", exc)

                    await send_voice_event(

                        "warning",

                        {

                            "message": (

                                "Voice turn could not start because the selected chat is no longer available. "

                                "Open or create a chat and try again."

                            ),

                            "detail": str(exc),

                            "turn_id": turn_id,

                        },

                        session_id=turn_session_id,

                    )

                    await send_voice_event(

                        "voice_state",

                        {"state": "idle", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    return

                try:

                    runtime.session.account_user_id = int(auth["user_id"])

                except Exception:

                    pass

                loop = asyncio.get_running_loop()

                start_voice_metrics: dict[str, float] = {"tts_seconds": 0.0}

                start_audio_task: Optional[asyncio.Task] = None

                async def send_start_task_audio() -> None:

                    start_text = _jarvis_start_task_message(turn_text)

                    if not start_text:

                        return

                    await send_voice_event(

                        "voice_state",

                        {"state": "synthesizing", "turn_id": turn_id, "phase": "start"},

                        session_id=turn_session_id,

                    )

                    start_tts_started = time.perf_counter()

                    try:

                        start_audio = await loop.run_in_executor(None, _synthesize_assistant_audio_sync, start_text)

                    except Exception as exc:

                        start_voice_metrics["tts_seconds"] = time.perf_counter() - start_tts_started

                        await send_voice_event(

                            "warning",

                            {"message": f"Assistant start audio unavailable: {str(exc)}", "turn_id": turn_id},

                            session_id=turn_session_id,

                        )

                        return

                    start_voice_metrics["tts_seconds"] = time.perf_counter() - start_tts_started

                    if not start_audio:

                        return

                    await send_voice_event(

                        "voice_state",

                        {"state": "speaking", "turn_id": turn_id, "phase": "start"},

                        session_id=turn_session_id,

                    )

                    start_audio["turn_id"] = turn_id

                    start_audio["phase"] = "start"

                    await send_model(

                        RealtimeServerEvent(

                            type="assistant_audio",

                            session_id=turn_session_id,

                            payload=start_audio,

                        )

                    )

                    await send_voice_event(

                        "voice_state",

                        {"state": "generating", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                if (

                    str(turn.get("surface_mode") or "").strip().lower() == "jarvis"

                    and _jarvis_voice_turn_is_task_like(turn_text)

                ):

                    start_audio_task = asyncio.create_task(send_start_task_audio())

                    track_background_task(start_audio_task)

                async def emit(event_data: dict) -> None:

                    kind = event_data.get("type")

                    if kind == "assistant_delta":

                        await send_model(

                            RealtimeServerEvent(

                                type="assistant_delta",

                                session_id=turn_session_id,

                                payload={"delta": event_data.get("delta", ""), "turn_id": turn_id},

                            )

                        )

                    elif kind == "tool_use":

                        confirmation = _jarvis_confirmation_prompt(

                            str(event_data.get("tool_name", "")),

                            event_data.get("tool_result"),

                        )

                        if confirmation and str(turn.get("surface_mode") or "").strip().lower() == "jarvis":

                            confirmation_key = str(turn_session_id or "__current__")

                            previous = pending_jarvis_confirmations.get(confirmation_key) or {}

                            if previous.get("confirmation_id") != confirmation.get("confirmation_id"):

                                pending_jarvis_confirmations[confirmation_key] = confirmation

                                await send_model(

                                    RealtimeServerEvent(

                                        type="voice_confirmation_required",

                                        session_id=turn_session_id,

                                        payload={**confirmation, "turn_id": turn_id},

                                    )

                                )

                                try:

                                    confirm_audio = await loop.run_in_executor(

                                        None,

                                        _synthesize_assistant_audio_sync,

                                        str(confirmation.get("spoken_prompt") or "Please confirm yes or no."),

                                    )

                                    if confirm_audio:

                                        confirm_audio["turn_id"] = turn_id

                                        confirm_audio["phase"] = "confirmation"

                                        await send_model(

                                            RealtimeServerEvent(

                                                type="assistant_audio",

                                                session_id=turn_session_id,

                                                payload=confirm_audio,

                                            )

                                        )

                                except Exception:

                                    logger.exception("[app] Jarvis confirmation audio failed")

                        if not runtime.verbose_mode:

                            return

                        tool_payload = _format_verbose_tool_event(

                            str(event_data.get("tool_name", "")),

                            event_data.get("tool_args") or {},

                            event_data.get("tool_result"),

                            float(event_data.get("duration_ms") or 0.0),

                        )

                        tool_payload["turn_id"] = turn_id

                        await send_model(

                            RealtimeServerEvent(

                                type="tool_event",

                                session_id=turn_session_id,

                                payload=tool_payload,

                            )

                        )

                    elif kind == "log":

                        if not runtime.verbose_mode:

                            return

                        log_payload = _format_runtime_log_entry(str(event_data.get("message", "")))

                        log_payload["turn_id"] = turn_id

                        await send_model(

                            RealtimeServerEvent(

                                type="log",

                                session_id=turn_session_id,

                                payload=log_payload,

                            )

                        )

                    elif kind == "status":

                        await send_model(

                            RealtimeServerEvent(

                                type="status",

                                session_id=turn_session_id,

                                payload={"message": event_data.get("message", ""), "turn_id": turn_id},

                            )

                        )

                llm_started = time.perf_counter()

                busy_notice_sent = False

                busy_deadline = time.perf_counter() + 90.0

                while True:

                    result = await _run_app_chat_turn_lazy(

                        runtime,

                        user_message=turn_text,

                        source_format="app_voice_transcript",

                        surface_mode=turn.get("surface_mode") or None,

                        interrupt_policy=str(turn.get("interrupt_policy") or "none"),

                        source_client_id=client_id,

                        log_callback=emit,

                    )

                    if not result.get("busy"):

                        break

                    if time.perf_counter() >= busy_deadline:

                        break

                    if not busy_notice_sent:

                        busy_notice_sent = True

                        await send_voice_event(

                            "status",

                            {"message": "Voice turn waiting for the current run to finish", "turn_id": turn_id},

                            session_id=turn_session_id,

                        )

                    await asyncio.sleep(0.5)

                llm_seconds = time.perf_counter() - llm_started

                if result.get("busy"):

                    if start_audio_task is not None and not start_audio_task.done():

                        start_audio_task.cancel()

                    await send_voice_event(

                        "warning",

                        {"message": "Voice turn could not start because the session stayed busy", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    await send_voice_event(

                        "voice_state",

                        {"state": "idle", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    return

                if result.get("steering"):

                    try:

                        runtime.session.account_user_id = int(auth["user_id"])

                        _mirror_session_snapshot(user_id=int(auth["user_id"]), bridge=bridge, session=runtime.session, reason="voice_ws_steering")

                    except Exception:

                        logger.exception("[recovery] failed mirroring voice websocket steering")

                    if start_audio_task is not None:

                        try:

                            await start_audio_task

                        except asyncio.CancelledError:

                            pass

                        except Exception:

                            logger.exception("[app] Jarvis start audio failed")

                    await send_voice_event(

                        "status",

                        {

                            "turn_id": turn_id,

                            "message": (

                                "Beta steering accepted"

                                if result.get("steering_status") == "armed"

                                else "Beta steering queued for next safe boundary"

                            ),

                        },

                        session_id=turn_session_id,

                    )

                    await send_voice_event(

                        "voice_state",

                        {"state": "idle", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    return

                final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or turn_session_id

                try:

                    runtime.session.account_user_id = int(auth["user_id"])

                    _sync_session_workspace_binding(user_id=int(auth["user_id"]), auth=auth, session=runtime.session)

                    _mirror_session_snapshot(user_id=int(auth["user_id"]), bridge=bridge, session=runtime.session, reason="voice_ws_turn")

                except Exception:

                    logger.exception("[recovery] failed syncing voice websocket session")

                if start_audio_task is not None:

                    try:

                        await start_audio_task

                    except Exception:

                        logger.exception("[app] Jarvis start audio failed")

                thinking_content = str(result.get("thinking_content") or "").strip()

                if thinking_content:

                    await send_model(

                        RealtimeServerEvent(

                            type="thinking",

                            session_id=final_session_id,

                            payload={

                                "text": thinking_content,

                                "formatted": _format_thinking_for_app(thinking_content),

                                "turn_id": turn_id,

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

                            "turn_id": turn_id,

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

                                "turn_id": turn_id,

                            },

                        )

                    )

                assistant_audio = None

                assistant_text = str(result.get("assistant_text", "") or "").strip()

                tts_seconds = 0.0

                if assistant_text:

                    await send_voice_event(

                        "voice_state",

                        {"state": "synthesizing", "turn_id": turn_id},

                        session_id=final_session_id,

                    )

                    tts_started = time.perf_counter()

                    try:

                        assistant_audio = await loop.run_in_executor(None, _synthesize_assistant_audio_sync, assistant_text)

                    except Exception as exc:

                        await send_voice_event(

                            "warning",

                            {"message": f"Assistant audio unavailable: {str(exc)}", "turn_id": turn_id},

                            session_id=final_session_id,

                        )

                    tts_seconds = time.perf_counter() - tts_started

                if assistant_audio:

                    await send_voice_event(

                        "voice_state",

                        {"state": "speaking", "turn_id": turn_id},

                        session_id=final_session_id,

                    )

                    assistant_audio["turn_id"] = turn_id

                    await send_model(

                        RealtimeServerEvent(

                            type="assistant_audio",

                            session_id=final_session_id,

                            payload=assistant_audio,

                        )

                    )

                await send_voice_event(

                    "status",

                    {

                        "turn_id": turn_id,

                        "message": (

                            "Voice timings: "

                            f"stt {float(turn.get('stt_seconds') or 0.0):.2f}s, "

                            + (

                                f"ack_tts {start_voice_metrics['tts_seconds']:.2f}s, "

                                if start_audio_task is not None

                                else ""

                            )

                            +

                            f"agent {llm_seconds:.2f}s, "

                            f"tts {tts_seconds:.2f}s, "

                            f"total {time.perf_counter() - float(turn.get('started_at') or time.perf_counter()):.2f}s"

                        ),

                    },

                    session_id=final_session_id,

                )

                await send_voice_event(

                    "voice_state",

                    {"state": "idle", "turn_id": turn_id},

                    session_id=final_session_id,

                )

            async def voice_agent_worker() -> None:

                while True:

                    turn = await voice_agent_queue.get()

                    try:

                        await run_voice_agent_turn(turn)

                    except asyncio.CancelledError:

                        raise

                    except Exception as exc:

                        logger.exception("[app] queued voice agent turn failed")

                        await send_voice_event(

                            "error",

                            {

                                "message": f"Voice agent turn failed: {str(exc)}",

                                "turn_id": str(turn.get("turn_id") or ""),

                            },

                            session_id=str(turn.get("session_id") or active_session_id or ""),

                        )

                    finally:

                        voice_agent_queue.task_done()

            async def finalize_voice_turn(turn: dict[str, Any]) -> None:

                turn_id = str(turn.get("turn_id") or "").strip()

                turn_session_id = str(turn.get("session_id") or "").strip() or active_session_id

                committed_draft = turn["draft"]

                is_jarvis_surface = str(turn.get("surface_mode") or "").strip().lower() == "jarvis"

                await send_voice_event(

                    "voice_state",

                    {"state": "finalizing", "turn_id": turn_id},

                    session_id=turn_session_id,

                )

                try:

                    if is_jarvis_surface:

                        await committed_draft.wait_for_pending(timeout=_jarvis_pending_wait_seconds())

                        if (

                            not committed_draft.transcript().strip()

                            and getattr(committed_draft, "cancel_empty_pending_before_final", True)

                        ):

                            committed_draft.cancel_pending()

                    else:

                        await committed_draft.wait_for_pending()

                    stt_started = time.perf_counter()

                    draft_text = (await committed_draft.final_transcript(

                        fast=is_jarvis_surface and _jarvis_fast_final_enabled(),

                    )).strip()

                    stt_seconds = time.perf_counter() - stt_started

                except Exception as exc:

                    logger.exception("[app] voice transcript finalization failed")

                    committed_draft.cancel_pending()

                    await send_voice_event(

                        "error",

                        {"message": f"Voice transcription failed: {str(exc)}", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    await send_voice_event(

                        "voice_state",

                        {"state": "idle", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    return

                if not draft_text:

                    committed_draft.reset()

                    if bool(turn.get("barge_in_candidate")):

                        await send_voice_event(

                            "voice_state",

                            {"state": "idle", "turn_id": turn_id, "ignored": "barge_in_empty"},

                            session_id=turn_session_id,

                        )

                        return

                    await send_voice_event(

                        "warning",

                        {"message": "No speech detected", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    await send_voice_event(

                        "voice_state",

                        {"state": "idle", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    return

                if bool(turn.get("barge_in_candidate")) and (

                    not _jarvis_barge_in_text_is_meaningful(draft_text)

                    or _jarvis_barge_in_is_self_echo(draft_text, str(turn.get("barge_in_reference_text") or ""))

                ):

                    logger.info("[app] ignored Jarvis barge-in candidate: %r", draft_text)

                    committed_draft.reset()

                    await send_voice_event(

                        "voice_state",

                        {"state": "idle", "turn_id": turn_id, "ignored": "barge_in_noise"},

                        session_id=turn_session_id,

                    )

                    return

                if is_jarvis_surface:

                    confirmation_key = str(turn_session_id or "__current__")

                    pending_confirmation = pending_jarvis_confirmations.get(confirmation_key)

                    confirmation_intent = _jarvis_confirmation_intent(draft_text) if pending_confirmation else None

                    if pending_confirmation and confirmation_intent is not None:

                        committed_draft.reset()

                        await send_model(

                            RealtimeServerEvent(

                                type="voice_final",

                                session_id=turn_session_id,

                                payload={

                                    "text": draft_text,

                                    "turn_id": turn_id,

                                    "confirmation_response": True,

                                    "confirmed": confirmation_intent,

                                },

                            )

                        )

                        if not confirmation_intent:

                            pending_jarvis_confirmations.pop(confirmation_key, None)

                            await send_voice_event(

                                "status",

                                {"message": "Jarvis confirmation canceled", "turn_id": turn_id},

                                session_id=turn_session_id,

                            )

                            try:

                                cancel_audio = await asyncio.get_running_loop().run_in_executor(

                                    None,

                                    _synthesize_assistant_audio_sync,

                                    "Cancelled.",

                                )

                                if cancel_audio:

                                    cancel_audio["turn_id"] = turn_id

                                    cancel_audio["phase"] = "confirmation_cancelled"

                                    await send_model(

                                        RealtimeServerEvent(

                                            type="assistant_audio",

                                            session_id=turn_session_id,

                                            payload=cancel_audio,

                                        )

                                    )

                            except Exception:

                                logger.exception("[app] Jarvis cancellation audio failed")

                            await send_voice_event(

                                "voice_state",

                                {"state": "idle", "turn_id": turn_id},

                                session_id=turn_session_id,

                            )

                            return

                        pending_jarvis_confirmations.pop(confirmation_key, None)

                        turn["text"] = (

                            "Yes, I confirm. Proceed with "

                            f"{pending_confirmation.get('action') or 'the requested action'}. "

                            "Use the same tool again with confirmed=true if that is required. "

                            f"Confirmation id: {pending_confirmation.get('confirmation_id') or 'voice confirmation'}."

                        )

                        turn["stt_seconds"] = stt_seconds

                        await voice_agent_queue.put(turn)

                        return

                    if pending_confirmation and confirmation_intent is None:

                        committed_draft.reset()

                        ambiguity_count = int(pending_confirmation.get("ambiguity_count") or 0) + 1

                        pending_confirmation["ambiguity_count"] = ambiguity_count

                        pending_jarvis_confirmations[confirmation_key] = pending_confirmation

                        await send_model(

                            RealtimeServerEvent(

                                type="voice_final",

                                session_id=turn_session_id,

                                payload={

                                    "text": draft_text,

                                    "turn_id": turn_id,

                                    "confirmation_response": True,

                                    "confirmed": None,

                                    "ambiguous": True,

                                },

                            )

                        )

                        if ambiguity_count <= 1:

                            reprompt = "I need a clear yes or no. Should I proceed?"

                            await send_voice_event(

                                "voice_confirmation_required",

                                {

                                    **pending_confirmation,

                                    "turn_id": turn_id,

                                    "ambiguous": True,

                                    "reprompt": reprompt,

                                },

                                session_id=turn_session_id,

                            )

                        else:

                            reprompt = "I could not confirm that by voice. I left the action pending in the app."

                            await send_voice_event(

                                "voice_confirmation_required",

                                {

                                    **pending_confirmation,

                                    "turn_id": turn_id,

                                    "ambiguous": True,

                                    "fallback_required": True,

                                },

                                session_id=turn_session_id,

                            )

                            await send_voice_event(

                                "status",

                                {"message": "Jarvis confirmation needs app approval", "turn_id": turn_id},

                                session_id=turn_session_id,

                            )

                        try:

                            reprompt_audio = await asyncio.get_running_loop().run_in_executor(

                                None,

                                _synthesize_assistant_audio_sync,

                                reprompt,

                            )

                            if reprompt_audio:

                                reprompt_audio["turn_id"] = turn_id

                                reprompt_audio["phase"] = "confirmation_reprompt" if ambiguity_count <= 1 else "confirmation_fallback"

                                await send_model(

                                    RealtimeServerEvent(

                                        type="assistant_audio",

                                        session_id=turn_session_id,

                                        payload=reprompt_audio,

                                    )

                                )

                        except Exception:

                            logger.exception("[app] Jarvis confirmation reprompt audio failed")

                        await send_voice_event(

                            "voice_state",

                            {"state": "idle", "turn_id": turn_id, "confirmation_pending": True},

                            session_id=turn_session_id,

                        )

                        return

                if turn.get("auto_send") is False:

                    await send_model(

                        RealtimeServerEvent(

                            type="voice_transcript",

                            session_id=turn_session_id,

                            payload={"text": draft_text, "auto_sent": False, "turn_id": turn_id},

                        )

                    )

                    await send_voice_event(

                        "voice_state",

                        {"state": "idle", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

                    committed_draft.reset()

                    return

                await send_model(

                    RealtimeServerEvent(

                        type="voice_final",

                        session_id=turn_session_id,

                        payload={"text": draft_text, "turn_id": turn_id},

                    )

                )

                turn["text"] = draft_text

                turn["stt_seconds"] = stt_seconds

                committed_draft.reset()

                await voice_agent_queue.put(turn)

                if voice_agent_queue.qsize() > 1:

                    await send_voice_event(

                        "status",

                        {"message": "Voice turn queued behind the current answer", "turn_id": turn_id},

                        session_id=turn_session_id,

                    )

            agent_worker_task = asyncio.create_task(voice_agent_worker())

            track_background_task(agent_worker_task)

            await send_model(

                RealtimeServerEvent(

                    type="voice_state",

                    session_id=active_session_id,

                    payload={"state": "connected"},

                )

            )

            while True:

                raw = await websocket.receive_text()

                event = VoiceClientEvent.model_validate_json(raw)

                if event.session_id:

                    active_session_id = event.session_id

                if event.surface_mode:

                    active_surface_mode = str(event.surface_mode or "").strip().lower()

                if event.utterance_id:

                    active_utterance_id = str(event.utterance_id or "").strip() or active_utterance_id

                if event.type == "voice_start":

                    active_utterance_id = str(event.utterance_id or "").strip() or secrets.token_hex(8)

                    draft.reset()

                    draft.state = "listening"

                    preconnect = getattr(draft, "preconnect", None)

                    if callable(preconnect):

                        preconnect_task = asyncio.create_task(preconnect())

                        draft.register_task(preconnect_task)

                    await send_voice_event("voice_state", {"state": "listening", "turn_id": active_utterance_id})

                elif event.type == "voice_chunk":

                    chunk_draft = draft

                    revision = chunk_draft.revision

                    session_for_chunk = active_session_id

                    turn_id_for_chunk = str(event.utterance_id or active_utterance_id or "").strip()

                    chunk_audio_base64 = event.audio_base64

                    chunk_mime_type = event.mime_type

                    chunk_sequence = event.sequence

                    async def process_chunk() -> None:

                        try:

                            partial_text = await chunk_draft.transcribe_chunk(

                                audio_base64=chunk_audio_base64,

                                mime_type=chunk_mime_type,

                                sequence=chunk_sequence,

                                revision=revision,

                            )

                            if revision != chunk_draft.revision:

                                return

                            chunk_draft.state = "listening"

                            await send_model(

                                RealtimeServerEvent(

                                    type="voice_partial",

                                    session_id=session_for_chunk,

                                    payload={"text": partial_text, "turn_id": turn_id_for_chunk},

                                )

                            )

                        except Exception as exc:

                            if revision != chunk_draft.revision:

                                return

                            chunk_draft.state = "error"

                            await send_model(

                                RealtimeServerEvent(

                                    type="error",

                                    session_id=session_for_chunk,

                                    payload={"message": f"Voice transcription failed: {str(exc)}", "turn_id": turn_id_for_chunk},

                                )

                            )

                    task = asyncio.create_task(process_chunk())

                    chunk_draft.register_task(task)

                elif event.type in {"voice_pause", "voice_resume"}:

                    draft.state = event.type.replace("voice_", "")

                    await send_voice_event("voice_state", {"state": draft.state, "turn_id": active_utterance_id})

                elif event.type == "voice_commit":

                    committed_draft = draft

                    turn_id = str(event.utterance_id or active_utterance_id or secrets.token_hex(8)).strip()

                    committed_draft.state = "finalizing"

                    turn = {

                        "draft": committed_draft,

                        "session_id": active_session_id,

                        "surface_mode": active_surface_mode or None,

                        "interrupt_policy": event.interrupt_policy or "none",

                        "auto_send": event.auto_send,

                        "barge_in_candidate": bool(event.barge_in_candidate),

                        "barge_in_reference_text": str(event.barge_in_reference_text or ""),

                        "turn_id": turn_id,

                        "started_at": time.perf_counter(),

                    }

                    draft = _new_voice_draft_state()

                    active_utterance_id = None

                    task = asyncio.create_task(finalize_voice_turn(turn))

                    track_background_task(task)

                elif event.type == "voice_cancel":

                    draft.reset()

                    cancelled_turn_id = str(event.utterance_id or active_utterance_id or "").strip()

                    active_utterance_id = None

                    await send_voice_event("voice_state", {"state": "cancelled", "turn_id": cancelled_turn_id})

        except WebSocketDisconnect:

            logger.info("[app] websocket /ws/app/voice disconnected")

            return

        except Exception as exc:

            try:

                logger.exception("[app] voice websocket failed")

                _record_runtime_error(

                    f"Voice websocket failed: {exc}",

                    traceback.format_exc(),

                )

                await send_model(

                    RealtimeServerEvent(

                        type="error",

                        session_id=active_session_id,

                        payload={

                            "message": f"Voice websocket failed: {str(exc)}",

                            "detail": traceback.format_exc(),

                        },

                    )

                )

            except Exception:

                pass

            return

        finally:

            for task in list(background_tasks):

                task.cancel()

            if background_tasks:

                await asyncio.gather(*background_tasks, return_exceptions=True)
