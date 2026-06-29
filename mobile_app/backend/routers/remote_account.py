from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from mobile_app.backend.models import (
    RemoteAccountCloudProfileRequest,
    RemoteAccountCloudProfileResponse,
    RemoteAccountDataDeleteResponse,
    RemoteAccountProfile,
    RemoteAccountSecretDeleteResponse,
    RemoteAccountSecretItem,
    RemoteAccountSecretsListResponse,
    RemoteAccountSecretsRevealRequest,
    RemoteAccountSecretsRevealResponse,
    RemoteAccountSecretsUpsertRequest,
    RemoteDesktopView,
    RemoteMobileView,
    RemoteUserView,
)


@dataclass(frozen=True)
class RemoteAccountRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    get_store: Callable[[], Any]
    remote_shared_state: Callable[[Dict[str, Any]], Dict[str, Any]]
    check_rate_limit: Callable[..., None]
    consume_approved_confirmation: Callable[..., None]
    disconnect_remote_desktops_for_user: Callable[..., Awaitable[int]]


def create_remote_account_router(deps: RemoteAccountRouterDeps) -> APIRouter:
    router = APIRouter(tags=["remote-account"])

    def _require_remote_account(authorization: Optional[str], *, detail: str) -> Dict[str, Any]:
        auth = dict(deps.resolve_token(authorization))
        if not deps.is_remote_session_auth(auth):
            raise HTTPException(status_code=403, detail=detail)
        return auth

    @router.get("/api/remote/account/me", response_model=RemoteAccountProfile)
    async def remote_account_me(authorization: Optional[str] = Header(default=None)) -> RemoteAccountProfile:
        auth = _require_remote_account(authorization, detail="Remote account access requires a remote session token")
        store = deps.get_store()
        user = store.get_user(int(auth["user_id"]))
        if not user:
            raise HTTPException(status_code=404, detail="Unknown account")
        desktops = store.list_desktops(user_id=int(auth["user_id"]))
        desktop = None
        if auth.get("desktop_id"):
            for item in desktops:
                if str(item.get("desktop_id") or "") == str(auth.get("desktop_id") or ""):
                    desktop = item
                    break
        mobile = None
        if auth.get("mobile_id"):
            mobile = {
                "mobile_id": auth.get("mobile_id"),
                "device_name": auth.get("device_name"),
                "device_platform": auth.get("device_platform"),
                "paired_desktop_id": store.paired_desktop_id_for_payload(auth),
                "created_at": None,
                "last_used_at": None,
            }
        return RemoteAccountProfile(
            user=RemoteUserView.model_validate(user),
            actor_kind=str(auth.get("actor_kind") or "mobile"),
            desktop=RemoteDesktopView.model_validate(desktop) if desktop else None,
            mobile=RemoteMobileView.model_validate(mobile) if mobile else None,
            profile=store.get_user_profile(user_id=int(auth["user_id"])),
            shared_state=deps.remote_shared_state(auth),
        )

    @router.get("/api/remote/account/profile", response_model=RemoteAccountCloudProfileResponse)
    async def remote_account_profile(authorization: Optional[str] = Header(default=None)) -> RemoteAccountCloudProfileResponse:
        auth = _require_remote_account(authorization, detail="Remote account profile access requires a remote session token")
        return RemoteAccountCloudProfileResponse(
            profile=deps.get_store().get_user_profile(user_id=int(auth["user_id"])),
        )

    @router.put("/api/remote/account/profile", response_model=RemoteAccountCloudProfileResponse)
    async def put_remote_account_profile(
        request: RemoteAccountCloudProfileRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> RemoteAccountCloudProfileResponse:
        auth = _require_remote_account(authorization, detail="Remote account profile updates require a remote session token")
        try:
            profile = deps.get_store().update_user_profile(
                user_id=int(auth["user_id"]),
                profile=request.profile,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown account") from exc
        return RemoteAccountCloudProfileResponse(profile=profile)

    @router.get("/api/remote/account/secrets", response_model=RemoteAccountSecretsListResponse)
    async def remote_account_secrets(
        namespace: Optional[str] = None,
        authorization: Optional[str] = Header(default=None),
    ) -> RemoteAccountSecretsListResponse:
        auth = _require_remote_account(authorization, detail="Remote account secrets require a remote session token")
        try:
            items = deps.get_store().list_user_secrets(
                user_id=int(auth["user_id"]),
                namespace=namespace,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RemoteAccountSecretsListResponse(items=[RemoteAccountSecretItem.model_validate(item) for item in items])

    @router.put("/api/remote/account/secrets", response_model=RemoteAccountSecretsListResponse)
    async def put_remote_account_secrets(
        request: RemoteAccountSecretsUpsertRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> RemoteAccountSecretsListResponse:
        auth = _require_remote_account(authorization, detail="Remote account secret updates require a remote session token")
        deps.check_rate_limit(http_request, email=str(auth["user_id"]), action="account_secrets_update")
        try:
            store = deps.get_store()
            store.upsert_user_secrets(
                user_id=int(auth["user_id"]),
                namespace=request.namespace,
                secrets_payload=request.secrets,
                metadata=request.metadata,
            )
            items = store.list_user_secrets(
                user_id=int(auth["user_id"]),
                namespace=request.namespace,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown account") from exc
        return RemoteAccountSecretsListResponse(items=[RemoteAccountSecretItem.model_validate(item) for item in items])

    @router.post("/api/remote/account/secrets/reveal", response_model=RemoteAccountSecretsRevealResponse)
    async def reveal_remote_account_secrets(
        request: RemoteAccountSecretsRevealRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
        x_emploai_manual_secret_reveal: Optional[str] = Header(default=None),
    ) -> RemoteAccountSecretsRevealResponse:
        auth = dict(deps.resolve_token(authorization))
        if not deps.is_remote_session_auth(auth) or str(auth.get("actor_kind") or "") != "desktop":
            raise HTTPException(status_code=403, detail="Secret reveal requires a signed-in desktop session")
        deps.check_rate_limit(http_request, email=str(auth["user_id"]), action="account_secrets_reveal")
        if str(x_emploai_manual_secret_reveal or "").strip().lower() not in {"1", "true", "yes"}:
            raise HTTPException(status_code=403, detail="Secret reveal is manual UI-only")
        try:
            secrets_payload = deps.get_store().reveal_user_secrets(
                user_id=int(auth["user_id"]),
                namespace=request.namespace,
                names=request.names,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RemoteAccountSecretsRevealResponse(namespace=request.namespace, secrets=secrets_payload)

    @router.delete("/api/remote/account/secrets/{namespace}/{name}", response_model=RemoteAccountSecretDeleteResponse)
    async def delete_remote_account_secret(
        namespace: str,
        name: str,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),
    ) -> RemoteAccountSecretDeleteResponse:
        auth = _require_remote_account(authorization, detail="Remote account secret deletion requires a remote session token")
        deps.check_rate_limit(http_request, email=str(auth["user_id"]), action="account_secrets_delete")
        deps.consume_approved_confirmation(
            user_id=int(auth["user_id"]),
            confirmation_id=confirmation_id,
            action_kind="remote_secret_delete",
            executed_by_surface=str(auth.get("actor_kind") or "app"),
            metadata={"namespace": namespace, "name": name},
        )
        try:
            deleted = deps.get_store().delete_user_secret(
                user_id=int(auth["user_id"]),
                namespace=namespace,
                name=name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RemoteAccountSecretDeleteResponse(deleted=deleted)

    @router.delete("/api/remote/account/data", response_model=RemoteAccountDataDeleteResponse)
    async def delete_remote_account_data(
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),
    ) -> RemoteAccountDataDeleteResponse:
        auth = _require_remote_account(authorization, detail="Remote account data deletion requires a remote session token")
        deps.check_rate_limit(http_request, email=str(auth["user_id"]), action="account_data_delete")
        deps.consume_approved_confirmation(
            user_id=int(auth["user_id"]),
            confirmation_id=confirmation_id,
            action_kind="remote_account_data_delete",
            executed_by_surface=str(auth.get("actor_kind") or "app"),
        )
        try:
            result = deps.get_store().delete_user_account_data(
                user_id=int(auth["user_id"]),
                preserve_session_token_hash=str(auth.get("session_token_hash") or "").strip() or None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown account") from exc
        result["disconnected_desktops"] = await deps.disconnect_remote_desktops_for_user(
            int(auth["user_id"]),
            reason="The account data was reset",
        )
        return RemoteAccountDataDeleteResponse(**result)

    return router
