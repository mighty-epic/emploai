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
    source_format: Optional[str] = None
    display_label: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class SessionTimelineEventView(BaseModel):
    id: str
    kind: str
    title: str
    content: str
    tone: Literal["neutral", "accent", "warn", "error"] = "neutral"
    timestamp: Optional[str] = None
    channel: Optional[ChannelType] = None
    source_format: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
    planner_model: Optional[str] = None
    agent_mode: str
    workspace: str = ""
    messages: List[SessionMessageView] = Field(default_factory=list)
    timeline_events: List[SessionTimelineEventView] = Field(default_factory=list)
    task_board: Optional["TaskBoardView"] = None
    completed_task_boards: List["TaskBoardView"] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    name: Optional[str] = None
    workspace: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session: SessionDetailView


class SessionSearchRequest(BaseModel):
    query: str
    limit: int = 40


class SessionSearchResultView(BaseModel):
    kind: Literal["project", "session", "message"]
    project_path: str
    project_name: str
    session_id: Optional[str] = None
    session_name: Optional[str] = None
    message_index: Optional[int] = None
    message_role: Optional[str] = None
    timestamp: Optional[str] = None
    snippet: str = ""
    match_reason: str
    score: float


class SessionSearchResponse(BaseModel):
    results: List[SessionSearchResultView] = Field(default_factory=list)


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


class ModelProviderGroup(BaseModel):
    provider: str
    models: List[str] = Field(default_factory=list)


class AgentHistoryItemView(BaseModel):
    role: str
    timestamp: Optional[str] = None
    preview: str
    display_label: Optional[str] = None


class PendingFileView(BaseModel):
    filename: str
    mime_type: Optional[str] = None
    size: Optional[int] = None
    source_format: Optional[str] = None
    uploaded_at: Optional[str] = None


class ContextCompactionView(BaseModel):
    applied: bool = False
    reason: str = "manual"
    model_id: str
    provider: str
    before_tokens: int = 0
    after_tokens: int = 0
    before_usage_percent: float = 0.0
    after_usage_percent: float = 0.0
    preserved_user_messages: int = 0
    preserved_agent_messages: int = 0
    summary_source_messages: int = 0
    summary_tokens: int = 0
    summary_strategy: str = "local"
    summary_message: str = ""
    message: str = ""
    threshold_percent: float = 40.0
    created_at: Optional[str] = None


class ContextUsageView(BaseModel):
    model: str
    max_tokens: int
    estimated_tokens: int
    usage_percent: float
    message_count: int
    threshold_percent: float = 40.0
    needs_compaction: bool = False
    compaction_state: Literal["ok", "needs_compaction", "compacted"] = "ok"
    last_compaction: Optional[ContextCompactionView] = None


class TaskBoardSubGoalView(BaseModel):
    id: str
    title: str
    status: Literal["open", "in_progress", "done", "blocked"] = "open"
    completion_reason: Optional[str] = None
    completion_evidence: Optional[str] = None


class TaskBoardView(BaseModel):
    task_id: str
    status: Literal["active", "completed", "blocked", "paused"] = "active"
    state: Literal["idle", "candidate", "active", "reassessing", "blocked_waiting_user", "completed_collapsed"] = "active"
    display_mode: Literal["active", "completed_collapsed"] = "active"
    main_goal: str
    goal_locked: bool = True
    sub_goals: List[TaskBoardSubGoalView] = Field(default_factory=list)
    current_focus: Optional[str] = None
    next_method: Optional[str] = None
    pending_reassessment_reason: Optional[str] = None
    progress_summary: Optional[str] = None
    completed_sub_goals: int = 0
    total_sub_goals: int = 0
    turn_count: int = 0
    model_turn_count: int = 0
    tool_call_count: int = 0
    reassessment_count: int = 0
    latest_summary: Optional[str] = None
    completion_summary: Optional[str] = None
    verification_status: Literal["open", "done"] = "open"
    verification_summary: Optional[str] = None
    collapsed_title: Optional[str] = None
    collapsed_completed_at: Optional[str] = None
    collapsed_completion_summary: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskBoardResponse(BaseModel):
    task_board: Optional[TaskBoardView] = None


class TimelineEventAppendRequest(BaseModel):
    kind: str
    title: str
    content: str
    tone: Literal["neutral", "accent", "warn", "error"] = "neutral"
    channel: Optional[ChannelType] = None
    source_format: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_client_id: Optional[str] = None


class HeartbeatStatusView(BaseModel):
    enabled: bool = False
    running: bool = False
    interval_seconds: int = 0
    check_count: int = 0
    last_heartbeat: Optional[str] = None


