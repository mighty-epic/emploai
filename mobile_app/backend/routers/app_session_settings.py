from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from mobile_app.backend.models import (
    SessionBotAssignmentRequest,
    SessionDetailView,
    SessionHeadlessEligibilityRequest,
    SessionSecurityPermissionRequest,
    ToolPackUpdateRequest,
)


@dataclass(frozen=True)
class AppSessionSettingsRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    bridge_for_user: Callable[[int], Any]
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
        session = bridge.update_session_tool_packs(session_id, request.enabled_tool_packs)
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
        if str(request.security_permission_mode or "").strip().lower() == "full_permissions":
            deps.consume_approved_confirmation(
                user_id=int(auth["user_id"]),
                confirmation_id=confirmation_id,
                action_kind="session_full_permissions",
                executed_by_surface=str(auth.get("actor_kind") or "app"),
                metadata={"session_id": session_id},
            )
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        session = bridge.update_session_security_permission_mode(session_id, request.security_permission_mode)
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
