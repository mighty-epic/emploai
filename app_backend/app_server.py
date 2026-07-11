from __future__ import annotations

import asyncio
import functools
import inspect
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
from starlette.websockets import WebSocketState
try:
    from telegram import Bot
except Exception:  # pragma: no cover - optional at import time for local app-only runs
    Bot = None  # type: ignore[assignment]

from runtime_support.ui_helpers import ThinkingModeVisualizer
from cli.tui_constants import AVAILABLE_MODELS, MODEL_CONFIGS, MODEL_CONTEXT_SIZES
from shared.runtime_paths import runtime_home
from shared.standalone_policy import standalone_desktop_enabled
from app_backend.auth_store import AppAuthStore
from app_backend.app_confirmation_workflow import (
    consume_approved_confirmation as _consume_approved_confirmation_workflow,
    publish_confirmation_delta as _publish_confirmation_delta_workflow,
)
from app_backend.fleet_orchestration import (
    fleet_selected_chat_for_worker as _fleet_selected_chat_for_worker,
    fleet_task_target_session_id as _fleet_task_target_session_id_from_values,
    task_requires_workspace_write as _task_requires_workspace_write,
    workspace_binding_blocker_for_task as _workspace_binding_blocker_for_task_values,
    workspace_id_for_task as _workspace_id_for_task_values,
)
from app_backend.fleet_preview import capture_local_worker_preview, request_fleet_worker_preview
from app_backend.fleet_local_runtime import get_local_fleet_runtime
from app_backend.fleet_task_dispatch import try_dispatch_fleet_worker_task, try_stop_fleet_worker_task
from app_backend.jarvis_voice_policy import (
    jarvis_barge_in_is_self_echo as _jarvis_barge_in_is_self_echo,
    jarvis_barge_in_text_is_meaningful as _jarvis_barge_in_text_is_meaningful,
    jarvis_barge_in_words as _jarvis_barge_in_words,
    jarvis_confirmation_intent as _jarvis_confirmation_intent,
    jarvis_confirmation_prompt as _jarvis_confirmation_prompt,
    jarvis_extract_wake_request as _jarvis_extract_wake_request,
    jarvis_start_task_message as _jarvis_start_task_message,
    jarvis_tool_update_every as _jarvis_tool_update_every,
    jarvis_tool_update_message as _jarvis_tool_update_message,
    jarvis_wake_phrase as _jarvis_wake_phrase,
    jarvis_voice_turn_is_task_like as _jarvis_voice_turn_is_task_like,
)
from app_backend.models import (
    AgentActionResponse,
    AgentConfigureRequest,
    AgentOverviewView,
    AutomationEventRunView,
    AppUserProfile,
    ChatSendRequest,
    ConfigEntryView,
    ConfigListResponse,
    ConfigUpdateRequest,
    CronFeedItemView,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    FleetAssignTaskRequest,
    FleetCreateLocalWorkerRequest,
    FleetContinueWorkerQueueRequest,
    FleetDeleteWorkerResponse,
    FleetActiveIdentityResponse,
    FleetGroupMembershipRequest,
    FleetGroupRequest,
    FleetIdentityView,
    FleetReportSearchRequest,
    FleetReportRequest,
    FleetReportView,
    FleetSetActiveChatRequest,
    FleetSetActiveIdentityRequest,
    FleetSnapshotResponse,
    FleetTaskRedirectRequest,
    FleetTaskReorderRequest,
    FleetTaskStatusRequest,
    FleetTaskView,
    FleetToolGrantDecisionRequest,
    FleetToolGrantRequest,
    FleetToolGrantView,
    FleetWorkerView,
    FleetWorkerUpdateRequest,
    FleetStopWorkerRequest,
    FleetWorkspaceBindingRequest,
    FleetWorkspaceBindingView,
    JobActionResponse,
    JobCreateRequest,
    JobDetailView,
    HeadlessConfigureRequest,
    IdentityStopRequest,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryNoteRequest,
    MemoryOperationRequest,
    MemoryOperationResponse,
    MemoryFactRequest,
    MemoryFactFeedbackRequest,
    MemoryFactView,
    MemoryFactListResponse,
    RealtimeServerEvent,
    RemoteDesktopSocketMessage,
    RemoteDesktopSyncEnvelope,
    RemoteDesktopView,
    RenameSessionRequest,
    ScheduledJobView,
    ScreenCaptureView,
    PlannerContractView,
    ProcessWaitView,
    SkillActivateRequest,
    SkillDetailView,
    SkillLearnRequest,
    SkillLearnResponse,
    SkillListResponse,
    SkillSummaryView,
    SkillValidationView,
    SessionDetailView,
    SessionSummaryView,
    SidebarStateRequest,
    SidebarStateResponse,
    SubAgentListResponse,
    SubAgentSpawnRequest,
    SubAgentTaskView,
    TaskBoardArmRequest,
    TaskBoardArmResponse,
    TaskBoardResponse,
    TrustedDeviceView,
    VoiceClientEvent,
    VoiceSttConfigureRequest,
    VoiceTtsConfigureRequest,
    RuntimeOrchestratorView,
    RuntimeActionRequest,
    ProcessWaitUpdateRequest,
    PlannerContractStatusRequest,
)
from app_backend.routers.app_confirmations import AppConfirmationsRouterDeps, create_app_confirmations_router
from app_backend.routers.app_files import AppFilesRouterDeps, create_app_files_router
from app_backend.routers.app_onboarding import AppOnboardingRouterDeps, create_app_onboarding_router
from app_backend.routers.app_recovery import AppRecoveryRouterDeps, create_app_recovery_router
from app_backend.routers.app_sessions import AppSessionsRouterDeps, create_app_sessions_router
from app_backend.routers.app_session_settings import AppSessionSettingsRouterDeps, create_app_session_settings_router
from app_backend.routers.app_telegram_bots import AppTelegramBotsRouterDeps, create_app_telegram_bots_router
from app_backend.routers.app_workspace import AppWorkspaceRouterDeps, create_app_workspace_router
from app_backend.routers.fleet_enrollment import FleetEnrollmentRouterDeps, create_fleet_enrollment_router
from app_backend.remote_command_broker import (
    BrokeredRemoteCommandError,
    dispatch_remote_desktop_command_via_broker,
    pump_remote_desktop_command_broker,
    request_remote_desktop_command_via_broker,
)
from app_backend.remote_control_runtime import get_remote_desktop_manager, remote_control_routing_status, remote_control_sqlite_broker_enabled
from app_backend.remote_control_store import (
    REMOTE_SESSION_TTL_SECONDS,
    RemoteControlPlaneStore,
)
from shared.channel_events import publish_current_session_changed, publish_status_update
from shared.channel_sync import get_channel_sync_hub
from shared.live_config import get_live_config
from shared.task_board import (
    archive_active_task_board,
    completed_task_board_views,
    format_task_board_for_user,
    get_active_task_board,
    get_display_task_board,
    get_task_board_armed_next_turn,
    request_task_board_reassessment,
    recover_stale_task_board,
    task_board_view,
)
from local_agent_runtime.cron_scheduler import get_scheduler, parse_schedule_with_error
from telegram_bot.restart_runtime import exec_current_process
from app_backend import (
    app_server_agent_runtime as _app_server_agent_runtime,
    app_server_auth as _app_server_auth,
    app_server_proactive as _app_server_proactive,
    app_server_realtime as _app_server_realtime,
    app_server_remote_ops as _app_server_remote_ops,
    app_server_remote_ws as _app_server_remote_ws,
    app_server_routes_agent as _app_server_routes_agent,
    app_server_routes_events as _app_server_routes_events,
    app_server_routes_fleet as _app_server_routes_fleet,
    app_server_routes_screen_ws as _app_server_routes_screen_ws,
    app_server_routes_sessions as _app_server_routes_sessions,
    app_server_routes_voice_ws as _app_server_routes_voice_ws,
    app_server_voice_helpers as _app_server_voice_helpers,
)