class MemorySummaryView(BaseModel):
    memory_file_exists: bool = False
    daily_log_count: int = 0
    oldest_log: Optional[str] = None
    newest_log: Optional[str] = None


class AnalyticsSummaryView(BaseModel):
    period_days: int = 7
    total_events: int = 0
    total_messages: int = 0
    total_commands: int = 0
    total_tokens: int = 0
    avg_tokens_per_message: float = 0.0
    top_skills: Dict[str, int] = Field(default_factory=dict)
    top_commands: Dict[str, int] = Field(default_factory=dict)
    model_usage: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    daily_activity: Dict[str, int] = Field(default_factory=dict)


class SecuritySummaryView(BaseModel):
    allowed_users_count: int = 0
    rate_limited_users: int = 0
    security_events_24h: int = 0
    warning_events_24h: int = 0
    error_events_24h: int = 0
    max_requests_per_minute: int = 0
    max_requests_per_hour: int = 0


class ConfigEntryView(BaseModel):
    key: str
    value: Any


class MemorySearchResultView(BaseModel):
    source: str
    line: Optional[int] = None
    content: str


class AgentOverviewView(BaseModel):
    session_id: Optional[str] = None
    current_model: str
    current_variant: str
    planner_model: Optional[str] = None
    available_planner_models: List[str] = Field(default_factory=list)
    available_variants: List[str] = Field(default_factory=list)
    model_groups: List[ModelProviderGroup] = Field(default_factory=list)
    max_turns: int
    workspace: str = ""
    auto_reply_enabled: bool = True
    verbose_mode: bool = True
    bridge_enabled: bool = False
    headless_mode: Literal["headless", "headed"] = "headless"
    heartbeat: HeartbeatStatusView = Field(default_factory=HeartbeatStatusView)
    context_usage: ContextUsageView
    history: List[AgentHistoryItemView] = Field(default_factory=list)
    pending_files: List[PendingFileView] = Field(default_factory=list)
    memory_summary: MemorySummaryView = Field(default_factory=MemorySummaryView)
    analytics: AnalyticsSummaryView = Field(default_factory=AnalyticsSummaryView)
    security: SecuritySummaryView = Field(default_factory=SecuritySummaryView)
    config_preview: List[ConfigEntryView] = Field(default_factory=list)
    task_board: Optional[TaskBoardView] = None
    completed_task_boards: List[TaskBoardView] = Field(default_factory=list)


class AgentConfigureRequest(BaseModel):
    model: Optional[str] = None
    variant: Optional[str] = None
    planner_model: Optional[str] = None
    max_turns: Optional[int] = None
    workspace: Optional[str] = None
    auto_reply_enabled: Optional[bool] = None
    verbose_mode: Optional[bool] = None
    bridge_enabled: Optional[bool] = None
    heartbeat_enabled: Optional[bool] = None
    heartbeat_interval_seconds: Optional[int] = None
    headless_mode: Optional[Literal["headless", "headed"]] = None


class AgentActionResponse(BaseModel):
    ok: bool = True
    action: str
    message: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str


class MemorySearchResponse(BaseModel):
    query: str
    results: List[MemorySearchResultView] = Field(default_factory=list)


class MemoryNoteRequest(BaseModel):
    note: str


class ConfigListResponse(BaseModel):
    items: List[ConfigEntryView] = Field(default_factory=list)


class ConfigUpdateRequest(BaseModel):
    key: str
    value: Any


class SkillSummaryView(BaseModel):
    name: str
    description: str
    user_invocable: bool = False
    available: bool = True
    active: bool = False
    unavailable_reason: Optional[str] = None


class SkillListResponse(BaseModel):
    items: List[SkillSummaryView] = Field(default_factory=list)


class SkillActivateRequest(BaseModel):
    name: str
    active: bool = True


class SkillValidationView(BaseModel):
    name: str
    valid: bool = False
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    scripts_count: int = 0
    references_count: int = 0
    assets_count: int = 0


class SubAgentTaskView(BaseModel):
    id: str
    prompt: str
    status: str
    created_at: Optional[str] = None
    headless: bool = True
    max_turns: int = 20
    result: Optional[str] = None
    error: Optional[str] = None
    completed_at: Optional[str] = None
    turns_used: int = 0


class SubAgentListResponse(BaseModel):
    total_tasks: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    tasks: List[SubAgentTaskView] = Field(default_factory=list)


class SubAgentSpawnRequest(BaseModel):
    prompt: str
    headless: bool = True
    max_turns: int = 30


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
    auto_send: Optional[bool] = None


class RealtimeServerEvent(BaseModel):
    type: str
    session_id: Optional[str] = None
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
