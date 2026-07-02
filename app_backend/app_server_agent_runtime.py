from __future__ import annotations

# Split from app_server.py; dependencies are injected by the app_server facade.

def _workspace_root() -> Path:

    runtime_home = os.getenv("EMPLOAI_HOME", "").strip()

    if runtime_home:

        return Path(runtime_home).expanduser().resolve()

    return Path(__file__).resolve().parents[2]

def _remote_account_user_id() -> Optional[int]:

    home = runtime_home() or _workspace_root()

    path = home / REMOTE_ACCOUNT_SESSION_FILENAME

    try:

        payload = json.loads(path.read_text(encoding="utf-8"))

    except Exception:

        return None

    if not isinstance(payload, dict):

        return None

    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}

    raw_user_id = user.get("user_id") or payload.get("user_id")

    try:

        user_id = int(raw_user_id)

    except (TypeError, ValueError):

        return None

    return user_id if user_id > 0 else None

def _default_user_id() -> int:

    return _remote_account_user_id() or DEFAULT_APP_USER_ID

def _get_security_manager() -> Optional[SecurityManager]:

    global _security_manager, _security_manager_attempted

    if _security_manager_attempted:

        return _security_manager

    _security_manager_attempted = True

    try:

        from runtime_support.security import SecurityManager

        _security_manager = SecurityManager(

            max_requests_per_minute=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),

            max_requests_per_hour=int(os.getenv("MAX_REQUESTS_PER_HOUR", "200")),

        )

    except Exception:

        _security_manager = None

    return _security_manager

def _telegram_allowed_user_ids() -> list[int]:

    raw_values = [item for item in os.getenv("ALLOWED_USER_IDS", "").split(",")]

    legacy_single_id = os.getenv("ALLOWED_USER_ID", "")

    if legacy_single_id:

        raw_values.append(legacy_single_id)

    user_ids: list[int] = []

    for raw in raw_values:

        clean = str(raw or "").strip()

        if not clean.isdigit():

            continue

        user_id = int(clean)

        if user_id not in user_ids:

            user_ids.append(user_id)

    return user_ids

def _sleep_mode_session_label(bridge: "AppSessionBridge", session_id: str) -> Optional[str]:

    clean_session_id = str(session_id or "").strip()

    if not clean_session_id:

        return None

    try:

        session = bridge.get_session(clean_session_id)

        name = str(getattr(session, "name", "") or "").strip()

        return f"{name} ({clean_session_id})" if name else clean_session_id

    except Exception:

        logger.debug("Failed to resolve sleep-mode session label for %s", clean_session_id, exc_info=True)

        return clean_session_id

def _sleep_mode_notice_text(*, bot_label: str, session_label: Optional[str]) -> str:

    lines = [

        "EmploAI sleep mode is now active.",

        "The desktop UI is being hidden. Until sleep mode is turned off, operate EmploAI from Telegram or local automations.",

        f"This Telegram bot ({bot_label}) now has one designated Telegram sleep chat while sleep mode is on.",

        "Opening the desktop app again will reconnect the UI and turn sleep mode off.",

    ]

    if session_label:

        lines.append(f"Designated sleep chat: {session_label}")

    else:

        lines.append("No sleep chat is assigned for this bot, so it cannot run tasks until one is assigned.")

    return "\n".join(lines)

async def _notify_sleep_mode_enabled(bridge: "AppSessionBridge") -> None:

    user_ids = _telegram_allowed_user_ids()

    if not user_ids:

        logger.info("Sleep mode enabled without Telegram notifications because no allowed Telegram user IDs are configured.")

        return

    bot_configs = bridge.orchestrator.telegram_bots.list_configs()

    if not bot_configs:

        logger.info("Sleep mode enabled without Telegram notifications because no Telegram bots are configured.")

        return

    sleep_session_by_bot = bridge.orchestrator.telegram_bots.get_sleep_session_by_bot()

    for config in bot_configs:

        bot_config_id = str(config.get("id") or "").strip()

        bot_token = str(config.get("bot_token") or "").strip()

        if not bot_config_id or not bot_token:

            continue

        bot_label = str(config.get("label") or "Telegram Bot").strip() or "Telegram Bot"

        session_id = str(sleep_session_by_bot.get(bot_config_id) or "").strip()

        text = _sleep_mode_notice_text(

            bot_label=bot_label,

            session_label=_sleep_mode_session_label(bridge, session_id) if session_id else None,

        )

        if Bot is None:

            logger.warning("Could not initialize Telegram bot for sleep-mode notice: %s", bot_config_id, exc_info=True)

            continue

        try:

            bot = Bot(token=bot_token)

        except Exception:

            logger.warning("Could not initialize Telegram bot for sleep-mode notice: %s", bot_config_id, exc_info=True)

            continue

        try:

            for user_id in user_ids:

                try:

                    await asyncio.wait_for(bot.send_message(chat_id=user_id, text=text), timeout=8)

                except Exception:

                    logger.warning(

                        "Failed to send sleep-mode Telegram notice via bot %s to user %s",

                        bot_config_id,

                        user_id,

                        exc_info=True,

                    )

        finally:

            shutdown = getattr(bot, "shutdown", None)

            if callable(shutdown):

                try:

                    result = shutdown()

                    if asyncio.iscoroutine(result):

                        await result

                except Exception:

                    logger.debug("Failed to shut down sleep-mode notice bot %s", bot_config_id, exc_info=True)

