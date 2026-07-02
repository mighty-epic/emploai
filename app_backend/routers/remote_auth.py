from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response

from app_backend.models import (
    RemoteAuthLoginRequest,
    RemoteAuthLoginResponse,
    RemoteAuthLogoutResponse,
    RemoteAuthOtpChallengeResponse,
    RemoteAuthOtpResendRequest,
    RemoteAuthOtpVerifyRequest,
    RemoteAuthRegisterRequest,
    RemoteGoogleAuthPollRequest,
    RemoteGoogleAuthPollResponse,
    RemoteGoogleAuthStartRequest,
    RemoteGoogleAuthStartResponse,
)


@dataclass(frozen=True)
class RemoteAuthRouterDeps:
    check_rate_limit: Callable[..., None]
    get_store: Callable[[], Any]
    send_otp_email: Callable[..., Awaitable[None]]
    invalidate_challenge: Callable[[Dict[str, Any]], None]
    challenge_response: Callable[[Dict[str, Any]], RemoteAuthOtpChallengeResponse]
    login_response_from_result: Callable[..., RemoteAuthLoginResponse]
    google_oauth_configured: Callable[[], bool]
    google_oauth_auth_url: Callable[..., str]
    google_callback_page: Callable[..., Response]
    exchange_google_oauth_code: Callable[[str], Awaitable[Dict[str, Any]]]
    verify_google_id_token: Callable[[str], Dict[str, Any]]
    bearer_token_from_header: Callable[[Optional[str]], str]
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    disconnect_remote_desktop_for_session: Callable[..., Awaitable[bool]]
    remote_auth_rate_limit_max_attempts: int
    remote_auth_poll_rate_limit_max_attempts: int
    google_oauth_request_ttl_seconds: int
    remote_session_ttl_seconds: int


