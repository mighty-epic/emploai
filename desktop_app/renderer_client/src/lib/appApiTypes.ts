export type AppProfile = {
  user_id: number;
  current_session_id?: string | null;
  current_model?: string | null;
  current_variant?: string | null;
  device_id?: string | null;
  device_name?: string | null;
  device_platform?: string | null;
};

export type RemoteUser = {
  user_id: number;
  email: string;
  display_name?: string | null;
  created_at?: string | null;
  last_login_at?: string | null;
  email_verified_at?: string | null;
};

export type RemoteDesktop = {
  desktop_id: string;
  device_key?: string | null;
  display_name?: string | null;
  status: 'offline' | 'connected' | 'planned';
  detail?: string | null;
  created_at?: string | null;
  last_seen_at?: string | null;
  last_heartbeat_at?: string | null;
  paired_mobile_ids: string[];
};

export type RemoteMobile = {
  mobile_id: string;
  device_name?: string | null;
  device_platform?: string | null;
  paired_desktop_id?: string | null;
  created_at?: string | null;
  last_used_at?: string | null;
};

export type RemoteAuthLoginResult = {
  session_token: string;
  expires_in_seconds: number;
  actor_kind: 'mobile' | 'desktop';
  user: RemoteUser;
  desktop?: RemoteDesktop | null;
  mobile?: RemoteMobile | null;
  remember_me?: boolean;
};

export type RemoteAuthOtpChallengeResult = {
  status: 'otp_required';
  challenge_id: string;
  email: string;
  purpose: 'signup_verify' | 'login_verify';
  expires_in_seconds: number;
  resend_available_in_seconds?: number;
};

export type RemoteGoogleAuthStartResult = {
  auth_url: string;
  request_id: string;
  poll_token: string;
  expires_in_seconds: number;
};

export type RemoteGoogleAuthPollResult = {
  status: 'pending' | 'complete' | 'error' | 'expired';
  error?: string | null;
  session_token?: string | null;
  expires_in_seconds?: number | null;
  actor_kind?: 'mobile' | 'desktop' | null;
  user?: RemoteUser | null;
  desktop?: RemoteDesktop | null;
  mobile?: RemoteMobile | null;
  remember_me?: boolean | null;
};