if TYPE_CHECKING:
    from runtime_support.security import SecurityManager
    from app_backend.session_bridge import AppSessionBridge


APP_SECRET_ENV = "EMPLO_APP_SECRET"
DEPLOYMENT_ENV_ENV = "EMPLOAI_ENV"
CORS_ORIGINS_ENV = "EMPLOAI_CORS_ORIGINS"

_auth_store: Optional[AppAuthStore] = None
_remote_control_store: Optional[RemoteControlPlaneStore] = None
_security_manager: Optional[SecurityManager] = None
_security_manager_attempted = False
_server_thread: Optional[threading.Thread] = None
_server_started = False
logger = logging.getLogger(__name__)
_BASE64_KEYS = frozenset({"image_base64", "base64", "image_data", "data", "screenshot"})
_APP_RUNTIME_STATUS: Dict[str, Any] = {
    "startup_state": "idle",
    "startup_error": None,
    "startup_error_detail": None,
    "last_runtime_error": None,
    "last_runtime_error_detail": None,
    "last_runtime_error_at": None,
}
_SESSION_SEARCH_CACHE_LOCK = threading.Lock()
_SESSION_SEARCH_CACHE: Dict[int, Dict[str, Dict[str, Any]]] = {}
_BACKGROUND_SESSION_MIRROR_TASKS: set[asyncio.Task] = set()
_SEARCH_NORMALIZE_RE = re.compile(r"[\W_]+", re.UNICODE)
_SESSION_SEARCH_LIMIT_MAX = 100
DEFAULT_APP_USER_ID = 0
REMOTE_HTTP_PROXY_TIMEOUT_SECONDS = 120.0
REMOTE_HTTP_PROXY_MAX_BODY_BYTES = 32 * 1024 * 1024
REMOTE_HTTP_PROXY_MAX_RESPONSE_BODY_BYTES = 32 * 1024 * 1024
REMOTE_WS_MAX_MESSAGE_BYTES = 8 * 1024 * 1024
REMOTE_CHAT_MAX_TEXT_CHARS = 32 * 1024
REMOTE_AUTH_RATE_LIMIT_WINDOW_SECONDS = 5 * 60
REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS = 20
REMOTE_AUTH_POLL_RATE_LIMIT_MAX_ATTEMPTS = 240
REMOTE_WS_AUTH_RATE_LIMIT_MAX_ATTEMPTS = 20
REMOTE_AUTH_RATE_LIMIT_MAX_KEYS = 10_000
DEBUG_ERROR_RESPONSES_ENV = "EMPLOAI_DEBUG_ERROR_RESPONSES"
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_PRODUCTION_ENV_VALUES = {"prod", "production"}
_DEFAULT_PRODUCTION_CORS_ORIGINS = [
    "emploai://renderer",
]
_DEFAULT_DEVELOPMENT_CORS_ORIGINS = [
    "emploai://renderer",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8787",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8787",
    *_DEFAULT_PRODUCTION_CORS_ORIGINS,
]
_REMOTE_AUTH_RATE_LIMIT_LOCK = threading.Lock()
_REMOTE_AUTH_RATE_LIMIT: Dict[str, list[float]] = {}



