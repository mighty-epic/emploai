from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app_backend.models import (
    SessionBotAssignmentRequest,
    SessionDetailView,
    SessionHeadlessEligibilityRequest,
    SessionModeActionRequest,
    SessionSecurityPermissionRequest,
    ToolPackUpdateRequest,
)
from app_backend.company_runtime_context import (
    company_record_matches,
    require_company_record,
    selected_company_scope,
)


@dataclass(frozen=True)
class AppSessionSettingsRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    bridge_for_user: Callable[[int], Any]
    get_company_store: Callable[[], Any]
    get_fleet_store: Callable[[], Any]
    update_manager_identity_tool_packs: Callable[..., Dict[str, Any]]
    consume_approved_confirmation: Callable[..., Dict[str, Any]]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_session_settings_router(deps: AppSessionSettingsRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-session-settings"])

    @router.post("/api/app/sessions/{session_id}/tool-packs", response_model=SessionDetailView)
    async def update_session_tool_packs(
        session_id: str,
        request: ToolPackUpdateRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionDetailView:
        auth = _require_local_app_backend(deps, authorization)
        _check_session_setting_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        existing, scope = _require_selected_company_session(deps, auth, bridge, session_id)
        role = str(getattr(existing, "fleet_identity_role", "") or "").strip().lower()
        identity_id = str(getattr(existing, "fleet_identity_id", "") or "").strip()
        requested_packs = list(request.enabled_tool_packs or [])
        if role == "manager" and identity_id:
            identity = deps.update_manager_identity_tool_packs(
                user_id=int(auth["user_id"]),
                identity_id=identity_id,
                enabled_tool_packs=requested_packs,
                source="local_chat",
            )
            requested_packs = list(identity.get("enabled_tool_packs") or [])
            for candidate in bridge.list_sessions():
                if not company_record_matches(
                    candidate,
                    company_id=scope.get("company_id"),
                    include_legacy=bool(scope.get("include_legacy")),
                ):
                    continue
                candidate_role = str(getattr(candidate, "fleet_identity_role", "") or "").strip().lower()
                candidate_identity_id = str(getattr(candidate, "fleet_identity_id", "") or "").strip()
                if candidate_role != "manager" or candidate_identity_id not in {"", identity_id}:
                    continue
                bridge.update_session_tool_packs(str(candidate.id), requested_packs)
            session = bridge.get_session(session_id)
        else:
            session = bridge.update_session_tool_packs(session_id, requested_packs)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @router.post("/api/app/sessions/{session_id}/telegram-bot", response_model=SessionDetailView)
    async def update_session_telegram_bot(
        session_id: str,
        request: SessionBotAssignmentRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionDetailView:
        auth = _require_local_app_backend(deps, authorization)
        _check_session_setting_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        _require_selected_company_session(deps, auth, bridge, session_id)
        try:
            session = bridge.update_session_telegram_bot_config(session_id, request.telegram_bot_config_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Telegram bot config not found") from exc
        return SessionDetailView(**bridge.detailed_session_view(session))

    @router.post("/api/app/sessions/{session_id}/headless-eligibility", response_model=SessionDetailView)
    async def update_session_headless_eligibility(
        session_id: str,
        request: SessionHeadlessEligibilityRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionDetailView:
        auth = _require_local_app_backend(deps, authorization)
        _check_session_setting_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        _require_selected_company_session(deps, auth, bridge, session_id)
        session = bridge.update_session_headless_eligible(session_id, request.headless_eligible)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @router.post("/api/app/sessions/{session_id}/security-permission-mode", response_model=SessionDetailView)
    async def update_session_security_permission_mode(
        session_id: str,
        request: SessionSecurityPermissionRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),
    ) -> SessionDetailView:
        auth = _require_local_app_backend(deps, authorization)
        _check_session_setting_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        _require_selected_company_session(deps, auth, bridge, session_id)
        if str(request.security_permission_mode or "").strip().lower() == "full_permissions":
            deps.consume_approved_confirmation(
                user_id=int(auth["user_id"]),
                confirmation_id=confirmation_id,
                action_kind="session_full_permissions",
                executed_by_surface=str(auth.get("actor_kind") or "app"),
                metadata={"session_id": session_id},
            )
        session = bridge.update_session_security_permission_mode(session_id, request.security_permission_mode)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @router.post("/api/app/sessions/{session_id}/mode", response_model=SessionDetailView)
    async def update_session_mode_state(
        session_id: str,
        request: SessionModeActionRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionDetailView:
        auth = _require_local_app_backend(deps, authorization)
        _check_session_setting_rate_limit(deps, http_request, auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        _require_selected_company_session(deps, auth, bridge, session_id)
        try:
            session = bridge.update_session_mode_state(session_id, request.action, request.reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SessionDetailView(**bridge.detailed_session_view(session))

    return router


def _require_local_app_backend(
    deps: AppSessionSettingsRouterDeps,
    authorization: Optional[str],
) -> Dict[str, Any]:
    auth = dict(deps.resolve_token(authorization))
    if deps.is_remote_session_auth(auth):
        raise HTTPException(status_code=409, detail="Session settings must run on the local desktop backend")
    return auth


def _check_session_setting_rate_limit(
    deps: AppSessionSettingsRouterDeps,
    http_request: Request,
    auth: Dict[str, Any],
) -> None:
    deps.check_rate_limit(
        http_request,
        email=str(auth["user_id"]),
        action="session_settings_update",
        max_attempts=deps.rate_limit_max_attempts,
    )


def _require_selected_company_session(
    deps: AppSessionSettingsRouterDeps,
    auth: Dict[str, Any],
    bridge: Any,
    session_id: str,
) -> tuple[Any, Dict[str, Any]]:
    try:
        session = bridge.get_session(session_id)
        scope = selected_company_scope(
            auth=auth,
            company_store=deps.get_company_store(),
            fleet_store=deps.get_fleet_store(),
        )
        require_company_record(
            session,
            company_id=scope.get("company_id"),
            include_legacy=bool(scope.get("include_legacy")),
            message="Session not found in the selected company",
        )
        return session, scope
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
