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
    run_mode: Optional[Literal["normal", "plan", "goal"]] = None
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
    variant: str = "standard"
    message_count: int
    workspace: str = ""
    latest_preview: Optional[str] = None
    origin_channels: List[ChannelType] = Field(default_factory=list)
    is_running: bool = False
    run_state: Literal["idle", "running"] = "idle"
    enabled_tool_packs: List[str] = Field(default_factory=list)
    security_permission_mode: str = "standard"
    available_tool_packs: List[str] = Field(default_factory=list)
    lock_status: Dict[str, Any] = Field(default_factory=dict)
    telegram_bot_config_id: Optional[str] = None
    headless_eligible: bool = False
    workspace_id: Optional[str] = None
    workspace_binding_status: Optional[str] = None
    fleet_identity_id: Optional[str] = None
    fleet_identity_role: Optional[str] = None
    fleet_worker_id: Optional[str] = None
    account_user_id: Optional[int] = None
    account_email: Optional[str] = None
    plan_mode: Optional[Dict[str, Any]] = None
    active_goal: Optional[Dict[str, Any]] = None
    artifact_count: int = 0
    latest_artifact_at: Optional[str] = None


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
    task_board_armed_next_turn: bool = False
    is_running: bool = False
    run_state: Literal["idle", "running"] = "idle"
    enabled_tool_packs: List[str] = Field(default_factory=list)
    security_permission_mode: str = "standard"
    available_tool_packs: List[str] = Field(default_factory=list)
    lock_status: Dict[str, Any] = Field(default_factory=dict)
    telegram_bot_config_id: Optional[str] = None
    headless_eligible: bool = False
    workspace_id: Optional[str] = None
    workspace_binding_status: Optional[str] = None
    fleet_identity_id: Optional[str] = None
    fleet_identity_role: Optional[str] = None
    fleet_worker_id: Optional[str] = None
    account_user_id: Optional[int] = None
    account_email: Optional[str] = None
    plan_mode: Optional[Dict[str, Any]] = None
    active_goal: Optional[Dict[str, Any]] = None
    artifact_count: int = 0
    latest_artifact_at: Optional[str] = None


class SessionModeActionRequest(BaseModel):
    action: Literal["exit_plan", "dismiss_plan", "clear_goal"]
    reason: Optional[str] = None


class ArtifactSummaryView(BaseModel):
    artifact_id: str
    title: str
    artifact_kind: str
    source_kind: str
    created_at: str
    mime_type: str
    size_bytes: int
    preview_text: str = ""
    summary_text: str = ""
    source_tool: Optional[str] = None
    source_command: Optional[str] = None
    file_path: Optional[str] = None
    workspace: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArtifactDetailView(ArtifactSummaryView):
    payload_file_name: Optional[str] = None
    inline_text: Optional[str] = None
    image_base64: Optional[str] = None
    index_segments: List[Dict[str, Any]] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    name: Optional[str] = None
    workspace: Optional[str] = None
    telegram_bot_config_id: Optional[str] = None
    enabled_tool_packs: List[str] = Field(default_factory=list)
    security_permission_mode: Optional[str] = None
    headless_eligible: bool = False
    workspace_id: Optional[str] = Field(default=None, max_length=256)
    workspace_binding_status: Optional[str] = Field(default=None, max_length=80)
    fleet_identity_id: Optional[str] = Field(default=None, max_length=128)
    fleet_identity_role: Optional[str] = Field(default=None, max_length=40)
    fleet_worker_id: Optional[str] = Field(default=None, max_length=128)


class CreateSessionResponse(BaseModel):
    session: SessionDetailView


class RenameSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class DeleteSessionResponse(BaseModel):
    deleted_session_id: str
    current_session_id: Optional[str] = None
    archive_id: Optional[str] = None


class TaskBoardArmRequest(BaseModel):
    armed: bool = False