def _resolve_target_session_id(bridge: "AppSessionBridge", session_id: Optional[str] = None) -> str:

    target_session_id = str(session_id or "").strip()

    if target_session_id:

        return target_session_id

    current = bridge.get_current_session()

    if not current:

        raise HTTPException(status_code=404, detail="No current session")

    return str(current.id)

def _require_explicit_agent_session_id(session_id: Optional[str]) -> str:

    target_session_id = str(session_id or "").strip()

    if not target_session_id:

        raise HTTPException(status_code=400, detail="Open or select a chat before using agent controls.")

    return target_session_id

def _load_runtime_session_or_409(bridge: AppSessionBridge, session_id: Optional[str] = None):

    try:

        target_session_id = _resolve_target_session_id(bridge, session_id)

        return bridge.orchestrator.get_worker(target_session_id)

    except HTTPException:

        raise

    except RuntimeError as exc:

        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except (KeyError, ValueError) as exc:

        detail = str(exc).strip() or "Session not found"

        raise HTTPException(status_code=404, detail=detail) from exc

def _current_headless_mode() -> str:

    return "headless" if os.getenv("HEADLESS", "true").strip().lower() in {"true", "1", "yes", "on"} else "headed"

def _model_groups(runtime) -> list[dict[str, Any]]:

    return runtime.get_available_model_groups(AVAILABLE_MODELS)

def _missing_provider_api_key_payload(runtime) -> Optional[dict[str, Any]]:

    get_enabled_providers = getattr(runtime, "get_enabled_providers", None)

    if not callable(get_enabled_providers):

        return None

    try:

        enabled_providers = {

            str(provider or "").strip().lower()

            for provider in get_enabled_providers()

            if str(provider or "").strip()

        }

    except Exception:

        logger.exception("[app] failed checking configured provider API keys")

        return None

    if enabled_providers:

        return None

    return {

        "message": "You have not set an API key yet. Add an API key in Setup before sending a message.",

        "code": "missing_provider_api_key",

        "retryable": False,

    }

def _estimate_message_tokens(message: Dict[str, Any]) -> int:

    content = message.get("content", "")

    if isinstance(content, str):

        return len(content) // 4

    if isinstance(content, list):

        return len(json.dumps(content)) // 4

    return len(str(content)) // 4

def _rough_message_tokens(messages: list[dict[str, Any]]) -> int:

    return sum(max(0, _estimate_message_tokens(message)) for message in messages)

def _active_tool_packs_for_context_usage(runtime) -> list[str]:

    return list(

        getattr(runtime, "_active_tool_packs_for_current_run", None)

        or getattr(runtime, "enabled_tool_packs", [])

        or []

    )

def _tool_definition_name_for_usage(tool: dict[str, Any]) -> str:

    if not isinstance(tool, dict):

        return ""

    if isinstance(tool.get("function"), dict):

        return str(tool["function"].get("name") or "").strip()

    return str(tool.get("name") or "").strip()

