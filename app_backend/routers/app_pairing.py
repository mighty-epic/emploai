from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app_backend.models import (
    DevicePairCompleteRequest,
    DevicePairCompleteResponse,
    DevicePairStartRequest,
    DevicePairStartResponse,
)


@dataclass(frozen=True)
class AppPairingRouterDeps:
    authorize_pair_start: Callable[[Optional[str], Optional[str]], int]
    resolve_pairing_user_id: Callable[[str], int]
    get_auth_store: Callable[[], Any]
    sign: Callable[[str], str]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int
    default_pair_ttl_seconds: int
    token_ttl_seconds: int


def create_app_pairing_router(deps: AppPairingRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-pairing"])

    @router.post("/api/app/pair/start", response_model=DevicePairStartResponse)
    async def pair_start(
        request: DevicePairStartRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
        x_app_pair_secret: Optional[str] = Header(default=None),
    ) -> DevicePairStartResponse:
        deps.check_rate_limit(
            http_request,
            email="legacy_app_pair_start",
            action="app_pair_start",
            max_attempts=deps.rate_limit_max_attempts,
        )
        created_by_user = deps.authorize_pair_start(authorization, x_app_pair_secret)
        record = deps.get_auth_store().create_pairing(
            device_name=request.device_name,
            created_by=f"user:{created_by_user}",
            ttl_seconds=deps.default_pair_ttl_seconds,
        )
        pairing_id = str(record["pairing_id"])
        issued_at = int(record["issued_at"])
        payload = f"{pairing_id}:{issued_at}"
        token = f"{payload}:{deps.sign(payload)}"
        return DevicePairStartResponse(
            pairing_id=pairing_id,
            pairing_token=token,
            expires_in_seconds=deps.default_pair_ttl_seconds,
        )

    @router.post("/api/app/pair/complete", response_model=DevicePairCompleteResponse)
    async def pair_complete(
        request: DevicePairCompleteRequest,
        http_request: Request,
    ) -> DevicePairCompleteResponse:
        deps.check_rate_limit(
            http_request,
            email=request.pairing_token[:128],
            action="app_pair_complete",
            max_attempts=deps.rate_limit_max_attempts,
        )
        try:
            pairing_id, issued_at, signature = request.pairing_token.split(":", 2)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Malformed pairing token") from exc
        payload = f"{pairing_id}:{issued_at}"
        if not hmac.compare_digest(signature, deps.sign(payload)):
            raise HTTPException(status_code=400, detail="Invalid pairing token")
        user_id = deps.resolve_pairing_user_id(pairing_id)
        try:
            result = deps.get_auth_store().complete_pairing(
                pairing_id=pairing_id,
                user_id=user_id,
                device_name=request.device_name,
                device_platform=request.device_platform,
                token_ttl_seconds=deps.token_ttl_seconds,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown pairing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DevicePairCompleteResponse(
            access_token=result["access_token"],
            device_id=result["device_id"],
            expires_in_seconds=deps.token_ttl_seconds,
        )

    return router
