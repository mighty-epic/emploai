from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from mobile_app.backend.models import (
    RemoteDesktopView,
    RemoteMobileView,
    RemotePairCompleteRequest,
    RemotePairCompleteResponse,
    RemotePairStartRequest,
    RemotePairStartResponse,
)


@dataclass(frozen=True)
class RemotePairingRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    get_store: Callable[[], Any]
    check_rate_limit: Callable[..., None]
    remote_pairing_rate_limit_max_attempts: int
    remote_pairing_ttl_seconds: int


def create_remote_pairing_router(deps: RemotePairingRouterDeps) -> APIRouter:
    router = APIRouter(tags=["remote-pairing"])

    @router.get("/api/remote/desktops", response_model=list[RemoteDesktopView])
    async def remote_list_desktops(authorization: Optional[str] = Header(default=None)) -> list[RemoteDesktopView]:
        auth = dict(deps.resolve_token(authorization))
        if not deps.is_remote_session_auth(auth):
            raise HTTPException(status_code=403, detail="Remote desktop access requires a remote session token")
        items = deps.get_store().list_desktops(user_id=int(auth["user_id"]))
        return [RemoteDesktopView.model_validate(item) for item in items]

    @router.post("/api/remote/pair/start", response_model=RemotePairStartResponse)
    async def remote_pair_start(
        request: RemotePairStartRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> RemotePairStartResponse:
        auth = dict(deps.resolve_token(authorization))
        if not deps.is_remote_session_auth(auth) or str(auth.get("actor_kind") or "") != "desktop":
            raise HTTPException(status_code=403, detail="Desktop login required to start pairing")
        deps.check_rate_limit(
            http_request,
            email=str(auth["user_id"]),
            action="remote_pair_start",
            max_attempts=deps.remote_pairing_rate_limit_max_attempts,
        )
        desktop_id = str(request.desktop_id or auth.get("desktop_id") or "").strip()
        if not desktop_id:
            raise HTTPException(status_code=400, detail="No desktop is available for pairing")
        try:
            pairing = deps.get_store().create_pairing(
                user_id=int(auth["user_id"]),
                desktop_id=desktop_id,
                ttl_seconds=deps.remote_pairing_ttl_seconds,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown desktop") from exc
        return RemotePairStartResponse.model_validate(pairing)

    @router.post("/api/remote/pair/complete", response_model=RemotePairCompleteResponse)
    async def remote_pair_complete(
        request: RemotePairCompleteRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> RemotePairCompleteResponse:
        auth = dict(deps.resolve_token(authorization))
        if not deps.is_remote_session_auth(auth) or str(auth.get("actor_kind") or "") != "mobile":
            raise HTTPException(status_code=403, detail="Mobile login required to complete pairing")
        mobile_id = str(auth.get("mobile_id") or "").strip()
        if not mobile_id:
            raise HTTPException(status_code=400, detail="Mobile device is unavailable")
        deps.check_rate_limit(
            http_request,
            email=str(auth["user_id"]),
            action="remote_pair_complete",
            max_attempts=deps.remote_pairing_rate_limit_max_attempts,
        )
        try:
            result = deps.get_store().complete_pairing(
                user_id=int(auth["user_id"]),
                pairing_token=request.pairing_token,
                mobile_id=mobile_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown pairing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RemotePairCompleteResponse(
            desktop=RemoteDesktopView.model_validate(result["desktop"]),
            mobile=RemoteMobileView.model_validate(result["mobile"]),
            shared_state=result.get("shared_state") or {},
        )

    return router
