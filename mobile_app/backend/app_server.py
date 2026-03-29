from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from mobile_app.backend.models import (
    AppUserProfile,
    ChatSendRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    DevicePairCompleteRequest,
    DevicePairCompleteResponse,
    DevicePairStartRequest,
    DevicePairStartResponse,
    JobActionResponse,
    JobCreateRequest,
    JobDetailView,
    RealtimeServerEvent,
    ScheduledJobView,
    SessionDetailView,
    SessionSummaryView,
    UploadResponse,
    VoiceClientEvent,
)
from mobile_app.backend.runtime import run_app_chat_turn
from mobile_app.backend.session_bridge import AppSessionBridge
from shared.live_config import get_live_config
from single_agent.cron_scheduler import get_scheduler, parse_schedule_with_error


APP_SECRET_ENV = "EMPLO_APP_SECRET"
DEFAULT_PAIR_TTL_SECONDS = 300
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30

_pairings: Dict[str, Dict[str, object]] = {}
_tokens: Dict[str, Dict[str, object]] = {}
_server_thread: Optional[threading.Thread] = None
_server_started = False


def _secret() -> str:
    return os.getenv(APP_SECRET_ENV) or os.getenv("TELEGRAM_BOT_TOKEN", "emploai-dev-secret")


def _sign(value: str) -> str:
    return hmac.new(_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _issue_token(device_id: str, user_id: int) -> str:
    raw = f"{device_id}:{user_id}:{secrets.token_urlsafe(24)}"
    token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")
    _tokens[token] = {
        "device_id": device_id,
        "user_id": user_id,
        "expires_at": time.time() + TOKEN_TTL_SECONDS,
    }
    return token


def _resolve_token(auth_header: Optional[str]) -> Dict[str, object]:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    payload = _tokens.get(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    if float(payload.get("expires_at", 0)) < time.time():
        _tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="Expired token")
    return payload


def _resolve_ws_token(token: Optional[str]) -> Dict[str, object]:
    payload = _tokens.get(token or "")
    if not payload:
        raise WebSocketDisconnect(code=4401)
    if float(payload.get("expires_at", 0)) < time.time():
        _tokens.pop(token or "", None)
        raise WebSocketDisconnect(code=4401)
    return payload


def _bridge_for_user(user_id: int) -> AppSessionBridge:
    workspace = Path(__file__).resolve().parents[2]
    return AppSessionBridge(user_id=user_id, workspace=workspace)


def _default_user_id() -> int:
    allowed = os.getenv("ALLOWED_USER_IDS", "").split(",")
    for item in allowed:
        item = item.strip()
        if item:
            try:
                return int(item)
            except ValueError:
                continue
    return 0


def create_app() -> FastAPI:
    app = FastAPI(title="EmploAI App Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/app/health")
    async def health() -> dict:
        config = get_live_config(Path(__file__).resolve().parents[2] / "config.json")
        return {
            "ok": True,
            "channel": "app",
            "enabled": bool(config.get("channels.app.enabled", False)),
        }

    @app.post("/api/app/pair/start", response_model=DevicePairStartResponse)
    async def pair_start(request: DevicePairStartRequest) -> DevicePairStartResponse:
        pairing_id = secrets.token_hex(8)
        issued_at = int(time.time())
        payload = f"{pairing_id}:{issued_at}"
        token = f"{payload}:{_sign(payload)}"
        _pairings[pairing_id] = {
            "token": token,
            "issued_at": issued_at,
            "expires_at": time.time() + DEFAULT_PAIR_TTL_SECONDS,
            "device_name": request.device_name,
        }
        return DevicePairStartResponse(pairing_id=pairing_id, pairing_token=token)

    @app.post("/api/app/pair/complete", response_model=DevicePairCompleteResponse)
    async def pair_complete(request: DevicePairCompleteRequest) -> DevicePairCompleteResponse:
        try:
            pairing_id, issued_at, signature = request.pairing_token.split(":", 2)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Malformed pairing token") from exc
        payload = f"{pairing_id}:{issued_at}"
        if not hmac.compare_digest(signature, _sign(payload)):
            raise HTTPException(status_code=400, detail="Invalid pairing token")
        pairing = _pairings.get(pairing_id)
        if not pairing:
            raise HTTPException(status_code=404, detail="Unknown pairing")
        if float(pairing.get("expires_at", 0)) < time.time():
            _pairings.pop(pairing_id, None)
            raise HTTPException(status_code=400, detail="Expired pairing token")
        device_id = secrets.token_hex(12)
        user_id = _default_user_id()
        access_token = _issue_token(device_id, user_id)
        _pairings.pop(pairing_id, None)
        return DevicePairCompleteResponse(access_token=access_token, device_id=device_id)

    @app.get("/api/app/me", response_model=AppUserProfile)
    async def me(authorization: Optional[str] = Header(default=None)) -> AppUserProfile:
        auth = _resolve_token(authorization)
        user_id = int(auth["user_id"])
        bridge = _bridge_for_user(user_id)
        current = bridge.get_current_session()
        return AppUserProfile(
            user_id=user_id,
            current_session_id=current.id if current else None,
            current_model=current.model if current else None,
            current_variant=current.variant if current else None,
        )

    @app.get("/api/app/sessions", response_model=list[SessionSummaryView])
    async def list_sessions(authorization: Optional[str] = Header(default=None)) -> list[SessionSummaryView]:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return [SessionSummaryView(**bridge.summarize_session(s)) for s in bridge.list_sessions()]

    @app.post("/api/app/sessions", response_model=CreateSessionResponse)
    async def create_session(request: CreateSessionRequest, authorization: Optional[str] = Header(default=None)) -> CreateSessionResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        session = bridge.create_session(request.name)
        detail = SessionDetailView(**bridge.detailed_session_view(session))
        return CreateSessionResponse(session=detail)

    @app.get("/api/app/sessions/{session_id}", response_model=SessionDetailView)
    async def get_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        session = bridge.get_session(session_id)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @app.post("/api/app/chat/send")
    async def send_chat(request: ChatSendRequest, authorization: Optional[str] = Header(default=None)) -> dict:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = bridge.load_runtime_session(request.session_id)
        result = await run_app_chat_turn(runtime, user_message=request.text, source_format=request.source_format)
        return result

    @app.get("/api/app/jobs", response_model=list[ScheduledJobView])
    async def list_jobs(authorization: Optional[str] = Header(default=None)) -> list[ScheduledJobView]:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        return [ScheduledJobView(**job) for job in bridge.list_jobs()]

    @app.get("/api/app/jobs/{job_id}", response_model=JobDetailView)
    async def get_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobDetailView:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            return JobDetailView(**bridge.get_job(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/api/app/jobs", response_model=JobDetailView)
    async def create_job(request: JobCreateRequest, authorization: Optional[str] = Header(default=None)) -> JobDetailView:
        auth = _resolve_token(authorization)
        interval_seconds, error = parse_schedule_with_error(request.schedule)
        if error or not interval_seconds:
            raise HTTPException(status_code=400, detail=error or "Invalid schedule")
        scheduler = get_scheduler()
        job_id = scheduler.add_job(
            name=request.name,
            prompt=request.prompt,
            interval_seconds=interval_seconds,
            schedule_text=request.schedule,
        )
        bridge = _bridge_for_user(int(auth["user_id"]))
        try:
            return JobDetailView(**bridge.get_job(job_id))
        except KeyError:
            return JobDetailView(
                id=job_id,
                name=request.name,
                prompt=request.prompt,
                schedule=request.schedule,
                enabled=True,
            )

    @app.post("/api/app/jobs/{job_id}/run", response_model=JobActionResponse)
    async def run_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.run_job_now(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="run")

    @app.post("/api/app/jobs/{job_id}/enable", response_model=JobActionResponse)
    async def enable(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.enable_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="enable")

    @app.post("/api/app/jobs/{job_id}/disable", response_model=JobActionResponse)
    async def disable(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.disable_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="disable")

    @app.delete("/api/app/jobs/{job_id}", response_model=JobActionResponse)
    async def delete_job(job_id: str, authorization: Optional[str] = Header(default=None)) -> JobActionResponse:
        _resolve_token(authorization)
        scheduler = get_scheduler()
        if not scheduler.remove_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return JobActionResponse(job_id=job_id, action="delete")

    @app.post("/api/app/upload", response_model=UploadResponse)
    async def upload(
        file: UploadFile = File(...),
        session_id: Optional[str] = None,
        authorization: Optional[str] = Header(default=None),
    ) -> UploadResponse:
        auth = _resolve_token(authorization)
        bridge = _bridge_for_user(int(auth["user_id"]))
        runtime = bridge.load_runtime_session(session_id)
        upload_id = secrets.token_hex(10)
        data = await file.read()
        effective_session_id = runtime.session_manager.get_current_session_id()
        bridge.attach_pending_file(
            runtime=runtime,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
        )
        return UploadResponse(
            upload_id=upload_id,
            filename=file.filename or "upload",
            session_id=effective_session_id,
            attached=True,
        )

    @app.websocket("/ws/app/chat")
    async def chat_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            token = websocket.query_params.get("token")
            session_id = websocket.query_params.get("session_id")
            auth = _resolve_ws_token(token)
            bridge = _bridge_for_user(int(auth["user_id"]))
            runtime = bridge.load_runtime_session(session_id)
            effective_session_id = runtime.session_manager.get_current_session_id()
            await websocket.send_json(
                RealtimeServerEvent(
                    type="session_snapshot",
                    session_id=effective_session_id,
                    payload={"connected": True},
                ).model_dump()
            )
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                text = str(data.get("text", "")).strip()
                req_session_id = data.get("session_id") or effective_session_id
                if not text:
                    await websocket.send_json(RealtimeServerEvent(type="warning", message="Empty message ignored").model_dump())
                    continue

                runtime = bridge.load_runtime_session(req_session_id)

                async def emit(event: dict) -> None:
                    kind = event.get("type")
                    if kind == "assistant_delta":
                        await websocket.send_json(
                            RealtimeServerEvent(
                                type="assistant_delta",
                                session_id=req_session_id,
                                payload={"delta": event.get("delta", "")},
                            ).model_dump()
                        )
                    elif kind == "tool_use":
                        await websocket.send_json(
                            RealtimeServerEvent(
                                type="tool_event",
                                session_id=req_session_id,
                                payload={
                                    "tool_name": event.get("tool_name"),
                                    "tool_args": event.get("tool_args"),
                                    "tool_result": event.get("tool_result"),
                                    "duration_ms": event.get("duration_ms"),
                                },
                            ).model_dump()
                        )
                    elif kind == "log":
                        await websocket.send_json(
                            RealtimeServerEvent(
                                type="log",
                                session_id=req_session_id,
                                payload={"message": event.get("message", "")},
                            ).model_dump()
                        )
                    elif kind == "status":
                        await websocket.send_json(
                            RealtimeServerEvent(
                                type="status",
                                session_id=req_session_id,
                                payload={"message": event.get("message", "")},
                            ).model_dump()
                        )

                result = await run_app_chat_turn(
                    runtime,
                    user_message=text,
                    source_format="app_text",
                    log_callback=emit,
                )
                final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or req_session_id
                await websocket.send_json(
                    RealtimeServerEvent(
                        type="assistant_final",
                        session_id=final_session_id,
                        payload={
                            "text": result.get("assistant_text", ""),
                            "duration_seconds": result.get("duration_seconds"),
                            "input_tokens": result.get("input_tokens"),
                            "output_tokens": result.get("output_tokens"),
                            "total_tokens": result.get("total_tokens"),
                        },
                    ).model_dump()
                )
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/app/voice")
    async def voice_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            token = websocket.query_params.get("token")
            auth = _resolve_ws_token(token)
            bridge = _bridge_for_user(int(auth["user_id"]))
            draft_text = ""
            active_session_id = websocket.query_params.get("session_id")
            await websocket.send_json(RealtimeServerEvent(type="voice_state", session_id=active_session_id, payload={"state": "connected"}).model_dump())
            while True:
                raw = await websocket.receive_text()
                event = VoiceClientEvent.model_validate_json(raw)
                if event.session_id:
                    active_session_id = event.session_id
                if event.type == "voice_start":
                    draft_text = ""
                    await websocket.send_json(RealtimeServerEvent(type="voice_state", session_id=active_session_id, payload={"state": "listening"}).model_dump())
                elif event.type == "voice_chunk":
                    piece = f" chunk{event.sequence or 0}"
                    draft_text = (draft_text + piece).strip()
                    await websocket.send_json(RealtimeServerEvent(type="voice_partial", session_id=active_session_id, payload={"text": draft_text}).model_dump())
                elif event.type in {"voice_pause", "voice_resume"}:
                    await websocket.send_json(RealtimeServerEvent(type="voice_state", session_id=active_session_id, payload={"state": event.type.replace('voice_', '')}).model_dump())
                elif event.type == "voice_commit":
                    runtime = bridge.load_runtime_session(active_session_id)
                    result = await run_app_chat_turn(
                        runtime,
                        user_message=draft_text or "Voice message",
                        source_format="app_voice_transcript",
                    )
                    final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or active_session_id
                    await websocket.send_json(RealtimeServerEvent(type="voice_final", session_id=final_session_id, payload={"text": draft_text or "Voice message"}).model_dump())
                    await websocket.send_json(RealtimeServerEvent(type="assistant_final", session_id=final_session_id, payload={"text": result.get("assistant_text", "")}).model_dump())
                    draft_text = ""
                elif event.type == "voice_cancel":
                    draft_text = ""
                    await websocket.send_json(RealtimeServerEvent(type="voice_state", session_id=active_session_id, payload={"state": "cancelled"}).model_dump())
        except WebSocketDisconnect:
            return

    return app


def start_embedded_app_server_if_enabled() -> None:
    global _server_thread, _server_started
    if _server_started:
        return

    workspace = Path(__file__).resolve().parents[2]
    config = get_live_config(workspace / "config.json")
    if not bool(config.get("channels.app.enabled", False)):
        return

    host = str(config.get("channels.app.host", "0.0.0.0"))
    port = int(config.get("channels.app.port", 8765))

    def _run() -> None:
        import uvicorn

        uvicorn.run(create_app(), host=host, port=port, log_level="info")

    _server_thread = threading.Thread(target=_run, name="emploai-app-server", daemon=True)
    _server_thread.start()
    _server_started = True