class TaskBoardArmResponse(BaseModel):
    session_id: Optional[str] = None
    task_board_armed_next_turn: bool = False


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
    channel: Optional[ChannelType] = "app"
    source_client_id: Optional[str] = None


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
    session_id: Optional[str] = None
    target_kind: Optional[str] = None
    target_identity_id: Optional[str] = None
    target_group_id: Optional[str] = None
    target_chat_id: Optional[str] = None
    chat_target: Optional[str] = None
    permission_mode: Optional[str] = None
    tool_packs: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_status: Optional[str] = None


class JobDetailView(BaseModel):
    id: str
    automation_id: Optional[str] = None
    name: str
    prompt: str
    schedule: Optional[str] = None
    schedule_mode: Optional[str] = None
    enabled: bool = True
    status: Optional[str] = None
    run_count: Optional[int] = None
    error_count: Optional[int] = None
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    one_time: bool = False
    target_kind: Optional[str] = None
    target_identity_id: Optional[str] = None
    target_group_id: Optional[str] = None
    target_chat_id: Optional[str] = None
    chat_target: Optional[str] = None
    permission_mode: Optional[str] = None
    tool_packs: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_status: Optional[str] = None
    confirmation_expires_at: Optional[str] = None


class VoiceCommitRequest(BaseModel):
    session_id: Optional[str] = None
    transcript: str


class ScheduledJobView(BaseModel):
    id: str
    automation_id: Optional[str] = None
    name: str
    prompt: str
    schedule: Optional[str] = None
    schedule_mode: Optional[str] = None
    enabled: bool = True
    status: Optional[str] = None
    run_count: Optional[int] = None
    error_count: Optional[int] = None
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    one_time: bool = False
    interval_seconds: Optional[int] = None
    due: bool = False
    target_kind: Optional[str] = None
    target_identity_id: Optional[str] = None
    target_group_id: Optional[str] = None
    target_chat_id: Optional[str] = None
    chat_target: Optional[str] = None
    permission_mode: Optional[str] = None
    tool_packs: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_status: Optional[str] = None
    confirmation_expires_at: Optional[str] = None
    owner_user_id: Optional[int] = None
    origin_session_id: Optional[str] = None
    origin_telegram_bot_config_id: Optional[str] = None
    origin_workspace: Optional[str] = None
    origin_model: Optional[str] = None
    origin_enabled_tool_packs: List[str] = Field(default_factory=list)


class CronFeedItemView(BaseModel):
    id: str
    timestamp: Optional[str] = None
    kind: str
    content: str
    session_id: Optional[str] = None
    session_name: Optional[str] = None
    job_id: Optional[str] = None
    job_name: Optional[str] = None
    telegram_bot_config_id: Optional[str] = None
    telegram_bot_label: Optional[str] = None
    status: Optional[str] = None
    event_type: Optional[str] = None
    event_source: Optional[str] = None
    importance: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    automation_id: Optional[str] = None
    target_identity_id: Optional[str] = None
    target_chat_id: Optional[str] = None
    dedupe_key: Optional[str] = None
    scheduled_for: Optional[str] = None
    acknowledged_at: Optional[str] = None


class AutomationEventRunView(BaseModel):
    event_run_id: str
    user_id: int
    event_id: Optional[str] = None
    automation_id: Optional[str] = None
    status: str
    target_identity_id: Optional[str] = None
    target_chat_id: Optional[str] = None
    attempt: int = 1
    max_attempts: int = 3
    next_attempt_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProcessWaitView(BaseModel):
    process_wait_id: str
    user_id: int
    session_id: Optional[str] = None
    command_id: str
    pid: Optional[int] = None
    command: Optional[str] = None
    cwd: Optional[str] = None
    shell: Optional[str] = None
    status: str
    resume_policy: Optional[str] = None
    persistent: bool = False
    ready_patterns: List[str] = Field(default_factory=list)
    meaningful_output_patterns: List[str] = Field(default_factory=list)
    failure_patterns: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None
    last_event_at: Optional[str] = None
    completed_at: Optional[str] = None