def _merge_tool_definitions_for_usage(*tool_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:

    merged: list[dict[str, Any]] = []

    seen: set[str] = set()

    for group in tool_groups:

        for tool in group or []:

            name = _tool_definition_name_for_usage(tool)

            if not name or name in seen:

                continue

            merged.append(tool)

            seen.add(name)

    return merged

def _context_usage_tool_schema_tokens(runtime, active_tool_packs: list[str]) -> tuple[int, int]:

    try:

        from cli.agent_tools.definitions import CLI_AGENT_TOOLS

        from shared import merge_openai_tools

        from shared.task_board import TASK_BOARD_FAILURE_REPORT_TOOL, get_active_task_board

        from shared.tool_packs import filter_openai_tools_by_enabled_packs, filter_tools_by_enabled_packs

        from local_agent_runtime.tool_manifest import AGENT_TOOLS

        from telegram_bot.telegram_unified_agent import get_auto_mode_extra_tools

        base_tools = filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, active_tool_packs)

        extra_tools = filter_openai_tools_by_enabled_packs(

            merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS),

            active_tool_packs,

        )

        all_tools = _merge_tool_definitions_for_usage(base_tools, extra_tools)

        if get_active_task_board(runtime):

            all_tools = _merge_tool_definitions_for_usage(all_tools, [TASK_BOARD_FAILURE_REPORT_TOOL])

        serialized = json.dumps(all_tools, ensure_ascii=False, default=str)

        return max(0, len(serialized) // 4), len(all_tools)

    except Exception:

        return 0, 0

def _context_usage_prompt_messages(runtime) -> tuple[list[dict[str, Any]], dict[str, int]]:

    active_tool_packs = _active_tool_packs_for_context_usage(runtime)

    system_messages: list[dict[str, Any]] = []

    injected_messages: list[dict[str, Any]] = []

    prelude_messages: list[dict[str, Any]] = []

    try:

        from shared.channel_runtime import _build_file_context, _memory_context

        from telegram_bot.telegram_unified_agent import build_unified_system_prompt

        skills_index = ""

        active_skills_context = ""

        if getattr(runtime, "skill_registry", None):

            skills_index = f"\n\n{runtime.skill_registry.get_skills_index()}"

            if getattr(runtime, "active_skills", None):

                active_skills_context = (

                    "\n\n# LOADED SPECIALIZED SKILLS\n"

                    f"{runtime.skill_registry.get_active_skills_context(runtime.active_skills)}"

                )

        system_messages.append(

            {

                "role": "system",

                "content": build_unified_system_prompt(

                    runtime,

                    memory_context=_memory_context(runtime),

                    skills_index=skills_index,

                    active_skills_context=active_skills_context,

                ),

            }

        )

        file_context = _build_file_context(list(getattr(runtime, "pending_files", []) or []))

        if file_context:

            injected_messages.append(

                {

                    "role": "system",

                    "content": f"USER ATTACHMENTS (structured data):\n{file_context}",

                }

            )

    except Exception:

        pass

    user_message = str(getattr(runtime, "last_user_message", "") or "")

    try:

        from app_backend.runtime import (

            _conversational_turn_guard,

            _kickstart_prelude,

            _screen_observation_contract,

            _task_execution_contract,

        )

        from shared.task_intent import (

            is_screen_observation_message,

            is_task_like_message,

            request_requires_tool_evidence,

        )

        screen_observation_turn = is_screen_observation_message(user_message)

        task_like_turn = screen_observation_turn or is_task_like_message(user_message)

        tool_evidence_turn = request_requires_tool_evidence(user_message)

        if screen_observation_turn:

            injected_messages.append(_screen_observation_contract(active_tool_packs))

        if tool_evidence_turn:

            injected_messages.append(_task_execution_contract(runtime, active_tool_packs))

        if not tool_evidence_turn or not task_like_turn:

            injected_messages.append(_conversational_turn_guard())

        if tool_evidence_turn and len(getattr(runtime, "chat_history", []) or []) <= 3:

            prelude_messages.extend(_kickstart_prelude(active_tool_packs))

    except Exception:

        pass

    try:

        from shared.channel_runtime import _desktop_window_context_message, _task_contract_context_message

        from shared.task_board import before_model_turn_messages

        injected_messages.extend(before_model_turn_messages(runtime))

        task_contract = _task_contract_context_message(runtime)

        if task_contract:

            injected_messages.append(task_contract)

        desktop_context = _desktop_window_context_message(runtime)

        if desktop_context:

            injected_messages.append(desktop_context)

    except Exception:

        pass

    try:

        from shared.artifact_store import ChatArtifactStore

        user_id = getattr(runtime, "user_id", None)

        session_id = runtime.session_manager.get_current_session_id() if getattr(runtime, "session_manager", None) else None

        if user_id is not None and session_id:

            board = get_display_task_board(runtime)

            task_focus = None

            if isinstance(board, dict):

                task_focus = str(board.get("current_focus") or board.get("main_goal") or "").strip() or None

            injected_messages.extend(

                ChatArtifactStore(user_id=int(user_id), session_id=str(session_id)).build_prompt_messages(

                    user_message=user_message,

                    task_focus=task_focus,

                )

            )

    except Exception:

        pass

    history_messages = [

        {"role": item.get("role", "user"), "content": item.get("content", "")}

        for item in list(getattr(runtime, "chat_history", []) or [])

    ]

    messages = [*system_messages, *injected_messages, *prelude_messages, *history_messages]

    breakdown = {

        "system_prompt_tokens": _rough_message_tokens(system_messages),

        "injected_context_tokens": _rough_message_tokens([*injected_messages, *prelude_messages]),

        "chat_history_tokens": _rough_message_tokens(history_messages),

        "prompt_message_count": len(messages),

    }

    return messages, breakdown

def _context_usage(runtime) -> dict[str, Any]:

    active_tool_packs = _active_tool_packs_for_context_usage(runtime)

    prompt_messages, breakdown = _context_usage_prompt_messages(runtime)

    tool_schema_tokens, tool_count = _context_usage_tool_schema_tokens(runtime, active_tool_packs)

    context_manager = getattr(runtime, "context_manager", None)

    if context_manager:

        max_tokens = context_manager.get_context_size(runtime.current_model)

        message_tokens, token_strategy = context_manager.count_tokens_with_strategy(prompt_messages, runtime.current_model)

        estimated_tokens = message_tokens + tool_schema_tokens

        usage_percent = (estimated_tokens / max_tokens) * 100 if max_tokens else 0.0

        threshold_percent = context_manager.COMPRESSION_THRESHOLD * 100

        last_compaction = getattr(runtime, "last_context_compaction", None)

        needs_compaction = usage_percent >= threshold_percent

        compaction_state = "needs_compaction" if needs_compaction else "compacted" if last_compaction and last_compaction.get("applied") else "ok"

        return {

            "model": runtime.current_model,

            "max_tokens": max_tokens,

            "estimated_tokens": estimated_tokens,

            "usage_percent": round(usage_percent, 2),

            "message_count": len(prompt_messages),

            "threshold_percent": threshold_percent,

            "needs_compaction": needs_compaction,

            "compaction_state": compaction_state,

            "token_strategy": token_strategy,

            "last_compaction": last_compaction,

            **breakdown,

            "tool_schema_tokens": tool_schema_tokens,

            "tool_schema_count": tool_count,

        }

    max_tokens = int(MODEL_CONTEXT_SIZES.get(runtime.current_model, 128000))

    message_tokens = _rough_message_tokens(prompt_messages)

    estimated_tokens = message_tokens + tool_schema_tokens

    usage_percent = (estimated_tokens / max_tokens) * 100 if max_tokens else 0.0

    threshold_percent = 40.0

    return {

        "model": runtime.current_model,

        "max_tokens": max_tokens,

        "estimated_tokens": estimated_tokens,

        "usage_percent": round(usage_percent, 2),

        "message_count": len(prompt_messages),

        "threshold_percent": threshold_percent,

        "needs_compaction": usage_percent >= threshold_percent,

        "compaction_state": "needs_compaction" if usage_percent >= threshold_percent else "ok",

        "token_strategy": "rough",

        "last_compaction": getattr(runtime, "last_context_compaction", None),

        **breakdown,

        "tool_schema_tokens": tool_schema_tokens,

        "tool_schema_count": tool_count,

    }

def _history_preview(runtime, count: int) -> list[dict[str, Any]]:

    preview_items: list[dict[str, Any]] = []

    for message in runtime.chat_history[-count:]:

        content = message.get("content", "")

        if isinstance(content, list):

            preview = json.dumps(content)

        else:

            preview = str(content)

        preview = preview.replace("\n", " ").strip()

        if len(preview) > 180:

            preview = preview[:180] + "..."

        preview_items.append(

            {

                "role": message.get("role", "user"),

                "timestamp": message.get("timestamp"),

                "preview": preview,

                "display_label": message.get("display_label"),

            }

        )

    return list(reversed(preview_items))

def _pending_files(runtime) -> list[dict[str, Any]]:

    items: list[dict[str, Any]] = []

    for pending in runtime.pending_files:

        items.append(

            {

                "filename": str(pending.get("filename", "upload")),

                "mime_type": pending.get("mime_type"),

                "size": pending.get("size"),

                "source_format": pending.get("source_format"),

                "uploaded_at": pending.get("uploaded_at"),

            }

        )

    return items

def _memory_summary(runtime) -> dict[str, Any]:

    if not runtime.memory_manager:

        return {

            "memory_file_exists": False,

            "daily_log_count": 0,

            "oldest_log": None,

            "newest_log": None,

        }

    return runtime.memory_manager.export_memory_summary()

def _analytics_summary(runtime, days: int) -> dict[str, Any]:

    if not runtime.analytics_tracker:

        return {

            "period_days": days,

            "total_events": 0,

            "total_messages": 0,

            "total_commands": 0,

            "total_tokens": 0,

            "avg_tokens_per_message": 0.0,

            "top_skills": {},

            "top_commands": {},

            "model_usage": {},

            "daily_activity": {},

        }

    return runtime.analytics_tracker.get_summary(days)

def _security_summary() -> dict[str, Any]:

    manager = _get_security_manager()

    if not manager:

        return {

            "allowed_users_count": len([item for item in os.getenv("ALLOWED_USER_IDS", "").split(",") if item.strip()]),

            "rate_limited_users": 0,

            "security_events_24h": 0,

            "warning_events_24h": 0,

            "error_events_24h": 0,

            "max_requests_per_minute": int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),

            "max_requests_per_hour": int(os.getenv("MAX_REQUESTS_PER_HOUR", "200")),

        }

    summary = manager.get_security_summary()

    summary["max_requests_per_minute"] = manager.max_requests_per_minute

    summary["max_requests_per_hour"] = manager.max_requests_per_hour

    return summary