_APP_SERVER_HELPER_FUNCTIONS = {
    _app_server_voice_helpers: ('_capture_runtime_status', '_capture_screen_snapshot', '_voice_runtime_status', '_preload_hebrew_voice_models', '_preload_tts_engine', '_runtime_env_file_path', '_write_runtime_env_values', '_remove_runtime_env_values', '_restore_env_value', '_configure_tts_backend', '_normalize_stt_backend', '_configure_stt_backend', '_new_voice_draft_state', '_jarvis_fast_final_enabled', '_jarvis_pending_wait_seconds', '_synthesize_assistant_audio_sync', '_run_app_chat_turn_lazy', '_try_start_manager_review_turn', '_is_active_steering_request', '_set_startup_state', '_record_runtime_error', '_chat_turn_failure_payload', '_record_chat_turn_failure', '_is_expected_websocket_close_error',),
    _app_server_realtime: ('_send_realtime_event', '_dependency_status', '_production_mode_enabled', '_secret', '_debug_error_responses_enabled', '_format_verbose_tool_event', '_format_runtime_log_entry', '_format_thinking_for_app', '_normalize_search_text', '_project_name_from_path', '_safe_datetime_value', '_session_file_signature', '_name_match_reason', '_build_message_snippet', '_user_session_search_cache', '_load_session_search_entry', '_search_sessions_in_manager', '_sync_event_to_realtime_event', '_resolve_external_current_session_id',),
    _app_server_remote_ws: ('_handle_remote_desktop_ws',),
    _app_server_auth: ('_sign', '_get_auth_store', '_get_remote_control_store', '_bearer_token_from_header', '_remote_auth_rate_limit_key', '_remote_auth_rate_limit_keys', '_check_remote_auth_rate_limit', '_record_remote_auth_rate_limit_attempt', '_remote_ws_auth_rate_limit_keys', '_empty_sidebar_state', '_sidebar_state_path', '_read_local_sidebar_state', '_write_local_sidebar_state', '_auth_debug_enabled', '_token_hash_prefix', '_log_invalid_token_debug', '_resolve_token', '_resolve_ws_token', '_remote_ws_session_is_active', '_remote_desktop_connection_session_is_active', '_mark_remote_desktop_offline', '_mark_remote_desktop_offline_if_no_live_connection', '_command_error_implies_desktop_unavailable', '_disconnect_remote_desktops_for_user', '_disconnect_remote_desktop_for_session', '_ensure_remote_ws_session_active', '_close_remote_ws_protocol_error', '_receive_remote_ws_text', '_remote_ws_json_object', '_websocket_origin_allowed', '_ensure_websocket_origin_allowed', '_resolve_ws_token_or_close',),
    _app_server_remote_ops: ('_bridge_for_user', '_timeline_event_is_user_visible', '_runtime_message_is_user_visible', '_run_workspace_git_command', '_workspace_git_empty_state', '_workspace_git_state', '_workspace_git_checkout', '_path_signature', '_is_remote_session_auth', '_is_remote_desktop_session_auth', '_remote_shared_state', '_remote_current_session_id', '_fleet_task_target_session_id', '_publish_fleet_delta', '_publish_confirmation_delta', '_consume_approved_confirmation', '_remote_profile_view', '_remote_session_summary_views', '_remote_session_detail_view', '_remote_wait_for_sync_version', '_remote_desktop_id_for_command', '_machine_id_for_workspace_binding', '_sync_session_workspace_binding', '_mirror_session_snapshot', '_mirror_session_snapshot_later', '_workspace_id_for_task_request', '_workspace_binding_blocker_for_task', '_remote_dispatch_command', '_remote_request_desktop_command', '_try_dispatch_fleet_worker_task', '_try_dispatch_next_fleet_worker_task', '_try_stop_fleet_worker_task', '_fleet_active_task_for_worker', '_stop_fleet_worker_active_task',),
    _app_server_agent_runtime: ('_workspace_root', '_default_user_id', '_get_security_manager', '_telegram_allowed_user_ids', '_sleep_mode_session_label', '_sleep_mode_notice_text', '_notify_sleep_mode_enabled', '_resolve_target_session_id', '_require_explicit_agent_session_id', '_load_runtime_session_or_409', '_current_headless_mode', '_model_groups', '_missing_provider_api_key_payload', '_estimate_message_tokens', '_rough_message_tokens', '_active_tool_packs_for_context_usage', '_tool_definition_name_for_usage', '_merge_tool_definitions_for_usage', '_context_usage_tool_schema_tokens', '_context_usage_prompt_messages', '_context_usage', '_history_preview', '_pending_files', '_memory_summary', '_analytics_summary', '_security_summary', '_config_preview', '_agent_overview', '_coerce_config_value', '_resolve_workspace_path', '_set_workspace', '_configure_runtime', '_publish_runtime_config_sync', '_active_task_agents', '_stop_runtime_execution', '_prepare_runtime_restart', '_ensure_background_runtime', '_skill_items', '_cors_allow_origins',),
    _app_server_proactive: ('_install_proactive_event_store_callback', '_restore_scheduler_job_from_durable', '_queue_manager_review_for_event_run', '_dispatch_claimed_event_run', '_event_run_reconciler', '_start_proactive_runtime_services', '_stop_proactive_runtime_services',),
}
_APP_SERVER_ROUTE_MODULES = (
    _app_server_routes_fleet,
    _app_server_routes_agent,
    _app_server_routes_sessions,
    _app_server_routes_events,
    _app_server_routes_screen_ws,
    _app_server_routes_voice_ws,
)
_APP_SERVER_MODULES = tuple(_APP_SERVER_HELPER_FUNCTIONS) + _APP_SERVER_ROUTE_MODULES