class PlannerContractView(BaseModel):
    contract_id: str
    user_id: int
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    status: str
    action: Optional[str] = None
    contract: Dict[str, Any] = Field(default_factory=dict)
    corrections: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    injected_at: Optional[str] = None


class RecoveryArchiveItemView(BaseModel):
    archive_id: str
    user_id: int
    object_kind: str
    object_id: str
    display_name: Optional[str] = None
    status: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    archived_at: Optional[str] = None
    expires_at: Optional[str] = None
    restored_at: Optional[str] = None
    purged_at: Optional[str] = None


class RecoveryListResponse(BaseModel):
    items: List[RecoveryArchiveItemView] = Field(default_factory=list)


class RecoveryActionResponse(BaseModel):
    ok: bool = True
    action: str
    item: Optional[RecoveryArchiveItemView] = None
    purged: Optional[int] = None
    restored_session_id: Optional[str] = None


class ConfirmationView(BaseModel):
    confirmation_id: str
    user_id: int
    action_kind: str
    title: str
    message: str
    risk_tier: str
    status: str
    origin_surface: Optional[str] = None
    origin_identity_id: Optional[str] = None
    origin_chat_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    decided_at: Optional[str] = None
    decided_by_surface: Optional[str] = None
    decided_by_actor: Optional[str] = None


class ConfirmationListResponse(BaseModel):
    items: List[ConfirmationView] = Field(default_factory=list)


class ConfirmationCreateRequest(BaseModel):
    action_kind: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    message: str = Field(min_length=1, max_length=2000)
    risk_tier: str = Field(default="danger", max_length=80)
    origin_surface: Optional[str] = Field(default=None, max_length=80)
    origin_identity_id: Optional[str] = Field(default=None, max_length=256)
    origin_chat_id: Optional[str] = Field(default=None, max_length=256)
    payload: Dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=300, ge=30, le=1800)


class ConfirmationDecisionRequest(BaseModel):
    decided_by_surface: str = Field(default="app", max_length=80)
    decided_by_actor: Optional[str] = Field(default=None, max_length=256)


class WorkspaceRestoreRequest(BaseModel):
    workspace_id: Optional[str] = Field(default=None, max_length=256)
    local_path: Optional[str] = Field(default=None, max_length=2000)
    machine_id: Optional[str] = Field(default=None, max_length=256)


class WorkspaceRestoreResponse(BaseModel):
    ok: bool = True
    restored_path: str
    restored_files: List[Dict[str, Any]] = Field(default_factory=list)
    missing_original_files: List[Dict[str, Any]] = Field(default_factory=list)
    conflict_count: int = 0


class RuntimeActionRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcessWaitUpdateRequest(BaseModel):
    persistent: Optional[bool] = None
    reason: Optional[str] = Field(default=None, max_length=1000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlannerContractStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=80)
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
    token_strategy: str = "rough"
    system_prompt_tokens: int = 0
    injected_context_tokens: int = 0
    chat_history_tokens: int = 0
    tool_schema_tokens: int = 0
    tool_schema_count: int = 0
    prompt_message_count: int = 0
    last_compaction: Optional[ContextCompactionView] = None


class TaskBoardSubGoalView(BaseModel):
    id: str
    title: str
    status: Literal["open", "in_progress", "done", "blocked"] = "open"
    completion_reason: Optional[str] = None
    completion_evidence: Optional[str] = None