def _config_preview(runtime, limit: int = 18) -> list[dict[str, Any]]:

    if not runtime.live_config:

        return []

    items = runtime.live_config.list_all()

    return [{"key": key, "value": value} for key, value in sorted(items.items())[:limit]]

def _shared_profile_preferences() -> dict[str, Any]:

    user_id = _remote_account_user_id()

    if not user_id:

        return {}

    try:

        profile = _get_remote_control_store().get_user_profile(user_id=int(user_id))

    except Exception:

        logger.exception("[app] failed to load remote account profile preferences")

        return {}

    preferences = profile.get("preferences") if isinstance(profile, dict) else {}

    return preferences if isinstance(preferences, dict) else {}

def _set_live_config_if_changed(live_config, key: str, value: Any, *, user_id: int) -> bool:

    if not live_config:

        return False

    if live_config.get(key) == value:

        return False

    live_config.set(key, value, user_id)

    return True

def _apply_shared_profile_to_runtime(runtime) -> None:

    preferences = _shared_profile_preferences()

    if not preferences:

        return

    live_config_changed = False

    max_turns = preferences.get("max_turns")

    if isinstance(max_turns, int) and 10 <= max_turns <= 1000:

        if runtime.max_turns != max_turns:

            runtime.max_turns = max_turns

        live_config_changed = _set_live_config_if_changed(

            runtime.live_config,

            "agent.max_turns",

            max_turns,

            user_id=runtime.user_id,

        ) or live_config_changed

    if isinstance(preferences.get("verbose_mode"), bool):

        runtime.verbose_mode = bool(preferences.get("verbose_mode"))

    prompt_append = preferences.get("custom_system_prompt_append")

    prompt_value = prompt_append.strip() if isinstance(prompt_append, str) else ""

    live_config_changed = _set_live_config_if_changed(

        runtime.live_config,

        "agent.custom_system_prompt_append",

        prompt_value,

        user_id=runtime.user_id,

    ) or live_config_changed

    memory_controls = preferences.get("memory_controls") if isinstance(preferences.get("memory_controls"), dict) else {}

    for profile_key, config_key in (

        ("prompt_context_enabled", "memory.prompt_context_enabled"),

        ("search_enabled", "memory.search_enabled"),

        ("write_enabled", "memory.write_enabled"),

    ):

        value = memory_controls.get(profile_key)

        live_config_changed = _set_live_config_if_changed(

            runtime.live_config,

            config_key,

            bool(value) if isinstance(value, bool) else True,

            user_id=runtime.user_id,

        ) or live_config_changed

    if live_config_changed and runtime.live_config:

        runtime.live_config.save_config()

