from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from mobile_app.backend.models import (
    FleetCompleteEnrollmentRequest,
    FleetCompleteEnrollmentResponse,
    FleetCreateEnrollmentRequest,
    FleetCreateEnrollmentResponse,
    FleetWorkerView,
    RemoteDesktopView,
    RemoteUserView,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FleetEnrollmentRouterDeps:
    require_fleet_manager_auth: Callable[[Optional[str]], Dict[str, Any]]
    get_store: Callable[[], Any]
    publish_fleet_delta: Callable[..., None]
    check_rate_limit: Callable[..., None]
    remote_auth_rate_limit_max_attempts: int
    remote_session_ttl_seconds: int


def create_fleet_enrollment_router(deps: FleetEnrollmentRouterDeps) -> APIRouter:
    router = APIRouter(tags=["fleet-enrollment"])

    @router.post("/api/fleet/enrollments", response_model=FleetCreateEnrollmentResponse)
    async def fleet_create_enrollment(
        request: FleetCreateEnrollmentRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> FleetCreateEnrollmentResponse:
        auth = deps.require_fleet_manager_auth(authorization)
        deps.check_rate_limit(
            http_request,
            email=str(auth["user_id"]),
            action="fleet_enrollment_create",
            max_attempts=deps.remote_auth_rate_limit_max_attempts,
        )
        try:
            enrollment = deps.get_store().create_worker_enrollment(
                user_id=int(auth["user_id"]),
                desktop_id=str(auth["desktop_id"]),
                display_name=request.display_name,
                ttl_seconds=request.expires_in_seconds or 60 * 30,
                metadata=request.metadata,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        deps.publish_fleet_delta(
            user_id=int(auth["user_id"]),
            event_type="fleet_audit_event",
            payload={"enrollment": enrollment, "reason": "worker_enrollment_created"},
            origin_channel=str(auth.get("actor_kind") or "app"),
        )
        return FleetCreateEnrollmentResponse.model_validate(enrollment)

    @router.post("/api/fleet/enrollments/complete", response_model=FleetCompleteEnrollmentResponse)
    async def fleet_complete_enrollment(
        request: FleetCompleteEnrollmentRequest,
        http_request: Request,
    ) -> FleetCompleteEnrollmentResponse:
        deps.check_rate_limit(
            http_request,
            email=request.enrollment_token[:128],
            action="fleet_enrollment_complete",
            max_attempts=deps.remote_auth_rate_limit_max_attempts,
        )
        try:
            result = deps.get_store().complete_worker_enrollment(
                enrollment_token=request.enrollment_token,
                device_name=request.device_name,
                device_platform=request.device_platform,
                device_key=request.device_key,
                token_ttl_seconds=deps.remote_session_ttl_seconds,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown worker enrollment") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        expires_at = float(result.get("expires_at") or time.time())
        try:
            deps.publish_fleet_delta(
                user_id=int(result["user"]["user_id"]),
                event_type="fleet_worker_presence",
                payload={"worker": result.get("worker"), "reason": "enrolled"},
                origin_channel="worker",
            )
        except Exception:
            logger.exception("[fleet] failed publishing worker enrollment delta")
        return FleetCompleteEnrollmentResponse(
            session_token=str(result["session_token"]),
            expires_in_seconds=max(0, int(expires_at - time.time())),
            user=RemoteUserView.model_validate(result["user"]),
            desktop=RemoteDesktopView.model_validate(result["desktop"]),
            worker=FleetWorkerView.model_validate(result["worker"]),
        )

    return router