class TaskBoardView(BaseModel):
    task_id: str
    status: Literal["active", "completed", "blocked", "paused", "interrupted"] = "active"
    state: Literal["idle", "candidate", "active", "reassessing", "blocked_waiting_user", "completed_collapsed", "history_collapsed"] = "active"
    display_mode: Literal["active", "completed_collapsed", "history_collapsed"] = "active"
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
    run_state: Literal["idle", "running"] = "idle"
    active_visual_monitors: int = 0
    task_board: Optional[TaskBoardView] = None
    completed_task_boards: List[TaskBoardView] = Field(default_factory=list)
    provider_availability: List[Dict[str, Any]] = Field(default_factory=list)
    task_board_armed_next_turn: bool = False
    available_tool_packs: List[str] = Field(default_factory=list)
    enabled_tool_packs: List[str] = Field(default_factory=list)
    lock_status: Dict[str, Any] = Field(default_factory=dict)


class TelegramBotConfigView(BaseModel):
    id: str
    label: str
    bot_token: str
    is_default: bool = False


class TelegramBotConfigCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    bot_token: str = Field(min_length=10, max_length=2000)


class TelegramBotConfigUpdateRequest(BaseModel):
    label: Optional[str] = Field(default=None, max_length=128)
    bot_token: Optional[str] = Field(default=None, min_length=10, max_length=2000)
    is_default: Optional[bool] = None


class ToolPackUpdateRequest(BaseModel):
    enabled_tool_packs: List[str] = Field(default_factory=list, max_length=64)


class SessionBotAssignmentRequest(BaseModel):
    telegram_bot_config_id: Optional[str] = Field(default=None, max_length=128)


class SessionHeadlessEligibilityRequest(BaseModel):
    headless_eligible: bool = False


class SessionSecurityPermissionRequest(BaseModel):
    security_permission_mode: Literal["low", "standard", "full_permissions"] = "standard"


class WorkspaceGitStateView(BaseModel):
    requestedPath: Optional[str] = None
    resolvedPath: Optional[str] = None
    repoRoot: Optional[str] = None
    isGitRepo: bool = False
    currentBranch: Optional[str] = None
    branches: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class WorkspaceGitCheckoutRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    branch: str = Field(min_length=1, max_length=512)


class RuntimeWorkerLockView(BaseModel):
    interactive_owner_session_id: Optional[str] = None
    workspace_write_owner_by_workspace: Dict[str, str] = Field(default_factory=dict)


class RuntimeWorkerStatusView(BaseModel):
    session_id: str
    is_running: bool = False
    run_state: Literal["idle", "running"] = "idle"
    workspace: str = ""
    enabled_tool_packs: List[str] = Field(default_factory=list)
    active_tool_packs: List[str] = Field(default_factory=list)
    telegram_bot_config_id: Optional[str] = None


class RuntimeOrchestratorView(BaseModel):
    max_concurrent_chats: int = 4
    running_sessions: List[RuntimeWorkerStatusView] = Field(default_factory=list)
    locks: RuntimeWorkerLockView = Field(default_factory=RuntimeWorkerLockView)
    headless_mode_enabled: bool = False
    default_sleep_session_by_bot: Dict[str, str] = Field(default_factory=dict)


class HeadlessConfigureRequest(BaseModel):
    enabled: Optional[bool] = None
    default_max_concurrent_chats: Optional[int] = None
    default_sleep_session_by_bot: Dict[str, Optional[str]] = Field(default_factory=dict)


class AgentConfigureRequest(BaseModel):
    model: Optional[str] = None
    variant: Optional[str] = None
    planner_model: Optional[str] = None
    max_turns: Optional[int] = None
    custom_system_prompt_append: Optional[str] = None
    memory_controls: Optional[Dict[str, bool]] = None
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


class IdentityStopRequest(BaseModel):
    session_id: Optional[str] = None
    identity_id: Optional[str] = None
    identity_role: Optional[str] = None
    worker_id: Optional[str] = None
    reason: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str


class MemorySearchResponse(BaseModel):
    query: str
    results: List[MemorySearchResultView] = Field(default_factory=list)


class MemoryNoteRequest(BaseModel):
    note: str


class MemoryOperationRequest(BaseModel):
    operations: List[Dict[str, Any]] = Field(default_factory=list)


