from __future__ import annotations

import asyncio
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

from mobile_app.backend.auth_store import AppAuthStore
from mobile_app.backend.capture_runtime import capture_screen_snapshot
from mobile_app.backend.models import (
    AppUserProfile,
    ChatSendRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    DeviceActionResponse,
    DevicePairCompleteRequest,
    DevicePairCompleteResponse,
    DevicePairStartRequest,
    DevicePairStartResponse,
    JobActionResponse,
    JobCreateRequest,
    JobDetailView,
    RealtimeServerEvent,
    ScheduledJobView,
    ScreenCaptureView,
    SessionDetailView,
    SessionSummaryView,
    TrustedDeviceView,
    UploadResponse,
    VoiceClientEvent,
)
from mobile_app.backend.runtime import run_app_chat_turn
from mobile_app.backend.session_bridge import AppSessionBridge
from mobile_app.backend.voice_runtime import VoiceDraftState, synthesize_assistant_audio
from shared.live_config import get_live_config
from single_agent.cron_scheduler import get_scheduler, parse_schedule_with_error


APP_SECRET_ENV = "EMPLO_APP_SECRET"
PAIRING_SECRET_ENV = "EMPLO_APP_PAIRING_SECRET"
DEFAULT_PAIR_TTL_SECONDS = 300
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30

_auth_store: Optional[AppAuthStore] = None
_server_thread: Optional[threading.Thread] = None
_server_started = False


def _secret() -> str:
    return os.getenv(APP_SECRET_ENV) or os.getenv("TELEGRAM_BOT_TOKEN", "emploai-dev-secret")


