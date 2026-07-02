from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app_backend.models import (
    ConfirmationCreateRequest,
    ConfirmationDecisionRequest,
    ConfirmationListResponse,
    ConfirmationView,
)


@dataclass(frozen=True)
class AppConfirmationsRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    get_store: Callable[[], Any]
    publish_confirmation_delta: Callable[..., None]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_confirmations_router(deps: AppConfirmationsRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-confirmations"])

    @router.get("/api/app/confirmations", response_model=ConfirmationListResponse)
    async def list_pending_confirmations(authorization: Optional[str] = Header(default=None)) -> ConfirmationListResponse:
        auth = dict(deps.resolve_token(authorization))
        items = deps.get_store().list_pending_confirmations(user_id=int(auth["user_id"]))
        return ConfirmationListResponse(items=[ConfirmationView(**item) for item in items])

    @router.post("/api/app/confirmations", response_model=ConfirmationView)
    async def create_pending_confirmation(
        request: ConfirmationCreateRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> ConfirmationView:
        auth = dict(deps.resolve_token(authorization))
        deps.check_rate_limit(
            http_request,
            email=str(auth["user_id"]),
            action="confirmation_create",
            max_attempts=deps.rate_limit_max_attempts,
        )
        origin_surface = request.origin_surface or str(auth.get("actor_kind") or "app")
        confirmation = deps.get_store().create_confirmation(
            user_id=int(auth["user_id"]),
            action_kind=request.action_kind,
            title=request.title,
            message=request.message,
            risk_tier=request.risk_tier,
            origin_surface=origin_surface,
            origin_identity_id=request.origin_identity_id,
            origin_chat_id=request.origin_chat_id,
            payload=request.payload,
            ttl_seconds=request.ttl_seconds,
        )
        deps.publish_confirmation_delta(
            user_id=int(auth["user_id"]),
            confirmation=confirmation,
            origin_channel=origin_surface,
        )
        return ConfirmationView(**confirmation)

    @router.post("/api/app/confirmations/{confirmation_id}/approve", response_model=ConfirmationView)
    async def approve_pending_confirmation(
        confirmation_id: str,
        request: ConfirmationDecisionRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> ConfirmationView:
        return _decide_pending_confirmation(
            deps,
            confirmation_id=confirmation_id,
            request=request,
            http_request=http_request,
            authorization=authorization,
            approved=True,
        )

    @router.post("/api/app/confirmations/{confirmation_id}/deny", response_model=ConfirmationView)
    async def deny_pending_confirmation(
        confirmation_id: str,
        request: ConfirmationDecisionRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> ConfirmationView:
        return _decide_pending_confirmation(
            deps,
            confirmation_id=confirmation_id,
            request=request,
            http_request=http_request,
            authorization=authorization,
            approved=False,
        )

    return router


def _decide_pending_confirmation(
    deps: AppConfirmationsRouterDeps,
    *,
    confirmation_id: str,
    request: ConfirmationDecisionRequest,
    http_request: Request,
    authorization: Optional[str],
    approved: bool,
) -> ConfirmationView:
    auth = dict(deps.resolve_token(authorization))
    surface = request.decided_by_surface or str(auth.get("actor_kind") or "app")
    deps.check_rate_limit(
        http_request,
        email=str(auth["user_id"]),
        action="confirmation_decide",
        max_attempts=deps.rate_limit_max_attempts,
    )
    try:
        confirmation = deps.get_store().decide_confirmation(
            user_id=int(auth["user_id"]),
            confirmation_id=confirmation_id,
            approved=approved,
            decided_by_surface=surface,
            decided_by_actor=request.decided_by_actor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Confirmation not found") from exc
    deps.publish_confirmation_delta(
        user_id=int(auth["user_id"]),
        confirmation=confirmation,
        origin_channel=surface,
    )
    return ConfirmationView(**confirmation)