export type RemoteAccountCloudProfile = {
  schema_version?: number;
  preferences?: {
    verbose_mode?: boolean;
    cloud_chat_backup_enabled?: boolean;
    interrupt_policy_default?: 'none' | 'steer_now' | 'after_tool' | string;
    custom_system_prompt_append?: string | null;
    max_turns?: number | null;
    sleep_mode_enabled?: boolean;
    memory_controls?: {
      prompt_context_enabled?: boolean;
      search_enabled?: boolean;
      write_enabled?: boolean;
      [key: string]: unknown;
    };
    default_workspace?: string | null;
    planner_model?: string | null;
    default_model?: string | null;
    [key: string]: unknown;
  };
  setup?: {
    desktop?: Record<string, unknown>;
    mobile?: Record<string, unknown>;
    completed_versions?: Record<string, unknown>;
    [key: string]: unknown;
  };
  integrations?: {
    telegram?: {
      enabled?: boolean;
      allowed_user_ids?: string[];
      allowedUserIds?: string[];
      default_bot_config_id?: string | null;
      bots?: Array<Record<string, unknown>>;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  credential_refs?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export type RemoteAccountProfile = {
  user: RemoteUser;
  actor_kind: 'mobile' | 'desktop';
  desktop?: RemoteDesktop | null;
  mobile?: RemoteMobile | null;
  profile: RemoteAccountCloudProfile;
  shared_state: Record<string, unknown>;
};

export type RemoteAccountCloudProfileResult = {
  profile: RemoteAccountCloudProfile;
};

export type RemoteAccountSecretItem = {
  namespace: string;
  name: string;
  redacted_value: string;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type RemoteAccountSecretsListResult = {
  items: RemoteAccountSecretItem[];
};

export type RemoteAccountSecretsRevealResult = {
  namespace: string;
  secrets: Record<string, string>;
};

export type RemoteAuthLogoutResult = {
  ok: boolean;
  revoked: boolean;
};

export type RemoteAccountDataDeleteResult = {
  ok: boolean;
  deleted_secrets: number;
  profile_reset: boolean;
  shared_state_reset: boolean;
  profile: RemoteAccountCloudProfile;
};

export type RemotePairStartResult = {
  pairing_id: string;
  pairing_token: string;
  pairing_uri: string;
  desktop_id: string;
  desktop_name?: string | null;
  expires_in_seconds: number;
};

export type RemotePairCompleteResult = {
  desktop: RemoteDesktop;
  mobile: RemoteMobile;
  shared_state: Record<string, unknown>;
};

export type SessionSummary = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  model: string;
  variant?: string | null;
  message_count: number;
  workspace?: string;
  latest_preview?: string | null;
  origin_channels: string[];
  is_running: boolean;
  run_state: 'idle' | 'running';
  enabled_tool_packs: string[];
  security_permission_mode?: 'low' | 'standard' | 'full_permissions' | string;
  available_tool_packs: string[];
  lock_status: Record<string, unknown>;
  telegram_bot_config_id?: string | null;
  headless_eligible: boolean;
  workspace_id?: string | null;
  workspace_binding_status?: string | null;
  fleet_identity_id?: string | null;
  fleet_identity_role?: string | null;
  fleet_worker_id?: string | null;
  fleet_task_mode?: 'direct' | 'delegated' | string | null;
  fleet_task_id?: string | null;
  account_user_id?: number | null;
  account_email?: string | null;
  plan_mode?: Record<string, unknown> | null;
  active_goal?: Record<string, unknown> | null;
  artifact_count: number;
  latest_artifact_at?: string | null;
};

export type SessionMessage = {
  message_id?: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
  source_format?: string | null;
  display_label?: string | null;
  run_mode?: 'normal' | 'plan' | 'goal' | null;
  raw?: Record<string, unknown>;
};

export type SessionTimelineEvent = {
  id: string;
  kind: string;
  title: string;
  content: string;
  tone: 'neutral' | 'accent' | 'warn' | 'error';
  timestamp?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
  source_format?: string | null;
  metadata?: Record<string, unknown>;
};

export type SessionDetail = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  model: string;
  variant: string;
  planner_model?: string | null;
  agent_mode: string;
  workspace?: string;
  messages: SessionMessage[];
  timeline_events: SessionTimelineEvent[];
  task_board?: TaskBoard | null;
  completed_task_boards: TaskBoard[];
  provider_availability: Array<Record<string, unknown>>;
  task_board_armed_next_turn: boolean;
  is_running: boolean;
  run_state: 'idle' | 'running';
  enabled_tool_packs: string[];
  security_permission_mode?: 'low' | 'standard' | 'full_permissions' | string;
  available_tool_packs: string[];
  lock_status: Record<string, unknown>;
  telegram_bot_config_id?: string | null;
  headless_eligible: boolean;
  workspace_id?: string | null;
  workspace_binding_status?: string | null;
  fleet_identity_id?: string | null;
  fleet_identity_role?: string | null;
  fleet_worker_id?: string | null;
  fleet_task_mode?: 'direct' | 'delegated' | string | null;
  fleet_task_id?: string | null;
  account_user_id?: number | null;
  account_email?: string | null;
  plan_mode?: Record<string, unknown> | null;
  active_goal?: Record<string, unknown> | null;
  artifact_count: number;
  latest_artifact_at?: string | null;
};

export type FleetIdentity = {
  identity_id: string;
  role: 'manager' | 'worker' | string;
  display_name: string;
  instance_id: string;
  desktop_id?: string | null;
  worker_id?: string | null;
  status?: string;
  is_default?: boolean;
  protected?: boolean;
  tool_profile?: string | null;
  enabled_tool_packs?: string[];
  capability_tags?: string[];
  published_upstream?: boolean;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type FleetWorker = {
  worker_id: string;
  kind: 'local' | 'remote' | string;
  machine_desktop_id?: string | null;
  instance_id?: string | null;
  display_name: string;
  status: string;
  detail?: string | null;
  group_id?: string | null;
  active_task_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
  last_seen_at?: string | null;
  is_default?: boolean;
  protected?: boolean;
  tool_profile?: string | null;
  enabled_tool_packs?: string[];
  capability_tags?: string[];
  published_upstream?: boolean;
};

export type FleetTask = {
  task_id: string;
  worker_id: string;
  status: string;
  prompt: string;
  source?: string | null;
  queue_position: number;
  report_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  canceled_at?: string | null;
};

export type FleetReport = {
  report_id: string;
  worker_id: string;
  task_id: string;
  status: string;
  summary: string;
  evidence?: unknown[];
  artifacts?: unknown[];
  blockers?: unknown[];
  confidence?: string | null;
  next_suggested_action?: string | null;
  raw?: Record<string, unknown>;
  created_at?: string | null;
};

export type FleetGroup = {
  group_id: string;
  display_name: string;
  description?: string | null;
  worker_ids?: string[];
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type FleetToolGrant = {
  grant_id: string;
  target_kind: string;
  target_id: string;
  tool_pack_id: string;
  status: string;
  reason?: string | null;
  task_id?: string | null;
  requested_turns?: number;
  approved_turns?: number | null;
  remaining_turns?: number | null;
  requested_by?: string | null;
  approved_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  expires_at?: string | null;
};

export type FleetWorkspaceBinding = {
  binding_id: string;
  workspace_id: string;
  machine_id: string;
  local_path: string;
  label?: string | null;
  status: string;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type FleetSnapshot = {
  schema_version?: number;
  user_id?: number;
  identities: FleetIdentity[];
  active_identity_id?: string | null;
  active_identity?: FleetIdentity | null;
  selected_chat_by_identity?: Record<string, string | null>;
  active_identity_version?: number;
  active_identity_updated_at?: string | null;
  instances?: Array<Record<string, unknown>>;
  manager?: Record<string, unknown> | null;
  workers: FleetWorker[];
  groups?: FleetGroup[];
  tasks: FleetTask[];
  reports: FleetReport[];
  workspace_bindings?: FleetWorkspaceBinding[];
  tool_grants?: FleetToolGrant[];
  audit_events?: Array<Record<string, unknown>>;
  locks?: Array<Record<string, unknown>>;
  feature_gated?: boolean;
};

export type ArtifactSummary = {
  artifact_id: string;
  title: string;
  artifact_kind: string;
  source_kind: string;
  created_at: string;
  mime_type: string;
  size_bytes: number;
  preview_text: string;
  summary_text: string;
  source_tool?: string | null;
  source_command?: string | null;
  file_path?: string | null;
  workspace?: string | null;
  metadata: Record<string, unknown>;
};

export type ArtifactDetail = ArtifactSummary & {
  payload_file_name?: string | null;
  inline_text?: string | null;
  image_base64?: string | null;
  index_segments: Array<Record<string, unknown>>;
};

export type DeleteSessionResult = {
  deleted_session_id: string;
  current_session_id?: string | null;
  archive_id?: string | null;
};

export type SessionSearchResult = {
  kind: 'project' | 'session' | 'message';
  project_path: string;
  project_name: string;
  session_id?: string | null;
  session_name?: string | null;
  message_index?: number | null;
  message_role?: string | null;
  timestamp?: string | null;
  snippet: string;
  match_reason: string;
  score: number;
};

export type ScheduledJob = {
  id: string;
  automation_id?: string | null;
  name: string;
  prompt: string;
  schedule?: string | null;
  schedule_mode?: string | null;
  enabled: boolean;
  status?: string | null;
  run_count?: number | null;
  error_count?: number | null;
  next_run_at?: string | null;
  last_run_at?: string | null;
  interval_seconds?: number | null;
  due?: boolean;
  one_time?: boolean;
  target_kind?: string | null;
  target_identity_id?: string | null;
  target_group_id?: string | null;
  target_chat_id?: string | null;
  chat_target?: string | null;
  permission_mode?: string | null;
  tool_packs?: string[];
  metadata?: Record<string, unknown>;
  requires_confirmation?: boolean;
  confirmation_status?: string | null;
  confirmation_expires_at?: string | null;
  owner_user_id?: number | null;
  origin_session_id?: string | null;
  origin_telegram_bot_config_id?: string | null;
  origin_workspace?: string | null;
  origin_model?: string | null;
  origin_enabled_tool_packs: string[];
};

export type JobCreatePayload = {
  name: string;
  prompt: string;
  schedule: string;
  session_id?: string | null;
  target_kind?: string | null;
  target_identity_id?: string | null;
  target_group_id?: string | null;
  target_chat_id?: string | null;
  chat_target?: string | null;
  permission_mode?: string | null;
  tool_packs?: string[];
  metadata?: Record<string, unknown>;
  requires_confirmation?: boolean;
  confirmation_status?: string | null;
};

export type CronFeedItem = {
  id: string;
  timestamp?: string | null;
  kind: string;
  content: string;
  session_id?: string | null;
  session_name?: string | null;
  job_id?: string | null;
  job_name?: string | null;
  telegram_bot_config_id?: string | null;
  telegram_bot_label?: string | null;
  status?: string | null;
  event_type?: string | null;
  event_source?: string | null;
  importance?: string | null;
  metadata?: Record<string, unknown>;
  automation_id?: string | null;
  target_identity_id?: string | null;
  target_chat_id?: string | null;
  dedupe_key?: string | null;
  scheduled_for?: string | null;
  acknowledged_at?: string | null;
};

export type AutomationEventRun = {
  event_run_id: string;
  event_id?: string | null;
  automation_id?: string | null;
  status: string;
  target_identity_id?: string | null;
  target_chat_id?: string | null;
  attempt: number;
  max_attempts: number;
  next_attempt_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  result?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ProcessWait = {
  process_wait_id: string;
  session_id?: string | null;
  command_id: string;
  pid?: number | null;
  command?: string | null;
  cwd?: string | null;
  shell?: string | null;
  status: string;
  resume_policy?: string | null;
  persistent: boolean;
  ready_patterns: string[];
  meaningful_output_patterns: string[];
  failure_patterns: string[];
  metadata?: Record<string, unknown>;
  started_at?: string | null;
  last_event_at?: string | null;
  completed_at?: string | null;
};

export type PlannerContract = {
  contract_id: string;
  session_id?: string | null;
  turn_id?: string | null;
  status: string;
  action?: string | null;
  contract: Record<string, unknown>;
  corrections: Array<Record<string, unknown>>;
  created_at?: string | null;
  updated_at?: string | null;
  injected_at?: string | null;
};

export type RecoveryArchiveItem = {
  archive_id: string;
  object_kind: string;
  object_id: string;
  display_name?: string | null;
  status: string;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  archived_at?: string | null;
  expires_at?: string | null;
  restored_at?: string | null;
  purged_at?: string | null;
};

export type RecoveryListResponse = {
  items: RecoveryArchiveItem[];
};

export type PendingConfirmation = {
  confirmation_id: string;
  action_kind: string;
  title: string;
  message: string;
  risk_tier: string;
  status: string;
  origin_surface?: string | null;
  origin_identity_id?: string | null;
  origin_chat_id?: string | null;
  payload?: Record<string, unknown>;
  created_at?: string | null;
  expires_at?: string | null;
  decided_at?: string | null;
  decided_by_surface?: string | null;
  decided_by_actor?: string | null;
};

export type ConfirmationCreatePayload = {
  action_kind: string;
  title: string;
  message: string;
  risk_tier?: string;
  origin_surface?: string | null;
  origin_identity_id?: string | null;
  origin_chat_id?: string | null;
  payload?: Record<string, unknown>;
  ttl_seconds?: number;
};

export type WorkspaceRestoreResponse = {
  ok: boolean;
  restored_path: string;
  restored_files: Array<Record<string, unknown>>;
  missing_original_files: Array<Record<string, unknown>>;
  conflict_count: number;
};

export type ModelProviderGroup = {
  provider: string;
  models: string[];
};

export type AgentHistoryItem = {
  role: string;
  timestamp?: string | null;
  preview: string;
  display_label?: string | null;
};

export type PendingFile = {
  filename: string;
  mime_type?: string | null;
  size?: number | null;
  source_format?: string | null;
  uploaded_at?: string | null;
};

export type UploadResponse = {
  upload_id: string;
  filename: string;
  accepted: boolean;
  session_id?: string | null;
  attached: boolean;
};

export type ContextCompaction = {
  applied: boolean;
  reason: string;
  model_id: string;
  provider: string;
  before_tokens: number;
  after_tokens: number;
  before_usage_percent: number;
  after_usage_percent: number;
  preserved_user_messages: number;
  preserved_agent_messages: number;
  summary_source_messages: number;
  summary_tokens: number;
  summary_strategy: string;
  summary_message: string;
  message: string;
  threshold_percent: number;
  created_at?: string | null;
};

export type ContextUsage = {
  model: string;
  max_tokens: number;
  estimated_tokens: number;
  usage_percent: number;
  message_count: number;
  threshold_percent: number;
  needs_compaction: boolean;
  compaction_state: 'ok' | 'needs_compaction' | 'compacted';
  token_strategy?: string;
  system_prompt_tokens?: number;
  injected_context_tokens?: number;
  chat_history_tokens?: number;
  tool_schema_tokens?: number;
  tool_schema_count?: number;
  prompt_message_count?: number;
  last_compaction?: ContextCompaction | null;
};

export type TaskBoardSubGoal = {
  id: string;
  title: string;
  status: 'open' | 'in_progress' | 'done' | 'blocked';
  completion_reason?: string | null;
  completion_evidence?: string | null;
};

export type TaskBoard = {
  task_id: string;
  status: 'active' | 'completed' | 'blocked' | 'paused' | 'interrupted';
  state: 'idle' | 'candidate' | 'active' | 'reassessing' | 'blocked_waiting_user' | 'completed_collapsed' | 'history_collapsed';
  display_mode: 'active' | 'completed_collapsed' | 'history_collapsed';
  main_goal: string;
  goal_locked: boolean;
  sub_goals: TaskBoardSubGoal[];
  current_focus?: string | null;
  next_method?: string | null;
  pending_reassessment_reason?: string | null;
  progress_summary?: string | null;
  completed_sub_goals: number;
  total_sub_goals: number;
  turn_count: number;
  model_turn_count: number;
  tool_call_count: number;
  reassessment_count: number;
  latest_summary?: string | null;
  completion_summary?: string | null;
  verification_status: 'open' | 'done';
  verification_summary?: string | null;
  collapsed_title?: string | null;
  collapsed_completed_at?: string | null;
  collapsed_completion_summary?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
};

export type HeartbeatStatus = {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  check_count: number;
  last_heartbeat?: string | null;
};

export type MemorySummary = {
  memory_file_exists: boolean;
  daily_log_count: number;
  oldest_log?: string | null;
  newest_log?: string | null;
};

export type AnalyticsSummary = {
  period_days: number;
  total_events: number;
  total_messages: number;
  total_commands: number;
  total_tokens: number;
  avg_tokens_per_message: number;
  top_skills: Record<string, number>;
  top_commands: Record<string, number>;
  model_usage: Record<string, { input: number; output: number }>;
  daily_activity: Record<string, number>;
};

export type SecuritySummary = {
  allowed_users_count: number;
  rate_limited_users: number;
  security_events_24h: number;
  warning_events_24h: number;
  error_events_24h: number;
  max_requests_per_minute: number;
  max_requests_per_hour: number;
};

export type ConfigEntry = {
  key: string;
  value: unknown;
};

export type AgentOverview = {
  session_id?: string | null;
  current_model: string;
  current_variant: string;
  planner_model?: string | null;
  available_planner_models: string[];
  available_variants: string[];
  model_groups: ModelProviderGroup[];
  max_turns: number;
  workspace: string;
  auto_reply_enabled: boolean;
  verbose_mode: boolean;
  bridge_enabled: boolean;
  headless_mode: 'headless' | 'headed';
  heartbeat: HeartbeatStatus;
  context_usage: ContextUsage;
  history: AgentHistoryItem[];
  pending_files: PendingFile[];
  memory_summary: MemorySummary;
  analytics: AnalyticsSummary;
  security: SecuritySummary;
  config_preview: ConfigEntry[];
  run_state: 'idle' | 'running';
  active_visual_monitors: number;
  task_board?: TaskBoard | null;
  completed_task_boards: TaskBoard[];
  task_board_armed_next_turn: boolean;
  available_tool_packs: string[];
  enabled_tool_packs: string[];
  lock_status: Record<string, unknown>;
};

export type TelegramBotConfig = {
  id: string;
  label: string;
  bot_token: string;
  is_default: boolean;
};

export type RuntimeWorkerStatus = {
  session_id: string;
  is_running: boolean;
  run_state: 'idle' | 'running';
  workspace: string;
  enabled_tool_packs: string[];
  active_tool_packs: string[];
  telegram_bot_config_id?: string | null;
};

export type RuntimeOrchestratorStatus = {
  max_concurrent_chats: number;
  running_sessions: RuntimeWorkerStatus[];
  locks: {
    interactive_owner_session_id?: string | null;
    workspace_write_owner_by_workspace: Record<string, string>;
  };
  headless_mode_enabled: boolean;
  default_sleep_session_by_bot: Record<string, string>;
};

export type WorkspaceGitState = {
  requestedPath?: string | null;
  resolvedPath?: string | null;
  repoRoot?: string | null;
  isGitRepo: boolean;
  currentBranch?: string | null;
  branches: string[];
  error?: string | null;
};

export type SidebarProjectState = {
  pinned?: boolean;
  collapsed?: boolean;
  displayName?: string | null;
  hidden?: boolean;
  recentActivity?: Array<Record<string, unknown>>;
};

export type SidebarSessionState = {
  pinned?: boolean;
  order?: number | null;
  displayName?: string | null;
};

export type SidebarState = {
  version: number;
  projectOrder: string[];
  projects: Record<string, SidebarProjectState>;
  sessionMeta: Record<string, SidebarSessionState>;
  selectedProjectPath?: string | null;
  lastSelectedProjectPath?: string | null;
};

export type SidebarStateResult = {
  state: SidebarState;
  shared_state?: Record<string, unknown>;
};

export type VoiceRuntimeStatus = {
  ok?: boolean;
  input_ok?: boolean;
  issues?: string[];
  stt_backend?: string | null;
  stt_model?: string | null;
  draft_model?: string | null;
  binary_flavor?: string | null;
  tts_enabled?: boolean;
  tts_backend?: string | null;
  tts_available_backends?: string[];
  tts_ready?: boolean;
  tts_voice?: string | null;
  tts_model?: string | null;
  tts_issues?: string[];
  tts_switch?: {
    ok?: boolean;
    backend?: string | null;
    requested_backend?: string | null;
    issues?: string[];
  } | null;
  stt_switch?: {
    ok?: boolean;
    backend?: string | null;
    requested_backend?: string | null;
    issues?: string[];
  } | null;
  selected_engine?: string | null;
  english_requested?: boolean;
  hebrew_requested?: boolean;
  english_pack_ready?: boolean;
  hebrew_pack_ready?: boolean;
  english_pack_manifest?: Record<string, unknown> | null;
  english_pack_manifest_verified?: boolean;
  hebrew_pack_manifest?: Record<string, unknown> | null;
  hebrew_pack_manifest_verified?: boolean;
  selected_engine_state?: string | null;
  selected_engine_ready?: boolean;
  warmup?: Record<string, unknown> | null;
};

export type TaskBoardArmResult = {
  session_id?: string | null;
  task_board_armed_next_turn: boolean;
};

export type AgentConfigurePayload = {
  model?: string;
  variant?: string;
  planner_model?: string | null;
  max_turns?: number;
  custom_system_prompt_append?: string | null;
  memory_controls?: {
    prompt_context_enabled?: boolean;
    search_enabled?: boolean;
    write_enabled?: boolean;
  };
  workspace?: string;
  auto_reply_enabled?: boolean;
  verbose_mode?: boolean;
  bridge_enabled?: boolean;
  heartbeat_enabled?: boolean;
  heartbeat_interval_seconds?: number;
  headless_mode?: 'headless' | 'headed';
};

export type ToolPackUpdatePayload = {
  enabled_tool_packs: string[];
};

export type ProjectOnboardingGuideMessage = {
  role: 'assistant' | 'user' | 'system';
  content: string;
  created_at?: string | null;
};

export type ProjectOnboardingToolRequirement = {
  tool_pack_id: string;
  label: string;
  status: 'enabled' | 'available' | 'missing';
  reason?: string | null;
};

export type ProjectOnboardingProfile = {
  workspace: string;
  workspace_key: string;
  workspace_id?: string | null;
  enabled: boolean;
  role_identity: string;
  job_mission: string;
  required_tools: string[];
  workflows: string[];
  constraints: string;
  communication_style: string;
  raw_notes: string;
  desired_tool_packs: string[];
  missing_requirements: string[];
  guided_transcript: ProjectOnboardingGuideMessage[];
  created_at?: string | null;
  updated_at?: string | null;
  prompt_preview: string;
};

export type ProjectOnboardingSavePayload = {
  workspace: string;
  workspace_id?: string | null;
  enabled?: boolean;
  role_identity?: string;
  job_mission?: string;
  required_tools?: string[];
  workflows?: string[];
  constraints?: string;
  communication_style?: string;
  raw_notes?: string;
  desired_tool_packs?: string[];
  missing_requirements?: string[];
  guided_transcript?: ProjectOnboardingGuideMessage[];
  apply_tool_packs?: boolean;
};

export type ProjectOnboardingSummarizePayload = {
  workspace: string;
  answers: Record<string, unknown>;
  guided_transcript?: ProjectOnboardingGuideMessage[];
};

export type ProjectOnboardingResponse = {
  profile: ProjectOnboardingProfile;
  tool_requirements: ProjectOnboardingToolRequirement[];
  updated_session_ids: string[];
  message?: string | null;
};

export type SessionBotAssignmentPayload = {
  telegram_bot_config_id?: string | null;
};

export type SessionHeadlessEligibilityPayload = {
  headless_eligible: boolean;
};

export type SessionSecurityPermissionPayload = {
  security_permission_mode: 'low' | 'standard' | 'full_permissions';
};

export type HeadlessConfigurePayload = {
  enabled?: boolean;
  default_max_concurrent_chats?: number;
  default_sleep_session_by_bot?: Record<string, string | null>;
};

export type AgentAction = {
  ok: boolean;
  action: string;
  message?: string | null;
};

export type BridgeStatus = {
  desired_backend?: string | null;
  extension_ready?: boolean;
  extension?: Record<string, unknown> | null;
  task_backend?: string | null;
  real_browser_available?: boolean;
  task_tab_available?: boolean;
  primary_tab_id?: string | number | null;
  owned_tab_ids?: Array<string | number>;
};

export type SkillSummary = {
  name: string;
  description: string;
  user_invocable: boolean;
  available: boolean;
  active: boolean;
  unavailable_reason?: string | null;
  body_loaded?: boolean;
  resources?: string[];
};

export type SkillResource = {
  name: string;
  type: string;
  loaded: boolean;
  content?: string | null;
};

export type SkillDetail = {
  name: string;
  description: string;
  path?: string;
  body: string;
  body_loaded: boolean;
  resources: SkillResource[];
  metadata: Record<string, unknown>;
  available: boolean;
  active: boolean;
  unavailable_reason?: string | null;
};

export type SkillLearnResult = {
  ok: boolean;
  action: string;
  message: string;
  skill: SkillDetail;
};

export type SkillValidation = {
  name: string;
  valid: boolean;
  errors: string[];
  warnings: string[];
  scripts_count: number;
  references_count: number;
  assets_count: number;
};

export type SubAgentTask = {
  id: string;
  prompt: string;
  status: string;
  created_at?: string | null;
  headless: boolean;
  max_turns: number;
  result?: string | null;
  error?: string | null;
  completed_at?: string | null;
  turns_used: number;
};

export type SubAgentStatus = {
  total_tasks: number;
  running: number;
  completed: number;
  failed: number;
  tasks: SubAgentTask[];
};

export type MemorySearchResult = {
  source: string;
  line?: number | null;
  content: string;
};

export type MemoryOperation = {
  action: 'add' | 'replace' | 'remove';
  section?: string;
  content?: string;
  old_text?: string;
  new_text?: string;
};

export type MemoryOperationResult = {
  changed: boolean;
  operations: Array<Record<string, unknown>>;
  memory_file?: string | null;
  message?: string | null;
};

export type MemoryFact = {
  id: number;
  content: string;
  category: string;
  tags: string[];
  trust: number;
  source: string;
  created_at: string;
  updated_at: string;
};