def _persist_shared_runtime_preferences(*, max_turns: Optional[int] = None, verbose_mode: Optional[bool] = None) -> None:

    user_id = _remote_account_user_id()

    if not user_id:

        return

    try:

        store = _get_remote_control_store()

        profile = store.get_user_profile(user_id=int(user_id))

        preferences = dict(profile.get("preferences") or {})

        changed = False

        if max_turns is not None and preferences.get("max_turns") != max_turns:

            preferences["max_turns"] = max_turns

            changed = True

        if verbose_mode is not None and preferences.get("verbose_mode") != verbose_mode:

            preferences["verbose_mode"] = verbose_mode

            changed = True

        if not changed:

            return

        store.update_user_profile(user_id=int(user_id), profile={**profile, "preferences": preferences})

    except Exception:

        logger.exception("[app] failed to persist shared runtime preferences")

def _agent_overview(runtime, bridge: "AppSessionBridge", *, history_count: int = 12, analytics_days: int = 7) -> dict[str, Any]:

    _apply_shared_profile_to_runtime(runtime)

    if runtime.ensure_current_model_available(AVAILABLE_MODELS):

        try:

            runtime.save_session()

        except Exception:

            logger.exception("[app] failed to persist automatic model/planner realignment")

    heartbeat = (

        runtime.heartbeat_manager.get_status()

        if runtime.heartbeat_manager

        else {

            "enabled": bool(runtime.live_config.get("heartbeat.enabled", False)) if runtime.live_config else False,

            "running": False,

            "interval_seconds": int(runtime.live_config.get("heartbeat.interval_seconds", 1800)) if runtime.live_config else 1800,

            "check_count": 0,

            "last_heartbeat": None,

        }

    )

    get_supported_planner_models = getattr(runtime, "get_supported_planner_models", None)

    planner_models = list(get_supported_planner_models(AVAILABLE_MODELS)) if callable(get_supported_planner_models) else []

    return {

        "session_id": runtime.session_manager.get_current_session_id() if runtime.session_manager else None,

        "current_model": runtime.current_model,

        "current_variant": runtime.current_variant,

        "planner_model": getattr(runtime, "planner_model", None),

        "available_planner_models": planner_models,

        "available_variants": runtime.get_available_variants(),

        "model_groups": _model_groups(runtime),

        "max_turns": runtime.max_turns,

        "workspace": str(runtime.workspace),

        "auto_reply_enabled": bool(runtime.auto_reply_enabled),

        "verbose_mode": bool(runtime.verbose_mode),

        "bridge_enabled": bool(runtime.live_config.get("browser.use_extension", True)) if runtime.live_config else False,

        "headless_mode": _current_headless_mode(),

        "heartbeat": heartbeat,

        "context_usage": _context_usage(runtime),

        "history": _history_preview(runtime, max(1, min(history_count, 25))),

        "pending_files": _pending_files(runtime),

        "memory_summary": _memory_summary(runtime),

        "analytics": _analytics_summary(runtime, max(1, min(analytics_days, 30))),

        "security": _security_summary(),

        "config_preview": _config_preview(runtime),

        "run_state": "running" if bool(getattr(runtime, "is_processing", False)) else "idle",

        "task_board": task_board_view(get_display_task_board(runtime)),

        "completed_task_boards": completed_task_board_views(runtime),

        "task_board_armed_next_turn": get_task_board_armed_next_turn(runtime),

        "available_tool_packs": bridge.orchestrator.available_tool_packs_for_session_obj(runtime.session),

        "enabled_tool_packs": list(getattr(runtime, "enabled_tool_packs", []) or []),

        "lock_status": bridge.orchestrator.lock_status_for_session_obj(runtime.session),

    }