def _app_server_function_delegate(name: str):
    def _delegate(*args, **kwargs):
        return globals()[name](*args, **kwargs)

    return _delegate


def _sync_app_server_modules() -> None:
    facade_globals = globals()
    for module in _APP_SERVER_MODULES:
        module_globals = module.__dict__
        for name, value in list(facade_globals.items()):
            if name.startswith("__"):
                continue
            if inspect.isfunction(value):
                module_globals[name] = _app_server_function_delegate(name)
            else:
                module_globals[name] = value


def _bind_app_server_helper(module: Any, name: str):
    target = getattr(module, name)
    if inspect.iscoroutinefunction(target):
        @functools.wraps(target)
        async def _async_wrapper(*args, **kwargs):
            _sync_app_server_modules()
            return await target(*args, **kwargs)

        return _async_wrapper

    @functools.wraps(target)
    def _wrapper(*args, **kwargs):
        _sync_app_server_modules()
        return target(*args, **kwargs)

    return _wrapper


for _module, _names in _APP_SERVER_HELPER_FUNCTIONS.items():
    for _name in _names:
        globals()[_name] = _bind_app_server_helper(_module, _name)


def _get_auth_store() -> AppAuthStore:
    global _auth_store
    if _auth_store is None:
        _auth_store = AppAuthStore()
    return _auth_store


