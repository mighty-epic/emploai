from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

def register_agent_routes(app):

    @app.get("/api/app/me", response_model=AppUserProfile)

    async def me(authorization: Optional[str] = Header(default=None)) -> AppUserProfile:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            return _remote_profile_view(auth)

        user_id = int(auth["user_id"])

        bridge = _bridge_for_user(user_id)

        current = bridge.get_current_session()

        return AppUserProfile(

            user_id=user_id,

            current_session_id=current.id if current else None,

            current_model=current.model if current else None,

            current_variant=current.variant if current else None,

            device_id=auth.get("device_id"),

            device_name=auth.get("device_name"),

            device_platform=auth.get("device_platform"),

        )

    @app.get("/api/app/voice/status")

    async def voice_status(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            return {

                "ok": True,

                "input_ok": False,

                "issues": ["Mobile voice is disabled in remote mode for v1."],

                "selected_engine": "none",

                "selected_engine_state": "disabled",

                "selected_engine_ready": False,

            }

        return _voice_runtime_status()

    @app.post("/api/app/voice/warm")

    async def warm_voice_engine(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:

        _resolve_token(authorization)

        status = _voice_runtime_status()

        selected_engine = str(status.get("selected_engine") or "").strip().lower()

        voice_warmup_ok = True

        if selected_engine == "hebrew_local":

            try:

                timings = _preload_hebrew_voice_models()

                status = _voice_runtime_status()

                status["warmup"] = {

                    "ok": True,

                    "engine": selected_engine,

                    "timings": timings,

                }

            except Exception as exc:

                voice_warmup_ok = False

                status = _voice_runtime_status()

                issues = list(status.get("issues") or [])

                issues.insert(0, f"Hebrew voice warmup failed: {exc}")

                status["issues"] = issues

                status["ok"] = False

                status["input_ok"] = False

                status["selected_engine_state"] = "error"

                status["selected_engine_ready"] = False

                status["warmup"] = {

                    "ok": False,

                    "engine": selected_engine,

                    "error": str(exc),

                }

        else:

            status["warmup"] = {

                "ok": True,

                "engine": selected_engine or "none",

                "timings": None,

            }

        try:

            tts_warmup = _preload_tts_engine()

            status = _voice_runtime_status()

            status["tts_warmup"] = tts_warmup

            warmup = dict(status.get("warmup") or {})

            warmup["ok"] = bool(warmup.get("ok", voice_warmup_ok))

            warmup["tts"] = tts_warmup

            status["warmup"] = warmup

        except Exception as exc:

            status = _voice_runtime_status()

            tts_issues = list(status.get("tts_issues") or [])

            tts_issues.insert(0, f"TTS warmup failed: {exc}")

            status["tts_issues"] = tts_issues

            status["tts_ok"] = False

            status["tts_ready"] = False

            status["tts_warmup"] = {

                "ok": False,

                "backend": status.get("tts_backend"),

                "error": str(exc),

            }

            warmup = dict(status.get("warmup") or {})

            warmup["ok"] = bool(warmup.get("ok", voice_warmup_ok))

            warmup["tts"] = status["tts_warmup"]

            status["warmup"] = warmup

        return status

    @app.post("/api/app/voice/tts")

    async def configure_voice_tts(

        request: VoiceTtsConfigureRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict[str, Any]:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Desktop voice TTS switching is unavailable in remote mode.")

        try:

            return _configure_tts_backend(request.backend)

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/app/voice/stt")

    async def configure_voice_stt(

        request: VoiceSttConfigureRequest,

        authorization: Optional[str] = Header(default=None),

    ) -> dict[str, Any]:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=409, detail="Desktop voice input switching is unavailable in remote mode.")

        try:

            return _configure_stt_backend(request.backend)

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/app/agent/overview", response_model=AgentOverviewView)

    async def agent_overview(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

        history_count: int = 12,

        analytics_days: int = 7,

    ) -> AgentOverviewView:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        return AgentOverviewView(**_agent_overview(runtime, bridge, history_count=history_count, analytics_days=analytics_days))

    @app.get("/api/app/agent/task-board", response_model=TaskBoardResponse)

    async def agent_task_board(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> TaskBoardResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        return TaskBoardResponse(task_board=task_board_view(get_display_task_board(runtime)))

    @app.post("/api/app/agent/task-board/arm", response_model=TaskBoardArmResponse)

    async def agent_task_board_arm(

        request: TaskBoardArmRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> TaskBoardArmResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        result = bridge.set_task_board_armed_next_turn(target_session_id, request.armed)

        return TaskBoardArmResponse(**result)

    @app.post("/api/app/agent/task-board/reassess", response_model=AgentActionResponse)

    async def agent_task_board_reassess(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        board = request_task_board_reassessment(runtime, "Manual reassessment requested by the user.")

        if not board:

            return AgentActionResponse(action="reassess", message="No active managed task.")

        runtime.save_session()

        get_channel_sync_hub().publish(

            user_id=int(auth["user_id"]),

            event={

                "type": "task_board",

                "session_id": runtime.session_manager.get_current_session_id() if runtime.session_manager else session_id,

                "origin_channel": "app",

                "payload": {

                    "board": board,

                    "completed_task_boards": completed_task_board_views(runtime),

                    "summary": "Manual reassessment completed. The active task board was revised immediately.",

                },

            },

        )

        return AgentActionResponse(

            action="reassess",

            message="Manual reassessment completed. The active task board was revised immediately.",

        )

    @app.post("/api/app/agent/configure", response_model=AgentActionResponse)

    async def configure_agent(

        request: AgentConfigureRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        _configure_runtime(runtime, request)

        _publish_runtime_config_sync(runtime, user_id=int(auth["user_id"]), origin_channel="app")

        return AgentActionResponse(action="configure", message="Agent controls updated")

    @app.post("/api/app/agent/provider-keys/reload", response_model=AgentActionResponse)

    async def reload_provider_keys(

        request: Dict[str, Any],

        authorization: Optional[str] = Header(default=None),

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        if _is_remote_session_auth(auth):

            raise HTTPException(status_code=400, detail="Provider key reload is only available on the paired desktop.")

        provider_secret_fields = {

            "OPENAI_API_KEY",

            "ANTHROPIC_API_KEY",

            "GOOGLE_API_KEY",

            "GEMINI_API_KEY",

            "XAI_API_KEY",

            "DEEPSEEK_API_KEY",

            "NVIDIA_API_KEY",

            "OPENROUTER_API_KEY",

        }

        raw_values = request.get("values") if isinstance(request, dict) else {}

        if not isinstance(raw_values, dict):

            raw_values = {}

        applied_values: Dict[str, str] = {}

        removed_values = set()

        for raw_key, raw_value in raw_values.items():

            key = str(raw_key or "").strip()

            value = str(raw_value or "").strip()

            if key not in provider_secret_fields:

                continue

            if value:

                os.environ[key] = value

                applied_values[key] = value

            else:

                os.environ.pop(key, None)

                removed_values.add(key)

        google_value = applied_values.get("GOOGLE_API_KEY") or applied_values.get("GEMINI_API_KEY")

        if google_value:

            os.environ["GOOGLE_API_KEY"] = google_value

            os.environ["GEMINI_API_KEY"] = google_value

            applied_values["GOOGLE_API_KEY"] = google_value

            applied_values["GEMINI_API_KEY"] = google_value

            removed_values.discard("GOOGLE_API_KEY")

            removed_values.discard("GEMINI_API_KEY")

        elif "GOOGLE_API_KEY" in removed_values or "GEMINI_API_KEY" in removed_values:

            os.environ.pop("GOOGLE_API_KEY", None)

            os.environ.pop("GEMINI_API_KEY", None)

            removed_values.add("GOOGLE_API_KEY")

            removed_values.add("GEMINI_API_KEY")

        changed_provider_keys = set(applied_values) | removed_values

        if not changed_provider_keys:

            return AgentActionResponse(action="provider_keys_reload", message="No provider keys were changed.")

        refreshed = 0

        try:

            from telegram_bot.telegram_session_state import user_sessions as runtime_user_sessions

        except Exception:

            runtime_user_sessions = {}

        for runtime in list(getattr(runtime_user_sessions, "values", lambda: [])()):

            if runtime is None or not hasattr(runtime, "_init_clients"):

                continue

            runtime._init_clients()

            try:

                if runtime.ensure_current_model_available(AVAILABLE_MODELS):

                    runtime.save_session()

            except Exception:

                pass

            refreshed += 1

        provider_count = len({key for key in changed_provider_keys if key != "GEMINI_API_KEY"})

        if refreshed:

            return AgentActionResponse(

                action="provider_keys_reload",

                message=f"Reloaded {provider_count} provider key change{'s' if provider_count != 1 else ''} for {refreshed} active runtime session{'s' if refreshed != 1 else ''}.",

            )

        return AgentActionResponse(

            action="provider_keys_reload",

            message=f"Stored {provider_count} provider key change{'s' if provider_count != 1 else ''} for new runtime sessions.",

        )

    @app.get("/api/app/agent/bridge-status")

    async def bridge_status(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> dict[str, Any]:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        try:

            from telegram_bot.telegram_unified_agent import get_browser_bridge_status

        except ImportError:

            from telegram_unified_agent import get_browser_bridge_status

        return dict(get_browser_bridge_status(runtime) or {})

    @app.get("/api/app/agent/config", response_model=ConfigListResponse)

    async def list_agent_config(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

        key: Optional[str] = None,

    ) -> ConfigListResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        if not runtime.live_config:

            return ConfigListResponse(items=[])

        if key:

            return ConfigListResponse(items=[ConfigEntryView(key=key, value=runtime.live_config.get(key))])

        items = runtime.live_config.list_all()

        return ConfigListResponse(

            items=[ConfigEntryView(key=entry_key, value=value) for entry_key, value in sorted(items.items())]

        )

    @app.post("/api/app/agent/config", response_model=ConfigEntryView)

    async def update_agent_config(

        request: ConfigUpdateRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> ConfigEntryView:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        if not runtime.live_config:

            raise HTTPException(status_code=503, detail="Live config is unavailable")

        parsed_value = _coerce_config_value(request.value)

        runtime.live_config.set(request.key, parsed_value, runtime.user_id)

        runtime.live_config.save_config()

        return ConfigEntryView(key=request.key, value=runtime.live_config.get(request.key))

    @app.post("/api/app/agent/memory/search", response_model=MemorySearchResponse)

    async def search_agent_memory(

        request: MemorySearchRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> MemorySearchResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        if runtime.live_config and runtime.live_config.get("memory.search_enabled", True) is False:

            raise HTTPException(status_code=403, detail="Memory search is disabled by account settings")

        if not runtime.memory_manager:

            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        query = request.query.strip()

        if not query:

            raise HTTPException(status_code=400, detail="Query is required")

        results = runtime.memory_manager.search_memory(query, max_results=8)

        return MemorySearchResponse(query=query, results=results)

    @app.post("/api/app/agent/memory/note", response_model=AgentActionResponse)

    async def append_agent_memory_note(

        request: MemoryNoteRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        if runtime.live_config and runtime.live_config.get("memory.write_enabled", True) is False:

            raise HTTPException(status_code=403, detail="Memory writes are disabled by account settings")

        if not runtime.memory_manager:

            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        note = request.note.strip()

        if not note:

            raise HTTPException(status_code=400, detail="Note is required")

        stored = runtime.memory_manager.append_to_memory("User Notes", f"- {note}")

        runtime.memory_manager.append_to_daily_log(note, "user_note")

        message = "Note saved to memory" if stored else "Note was already present in memory"

        return AgentActionResponse(action="memory_note", message=message)

    @app.post("/api/app/agent/memory/operations", response_model=MemoryOperationResponse)

    async def apply_agent_memory_operations(

        request: MemoryOperationRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> MemoryOperationResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        if runtime.live_config and runtime.live_config.get("memory.write_enabled", True) is False:

            raise HTTPException(status_code=403, detail="Memory writes are disabled by local settings")

        if not runtime.memory_manager:

            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        try:

            result = runtime.memory_manager.apply_operations(request.operations)

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return MemoryOperationResponse(**result)

    @app.post("/api/app/agent/memory/facts", response_model=MemoryFactView)

    async def add_agent_memory_fact(

        request: MemoryFactRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> MemoryFactView:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        if runtime.live_config and runtime.live_config.get("memory.write_enabled", True) is False:

            raise HTTPException(status_code=403, detail="Memory writes are disabled by local settings")

        if not runtime.memory_manager:

            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        try:

            fact = runtime.memory_manager.fact_store.add_fact(

                request.content,

                category=request.category,

                tags=request.tags,

                trust=request.trust,

                source="desktop_ui",

            )

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return MemoryFactView(**fact)

    @app.get("/api/app/agent/memory/facts", response_model=MemoryFactListResponse)

    async def list_agent_memory_facts(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

        category: Optional[str] = None,

        limit: int = 50,

    ) -> MemoryFactListResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        if runtime.live_config and runtime.live_config.get("memory.search_enabled", True) is False:

            raise HTTPException(status_code=403, detail="Memory search is disabled by local settings")

        if not runtime.memory_manager:

            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        facts = runtime.memory_manager.fact_store.list_facts(

            category=category,

            min_trust=0.0,

            limit=max(1, min(200, int(limit or 50))),

        )

        return MemoryFactListResponse(items=[MemoryFactView(**fact) for fact in facts])

    @app.delete("/api/app/agent/memory/facts/{fact_id}", response_model=AgentActionResponse)

    async def delete_agent_memory_fact(

        fact_id: int,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        if runtime.live_config and runtime.live_config.get("memory.write_enabled", True) is False:

            raise HTTPException(status_code=403, detail="Memory writes are disabled by local settings")

        if not runtime.memory_manager:

            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        removed = runtime.memory_manager.fact_store.remove_fact(fact_id)

        if not removed:

            raise HTTPException(status_code=404, detail=f"Fact not found: {fact_id}")

        return AgentActionResponse(action="memory_fact_delete", message=f"Deleted local fact #{fact_id}")

    @app.post("/api/app/agent/memory/facts/feedback", response_model=MemoryFactView)

    async def rate_agent_memory_fact(

        request: MemoryFactFeedbackRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> MemoryFactView:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        if runtime.live_config and runtime.live_config.get("memory.write_enabled", True) is False:

            raise HTTPException(status_code=403, detail="Memory writes are disabled by local settings")

        if not runtime.memory_manager:

            raise HTTPException(status_code=503, detail="Memory manager not initialized")

        try:

            fact = runtime.memory_manager.fact_store.record_feedback(request.fact_id, helpful=request.helpful)

        except KeyError as exc:

            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return MemoryFactView(**fact)

    @app.post("/api/app/agent/files/clear", response_model=AgentActionResponse)

    async def clear_pending_files(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        runtime.pending_files = []

        runtime.save_session()

        return AgentActionResponse(action="clear_files", message="Pending files cleared")

    @app.post("/api/app/agent/forget-last", response_model=AgentActionResponse)

    async def forget_last_user_message(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        removed = False

        for index in range(len(runtime.chat_history) - 1, -1, -1):

            if runtime.chat_history[index].get("role") == "user":

                del runtime.chat_history[index]

                removed = True

                break

        if removed:

            runtime.save_session()

            return AgentActionResponse(action="forget_last", message="Last user message removed from context")

        return AgentActionResponse(action="forget_last", message="No user message found to remove")

    @app.post("/api/app/agent/reset", response_model=AgentActionResponse)

    async def reset_agent_context(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        runtime.chat_history = []

        runtime.pending_files = []

        runtime.message_id_map = {}

        if runtime.single_agent:

            runtime.single_agent.messages = []

        if runtime.unified_agent:

            runtime.unified_agent.conversation_history = []

        runtime.save_session()

        return AgentActionResponse(action="reset", message="Chat history cleared")

    @app.post("/api/app/agent/compact", response_model=AgentActionResponse)

    async def compact_agent_context(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        async with runtime.lock:

            if getattr(runtime, "is_processing", False):

                raise HTTPException(status_code=409, detail="Session is busy")

            from shared.channel_runtime import compact_session_history

            result = compact_session_history(runtime, reason="manual", announce=True)

            if not result:

                raise HTTPException(status_code=503, detail="Context manager is unavailable")

            runtime.save_session()

        return AgentActionResponse(action="compact", message=result.message)

    @app.get("/api/app/agent/skills", response_model=SkillListResponse)

    async def list_agent_skills(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> SkillListResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        return SkillListResponse(items=[SkillSummaryView(**item) for item in _skill_items(runtime)])

    @app.get("/api/app/agent/skills/{skill_name}", response_model=SkillDetailView)

    async def view_agent_skill(

        skill_name: str,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

        include_resources: bool = False,

    ) -> SkillDetailView:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        registry = getattr(runtime, "skill_registry", None)

        if not registry:

            raise HTTPException(status_code=503, detail="Skill system is unavailable")

        name = skill_name.strip()

        detail = registry.get_skill_detail(name, include_body=True, include_resources=include_resources)

        if not detail:

            raise HTTPException(status_code=404, detail="Skill not found")

        gating = getattr(registry, "gating", None)

        available = bool(gating.is_available(name)) if gating else True

        reason = gating.get_unavailable_reason(name) if gating and not available else None

        detail.update(

            {

                "available": available,

                "active": name in set(getattr(runtime, "active_skills", []) or []),

                "unavailable_reason": reason,

            }

        )

        return SkillDetailView(**detail)

    @app.post("/api/app/agent/skills/learn", response_model=SkillLearnResponse)

    async def learn_agent_skill(

        request: SkillLearnRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> SkillLearnResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        registry = getattr(runtime, "skill_registry", None)

        if not registry:

            raise HTTPException(status_code=503, detail="Skill system is unavailable")

        try:

            from shared.local_skill_authoring import create_local_skill, workflow_from_recent_messages

            workflow = str(request.workflow or "").strip()

            if not workflow:

                workflow = workflow_from_recent_messages(getattr(runtime, "chat_history", []) or [])

            result = create_local_skill(

                registry.loader.skills_dir,

                name=request.name,

                description=request.description,

                workflow=workflow,

                source="desktop_command",

                overwrite=request.overwrite,

            )

        except FileExistsError as exc:

            raise HTTPException(status_code=409, detail=str(exc)) from exc

        except ValueError as exc:

            raise HTTPException(status_code=400, detail=str(exc)) from exc

        registry.reload()

        if request.activate:

            runtime.active_skills = [result["name"]]

            runtime.save_session()

        detail = registry.get_skill_detail(result["name"], include_body=True, include_resources=False)

        if not detail:

            raise HTTPException(status_code=500, detail="Skill was written but could not be reloaded")

        detail.update(

            {

                "available": True,

                "active": result["name"] in set(getattr(runtime, "active_skills", []) or []),

                "unavailable_reason": None,

            }

        )

        return SkillLearnResponse(

            message=f"Learned local skill {result['name']}.",

            skill=SkillDetailView(**detail),

        )

    @app.post("/api/app/agent/skills/activate", response_model=AgentActionResponse)

    async def activate_agent_skill(

        request: SkillActivateRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        registry = getattr(runtime, "skill_registry", None)

        if not registry:

            raise HTTPException(status_code=503, detail="Skill system is unavailable")

        skill_name = request.name.strip()

        if not skill_name:

            raise HTTPException(status_code=400, detail="Skill name is required")

        if request.active:

            skill = registry.loader.get_skill(skill_name)

            if not skill:

                raise HTTPException(status_code=404, detail="Skill not found")

            if not registry.gating.is_available(skill_name):

                reason = registry.gating.get_unavailable_reason(skill_name)

                raise HTTPException(status_code=400, detail=reason or "Skill is unavailable")

            runtime.active_skills = [skill_name]

            message = f"{skill_name} will be active for your next messages"

        else:

            runtime.active_skills = [name for name in runtime.active_skills if name != skill_name]

            message = f"{skill_name} removed from active skills"

        runtime.save_session()

        return AgentActionResponse(action="skill_activate", message=message)

    @app.post("/api/app/agent/skills/validate", response_model=SkillValidationView)

    async def validate_agent_skill(

        request: SkillActivateRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> SkillValidationView:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        registry = getattr(runtime, "skill_registry", None)

        if not registry:

            raise HTTPException(status_code=503, detail="Skill system is unavailable")

        skill_name = request.name.strip()

        if not skill_name:

            raise HTTPException(status_code=400, detail="Skill name is required")

        result = registry.validate_skill(skill_name)

        resources = result.get("resources", {}) or {}

        return SkillValidationView(

            name=skill_name,

            valid=bool(result.get("valid")),

            errors=[str(item) for item in result.get("errors", [])],

            warnings=[str(item) for item in result.get("warnings", [])],

            scripts_count=len(resources.get("scripts", [])),

            references_count=len(resources.get("references", [])),

            assets_count=len(resources.get("assets", [])),

        )

    @app.get("/api/app/agent/subagents", response_model=SubAgentListResponse)

    async def list_agent_subagents(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> SubAgentListResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, session_id)

        spawn_tool = getattr(runtime, "spawn_tool", None)

        if not spawn_tool:

            return SubAgentListResponse()

        status = spawn_tool.get_status()

        tasks = [SubAgentTaskView(**task) for task in status.get("tasks", [])]

        return SubAgentListResponse(

            total_tasks=int(status.get("total_tasks", 0)),

            running=int(status.get("running", 0)),

            completed=int(status.get("completed", 0)),

            failed=int(status.get("failed", 0)),

            tasks=tasks,

        )

    @app.post("/api/app/agent/subagents", response_model=AgentActionResponse)

    async def spawn_agent_subtask(

        request: SubAgentSpawnRequest,

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        bridge = _bridge_for_user(int(auth["user_id"]))

        target_session_id = _require_explicit_agent_session_id(session_id)

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        prompt = request.prompt.strip()

        if not prompt:

            raise HTTPException(status_code=400, detail="Prompt is required")

        _ensure_background_runtime(runtime)

        task_id = await runtime.spawn_tool.spawn(

            prompt=prompt,

            headless=bool(request.headless),

            max_turns=int(request.max_turns),

            announce_on_complete=False,

        )

        return AgentActionResponse(action="spawn", message=f"Sub-agent {task_id} started")

    @app.post("/api/app/agent/control/pause", response_model=AgentActionResponse)

    async def pause_agent_run(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        target_session_id = _require_explicit_agent_session_id(session_id)

        if _is_remote_session_auth(auth):

            await _remote_dispatch_command(

                auth,

                command_name="pause_run",

                payload={"session_id": target_session_id},

            )

            return AgentActionResponse(action="pause", message="Pause requested for the paired desktop")

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        agents = _active_task_agents(runtime)

        if not agents:

            return AgentActionResponse(action="pause", message="No task is currently running")

        for agent in agents:

            agent.pause()

        return AgentActionResponse(action="pause", message="Pause requested for the current task")

    @app.post("/api/app/agent/control/stop", response_model=AgentActionResponse)

    async def stop_agent_run(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        target_session_id = _require_explicit_agent_session_id(session_id)

        if _is_remote_session_auth(auth):

            await _remote_dispatch_command(

                auth,

                command_name="stop_run",

                payload={"session_id": target_session_id},

            )

            return AgentActionResponse(action="stop", message="Stop requested for the paired desktop")

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        current_runtime_session_id = (

            str(getattr(getattr(runtime, "session", None), "id", "") or "").strip()

            or (runtime.session_manager.get_current_session_id() if runtime.session_manager else None)

            or target_session_id

        )

        stop_summary = _stop_runtime_execution(runtime)

        stopped_event_runs: list[Dict[str, Any]] = []

        stopped_process_waits: list[Dict[str, Any]] = []

        if current_runtime_session_id:

            try:

                stopped_event_runs = _get_remote_control_store().cancel_event_runs_for_session(

                    user_id=int(auth["user_id"]),

                    session_id=str(current_runtime_session_id),

                    reason="Stopped by user from app",

                )

                stopped_process_waits = _get_remote_control_store().stop_process_waits_for_session(

                    user_id=int(auth["user_id"]),

                    session_id=str(current_runtime_session_id),

                    reason="Stopped by user from app",

                )

            except Exception:

                logger.exception("[app] failed stopping event/process runtime state")

        archived_board = archive_active_task_board(

            runtime,

            status="interrupted",

            summary="The current managed task was stopped by the user.",

        )

        runtime.save_session()

        if current_runtime_session_id:

            try:

                await bridge.orchestrator.force_release_turn(str(current_runtime_session_id), worker=runtime)

            except Exception:

                logger.exception("[app] failed releasing orchestrator turn during stop")

        publish_status_update(

            user_id=int(auth["user_id"]),

            session_id=current_runtime_session_id,

            origin_channel="app",

            message="ready",

            run_state="idle",

        )

        get_channel_sync_hub().publish(

            user_id=int(auth["user_id"]),

            event={

                "type": "task_board",

                "session_id": current_runtime_session_id,

                "origin_channel": "app",

                "payload": {

                    "board": task_board_view(get_display_task_board(runtime)),

                    "completed_task_boards": completed_task_board_views(runtime),

                    "summary": (archived_board or {}).get("completion_summary") if archived_board else "Managed task stopped.",

                },

            },

        )

        killed_count = int((stop_summary.get("background_commands") or {}).get("killed_count") or 0)

        stopped_bits = []

        if stop_summary.get("was_processing"):

            stopped_bits.append("agent turn")

        if killed_count:

            stopped_bits.append(f"{killed_count} command process{'es' if killed_count != 1 else ''}")

        if stop_summary.get("subagents_stopped"):

            stopped_bits.append(f"{stop_summary['subagents_stopped']} sub-agent task{'s' if stop_summary['subagents_stopped'] != 1 else ''}")

        if stopped_event_runs:

            stopped_bits.append(f"{len(stopped_event_runs)} event run{'s' if len(stopped_event_runs) != 1 else ''}")

        if stopped_process_waits:

            stopped_bits.append(f"{len(stopped_process_waits)} process wait{'s' if len(stopped_process_waits) != 1 else ''}")

        message = f"Stopped {' and '.join(stopped_bits)}" if stopped_bits else "Stop requested; no active run was found"

        return AgentActionResponse(action="stop", message=message)

    @app.post("/api/app/agent/control/restart", response_model=AgentActionResponse)

    async def restart_agent_process(

        authorization: Optional[str] = Header(default=None),

        session_id: Optional[str] = None,

    ) -> AgentActionResponse:

        auth = _resolve_token(authorization)

        target_session_id = _require_explicit_agent_session_id(session_id)

        if _is_remote_session_auth(auth):

            await _remote_dispatch_command(

                auth,

                command_name="restart_runtime",

                payload={"session_id": target_session_id},

            )

            return AgentActionResponse(action="restart", message="Restart requested for the paired desktop")

        bridge = _bridge_for_user(int(auth["user_id"]))

        runtime = _load_runtime_session_or_409(bridge, target_session_id)

        async def _restart_later() -> None:

            await asyncio.sleep(1.0)

            exec_current_process(

                script_path_fallback=str(Path(__file__).resolve().parents[2] / "telegram_bot" / "telegram_agent.py")

            )

        _prepare_runtime_restart(runtime)

        asyncio.create_task(_restart_later())

        return AgentActionResponse(action="restart", message="Restart scheduled")