def _coerce_config_value(raw_value: Any) -> Any:

    if not isinstance(raw_value, str):

        return raw_value

    value = raw_value.strip()

    if value.lower() in {"true", "false"}:

        return value.lower() == "true"

    if value.startswith("{") or value.startswith("["):

        try:

            return json.loads(value)

        except json.JSONDecodeError:

            return value

    try:

        return int(value)

    except ValueError:

        pass

    try:

        return float(value)

    except ValueError:

        return value

def _resolve_workspace_path(requested: str, *, user_id: int) -> Path:

    requested_value = (requested or "").strip()

    if not requested_value:

        raise HTTPException(status_code=400, detail="Workspace is required")

    manager = _get_security_manager()

    resolved_path: Optional[Path] = None

    if manager:

        valid, resolved_path, error = manager.validate_path(requested_value, user_id)

        if not valid or not resolved_path:

            raise HTTPException(status_code=400, detail=error or "Invalid workspace path")

    else:

        resolved_path = Path(requested_value).expanduser().resolve()

    if not resolved_path.exists() or not resolved_path.is_dir():

        raise HTTPException(status_code=400, detail="Workspace path does not exist or is not a directory")

    return resolved_path

def _set_workspace(runtime, workspace_value: str) -> None:

    resolved_path = _resolve_workspace_path(workspace_value, user_id=runtime.user_id)

    try:

        runtime.set_workspace(resolved_path)

    except RuntimeError as exc:

        raise HTTPException(status_code=409, detail=str(exc)) from exc

    runtime.save_session()