def _get_remote_control_store() -> RemoteControlPlaneStore:
    global _remote_control_store
    if _remote_control_store is None:
        _remote_control_store = RemoteControlPlaneStore()
    return _remote_control_store


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


_sync_app_server_modules()

@asynccontextmanager
async def _app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    await _start_proactive_runtime_services(app)
    try:
        yield
    finally:
        await get_local_fleet_runtime().shutdown()
        await _stop_proactive_runtime_services(app)


def create_app() -> FastAPI:
    _sync_app_server_modules()
    _install_proactive_event_store_callback()
    app = FastAPI(title="EmploAI App Backend", version="0.1.0", lifespan=_app_lifespan)
    cloud_routes_enabled = False
    mobile_routes_enabled = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allow_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(
        create_app_files_router(
            AppFilesRouterDeps(
                resolve_token=_resolve_token,
                is_remote_session_auth=_is_remote_session_auth,
                bridge_for_user=_bridge_for_user,
                load_runtime_session_or_409=_load_runtime_session_or_409,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    app.include_router(
        create_app_confirmations_router(
            AppConfirmationsRouterDeps(
                resolve_token=_resolve_token,
                get_store=_get_remote_control_store,
                publish_confirmation_delta=_publish_confirmation_delta,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    app.include_router(
        create_app_recovery_router(
            AppRecoveryRouterDeps(
                resolve_token=_resolve_token,
                is_remote_session_auth=_is_remote_session_auth,
                get_store=_get_remote_control_store,
                bridge_for_user=_bridge_for_user,
                sync_session_workspace_binding=_sync_session_workspace_binding,
                consume_approved_confirmation=_consume_approved_confirmation,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    app.include_router(
        create_app_workspace_router(
            AppWorkspaceRouterDeps(
                resolve_token=_resolve_token,
                is_remote_session_auth=_is_remote_session_auth,
                workspace_git_state=_workspace_git_state,
                workspace_git_checkout=_workspace_git_checkout,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    app.include_router(
        create_app_telegram_bots_router(
            AppTelegramBotsRouterDeps(
                resolve_token=_resolve_token,
                is_remote_session_auth=_is_remote_session_auth,
                bridge_for_user=_bridge_for_user,
                remove_runtime_env_values=_remove_runtime_env_values,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    app.include_router(
        create_app_session_settings_router(
            AppSessionSettingsRouterDeps(
                resolve_token=_resolve_token,
                is_remote_session_auth=_is_remote_session_auth,
                bridge_for_user=_bridge_for_user,
                consume_approved_confirmation=_consume_approved_confirmation,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    app.include_router(
        create_app_onboarding_router(
            AppOnboardingRouterDeps(
                resolve_token=_resolve_token,
                is_remote_session_auth=_is_remote_session_auth,
                bridge_for_user=_bridge_for_user,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    app.include_router(
        create_app_sessions_router(
            AppSessionsRouterDeps(
                resolve_token=_resolve_token,
                is_remote_session_auth=_is_remote_session_auth,
                bridge_for_user=_bridge_for_user,
                remote_session_summary_views=_remote_session_summary_views,
                remote_session_detail_view=_remote_session_detail_view,
                remote_shared_state=_remote_shared_state,
                search_sessions_in_manager=_search_sessions_in_manager,
                mirror_session_snapshot=_mirror_session_snapshot,
                check_rate_limit=_check_remote_auth_rate_limit,
                rate_limit_max_attempts=REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            )
        )
    )
    @app.middleware("http")
    async def log_http_requests(request: Request, call_next):
        started_at = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > REMOTE_HTTP_PROXY_MAX_BODY_BYTES:
                        response = JSONResponse(
                            status_code=413,
                            content={"detail": "Request body is too large"},
                        )
                        duration_ms = int((time.perf_counter() - started_at) * 1000)
                        logger.info(
                            "[app] %s %s from %s -> %s (%sms)",
                            request.method,
                            request.url.path,
                            client_host,
                            response.status_code,
                            duration_ms,
                        )
                        return response
                except ValueError:
                    pass
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.exception("[app] %s %s from %s failed after %sms", request.method, request.url.path, client_host, duration_ms)
            _record_runtime_error(
                f"{request.method} {request.url.path} failed",
                traceback.format_exc(),
            )
            raise

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "geolocation=()")
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("[app] %s %s from %s -> %s (%sms)", request.method, request.url.path, client_host, response.status_code, duration_ms)
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):  # type: ignore[override]
        detail = traceback.format_exc()
        request_error_id = str(request.headers.get("x-request-id") or "").strip()[:128]
        error_id = request_error_id or secrets.token_urlsafe(12)
        _record_runtime_error(
            f"{request.method} {request.url.path} crashed: {type(exc).__name__}: {exc}",
            detail,
        )
        if _debug_error_responses_enabled():
            content = {
                "detail": f"{type(exc).__name__}: {exc}",
                "traceback": detail,
                "error_id": error_id,
            }
        else:
            content = {
                "detail": "Internal server error",
                "error_id": error_id,
            }
        return JSONResponse(
            status_code=500,
            content=content,
            headers={"X-EmploAI-Error-Id": error_id},
        )

    @app.get("/api/app/health")
    async def health(shallow: bool = False) -> dict:
        config = get_live_config(_workspace_root() / "config.json")
        forced_app_server = os.getenv("EMPLOAI_DESKTOP_FORCE_APP_SERVER", "").strip().lower() in {"1", "true", "yes", "on"}
        current_runtime_home = runtime_home()
        payload = {
            "ok": True,
            "channel": "app",
            "process_id": os.getpid(),
            "runtime_home": str(current_runtime_home) if current_runtime_home is not None else None,
            "enabled": bool(forced_app_server or config.get("channels.app.enabled", False)),
            "steering_beta_enabled": bool(
                os.getenv("EMPLO_APP_STEERING_BETA_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
                or config.get("channels.app.steering_beta", False)
            ),
            "startup_state": _APP_RUNTIME_STATUS["startup_state"],
            "startup_error": _APP_RUNTIME_STATUS["startup_error"],
            "startup_error_detail": _APP_RUNTIME_STATUS["startup_error_detail"],
            "last_runtime_error": _APP_RUNTIME_STATUS["last_runtime_error"],
            "last_runtime_error_detail": _APP_RUNTIME_STATUS["last_runtime_error_detail"],
            "last_runtime_error_at": _APP_RUNTIME_STATUS["last_runtime_error_at"],
            "readiness_scope": "app_api" if shallow else "full",
            "remote_control_routing": remote_control_routing_status(),
            "standalone_desktop_enabled": standalone_desktop_enabled(),
            "cloud_backend_enabled": cloud_routes_enabled,
            "mobile_connection_enabled": mobile_routes_enabled,
        }
        if shallow:
            return payload
        payload["dependency_status"] = _dependency_status()
        return payload


    _sync_app_server_modules()
    _app_server_routes_fleet.register_fleet_routes(app)
    _app_server_routes_agent.register_agent_routes(app)
    _app_server_routes_sessions.register_session_routes(app)
    _app_server_routes_events.register_event_routes(app)
    _app_server_routes_screen_ws.register_screen_ws_routes(app)
    _app_server_routes_voice_ws.register_voice_ws_routes(app)
    return app

def start_embedded_app_server_if_enabled(*, force: bool = False) -> None:
    global _server_thread, _server_started
    if _server_started:
        return

    workspace = _workspace_root()
    config = get_live_config(workspace / "config.json")
    if not force and not bool(config.get("channels.app.enabled", False)):
        return

    host = str(config.get("channels.app.host", "0.0.0.0"))
    port = int(config.get("channels.app.port", 8787))
    _set_startup_state("starting")

    def _run() -> None:
        try:
            import uvicorn

            _set_startup_state("ready")
            uvicorn.run(
                create_app(),
                host=host,
                port=port,
                log_level="warning",
                access_log=False,
                loop="asyncio",
                http="h11",
                ws="websockets",
            )
        except Exception as exc:
            detail = traceback.format_exc()
            logger.exception("[app] embedded app server failed to start")
            _set_startup_state(
                "error",
                error=f"Embedded app server failed to start: {exc}",
                detail=detail,
            )

    _server_thread = threading.Thread(target=_run, name="emploai-app-server", daemon=True)
    _server_thread.start()
    _server_started = True
