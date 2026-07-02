from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app_backend.models import DeviceActionResponse, TrustedDeviceView


@dataclass(frozen=True)
class AppDevicesRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    get_auth_store: Callable[[], Any]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_devices_router(deps: AppDevicesRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-devices"])

    @router.get("/api/app/devices", response_model=list[TrustedDeviceView])
    async def list_devices(authorization: Optional[str] = Header(default=None)) -> list[TrustedDeviceView]:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(deps, auth)
        user_id = int(auth["user_id"])
        return [TrustedDeviceView(**item) for item in deps.get_auth_store().list_devices(user_id=user_id)]

    @router.post("/api/app/devices/{device_id}/revoke", response_model=DeviceActionResponse)
    async def revoke_device(
        device_id: str,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> DeviceActionResponse:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(deps, auth)
        user_id = int(auth["user_id"])
        deps.check_rate_limit(
            http_request,
            email=str(user_id),
            action="app_device_revoke",
            max_attempts=deps.rate_limit_max_attempts,
        )
        if not deps.get_auth_store().revoke_device(user_id=user_id, device_id=device_id):
            raise HTTPException(status_code=404, detail="Device not found")
        return DeviceActionResponse(device_id=device_id, action="revoke")

    return router


def _ensure_local_app_backend(deps: AppDevicesRouterDeps, auth: Dict[str, Any]) -> None:
    if deps.is_remote_session_auth(auth):
        raise HTTPException(status_code=409, detail="Trusted device management must run on the local app backend")