def _configure_runtime(runtime, request: AgentConfigureRequest) -> None:

    _apply_shared_profile_to_runtime(runtime)

    runtime.ensure_current_model_available(AVAILABLE_MODELS)

    should_save_session = False

    persist_max_turns: Optional[int] = None

    persist_verbose_mode: Optional[bool] = None

    if request.model is not None:

        if request.model not in runtime.get_available_models(AVAILABLE_MODELS):

            raise HTTPException(status_code=400, detail="Model is unavailable for configured providers")

        runtime.current_model = request.model

        should_save_session = True

    available_variants = runtime.get_available_variants()

    if runtime.current_variant not in available_variants:

        runtime.current_variant = available_variants[0] if available_variants else "standard"

    if request.variant is not None:

        available_variants = runtime.get_available_variants()

        if request.variant not in available_variants:

            raise HTTPException(status_code=400, detail="Variant is not available for the current model")

        runtime.current_variant = request.variant

        should_save_session = True

    if request.planner_model is not None:

        planner_value = str(request.planner_model).strip() or None

        get_supported_planner_models = getattr(runtime, "get_supported_planner_models", None)

        supported_planner_models = (

            set(get_supported_planner_models(AVAILABLE_MODELS))

            if callable(get_supported_planner_models)

            else set(runtime.get_available_models(AVAILABLE_MODELS))

        )

        if planner_value and planner_value not in supported_planner_models:

            raise HTTPException(status_code=400, detail="Planner model is unavailable for the lightweight planner runtime")

        runtime.planner_model = planner_value

        should_save_session = True

    if request.max_turns is not None:

        max_turns = int(request.max_turns)

        if max_turns < 10 or max_turns > 1000:

            raise HTTPException(status_code=400, detail="Max turns must be between 10 and 1000")

        runtime.max_turns = max_turns

        if runtime.live_config:

            runtime.live_config.set("agent.max_turns", max_turns, runtime.user_id)

            runtime.live_config.save_config()

        persist_max_turns = max_turns

    if request.custom_system_prompt_append is not None:

        prompt_append = str(request.custom_system_prompt_append or "").strip()

        if len(prompt_append) > 8000:

            raise HTTPException(status_code=400, detail="Custom instructions must be 8000 characters or less")

        if runtime.live_config:

            runtime.live_config.set("agent.custom_system_prompt_append", prompt_append, runtime.user_id)

            runtime.live_config.save_config()

    if request.memory_controls is not None:

        memory_controls = request.memory_controls if isinstance(request.memory_controls, dict) else {}

        if runtime.live_config:

            for profile_key, config_key in (

                ("prompt_context_enabled", "memory.prompt_context_enabled"),

                ("search_enabled", "memory.search_enabled"),

                ("write_enabled", "memory.write_enabled"),

            ):

                if profile_key in memory_controls:

                    runtime.live_config.set(config_key, bool(memory_controls.get(profile_key)), runtime.user_id)

            runtime.live_config.save_config()

    if request.workspace is not None:

        _set_workspace(runtime, request.workspace)

        should_save_session = True

    if request.auto_reply_enabled is not None:

        runtime.auto_reply_enabled = bool(request.auto_reply_enabled)

        if runtime.auto_reply_enabled:

            runtime.auto_reply_notice_sent = False

    if request.verbose_mode is not None:

        runtime.verbose_mode = bool(request.verbose_mode)

        persist_verbose_mode = bool(request.verbose_mode)

    if request.bridge_enabled is not None and runtime.live_config:

        runtime.live_config.set("browser.use_extension", bool(request.bridge_enabled), runtime.user_id)

        runtime.live_config.save_config()

        runtime.reset_browser_task_context(runtime.current_task_id)

        if request.bridge_enabled:

            try:

                from telegram_bot.telegram_unified_agent import ensure_extension_bridge

                ensure_extension_bridge(runtime)

            except Exception:

                logger.exception("[app] failed to enable browser bridge")

    if request.heartbeat_interval_seconds is not None:

        seconds = int(request.heartbeat_interval_seconds)

        if seconds < 60 or seconds > 86400:

            raise HTTPException(status_code=400, detail="Heartbeat interval must be between 60 and 86400 seconds")

        if runtime.live_config:

            runtime.live_config.set("heartbeat.interval_seconds", seconds, runtime.user_id)

            runtime.live_config.save_config()

        if runtime.heartbeat_manager:

            runtime.heartbeat_manager.set_interval(seconds)

    if request.heartbeat_enabled is not None:

        enabled = bool(request.heartbeat_enabled)

        if runtime.live_config:

            runtime.live_config.set("heartbeat.enabled", enabled, runtime.user_id)

            runtime.live_config.save_config()

        if runtime.heartbeat_manager:

            if enabled:

                runtime.heartbeat_manager.start()

            else:

                runtime.heartbeat_manager.stop()

    if request.headless_mode is not None:

        os.environ["HEADLESS"] = "true" if request.headless_mode == "headless" else "false"

        if runtime.refined_agent:

            runtime.refined_agent.browser.headless = request.headless_mode == "headless"

    if should_save_session:

        runtime.save_session()

    if persist_max_turns is not None or persist_verbose_mode is not None:

        _persist_shared_runtime_preferences(max_turns=persist_max_turns, verbose_mode=persist_verbose_mode)

def _publish_runtime_config_sync(runtime, *, user_id: int, origin_channel: str) -> None:

    try:

        session_id = str(getattr(getattr(runtime, "session", None), "id", "") or "").strip()

        if not session_id and runtime.session_manager:

            session_id = runtime.session_manager.get_current_session_id()

        if not session_id:

            return

        get_channel_sync_hub().publish(

            user_id=user_id,

            event={

                "type": "session_config",

                "session_id": session_id,

                "origin_channel": origin_channel,

                "payload": {

                    "model": runtime.current_model,

                    "variant": runtime.current_variant,

                    "planner_model": getattr(runtime, "planner_model", None),

                    "max_turns": runtime.max_turns,

                    "auto_reply_enabled": bool(runtime.auto_reply_enabled),

                    "verbose_mode": bool(runtime.verbose_mode),

                    "bridge_enabled": bool(runtime.live_config.get("browser.use_extension", True)) if runtime.live_config else False,

                    "headless_mode": _current_headless_mode(),

                    "enabled_tool_packs": list(getattr(runtime, "enabled_tool_packs", []) or []),

                    "telegram_bot_config_id": getattr(runtime, "telegram_bot_config_id", None),

                    "headless_eligible": bool(getattr(runtime, "headless_eligible", False)),

                },

            },

        )

    except Exception:

        logger.exception("[app] failed to publish runtime config sync")

def _active_task_agents(runtime) -> list[Any]:

    agents = []

    for attr in ("unified_agent", "refined_agent", "single_agent"):

        agent = getattr(runtime, attr, None)

        if agent and getattr(agent, "current_task", None):

            agents.append(agent)

    return agents