def _sign(value: str) -> str:
    return hmac.new(_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _get_auth_store() -> AppAuthStore:
    global _auth_store
    if _auth_store is None:
        _auth_store = AppAuthStore()
    return _auth_store


def _bearer_token_from_header(auth_header: Optional[str]) -> str:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return auth_header.split(" ", 1)[1].strip()


def _resolve_token(auth_header: Optional[str]) -> Dict[str, object]:
    token = _bearer_token_from_header(auth_header)
    payload = _get_auth_store().resolve_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def _resolve_ws_token(token: Optional[str]) -> Dict[str, object]:
    payload = _get_auth_store().resolve_access_token(token or "")
    if not payload:
        raise WebSocketDisconnect(code=4401)
    return payload


def _authorize_pair_start(auth_header: Optional[str], pair_secret: Optional[str]) -> int:
    if auth_header:
        return int(_resolve_token(auth_header)["user_id"])

    configured_secret = os.getenv(PAIRING_SECRET_ENV, "").strip()
    provided_secret = (pair_secret or "").strip()
    if configured_secret and provided_secret and hmac.compare_digest(provided_secret, configured_secret):
        return _default_user_id()

    raise HTTPException(
        status_code=401,
        detail="Pair start requires an existing device token or X-App-Pair-Secret",
    )


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
            "pairing_bootstrap_enabled": bool(os.getenv(PAIRING_SECRET_ENV, "").strip()),
            "steering_beta_enabled": bool(
                os.getenv("EMPLO_APP_STEERING_BETA_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
                or config.get("channels.app.steering_beta", False)
            ),
        }

    @app.post("/api/app/pair/start", response_model=DevicePairStartResponse)
    async def pair_start(
        request: DevicePairStartRequest,
        authorization: Optional[str] = Header(default=None),
        x_app_pair_secret: Optional[str] = Header(default=None),
    ) -> DevicePairStartResponse:
        created_by_user = _authorize_pair_start(authorization, x_app_pair_secret)
        record = _get_auth_store().create_pairing(
            device_name=request.device_name,
            created_by=f"user:{created_by_user}",
            ttl_seconds=DEFAULT_PAIR_TTL_SECONDS,
        )
        pairing_id = str(record["pairing_id"])
        issued_at = int(record["issued_at"])
        payload = f"{pairing_id}:{issued_at}"
        token = f"{payload}:{_sign(payload)}"
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
        user_id = _default_user_id()
        try:
            result = _get_auth_store().complete_pairing(
                pairing_id=pairing_id,
                user_id=user_id,
                device_name=request.device_name,
                device_platform=request.device_platform,
                token_ttl_seconds=TOKEN_TTL_SECONDS,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown pairing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DevicePairCompleteResponse(access_token=result["access_token"], device_id=result["device_id"])

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
            device_id=auth.get("device_id"),
            device_name=auth.get("device_name"),
            device_platform=auth.get("device_platform"),
        )

    @app.get("/api/app/devices", response_model=list[TrustedDeviceView])
    async def list_devices(authorization: Optional[str] = Header(default=None)) -> list[TrustedDeviceView]:
        auth = _resolve_token(authorization)
        devices = _get_auth_store().list_devices(user_id=int(auth["user_id"]))
        return [TrustedDeviceView(**device) for device in devices]

    @app.post("/api/app/devices/{device_id}/revoke", response_model=DeviceActionResponse)
    async def revoke_device(device_id: str, authorization: Optional[str] = Header(default=None)) -> DeviceActionResponse:
        auth = _resolve_token(authorization)
        if not _get_auth_store().revoke_device(user_id=int(auth["user_id"]), device_id=device_id):
            raise HTTPException(status_code=404, detail="Device not found")
        return DeviceActionResponse(device_id=device_id, action="revoke")

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
        result = await run_app_chat_turn(
            runtime,
            user_message=request.text,
            source_format=request.source_format,
            interrupt_policy=request.interrupt_policy,
        )
        if result.get("busy"):
            raise HTTPException(status_code=409, detail="Session is already processing another message")
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

    @app.get("/api/app/screenshot/current", response_model=ScreenCaptureView)
    async def current_screenshot(authorization: Optional[str] = Header(default=None)) -> ScreenCaptureView:
        _resolve_token(authorization)
        try:
            capture = capture_screen_snapshot()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Screenshot capture failed: {str(exc)}") from exc
        return ScreenCaptureView(**capture)

    @app.websocket("/ws/app/screen")
    async def screen_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        send_lock = asyncio.Lock()

        async def send_model(event: RealtimeServerEvent) -> None:
            async with send_lock:
                await websocket.send_json(event.model_dump())

        try:
            token = websocket.query_params.get("token")
            _resolve_ws_token(token)

            try:
                fps = float(websocket.query_params.get("fps", "1.0") or "1.0")
            except ValueError:
                fps = 1.0
            fps = max(0.4, min(fps, 3.0))
            interval_seconds = 1.0 / fps

            try:
                max_width = int(websocket.query_params.get("max_width", "960") or "960")
            except ValueError:
                max_width = 960

            try:
                jpeg_quality = int(websocket.query_params.get("quality", "55") or "55")
            except ValueError:
                jpeg_quality = 55
            jpeg_quality = max(30, min(jpeg_quality, 85))

            await send_model(
                RealtimeServerEvent(
                    type="screen_state",
                    payload={
                        "state": "connected",
                        "fps": fps,
                        "max_width": max_width,
                        "quality": jpeg_quality,
                    },
                )
            )

            announced_streaming = False
            loop = asyncio.get_running_loop()
            while True:
                capture = await loop.run_in_executor(
                    None,
                    lambda: capture_screen_snapshot(max_width=max_width, jpeg_quality=jpeg_quality),
                )
                if not announced_streaming:
                    await send_model(
                        RealtimeServerEvent(
                            type="screen_state",
                            payload={"state": "streaming", "fps": fps},
                        )
                    )
                    announced_streaming = True
                await send_model(
                    RealtimeServerEvent(
                        type="screen_frame",
                        payload=capture,
                    )
                )
                await asyncio.sleep(interval_seconds)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            try:
                await send_model(
                    RealtimeServerEvent(
                        type="error",
                        payload={"message": f"Screen feed failed: {str(exc)}"},
                    )
                )
            except Exception:
                pass
            return

    @app.websocket("/ws/app/chat")
    async def chat_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        send_lock = asyncio.Lock()

        async def send_model(event: RealtimeServerEvent) -> None:
            async with send_lock:
                await websocket.send_json(event.model_dump())

        try:
            token = websocket.query_params.get("token")
            session_id = websocket.query_params.get("session_id")
            auth = _resolve_ws_token(token)
            bridge = _bridge_for_user(int(auth["user_id"]))
            runtime = bridge.load_runtime_session(session_id)
            effective_session_id = runtime.session_manager.get_current_session_id()
            await send_model(
                RealtimeServerEvent(
                    type="session_snapshot",
                    session_id=effective_session_id,
                    payload={"connected": True},
                )
            )
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                text = str(data.get("text", "")).strip()
                req_session_id = data.get("session_id") or effective_session_id
                if not text:
                    await send_model(RealtimeServerEvent(type="warning", message="Empty message ignored"))
                    continue

                runtime = bridge.load_runtime_session(req_session_id)

                async def emit(event: dict) -> None:
                    kind = event.get("type")
                    if kind == "assistant_delta":
                        await send_model(
                            RealtimeServerEvent(
                                type="assistant_delta",
                                session_id=req_session_id,
                                payload={"delta": event.get("delta", "")},
                            )
                        )
                    elif kind == "tool_use":
                        await send_model(
                            RealtimeServerEvent(
                                type="tool_event",
                                session_id=req_session_id,
                                payload={
                                    "tool_name": event.get("tool_name"),
                                    "tool_args": event.get("tool_args"),
                                    "tool_result": event.get("tool_result"),
                                    "duration_ms": event.get("duration_ms"),
                                },
                            )
                        )
                    elif kind == "log":
                        await send_model(
                            RealtimeServerEvent(
                                type="log",
                                session_id=req_session_id,
                                payload={"message": event.get("message", "")},
                            )
                        )
                    elif kind == "status":
                        await send_model(
                            RealtimeServerEvent(
                                type="status",
                                session_id=req_session_id,
                                payload={"message": event.get("message", "")},
                            )
                        )

                result = await run_app_chat_turn(
                    runtime,
                    user_message=text,
                    source_format="app_text",
                    interrupt_policy=str(data.get("interrupt_policy", "none")),
                    log_callback=emit,
                )
                if result.get("busy"):
                    await send_model(
                        RealtimeServerEvent(
                            type="warning",
                            session_id=req_session_id,
                            payload={"message": "Session is already processing another message"},
                        )
                    )
                    continue
                if result.get("steering"):
                    await send_model(
                        RealtimeServerEvent(
                            type="status",
                            session_id=req_session_id,
                            payload={
                                "message": (
                                    "Beta steering accepted"
                                    if result.get("steering_status") == "armed"
                                    else "Beta steering queued for next safe boundary"
                                )
                            },
                        )
                    )
                    continue
                final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or req_session_id
                await send_model(
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
                    )
                )
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/app/voice")
    async def voice_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        send_lock = asyncio.Lock()

        async def send_model(event: RealtimeServerEvent) -> None:
            async with send_lock:
                await websocket.send_json(event.model_dump())

        try:
            token = websocket.query_params.get("token")
            auth = _resolve_ws_token(token)
            bridge = _bridge_for_user(int(auth["user_id"]))
            draft = VoiceDraftState()
            active_session_id = websocket.query_params.get("session_id")
            await send_model(
                RealtimeServerEvent(
                    type="voice_state",
                    session_id=active_session_id,
                    payload={"state": "connected"},
                )
            )
            while True:
                raw = await websocket.receive_text()
                event = VoiceClientEvent.model_validate_json(raw)
                if event.session_id:
                    active_session_id = event.session_id

                async def send_voice_event(event_type: str, payload: Optional[dict] = None) -> None:
                    await send_model(
                        RealtimeServerEvent(
                            type=event_type,
                            session_id=active_session_id,
                            payload=payload or {},
                        )
                    )

                if event.type == "voice_start":
                    draft.reset()
                    draft.state = "listening"
                    await send_voice_event("voice_state", {"state": "listening"})
                elif event.type == "voice_chunk":
                    revision = draft.revision
                    session_for_chunk = active_session_id
                    chunk_audio_base64 = event.audio_base64
                    chunk_mime_type = event.mime_type
                    chunk_sequence = event.sequence

                    async def process_chunk() -> None:
                        try:
                            partial_text = await draft.transcribe_chunk(
                                audio_base64=chunk_audio_base64,
                                mime_type=chunk_mime_type,
                                sequence=chunk_sequence,
                                revision=revision,
                            )
                            if revision != draft.revision:
                                return
                            draft.state = "listening"
                            await send_model(
                                RealtimeServerEvent(
                                    type="voice_partial",
                                    session_id=session_for_chunk,
                                    payload={"text": partial_text},
                                )
                            )
                        except Exception as exc:
                            if revision != draft.revision:
                                return
                            draft.state = "error"
                            await send_model(
                                RealtimeServerEvent(
                                    type="error",
                                    session_id=session_for_chunk,
                                    payload={"message": f"Voice transcription failed: {str(exc)}"},
                                )
                            )

                    task = asyncio.create_task(process_chunk())
                    draft.register_task(task)
                elif event.type in {"voice_pause", "voice_resume"}:
                    draft.state = event.type.replace("voice_", "")
                    await send_voice_event("voice_state", {"state": draft.state})
                elif event.type == "voice_commit":
                    draft.state = "finalizing"
                    await send_voice_event("voice_state", {"state": "finalizing"})
                    await draft.wait_for_pending()
                    draft_text = draft.transcript().strip()
                    if not draft_text:
                        draft.reset()
                        await send_voice_event("warning", {"message": "No speech detected"})
                        await send_voice_event("voice_state", {"state": "idle"})
                        continue
                    runtime = bridge.load_runtime_session(active_session_id)
                    await send_voice_event("voice_state", {"state": "generating"})

                    async def emit(event_data: dict) -> None:
                        kind = event_data.get("type")
                        if kind == "assistant_delta":
                            await send_model(
                                RealtimeServerEvent(
                                    type="assistant_delta",
                                    session_id=active_session_id,
                                    payload={"delta": event_data.get("delta", "")},
                                )
                            )
                        elif kind == "tool_use":
                            await send_model(
                                RealtimeServerEvent(
                                    type="tool_event",
                                    session_id=active_session_id,
                                    payload={
                                        "tool_name": event_data.get("tool_name"),
                                        "tool_args": event_data.get("tool_args"),
                                        "tool_result": event_data.get("tool_result"),
                                        "duration_ms": event_data.get("duration_ms"),
                                    },
                                )
                            )
                        elif kind == "log":
                            await send_model(
                                RealtimeServerEvent(
                                    type="log",
                                    session_id=active_session_id,
                                    payload={"message": event_data.get("message", "")},
                                )
                            )
                        elif kind == "status":
                            await send_model(
                                RealtimeServerEvent(
                                    type="status",
                                    session_id=active_session_id,
                                    payload={"message": event_data.get("message", "")},
                                )
                            )

                    result = await run_app_chat_turn(
                        runtime,
                        user_message=draft_text,
                        source_format="app_voice_transcript",
                        interrupt_policy=event.interrupt_policy or "none",
                        log_callback=emit,
                    )
                    if result.get("busy"):
                        await send_voice_event("warning", {"message": "Session is already processing another message"})
                        continue
                    if result.get("steering"):
                        await send_model(
                            RealtimeServerEvent(
                                type="voice_final",
                                session_id=active_session_id,
                                payload={"text": draft_text},
                            )
                        )
                        await send_voice_event(
                            "status",
                            {
                                "message": (
                                    "Beta steering accepted"
                                    if result.get("steering_status") == "armed"
                                    else "Beta steering queued for next safe boundary"
                                )
                            },
                        )
                        draft.reset()
                        continue
                    final_session_id = result.get("session_id") or runtime.session_manager.get_current_session_id() or active_session_id
                    await send_model(
                        RealtimeServerEvent(
                            type="voice_final",
                            session_id=final_session_id,
                            payload={"text": draft_text},
                        )
                    )
                    await send_model(
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
                        )
                    )
                    assistant_audio = None
                    assistant_text = str(result.get("assistant_text", "") or "").strip()
                    if assistant_text:
                        await send_voice_event("voice_state", {"state": "synthesizing"})
                        loop = asyncio.get_running_loop()
                        try:
                            assistant_audio = await loop.run_in_executor(None, synthesize_assistant_audio, assistant_text)
                        except Exception as exc:
                            await send_voice_event("warning", {"message": f"Assistant audio unavailable: {str(exc)}"})

                    if assistant_audio:
                        await send_voice_event("voice_state", {"state": "speaking"})
                        await send_model(
                            RealtimeServerEvent(
                                type="assistant_audio",
                                session_id=final_session_id,
                                payload=assistant_audio,
                            )
                        )
                    else:
                        await send_voice_event("voice_state", {"state": "idle"})
                    draft.reset()
                elif event.type == "voice_cancel":
                    draft.reset()
                    await send_voice_event("voice_state", {"state": "cancelled"})
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
    port = int(config.get("channels.app.port", 8787))

    def _run() -> None:
        import uvicorn

        uvicorn.run(create_app(), host=host, port=port, log_level="info")

    _server_thread = threading.Thread(target=_run, name="emploai-app-server", daemon=True)
    _server_thread.start()
    _server_started = True