class MemoryOperationResponse(BaseModel):
    changed: bool = False
    operations: List[Dict[str, Any]] = Field(default_factory=list)
    memory_file: Optional[str] = None
    message: Optional[str] = None


class MemoryFactRequest(BaseModel):
    content: str
    category: str = "general"
    tags: List[str] = Field(default_factory=list)
    trust: float = 0.7


class MemoryFactFeedbackRequest(BaseModel):
    fact_id: int
    helpful: bool = True


class MemoryFactView(BaseModel):
    id: int
    content: str
    category: str = "general"
    tags: List[str] = Field(default_factory=list)
    trust: float = 0.0
    source: str = "memory"
    created_at: str = ""
    updated_at: str = ""


class MemoryFactListResponse(BaseModel):
    items: List[MemoryFactView] = Field(default_factory=list)


class ConfigListResponse(BaseModel):
    items: List[ConfigEntryView] = Field(default_factory=list)


class ConfigUpdateRequest(BaseModel):
    key: str
    value: Any


class VoiceTtsConfigureRequest(BaseModel):
    backend: Literal["openai", "kokoro", "kokoro_onnx", "kokoro-onnx", "kyutai", "kyutai_clone", "pocket", "pocket_tts"]


class VoiceSttConfigureRequest(BaseModel):
    backend: Literal[
        "local",
        "local_whisper",
        "local-whisper",
        "whisper",
        "whisper_cpp",
        "whisper-cpp",
        "openai",
        "openai_realtime",
        "openai-realtime",
        "realtime",
        "realtime_api",
        "realtime-api",
        "gemini",
        "gemini_api",
        "gemini-api",
        "google",
        "google_gemini",
        "google-gemini",
    ]


class SkillSummaryView(BaseModel):
    name: str
    description: str
    user_invocable: bool = False
    available: bool = True
    active: bool = False
    unavailable_reason: Optional[str] = None
    body_loaded: bool = False
    resources: List[str] = Field(default_factory=list)


class SkillListResponse(BaseModel):
    items: List[SkillSummaryView] = Field(default_factory=list)


class SkillResourceView(BaseModel):
    name: str
    type: str
    loaded: bool = False
    content: Optional[str] = None


class SkillDetailView(BaseModel):
    name: str
    description: str
    path: str = ""
    body: str = ""
    body_loaded: bool = False
    resources: List[SkillResourceView] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    active: bool = False
    unavailable_reason: Optional[str] = None


class SkillLearnRequest(BaseModel):
    name: str
    description: Optional[str] = None
    workflow: Optional[str] = None
    activate: bool = True
    overwrite: bool = False


class SkillLearnResponse(BaseModel):
    ok: bool = True
    action: str = "skill_learn"
    message: str = ""
    skill: SkillDetailView


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
    surface_mode: Optional[str] = None
    capture_mode: Optional[str] = None
    wake_phrase: Optional[str] = None
    wake_verified_locally: Optional[bool] = None
    utterance_id: Optional[str] = None
    barge_in_candidate: Optional[bool] = None
    barge_in_reference_text: Optional[str] = None


class RealtimeServerEvent(BaseModel):
    type: str
    session_id: Optional[str] = None
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class RemoteDesktopView(BaseModel):
    desktop_id: str
    device_key: Optional[str] = None
    display_name: Optional[str] = None
    status: Literal["offline", "connected", "planned"] = "offline"
    detail: Optional[str] = None
    created_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_heartbeat_at: Optional[str] = None


class FleetInstanceView(BaseModel):
    instance_id: str
    user_id: int
    role: Literal["manager", "worker"]
    desktop_id: Optional[str] = None
    worker_id: Optional[str] = None
    display_name: Optional[str] = None
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    reset_at: Optional[str] = None