def _stop_runtime_execution(runtime) -> dict[str, Any]:

    """Stop the current runtime turn and terminate task-owned background work."""

    was_processing = bool(getattr(runtime, "is_processing", False))

    runtime.should_interrupt = True

    runtime.interrupt_message = None

    if hasattr(runtime, "interrupt_queue"):

        try:

            runtime.interrupt_queue.clear()

        except Exception:

            runtime.interrupt_queue = []

    if hasattr(runtime, "deferred_interrupt_queue"):

        try:

            runtime.deferred_interrupt_queue.clear()

        except Exception:

            runtime.deferred_interrupt_queue = []

    agents_stopped = 0

    for agent in _active_task_agents(runtime):

        try:

            agent.stop()

            agents_stopped += 1

        except Exception:

            logger.exception("[app] failed stopping agent")

    background_commands = {}

    tool_executor = getattr(runtime, "tool_executor", None)

    kill_all = getattr(tool_executor, "kill_all_background_commands", None)

    if callable(kill_all):

        try:

            background_commands = kill_all()

        except Exception:

            logger.exception("[app] failed killing runtime background commands")

            background_commands = {"killed": [], "already_exited": [], "errors": [{"error": "kill_all_background_commands failed"}]}

    subagents_stopped = 0

    spawn_tool = getattr(runtime, "spawn_tool", None)

    stop_all_tasks = getattr(spawn_tool, "stop_all_tasks", None)

    if callable(stop_all_tasks):

        try:

            subagents_stopped = int(stop_all_tasks() or 0)

        except Exception:

            logger.exception("[app] failed stopping sub-agent tasks")

    runtime.current_turn_allowed_tool_names = None

    runtime.current_turn_allowed_tool_definitions = []

    runtime.is_processing = False

    return {

        "was_processing": was_processing,

        "agents_stopped": agents_stopped,

        "subagents_stopped": subagents_stopped,

        "background_commands": background_commands,

    }

def _prepare_runtime_restart(runtime) -> None:

    _stop_runtime_execution(runtime)

    runtime.should_interrupt = True

    if getattr(runtime, "heartbeat_manager", None):

        try:

            runtime.heartbeat_manager.stop()

        except Exception:

            logger.exception("[app] failed stopping heartbeat during restart prep")

    runtime.save_session()

def _ensure_background_runtime(runtime) -> None:

    if getattr(runtime, "spawn_tool", None):

        return

    try:

        loop = asyncio.get_running_loop()

    except RuntimeError as exc:  # pragma: no cover - app routes always have a loop

        raise HTTPException(status_code=503, detail="No event loop is available") from exc

    runtime.init_single_agent(None, loop)

def _skill_items(runtime) -> list[dict[str, Any]]:

    registry = getattr(runtime, "skill_registry", None)

    if not registry:

        return []

    gating = getattr(registry, "gating", None)

    available_skills = gating.list_available_skills() if gating else []

    unavailable = getattr(gating, "_unavailable_skills", {}) if gating else {}

    active = set(getattr(runtime, "active_skills", []) or [])

    items: list[dict[str, Any]] = []

    for skill in available_skills:

        items.append(

            {

                "name": skill.name,

                "description": skill.description,

                "user_invocable": bool(getattr(skill.metadata, "user_invocable", False)),

                "available": True,

                "active": skill.name in active,

                "unavailable_reason": None,

                "body_loaded": bool(getattr(skill, "body_loaded", False)),

                "resources": sorted(list(getattr(skill, "resources", {}) or {})),

            }

        )

    for name, reason in sorted((unavailable or {}).items()):

        items.append(

            {

                "name": name,

                "description": str(reason),

                "user_invocable": False,

                "available": False,

                "active": False,

                "unavailable_reason": str(reason),

                "body_loaded": False,

                "resources": [],

            }

        )

    items.sort(key=lambda item: (not item["active"], not item["available"], item["name"].lower()))

    return items

def _cors_allow_origins() -> list[str]:

    configured = os.getenv(CORS_ORIGINS_ENV, "").strip()

    origins = (

        [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]

        if configured

        else list(_DEFAULT_PRODUCTION_CORS_ORIGINS if _production_mode_enabled() else _DEFAULT_DEVELOPMENT_CORS_ORIGINS)

    )

    if _production_mode_enabled():

        unsafe = [

            origin

            for origin in origins

            if (

                origin in {"*", "null"}

                or origin.startswith("http://")

                or "localhost" in origin.lower()

                or "127.0.0.1" in origin

                or "[::1]" in origin

            )

        ]

        if unsafe:

            raise RuntimeError(

                f"{CORS_ORIGINS_ENV} contains unsafe production origins: {', '.join(sorted(set(unsafe)))}"

            )

    return origins