def create_remote_auth_router(deps: RemoteAuthRouterDeps) -> APIRouter:
    router = APIRouter(tags=["remote-auth"])

    @router.post("/api/remote/auth/register", response_model=RemoteAuthOtpChallengeResponse)
    async def remote_register(request: RemoteAuthRegisterRequest, http_request: Request) -> RemoteAuthOtpChallengeResponse:
        deps.check_rate_limit(http_request, email=request.email, action="register")
        challenge: Dict[str, Any] = {}
        try:
            challenge = deps.get_store().begin_signup_otp(
                email=request.email,
                password=request.password,
                display_name=request.display_name,
                actor_kind=request.actor_kind,
                device_name=request.device_name,
                device_platform=request.device_platform,
                device_key=request.device_key,
                remember_me=request.remember_me,
            )
            await deps.send_otp_email(
                email=str(challenge.get("email") or request.email),
                code=str(challenge.get("otp_code") or ""),
                purpose=str(challenge.get("purpose") or "signup_verify"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            deps.invalidate_challenge(challenge)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return deps.challenge_response(challenge)

    @router.post("/api/remote/auth/login", response_model=RemoteAuthOtpChallengeResponse)
    async def remote_login(request: RemoteAuthLoginRequest, http_request: Request) -> RemoteAuthOtpChallengeResponse:
        deps.check_rate_limit(http_request, email=request.email, action=f"login:{request.actor_kind}")
        challenge: Dict[str, Any] = {}
        try:
            challenge = deps.get_store().begin_login_otp(
                email=request.email,
                password=request.password,
                actor_kind=request.actor_kind,
                device_name=request.device_name,
                device_platform=request.device_platform,
                device_key=request.device_key,
                remember_me=request.remember_me,
            )
            await deps.send_otp_email(
                email=str(challenge.get("email") or request.email),
                code=str(challenge.get("otp_code") or ""),
                purpose=str(challenge.get("purpose") or "login_verify"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            deps.invalidate_challenge(challenge)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return deps.challenge_response(challenge)

    @router.post("/api/remote/auth/otp/verify", response_model=RemoteAuthLoginResponse)
    async def remote_auth_otp_verify(
        request: RemoteAuthOtpVerifyRequest,
        http_request: Request,
    ) -> RemoteAuthLoginResponse:
        deps.check_rate_limit(
            http_request,
            email=request.challenge_id,
            action="otp_verify",
            max_attempts=deps.remote_auth_rate_limit_max_attempts,
            include_client_bucket=True,
        )
        try:
            result = deps.get_store().verify_auth_otp(
                challenge_id=request.challenge_id,
                code=request.code,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return deps.login_response_from_result(result, actor_kind=str(result.get("actor_kind") or "mobile"))

    @router.post("/api/remote/auth/otp/resend", response_model=RemoteAuthOtpChallengeResponse)
    async def remote_auth_otp_resend(
        request: RemoteAuthOtpResendRequest,
        http_request: Request,
    ) -> RemoteAuthOtpChallengeResponse:
        deps.check_rate_limit(
            http_request,
            email=request.challenge_id,
            action="otp_resend",
            max_attempts=10,
            include_client_bucket=True,
        )
        challenge: Dict[str, Any] = {}
        try:
            challenge = deps.get_store().resend_auth_otp(challenge_id=request.challenge_id)
            await deps.send_otp_email(
                email=str(challenge.get("email") or ""),
                code=str(challenge.get("otp_code") or ""),
                purpose=str(challenge.get("purpose") or "login_verify"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            deps.invalidate_challenge(challenge)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return deps.challenge_response(challenge)

    @router.post("/api/remote/auth/google/start", response_model=RemoteGoogleAuthStartResponse)
    async def remote_google_auth_start(
        request: RemoteGoogleAuthStartRequest,
        http_request: Request,
    ) -> RemoteGoogleAuthStartResponse:
        deps.check_rate_limit(http_request, email="google", action=f"google_start:{request.actor_kind}")
        if not deps.google_oauth_configured():
            raise HTTPException(status_code=503, detail="Google login is not configured")
        try:
            login_request = deps.get_store().create_oauth_login_request(
                provider="google",
                actor_kind=request.actor_kind,
                device_name=request.device_name,
                device_platform=request.device_platform,
                device_key=request.device_key,
                ttl_seconds=deps.google_oauth_request_ttl_seconds,
                remember_me=request.remember_me,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        expires_at = float(login_request.get("expires_at") or 0)
        return RemoteGoogleAuthStartResponse(
            auth_url=deps.google_oauth_auth_url(state=str(login_request["state"])),
            request_id=str(login_request["request_id"]),
            poll_token=str(login_request["poll_token"]),
            expires_in_seconds=max(0, int(expires_at - time.time())),
        )

    @router.get("/api/remote/auth/google/callback")
    async def remote_google_auth_callback(
        http_request: Request,
        code: Optional[str] = None,
        state: Optional[str] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ) -> Response:
        state_value = str(state or "").strip()
        if not state_value:
            return deps.google_callback_page(
                title="Google sign-in failed",
                message="The sign-in request was missing its state. Please return to EmploAI and try again.",
                is_error=True,
            )
        deps.check_rate_limit(http_request, email=state_value[:128], action="google_callback")
        request_status = deps.get_store().get_oauth_login_request_status(provider="google", state=state_value)
        if not request_status:
            return deps.google_callback_page(
                title="Google sign-in failed",
                message="This sign-in request was not recognized. Please return to EmploAI and start Google sign-in again.",
                is_error=True,
            )
        if str(request_status.get("status") or "") != "pending":
            return deps.google_callback_page(
                title="Google sign-in failed",
                message="This sign-in request is no longer active. Please return to EmploAI and start Google sign-in again.",
                is_error=True,
            )
        if error:
            detail = error_description or error
            deps.get_store().fail_oauth_login_request(provider="google", state=state_value, error=detail)
            return deps.google_callback_page(
                title="Google sign-in cancelled",
                message="Return to EmploAI to start a new sign-in request.",
                is_error=True,
            )
        if not code:
            deps.get_store().fail_oauth_login_request(provider="google", state=state_value, error="Missing Google authorization code")
            return deps.google_callback_page(
                title="Google sign-in failed",
                message="Google did not return an authorization code. Please return to EmploAI and try again.",
                is_error=True,
            )
        try:
            token_payload = await deps.exchange_google_oauth_code(code)
            claims = deps.verify_google_id_token(str(token_payload.get("id_token") or ""))
            deps.get_store().complete_oauth_login_request(
                provider="google",
                state=state_value,
                subject=str(claims.get("sub") or ""),
                email=str(claims.get("email") or ""),
                email_verified=bool(claims.get("email_verified", False)),
                display_name=str(claims.get("name") or claims.get("given_name") or "") or None,
                avatar_url=str(claims.get("picture") or "") or None,
            )
        except Exception as exc:
            deps.get_store().fail_oauth_login_request(provider="google", state=state_value, error=str(exc))
            return deps.google_callback_page(
                title="Google sign-in failed",
                message="Return to EmploAI and try again. The app will show the detailed status there.",
                is_error=True,
            )
        return deps.google_callback_page(
            title="Google sign-in complete",
            message="You can close this browser tab and return to EmploAI.",
        )

    @router.post("/api/remote/auth/google/poll", response_model=RemoteGoogleAuthPollResponse)
    async def remote_google_auth_poll(
        request: RemoteGoogleAuthPollRequest,
        http_request: Request,
    ) -> RemoteGoogleAuthPollResponse:
        deps.check_rate_limit(
            http_request,
            email=request.request_id,
            action="google_poll",
            max_attempts=deps.remote_auth_poll_rate_limit_max_attempts,
            include_client_bucket=False,
        )
        try:
            result = deps.get_store().consume_oauth_login_request(
                request_id=request.request_id,
                poll_token=request.poll_token,
                token_ttl_seconds=deps.remote_session_ttl_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        status = str(result.get("status") or "pending")
        if status != "complete":
            return RemoteGoogleAuthPollResponse(
                status=status if status in {"pending", "error", "expired"} else "error",
                error=result.get("error"),
            )
        actor_kind = str(result.get("actor_kind") or "mobile")
        login_response = deps.login_response_from_result(result, actor_kind=actor_kind)
        return RemoteGoogleAuthPollResponse(
            status="complete",
            session_token=login_response.session_token,
            expires_in_seconds=login_response.expires_in_seconds,
            actor_kind=login_response.actor_kind,
            user=login_response.user,
            desktop=login_response.desktop,
            mobile=login_response.mobile,
            remember_me=login_response.remember_me,
        )

    @router.post("/api/remote/auth/logout", response_model=RemoteAuthLogoutResponse)
    async def remote_logout(authorization: Optional[str] = Header(default=None)) -> RemoteAuthLogoutResponse:
        token = deps.bearer_token_from_header(authorization)
        auth = deps.resolve_token(authorization)
        if not deps.is_remote_session_auth(auth):
            raise HTTPException(status_code=403, detail="Remote account logout requires a remote session token")
        revoked = deps.get_store().revoke_session_token(token)
        disconnected_desktop = False
        if revoked:
            disconnected_desktop = await deps.disconnect_remote_desktop_for_session(
                auth,
                reason="desktop session logged out",
            )
        return RemoteAuthLogoutResponse(revoked=revoked, disconnected_desktop=disconnected_desktop)

    return router
