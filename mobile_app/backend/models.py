from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


ChannelType = Literal["telegram", "app", "system"]
InterruptPolicy = Literal["none", "steer_now", "after_tool"]
SourceFormat = Literal[
    "telegram_text",
    "app_text",
    "app_voice_transcript",
    "app_file_upload",
    "app_system",
    "scheduled_job_announcement",
    "scheduled_job_result",
]


class DevicePairStartRequest(BaseModel):
    device_name: Optional[str] = None


class DevicePairStartResponse(BaseModel):
    pairing_id: str
    pairing_token: str
    expires_in_seconds: int = 300


class DevicePairCompleteRequest(BaseModel):
    pairing_token: str
    device_name: Optional[str] = None
    device_platform: Optional[str] = None


class DevicePairCompleteResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = 60 * 60 * 24 * 30
    device_id: str


class AppUserProfile(BaseModel):
    user_id: int
    channel: ChannelType = "app"
    current_session_id: Optional[str] = None
    current_model: Optional[str] = None
    current_variant: Optional[str] = None
    app_enabled: bool = True
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    device_platform: Optional[str] = None


class SessionMessageView(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    channel: Optional[ChannelType] = None
    source_format: Optional[SourceFormat] = None
    display_label: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class SessionSummaryView(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    model: str
    message_count: int
    workspace: str = ""
    latest_preview: Optional[str] = None
    origin_channels: List[ChannelType] = Field(default_factory=list)


class SessionDetailView(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    model: str
    variant: str
    agent_mode: str
    workspace: str = ""
    messages: List[SessionMessageView] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    name: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session: SessionDetailView


class ChatSendRequest(BaseModel):
    session_id: Optional[str] = None
    text: str
    source_format: SourceFormat = "app_text"
    interrupt_policy: InterruptPolicy = "none"


class UploadDescriptor(BaseModel):
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    accepted: bool = True
    session_id: Optional[str] = None
    attached: bool = True


class ScreenCaptureView(BaseModel):
    mime_type: str
    image_base64: str
    width: int
    height: int
    backend: str
    captured_at: float


class JobCreateRequest(BaseModel):
    name: str
    prompt: str
    schedule: str


class JobDetailView(BaseModel):
    id: str
    name: str
    prompt: str
    schedule: Optional[str] = None
    enabled: bool = True
    run_count: Optional[int] = None
    error_count: Optional[int] = None
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None


class VoiceCommitRequest(BaseModel):
    session_id: Optional[str] = None
    transcript: str


class ScheduledJobView(BaseModel):
    id: str
    name: str
    prompt: str
    schedule: Optional[str] = None
    enabled: bool = True
    run_count: Optional[int] = None
    error_count: Optional[int] = None
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    interval_seconds: Optional[int] = None
    due: bool = False
    owner_user_id: Optional[int] = None


class CronFeedItemView(BaseModel):
    id: str
    timestamp: Optional[str] = None
    kind: Literal["announcement", "result"]
    content: str
    session_id: Optional[str] = None
    session_name: Optional[str] = None
    job_id: Optional[str] = None
    job_name: Optional[str] = None


class JobActionResponse(BaseModel):
    ok: bool = True
    job_id: str
    action: str


class TrustedDeviceView(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    device_platform: Optional[str] = None
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    revoked_at: Optional[str] = None
    revoked: bool = False


class DeviceActionResponse(BaseModel):
    ok: bool = True
    device_id: str
    action: str


class VoiceClientEvent(BaseModel):
    type: Literal[
        "voice_start",
        "voice_chunk",
        "voice_pause",
        "voice_resume",
        "voice_commit",
        "voice_cancel",
    ]
    session_id: Optional[str] = None
    mime_type: Optional[str] = None
    audio_base64: Optional[str] = None
    sequence: Optional[int] = None
    interrupt_policy: Optional[InterruptPolicy] = None


class RealtimeServerEvent(BaseModel):
    type: str
    session_id: Optional[str] = None
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