class FleetIdentityView(BaseModel):
    identity_id: str
    role: Literal["manager", "worker"]
    display_name: str
    instance_id: str
    desktop_id: Optional[str] = None
    worker_id: Optional[str] = None
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FleetWorkerView(BaseModel):
    worker_id: str
    user_id: int
    kind: Literal["local", "remote"]
    machine_desktop_id: Optional[str] = None
    instance_id: Optional[str] = None
    display_name: str
    status: str = "idle"
    detail: Optional[str] = None
    group_id: Optional[str] = None
    active_task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    queue_policy: Literal["review_required", "auto_continue_success"] = "review_required"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_seen_at: Optional[str] = None


class FleetTaskView(BaseModel):
    task_id: str
    user_id: int
    worker_id: str
    status: Literal["queued", "running", "paused", "blocked", "needs_review", "completed", "failed", "stopped", "canceled"]
    prompt: str
    source: Optional[str] = None
    queue_position: int = 0
    report_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    canceled_at: Optional[str] = None


class FleetReportView(BaseModel):
    report_id: str
    user_id: int
    worker_id: str
    task_id: str
    status: str
    summary: str
    evidence: List[Any] = Field(default_factory=list)
    artifacts: List[Any] = Field(default_factory=list)
    blockers: List[Any] = Field(default_factory=list)
    confidence: Optional[str] = None
    next_suggested_action: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class FleetWorkspaceBindingView(BaseModel):
    binding_id: str
    workspace_id: str
    machine_id: str
    local_path: str
    label: Optional[str] = None
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FleetToolGrantView(BaseModel):
    grant_id: str
    target_kind: str
    target_id: str
    tool_pack_id: str
    status: str
    reason: Optional[str] = None
    task_id: Optional[str] = None
    requested_turns: int = 1
    approved_turns: Optional[int] = None
    remaining_turns: Optional[int] = None
    requested_by: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None


class FleetSnapshotResponse(BaseModel):
    schema_version: int = 1
    user_id: int
    identities: List[FleetIdentityView] = Field(default_factory=list)
    active_identity_id: Optional[str] = None
    active_identity: Optional[FleetIdentityView] = None
    selected_chat_by_identity: Dict[str, Optional[str]] = Field(default_factory=dict)
    active_identity_version: int = 0
    active_identity_updated_at: Optional[str] = None
    instances: List[FleetInstanceView] = Field(default_factory=list)
    manager: Optional[FleetInstanceView] = None
    desktops: List[Dict[str, Any]] = Field(default_factory=list)
    connection_permissions: List[Dict[str, Any]] = Field(default_factory=list)
    delegations: List[Dict[str, Any]] = Field(default_factory=list)
    upstream_requests: List[Dict[str, Any]] = Field(default_factory=list)
    workers: List[FleetWorkerView] = Field(default_factory=list)
    groups: List[Dict[str, Any]] = Field(default_factory=list)
    tasks: List[FleetTaskView] = Field(default_factory=list)
    reports: List[FleetReportView] = Field(default_factory=list)
    workspace_bindings: List[FleetWorkspaceBindingView] = Field(default_factory=list)
    tool_grants: List[FleetToolGrantView] = Field(default_factory=list)
    audit_events: List[Dict[str, Any]] = Field(default_factory=list)
    locks: List[Dict[str, Any]] = Field(default_factory=list)
    feature_gated: bool = True


class FleetSetActiveIdentityRequest(BaseModel):
    identity_id: str = Field(min_length=1, max_length=128)
    selected_chat_id: Optional[str] = Field(default=None, max_length=128)
    source: Optional[str] = Field(default=None, max_length=80)


class FleetSetActiveChatRequest(BaseModel):
    chat_id: Optional[str] = Field(default=None, max_length=128)
    source: Optional[str] = Field(default=None, max_length=80)


class FleetActiveIdentityResponse(BaseModel):
    active_identity_id: Optional[str] = None
    active_identity: Optional[FleetIdentityView] = None
    selected_chat_by_identity: Dict[str, Optional[str]] = Field(default_factory=dict)
    active_identity_version: int = 0
    active_identity_updated_at: Optional[str] = None


class FleetGroupRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=1000)
    worker_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetGroupMembershipRequest(BaseModel):
    worker_ids: List[str] = Field(default_factory=list)


class FleetCreateLocalWorkerRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=160)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetCreateEnrollmentRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=160)
    expires_in_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetCreateEnrollmentResponse(BaseModel):
    enrollment_id: str
    enrollment_token: str
    expires_in_seconds: int
    display_name: Optional[str] = None


class FleetWorkerUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    queue_policy: Optional[Literal["review_required", "auto_continue_success"]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetStopWorkerRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetContinueWorkerQueueRequest(BaseModel):
    reviewed_report_id: Optional[str] = Field(default=None, max_length=128)
    source: str = Field(default="manager", max_length=80)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetCompleteEnrollmentRequest(BaseModel):
    enrollment_token: str = Field(min_length=16, max_length=256)
    device_name: Optional[str] = Field(default=None, max_length=160)
    device_platform: Optional[str] = Field(default=None, max_length=80)
    device_key: Optional[str] = Field(default=None, max_length=256)


class FleetCompleteEnrollmentResponse(BaseModel):
    session_token: str
    expires_in_seconds: int
    user_id: int
    desktop: RemoteDesktopView
    worker: Optional[FleetWorkerView] = None


class FleetComputerDelegationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    target_kind: Literal["manager", "worker"] = "manager"
    target_selector: Optional[str] = Field(default=None, max_length=160)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetRemoteWorkerCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)


class FleetConnectionPermissionRequest(BaseModel):
    permissions: Dict[str, bool] = Field(default_factory=dict)
    reason: Optional[str] = Field(default=None, max_length=1000)


class FleetUpstreamRequestDecision(BaseModel):
    decision: Literal["approved", "denied", "replied"]
    response: Optional[str] = Field(default=None, max_length=8000)


class ProviderAvailabilitySyncRequest(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list, max_length=100)
    source: str = Field(default="yggdrasil", max_length=80)


class FleetAssignTaskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    source: str = Field(default="manager", max_length=80)
    target_session_id: Optional[str] = Field(default=None, max_length=128)
    target_mode: str = Field(default="auto", max_length=40)
    workspace_id: Optional[str] = Field(default=None, max_length=256)
    requires_workspace_write: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetTaskReorderRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    task_ids: List[str] = Field(default_factory=list)


class FleetTaskRedirectRequest(BaseModel):
    direction: str = Field(min_length=1, max_length=20000)
    source: str = Field(default="manager", max_length=80)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetReportSearchRequest(BaseModel):
    query: Optional[str] = Field(default=None, max_length=1000)
    worker: Optional[str] = Field(default=None, max_length=160)
    status: Optional[str] = Field(default=None, max_length=80)
    limit: int = Field(default=20, ge=1, le=200)


class FleetTaskStatusRequest(BaseModel):
    status: Literal["queued", "running", "paused", "blocked", "needs_review", "completed", "failed", "stopped", "canceled"]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetReportRequest(BaseModel):
    status: str = Field(default="completed", max_length=80)
    summary: str = Field(min_length=1, max_length=20000)
    evidence: List[Any] = Field(default_factory=list)
    artifacts: List[Any] = Field(default_factory=list)
    blockers: List[Any] = Field(default_factory=list)
    confidence: Optional[str] = Field(default=None, max_length=80)
    next_suggested_action: Optional[str] = Field(default=None, max_length=4000)
    raw: Dict[str, Any] = Field(default_factory=dict)


class FleetWorkspaceBindingRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=256)
    machine_id: str = Field(min_length=1, max_length=256)
    local_path: str = Field(min_length=1, max_length=2000)
    label: Optional[str] = Field(default=None, max_length=256)
    status: str = Field(default="active", max_length=80)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetToolGrantRequest(BaseModel):
    target_kind: str = Field(default="worker", max_length=40)
    target_id: str = Field(min_length=1, max_length=128)
    tool_pack_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=1000)
    task_id: Optional[str] = Field(default=None, max_length=128)
    requested_turns: int = Field(default=10, ge=1, le=10)
    requested_by: Optional[str] = Field(default=None, max_length=128)


class FleetToolGrantDecisionRequest(BaseModel):
    approved: bool
    approved_turns: Optional[int] = Field(default=None, ge=1, le=10)
    approved_by: Optional[str] = Field(default=None, max_length=128)


class FleetDeleteWorkerResponse(BaseModel):
    ok: bool = True
    deleted: bool = False
    worker_id: str
    wipe_state: bool = True
    connection_revoked: bool = False


class RemoteDesktopSyncEnvelope(BaseModel):
    desktop_id: str
    current_session_id: Optional[str] = None
    current_model: Optional[str] = None
    current_variant: Optional[str] = None
    desktop_name: Optional[str] = None
    desktop_status_detail: Optional[str] = None
    sessions: List[Dict[str, Any]] = Field(default_factory=list)
    session_details: Dict[str, Any] = Field(default_factory=dict)
    jobs: List[Dict[str, Any]] = Field(default_factory=list)
    project_groups: List[Dict[str, Any]] = Field(default_factory=list)
    sidebar_state: Dict[str, Any] = Field(default_factory=dict)
    provider_availability: Optional[List[Dict[str, Any]]] = None


class RemoteDesktopSocketMessage(BaseModel):
    type: str
    command_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class SidebarStateRequest(BaseModel):
    state: Dict[str, Any] = Field(default_factory=dict)


class SidebarStateResponse(BaseModel):
    state: Dict[str, Any] = Field(default_factory=dict)
    shared_state: Dict[str, Any] = Field(default_factory=dict)


class ProjectOnboardingGuideMessage(BaseModel):
    role: Literal["assistant", "user", "system"] = "user"
    content: str = ""
    created_at: Optional[str] = None


class ProjectOnboardingToolRequirement(BaseModel):
    tool_pack_id: str
    label: str = ""
    status: Literal["enabled", "available", "missing"] = "available"
    reason: Optional[str] = None


class ProjectOnboardingProfile(BaseModel):
    workspace: str = ""
    workspace_key: str = ""
    workspace_id: Optional[str] = None
    enabled: bool = False
    role_identity: str = ""
    job_mission: str = ""
    required_tools: List[str] = Field(default_factory=list)
    workflows: List[str] = Field(default_factory=list)
    constraints: str = ""
    communication_style: str = ""
    raw_notes: str = ""
    desired_tool_packs: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    guided_transcript: List[ProjectOnboardingGuideMessage] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    prompt_preview: str = ""


class ProjectOnboardingSaveRequest(BaseModel):
    workspace: str = Field(min_length=1, max_length=2000)
    workspace_id: Optional[str] = Field(default=None, max_length=256)
    enabled: bool = True
    role_identity: str = ""
    job_mission: str = ""
    required_tools: List[str] = Field(default_factory=list)
    workflows: List[str] = Field(default_factory=list)
    constraints: str = ""
    communication_style: str = ""
    raw_notes: str = ""
    desired_tool_packs: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    guided_transcript: List[ProjectOnboardingGuideMessage] = Field(default_factory=list)
    apply_tool_packs: bool = True


class ProjectOnboardingSummarizeRequest(BaseModel):
    workspace: str = Field(min_length=1, max_length=2000)
    answers: Dict[str, Any] = Field(default_factory=dict)
    guided_transcript: List[ProjectOnboardingGuideMessage] = Field(default_factory=list)


class ProjectOnboardingResponse(BaseModel):
    profile: ProjectOnboardingProfile
    tool_requirements: List[ProjectOnboardingToolRequirement] = Field(default_factory=list)
    updated_session_ids: List[str] = Field(default_factory=list)
    message: Optional[str] = None
