export type DesktopRuntimeStatus = {
  ok: boolean;
  state: string;
  mode: string;
  api_base_url?: string;
  apiBaseUrl?: string;
  startup_state?: string | null;
  readiness_scope?: string | null;
  degraded?: boolean;
  issues?: string[] | null;
  detail?: string | null;
  process_id?: number | null;
  processId?: number | null;
  runtimeProcessDetected?: boolean;
};

export type DesktopTelegramStatus = {
  enabled: boolean;
  configured: boolean;
  state: string;
  detail?: string | null;
  process_id?: number | null;
  processId?: number | null;
  log_path?: string | null;
  logPath?: string | null;
  ready_at?: string | null;
  readyAt?: string | null;
};

export type DesktopRemoteControlStatus = {
  configured: boolean;
  state: string;
  detail?: string | null;
  process_id?: number | null;
  processId?: number | null;
  log_path?: string | null;
  logPath?: string | null;
  desktop_id?: string | null;
  desktopId?: string | null;
  desktop_name?: string | null;
  desktopName?: string | null;
  ready_at?: string | null;
  readyAt?: string | null;
};

export type DesktopRemoteAccountUser = {
  user_id?: number;
  email?: string;
  display_name?: string | null;
  created_at?: string | null;
};

export type DesktopRemoteAccountDesktop = {
  desktop_id?: string;
  display_name?: string | null;
  status?: string | null;
  detail?: string | null;
  last_seen_at?: string | null;
};

export type DesktopRemoteAuthStatus = {
  signedIn: boolean;
  cloudDisabled?: boolean;
  mobileDisabled?: boolean;
  standalone?: boolean;
  apiBaseUrl?: string | null;
  user?: DesktopRemoteAccountUser | null;
  desktop?: DesktopRemoteAccountDesktop | null;
  profile?: Record<string, unknown> | null;
  error?: string | null;
  detail?: string | null;
  sessionPath?: string | null;
  sessionStorage?: string | null;
};

export type DesktopCodexAuthStatus = {
  provider?: string;
  configured: boolean;
  signedIn?: boolean;
  authMode?: string | null;
  baseUrl?: string | null;
  accountId?: string | null;
  expiresAt?: number | null;
  expiresAtIso?: string | null;
  hasRefreshToken?: boolean;
  accessTokenUsable?: boolean;
  pendingDeviceLogin?: boolean;
  authPath?: string | null;
  ok?: boolean;
  state?: string | null;
  detail?: string | null;
  error?: string | null;
};

export type DesktopCodexDeviceLogin = {
  ok: boolean;
  provider?: string;
  verification_uri?: string;
  verificationUri?: string;
  user_code?: string;
  userCode?: string;
  interval_seconds?: number;
  intervalSeconds?: number;
  expires_at?: number;
  expiresAt?: number;
  authPath?: string | null;
};

export type DesktopRemoteAuthOtpChallenge = {
  status: 'otp_required';
  challenge_id: string;
  email: string;
  purpose: 'signup_verify' | 'login_verify';
  expires_in_seconds: number;
  resend_available_in_seconds?: number;
};

export type DesktopRemoteAuthPayload = {
  apiBaseUrl?: string | null;
  email: string;
  password: string;
  displayName?: string | null;
  deviceName?: string | null;
  deviceKey?: string | null;
  rememberMe?: boolean;
  remember_me?: boolean;
};

export type DesktopRemotePairingToken = {
  pairing_id: string;
  pairing_token: string;
  pairing_uri?: string | null;
  desktop_id?: string | null;
  desktop_name?: string | null;
  expires_in_seconds: number;
};

export type DesktopRemoteSecretItem = {
  namespace: string;
  name: string;
  redacted_value: string;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DesktopLocalRuntimeSecretPreview = {
  redacted_value?: string;
  source?: string | null;
};

export type DesktopRemoteSecretsList = {
  items: DesktopRemoteSecretItem[];
};

export type DesktopRemoteSecretsApplyResult = {
  applied: boolean;
  count: number;
  detail?: string | null;
  bootstrap?: DesktopBootstrap | null;
  profile?: Record<string, unknown> | null;
  setupSecretCount?: number;
  telegramBotSecretCount?: number;
};

export type DesktopRemoteAccountDataDeleteResult = {
  ok?: boolean;
  deleted_secrets?: number;
  profile_reset?: boolean;
  shared_state_reset?: boolean;
  profile?: Record<string, unknown>;
};

export type DesktopRemoteAccountProfileResult = {
  profile?: Record<string, unknown>;
};

export type DesktopFleetWorker = {
  worker_id: string;
  user_id?: number;
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
  queue_policy?: 'review_required' | 'auto_continue_success' | string;
};

export type DesktopFleetIdentity = {
  identity_id: string;
  role: 'manager' | 'worker' | string;
  display_name: string;
  instance_id: string;
  desktop_id?: string | null;
  worker_id?: string | null;
  status?: string;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DesktopFleetTask = {
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
};

export type DesktopFleetReport = {
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
  created_at?: string | null;
};

export type DesktopFleetConnectionPermissions = {
  desktop_id?: string;
  permissions: {
    delegate_manager: boolean;
    delegate_workers: boolean;
    create_workers: boolean;
  };
  pending_request?: Record<string, unknown> | null;
  pendingRequest?: Record<string, unknown> | null;
  last_decision?: Record<string, unknown> | null;
  lastDecision?: Record<string, unknown> | null;
  source?: string | null;
  updated_at?: string | null;
  updatedAt?: number | string | null;
};

export type DesktopFleetDelegation = {
  delegation_id: string;
  desktop_id: string;
  target_kind: 'manager' | 'worker' | string;
  target_selector?: string | null;
  prompt: string;
  status: string;
  report?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DesktopFleetSnapshot = {
  schema_version?: number;
  user_id?: number;
  identities?: DesktopFleetIdentity[];
  active_identity_id?: string | null;
  active_identity?: DesktopFleetIdentity | null;
  selected_chat_by_identity?: Record<string, string | null>;
  active_identity_version?: number;
  active_identity_updated_at?: string | null;
  instances?: Array<Record<string, unknown>>;
  manager?: Record<string, unknown> | null;
  desktops?: Array<{
    desktop_id: string;
    display_name?: string | null;
    status?: string | null;
    detail?: string | null;
    last_seen_at?: string | null;
    last_heartbeat_at?: string | null;
  }>;
  connection_permissions?: DesktopFleetConnectionPermissions[];
  delegations?: DesktopFleetDelegation[];
  workers: DesktopFleetWorker[];
  groups?: Array<Record<string, unknown>>;
  tasks: DesktopFleetTask[];
  reports: DesktopFleetReport[];
  workspace_bindings?: Array<Record<string, unknown>>;
  tool_grants?: Array<Record<string, unknown>>;
  audit_events?: Array<Record<string, unknown>>;
  feature_gated?: boolean;
};

export type DesktopFleetEnrollment = {
  enrollment_id: string;
  enrollment_token: string;
  expires_in_seconds: number;
  display_name?: string | null;
};

export type DesktopFleetYggdrasilConnection = {
  configured: boolean;
  role: 'manager' | 'paired' | 'worker';
  managerUrl?: string | null;
  managerYggdrasilIp?: string | null;
  pairedAt?: number | null;
  desktopId?: string | null;
  desktopName?: string | null;
  workerId?: string | null;
  workerName?: string | null;
  relayState?: string | null;
  relayDetail?: string | null;
  permissions?: DesktopFleetConnectionPermissions['permissions'];
  pendingRequest?: Record<string, unknown> | null;
  lastDecision?: Record<string, unknown> | null;
  updatedAt?: number | string | null;
};

export type DesktopFleetYggdrasilStatus = {
  available: boolean;
  running: boolean;
  address?: string | null;
  public_key?: string | null;
  installHint?: string | null;
  connection?: DesktopFleetYggdrasilConnection | null;
};

export type DesktopFleetYggdrasilPairing = {
  ok: boolean;
  transport: 'yggdrasil';
  managerUrl: string;
  managerYggdrasilIp: string;
  pairingToken: string;
  expiresAt: number;
  expiresInSeconds: number;
  managerBindChanged?: boolean;
};

export type DesktopFleetYggdrasilJoinResult = {
  ok: boolean;
  transport: 'yggdrasil';
  managerUrl: string;
  worker?: DesktopFleetWorker | null;
  desktop?: Record<string, unknown> | null;
  pairedComputerRelayStarted?: boolean;
  remoteWorkerStarted: boolean;
  deviceName: string;
};

export type DesktopSetupValues = {
  TELEGRAM_BOT_TOKEN: string;
  ALLOWED_USER_IDS: string;
  EMPLOAI_REMOTE_CONTROL_BASE_URL: string;
  EMPLOAI_REMOTE_CONTROL_EMAIL: string;
  EMPLOAI_REMOTE_CONTROL_PASSWORD: string;
  EMPLOAI_REMOTE_DESKTOP_NAME: string;
  EMPLOAI_REMOTE_DESKTOP_KEY: string;
  DEFAULT_WORKSPACE: string;
  PLANNER_MODEL: string;
  INTERRUPT_POLICY_DEFAULT: string;
  OPENAI_PROVIDER_MODE: string;
  OPENAI_API_KEY: string;
  ANTHROPIC_API_KEY: string;
  GOOGLE_API_KEY: string;
  XAI_API_KEY: string;
  DEEPSEEK_API_KEY: string;
  NVIDIA_API_KEY: string;
  OPENROUTER_API_KEY: string;
  VOICE_DEFAULT_ENGINE: string;
  VOICE_ENGLISH_REQUESTED: string;
  VOICE_HEBREW_REQUESTED: string;
};

export type DesktopVoiceRuntimeStatus = {
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
  voice_gate_dbfs?: number | null;
  hebrew_voice_gate_dbfs?: number | null;
  jarvis_barge_in_gate_dbfs?: number | null;
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
};

export type DesktopVoicePackSummary = {
  id: string;
  kind?: 'stt' | 'tts' | string;
  backend?: string | null;
  title: string;
  description: string;
  requested: boolean;
  installed: boolean;
  available: boolean;
  enabled: boolean;
  placeholder: boolean;
  supportsAlwaysOn: boolean;
  status: string;
  removable?: boolean;
  source?: string;
  path?: string | null;
  issues?: string[];
};

export type DesktopVoicePackInstallProgress = {
  packId: string;
  state: string;
  phase: string;
  message: string;
  percent?: number | null;
  downloadedBytes?: number | null;
  totalBytes?: number | null;
};

export type DesktopVoicePackState = {
  defaultEngine: string;
  selectionSource: string;
  packs: DesktopVoicePackSummary[];
};

export type DesktopSetupState = {
  required: boolean;
  versioned: boolean;
  telegramRebindRequired?: boolean;
  releaseVersion: string;
  runtimeHome: string;
  envFilePath: string;
  extensionPath: string;
  extensionGuidePath: string;
  values: DesktopSetupValues;
  validationIssues: string[];
  configuredProviders: string[];
  localRuntimeSecrets?: Record<string, DesktopLocalRuntimeSecretPreview>;
  modelGroups?: Array<{ provider: string; models: string[] }>;
  plannerModels?: string[];
  telegramConfigured: boolean;
  telegramPartiallyConfigured: boolean;
  remoteControlConfigured?: boolean;
  remoteControlPartiallyConfigured?: boolean;
  ocrAvailable: boolean;
  ocrSource?: string | null;
  voiceAvailable: boolean;
  voiceStatus?: DesktopVoiceRuntimeStatus | null;
  voicePacks?: DesktopVoicePackState | null;
  remoteControlStatus?: DesktopRemoteControlStatus | null;
  codexAuth?: DesktopCodexAuthStatus | null;
};

export type DesktopMemoryState = {
  ok: boolean;
  exists: boolean;
  memoryFilePath: string;
  memoryDirPath: string;
  content: string;
  dailyLogCount: number;
  oldestLog?: string | null;
  newestLog?: string | null;
};

export type DesktopUpdateStatus = {
  ok: boolean;
  currentVersion: string;
  releaseTag: string;
  channel: string;
  repo: string;
  manifestUrl?: string | null;
  source?: string | null;
  intervalHours: number;
  checked: boolean;
  updateAvailable: boolean;
  update?: {
    version: string;
    tagName: string;
    assetName: string;
    assetUrl: string;
    publishedAt?: string | null;
    commit?: string | null;
  } | null;
  lastCheckedAt?: string | null;
  lastError?: string | null;
  message?: string | null;
  branch?: string | null;
  upstream?: string | null;
  currentCommit?: string | null;
  latestCommit?: string | null;
  aheadCount?: number;
  behindCount?: number;
  dirty?: boolean;
  dirtyCount?: number;
  blocked?: boolean;
  requiresManualUpdate?: boolean;
  localChangesWillBePreserved?: boolean;
};

export type DesktopFleetPreviewCapture = {
  mime_type: string;
  image_base64: string;
  width: number;
  height: number;
  backend: string;
  captured_at: number;
};

export type DesktopFleetPreviewResult = {
  ok: boolean;
  preview_id: string;
  worker_id: string;
  display_name?: string | null;
  desktop_id?: string | null;
  dispatch_status: string;
  command_id?: string | null;
  detail?: string | null;
  capture?: DesktopFleetPreviewCapture | null;
};

export type DesktopShortcutResult = {
  ok: boolean;
  shortcutPath?: string | null;
  target?: string | null;
  message?: string | null;
};

export type DesktopBootstrap = {
  ok: boolean;
  apiBaseUrl: string;
  accessToken: string;
  currentSessionId?: string | null;
  runtimeMode: string;
  runtimeStatus?: DesktopRuntimeStatus | null;
  deviceId?: string | null;
  userId?: number | null;
  runtimeAvailable?: boolean;
  canLaunchLocalRuntime?: boolean;
  runtimeProcessDetected?: boolean;
  workspaceRoot?: string | null;
  runtimeHome?: string | null;
  envFilePath?: string | null;
  desktopLogPath?: string | null;
  telegramLogPath?: string | null;
  releaseVersion?: string | null;
  setupState?: DesktopSetupState | null;
  telegramStatus?: DesktopTelegramStatus | null;
  startupTimings?: Record<string, number> | null;
};

export type DesktopSetupFieldValidation = {
  field: keyof DesktopSetupValues | string;
  status: 'idle' | 'checking' | 'valid' | 'invalid' | 'error';
  message: string;
};

export type DesktopBridgeEvent = {
  type: string;
  payload?: Record<string, any>;
  runtimeMode?: string;
  runtimeStatus?: DesktopRuntimeStatus | null;
  currentSessionId?: string | null;
};

export type DesktopSidebarProjectActivity = {
  id: string;
  message: string;
  timestamp: string;
  sessionId?: string | null;
  relatedProjectPath?: string | null;
};

export type DesktopSidebarProjectState = {
  pinned?: boolean;
  collapsed?: boolean;
  displayName?: string | null;
  hidden?: boolean;
  recentActivity?: DesktopSidebarProjectActivity[];
};

export type DesktopSidebarSessionState = {
  pinned?: boolean;
  order?: number | null;
};

export type DesktopSidebarState = {
  version: number;
  projectOrder: string[];
  projects: Record<string, DesktopSidebarProjectState>;
  sessionMeta: Record<string, DesktopSidebarSessionState>;
  selectedProjectPath?: string | null;
  lastSelectedProjectPath?: string | null;
};

export type DesktopPathStatus = {
  requestedPath?: string | null;
  resolvedPath?: string | null;
  exists: boolean;
  isDirectory: boolean;
};

export type DesktopGitRepoState = {
  requestedPath?: string | null;
  resolvedPath?: string | null;
  repoRoot?: string | null;
  isGitRepo: boolean;
  currentBranch?: string | null;
  branches: string[];
  error?: string | null;
};

type DesktopBridge = {
  bootstrap: (payload?: { force?: boolean; deferServices?: boolean; launchIfNeeded?: boolean }) => Promise<DesktopBootstrap>;
  getRuntimeStatus: () => Promise<DesktopRuntimeStatus>;
  runtime?: {
    start: (payload?: { attachTimeoutSeconds?: number; restartAttachTimeoutSeconds?: number; deferServices?: boolean }) => Promise<DesktopBootstrap>;
    stop: () => Promise<DesktopBootstrap>;
  };
  setup?: {
    save: (payload: { values: Partial<DesktopSetupValues>; restart_policy?: 'auto' | 'never' }) => Promise<DesktopBootstrap>;
    validateField: (payload: { field: keyof DesktopSetupValues | string; value: string }) => Promise<DesktopSetupFieldValidation>;
  };
  codexAuth?: {
    status: () => Promise<DesktopCodexAuthStatus>;
    startDevice: () => Promise<DesktopCodexDeviceLogin>;
    pollDevice: () => Promise<DesktopCodexAuthStatus>;
    logout: () => Promise<DesktopCodexAuthStatus>;
  };
  remoteAuth?: {
    status: () => Promise<DesktopRemoteAuthStatus>;
  };
  fleet?: {
    snapshot: () => Promise<DesktopFleetSnapshot>;
    delegateToComputer: (payload: { desktopId?: string; desktop_id?: string; prompt: string; targetKind?: string; target_kind?: string; targetSelector?: string | null; target_selector?: string | null; metadata?: Record<string, unknown> }) => Promise<DesktopFleetDelegation>;
    createWorkerOnComputer: (payload: { desktopId?: string; desktop_id?: string; displayName?: string; display_name?: string }) => Promise<Record<string, unknown>>;
    requestComputerPermissions: (payload: { desktopId?: string; desktop_id?: string; permissions: Record<string, boolean>; reason?: string | null }) => Promise<Record<string, unknown>>;
    setActiveIdentity: (payload: { identityId?: string; identity_id?: string; selectedChatId?: string | null; selected_chat_id?: string | null; source?: string }) => Promise<Record<string, unknown>>;
    setIdentityActiveChat: (payload: { identityId?: string; identity_id?: string; chatId?: string | null; chat_id?: string | null; source?: string }) => Promise<Record<string, unknown>>;
    createLocalWorker: (payload?: { displayName?: string | null; display_name?: string | null; metadata?: Record<string, unknown> }) => Promise<DesktopFleetWorker>;
    createEnrollment: (payload?: { displayName?: string | null; display_name?: string | null; expiresInSeconds?: number | null; expires_in_seconds?: number | null; metadata?: Record<string, unknown> }) => Promise<DesktopFleetEnrollment>;
    yggdrasilStatus: () => Promise<DesktopFleetYggdrasilStatus>;
    yggdrasilBootstrap: () => Promise<Record<string, unknown>>;
    yggdrasilCreatePairing: (payload?: { displayName?: string | null; expiresInSeconds?: number | null }) => Promise<DesktopFleetYggdrasilPairing>;
    yggdrasilJoin: (payload: { pairingToken: string; deviceName?: string | null }) => Promise<DesktopFleetYggdrasilJoinResult>;
    yggdrasilPermissions: () => Promise<DesktopFleetConnectionPermissions>;
    yggdrasilSetPermissions: (payload: { permissions: Record<string, boolean> }) => Promise<DesktopFleetConnectionPermissions>;
    yggdrasilDecidePermissionRequest: (payload: { requestId: string; approve: boolean }) => Promise<DesktopFleetConnectionPermissions>;
    renameWorker: (payload: { workerId?: string; worker_id?: string; displayName?: string; display_name?: string; queuePolicy?: string; queue_policy?: string; metadata?: Record<string, unknown> }) => Promise<DesktopFleetWorker>;
    resetWorker: (payload: { workerId?: string; worker_id?: string; reason?: string | null; metadata?: Record<string, unknown>; confirmationId?: string | null; confirmation_id?: string | null }) => Promise<Record<string, unknown>>;
    deleteWorker: (payload: { workerId?: string; worker_id?: string; wipeState?: boolean; wipe_state?: boolean; confirmationId?: string | null; confirmation_id?: string | null }) => Promise<Record<string, unknown>>;
    stopWorker: (payload: { workerId?: string; worker_id?: string; reason?: string | null; metadata?: Record<string, unknown> }) => Promise<Record<string, unknown>>;
    stopAll: (payload?: { reason?: string | null; metadata?: Record<string, unknown>; confirmationId?: string | null; confirmation_id?: string | null }) => Promise<Record<string, unknown>>;
    requestWorkerPreview: (payload: { workerId?: string; worker_id?: string }) => Promise<DesktopFleetPreviewResult>;
    createGroup: (payload: { displayName?: string; display_name?: string; workerIds?: string[]; worker_ids?: string[]; description?: string | null; metadata?: Record<string, unknown> }) => Promise<Record<string, unknown>>;
    updateGroup: (payload: { groupId?: string; group_id?: string; displayName?: string; display_name?: string; workerIds?: string[]; worker_ids?: string[]; description?: string | null; metadata?: Record<string, unknown> }) => Promise<Record<string, unknown>>;
    deleteGroup: (payload: { groupId?: string; group_id?: string; confirmationId?: string | null; confirmation_id?: string | null }) => Promise<Record<string, unknown>>;
    assignTask: (payload: { workerId?: string; worker_id?: string; prompt: string; source?: string; targetSessionId?: string | null; target_session_id?: string | null; targetMode?: string; target_mode?: string; workspaceId?: string | null; workspace_id?: string | null; requiresWorkspaceWrite?: boolean; requires_workspace_write?: boolean; metadata?: Record<string, unknown> }) => Promise<DesktopFleetTask>;
    assignGroupTask: (payload: { groupId?: string; group_id?: string; prompt: string; source?: string; targetSessionId?: string | null; target_session_id?: string | null; targetMode?: string; target_mode?: string; workspaceId?: string | null; workspace_id?: string | null; requiresWorkspaceWrite?: boolean; requires_workspace_write?: boolean; metadata?: Record<string, unknown>; confirmationId?: string | null; confirmation_id?: string | null }) => Promise<DesktopFleetTask[]>;
    continueWorkerQueue: (payload: { workerId?: string; worker_id?: string; reviewedReportId?: string | null; reviewed_report_id?: string | null; source?: string; metadata?: Record<string, unknown> }) => Promise<Record<string, unknown>>;
    reorderTasks: (payload: { workerId?: string; worker_id?: string; taskIds?: string[]; task_ids?: string[] }) => Promise<DesktopFleetTask[]>;
    redirectTask: (payload: { taskId?: string; task_id?: string; direction: string; source?: string; metadata?: Record<string, unknown> }) => Promise<DesktopFleetTask>;
    updateTaskStatus: (payload: { taskId?: string; task_id?: string; status: string; metadata?: Record<string, unknown> }) => Promise<DesktopFleetTask>;
    createTaskReport: (payload: { taskId?: string; task_id?: string; status?: string; summary: string; evidence?: unknown[]; artifacts?: unknown[]; blockers?: unknown[]; confidence?: string | null; nextSuggestedAction?: string | null; next_suggested_action?: string | null; raw?: Record<string, unknown> }) => Promise<DesktopFleetReport>;
    searchReports: (payload: { query?: string | null; worker?: string | null; status?: string | null; limit?: number }) => Promise<Record<string, unknown>>;
    upsertWorkspaceBinding: (payload: { workspaceId?: string; workspace_id?: string; machineId?: string; machine_id?: string; localPath?: string; local_path?: string; label?: string | null; status?: string; metadata?: Record<string, unknown> }) => Promise<Record<string, unknown>>;
    requestToolGrant: (payload: { targetKind?: string; target_kind?: string; targetId?: string; target_id?: string; toolPackId?: string; tool_pack_id?: string; reason?: string; taskId?: string | null; task_id?: string | null; requestedTurns?: number; requested_turns?: number; requestedBy?: string | null; requested_by?: string | null }) => Promise<Record<string, unknown>>;
    decideToolGrant: (payload: { grantId?: string; grant_id?: string; approved: boolean; approvedTurns?: number | null; approved_turns?: number | null; approvedBy?: string | null; approved_by?: string | null }) => Promise<Record<string, unknown>>;
  };
  voicePacks?: {
    install: (packId: string) => Promise<DesktopBootstrap>;
    remove: (packId: string) => Promise<DesktopBootstrap>;
    setDefaultEngine: (engine: string) => Promise<DesktopBootstrap>;
  };
  updates?: {
    check: (payload?: { force?: boolean }) => Promise<DesktopUpdateStatus>;
    install: () => Promise<Record<string, any>>;
  };
  shell?: {
    openPath: (targetPath: string) => Promise<string>;
    openChromeExtensions: () => Promise<string>;
    createDesktopShortcut?: () => Promise<DesktopShortcutResult>;
    editCommand?: (payload: { command: string; query?: string; findNext?: boolean }) => Promise<Record<string, any>>;
    zoom?: (payload: { command: 'in' | 'out' | 'reset' }) => Promise<Record<string, any>>;
    diagnostics?: () => Promise<Record<string, any>>;
    requestExit?: (payload: { mode: 'default' | 'keep_running' | 'stop_everything' | 'force' | 'cancel' }) => Promise<Record<string, any>>;
    onExitRequested?: (callback: (payload: Record<string, any>) => void) => () => void;
  };
  clipboard?: {
    writeText: (textValue: string) => Promise<Record<string, any>>;
  };
  memory?: {
    read: () => Promise<DesktopMemoryState>;
    write: (payload: { content: string }) => Promise<DesktopMemoryState>;
  };
  sidebar?: {
    readState: () => Promise<DesktopSidebarState | null>;
    writeState: (payload: { state: DesktopSidebarState | null }) => Promise<DesktopSidebarState | null>;
    pickFolder: (payload?: { defaultPath?: string | null }) => Promise<string | null>;
    createFolder: (payload?: { parentPath?: string | null; folderName?: string | null }) => Promise<{ path?: string; parentPath?: string; folderName?: string } | null>;
    pathStatus: (payload: { path?: string | null }) => Promise<DesktopPathStatus | null>;
    gitRepoInfo: (payload: { path?: string | null }) => Promise<DesktopGitRepoState | null>;
    checkoutBranch: (payload: { path?: string | null; branch?: string | null }) => Promise<DesktopGitRepoState | null>;
  };
  window?: {
    hideForSleepMode: () => Promise<Record<string, any>>;
  };
  onRuntimeEvent: (callback: (event: DesktopBridgeEvent) => void) => () => void;
};

declare global {
  interface Window {
    emploaiDesktop?: DesktopBridge;
  }
}

let bootstrapPromise: Promise<DesktopBootstrap> | null = null;

export function normalizeDesktopBootstrapRuntimeStatus(payload: DesktopBootstrap): DesktopBootstrap {
  if (!payload.runtimeStatus || typeof payload.runtimeProcessDetected !== 'boolean') {
    return payload;
  }
  if (payload.runtimeStatus.runtimeProcessDetected === payload.runtimeProcessDetected) {
    return payload;
  }
  return {
    ...payload,
    runtimeStatus: {
      ...payload.runtimeStatus,
      runtimeProcessDetected: payload.runtimeProcessDetected,
    },
  };
}

export function getDesktopBridge(): DesktopBridge | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }
  return window.emploaiDesktop;
}

export function isDesktopEnvironment() {
  return Boolean(getDesktopBridge());
}

export async function loadDesktopBootstrap(options?: { force?: boolean; deferServices?: boolean; launchIfNeeded?: boolean }) {
  const bridge = getDesktopBridge();
  if (!bridge) {
    return null;
  }
  if (options?.force) {
    bootstrapPromise = null;
  }
  if (!bootstrapPromise) {
    const request = bridge.bootstrap({
      force: Boolean(options?.force),
      deferServices: Boolean(options?.deferServices),
      launchIfNeeded: Boolean(options?.launchIfNeeded),
    }).then(normalizeDesktopBootstrapRuntimeStatus);
    bootstrapPromise = request;
    request.finally(() => {
      if (bootstrapPromise === request) {
        bootstrapPromise = null;
      }
    });
  }
  return bootstrapPromise;
}

export async function startDesktopRuntime(options?: { attachTimeoutSeconds?: number; restartAttachTimeoutSeconds?: number; deferServices?: boolean }) {
  const bridge = getDesktopBridge();
  if (!bridge?.runtime?.start) {
    return null;
  }
  const payload = normalizeDesktopBootstrapRuntimeStatus(await bridge.runtime.start(options));
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function stopDesktopRuntime() {
  const bridge = getDesktopBridge();
  if (!bridge?.runtime?.stop) {
    return null;
  }
  const payload = normalizeDesktopBootstrapRuntimeStatus(await bridge.runtime.stop());
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function saveDesktopSetup(
  values: Partial<DesktopSetupValues>,
  options?: { restartPolicy?: 'auto' | 'never' },
) {
  const bridge = getDesktopBridge();
  if (!bridge?.setup?.save) {
    return null;
  }
  const payload = normalizeDesktopBootstrapRuntimeStatus(
    await bridge.setup.save({ values, restart_policy: options?.restartPolicy })
  );
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function validateDesktopSetupField(field: keyof DesktopSetupValues | string, value: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.setup?.validateField) {
    return null;
  }
  return bridge.setup.validateField({ field, value });
}

export async function loadDesktopCodexAuthStatus() {
  const bridge = getDesktopBridge();
  if (!bridge?.codexAuth?.status) {
    return null;
  }
  return bridge.codexAuth.status();
}

export async function startDesktopCodexDeviceLogin() {
  const bridge = getDesktopBridge();
  if (!bridge?.codexAuth?.startDevice) {
    return null;
  }
  return bridge.codexAuth.startDevice();
}

export async function pollDesktopCodexDeviceLogin() {
  const bridge = getDesktopBridge();
  if (!bridge?.codexAuth?.pollDevice) {
    return null;
  }
  return bridge.codexAuth.pollDevice();
}

export async function logoutDesktopCodexAuth() {
  const bridge = getDesktopBridge();
  if (!bridge?.codexAuth?.logout) {
    return null;
  }
  return bridge.codexAuth.logout();
}

export async function loadDesktopRemoteAuthStatus() {
  const bridge = getDesktopBridge();
  if (!bridge?.remoteAuth?.status) {
    return null;
  }
  return bridge.remoteAuth.status();
}

export async function loginDesktopRemoteAuth(_payload: DesktopRemoteAuthPayload): Promise<DesktopRemoteAuthStatus | DesktopRemoteAuthOtpChallenge | null> { return null; }

export async function loginDesktopRemoteGoogle(_payload?: Partial<DesktopRemoteAuthPayload>): Promise<DesktopRemoteAuthStatus | null> { return null; }

export async function registerDesktopRemoteAuth(_payload: DesktopRemoteAuthPayload): Promise<DesktopRemoteAuthStatus | DesktopRemoteAuthOtpChallenge | null> { return null; }

export async function verifyDesktopRemoteAuthOtp(_payload: { apiBaseUrl?: string | null; challengeId?: string; challenge_id?: string; code: string }): Promise<DesktopRemoteAuthStatus | null> { return null; }

export async function resendDesktopRemoteAuthOtp(_payload: { apiBaseUrl?: string | null; challengeId?: string; challenge_id?: string }): Promise<DesktopRemoteAuthOtpChallenge | null> { return null; }

export async function logoutDesktopRemoteAuth(): Promise<DesktopRemoteAuthStatus | null> { return loadDesktopRemoteAuthStatus(); }

export async function createDesktopRemotePairingToken(): Promise<DesktopRemotePairingToken | null> { return null; }

export async function listDesktopRemoteSecrets(_namespace = 'setup'): Promise<DesktopRemoteSecretsList | null> { return null; }

export async function saveDesktopSetupSecrets(_values: Partial<DesktopSetupValues>): Promise<DesktopRemoteSecretsList | null> { return null; }

export async function saveDesktopRemoteSecrets(
  _namespace: string,
  _secrets: Record<string, string>,
  _metadata?: Record<string, unknown>,
): Promise<DesktopRemoteSecretsList | null> { return null; }

export async function applyDesktopAccountData(): Promise<DesktopRemoteSecretsApplyResult | null> { return null; }

export async function deleteDesktopRemoteSecret(_namespace: string, _name: string, _confirmationId?: string | null): Promise<{ ok?: boolean; deleted?: boolean } | null> { return null; }

export async function deleteDesktopRemoteAccountData(_confirmationId?: string | null): Promise<DesktopRemoteAccountDataDeleteResult | null> { return null; }

export async function loadDesktopRemoteAccountProfile(): Promise<DesktopRemoteAccountProfileResult | null> { return null; }

export async function updateDesktopRemoteAccountProfile(_profile: Record<string, unknown>): Promise<DesktopRemoteAccountProfileResult | null> { return null; }

export async function applyDesktopSetupSecrets(_names?: string[]): Promise<DesktopRemoteSecretsApplyResult | null> { return null; }

export async function loadDesktopFleetSnapshot() {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.snapshot) {
    return null;
  }
  return bridge.fleet.snapshot();
}

export async function delegateDesktopFleetComputer(
  desktopId: string,
  prompt: string,
  targetKind: 'manager' | 'worker' = 'manager',
  targetSelector?: string | null,
) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.delegateToComputer) return null;
  return bridge.fleet.delegateToComputer({ desktopId, prompt, targetKind, targetSelector: targetSelector || null });
}

export async function createDesktopFleetWorkerOnComputer(desktopId: string, displayName: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.createWorkerOnComputer) return null;
  return bridge.fleet.createWorkerOnComputer({ desktopId, displayName });
}

export async function requestDesktopFleetComputerPermissions(
  desktopId: string,
  permissions: Record<string, boolean>,
  reason?: string | null,
) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.requestComputerPermissions) return null;
  return bridge.fleet.requestComputerPermissions({ desktopId, permissions, reason: reason || null });
}

export async function loadDesktopFleetConnectionPermissions() {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.yggdrasilPermissions) return null;
  return bridge.fleet.yggdrasilPermissions();
}

export async function setDesktopFleetConnectionPermissions(permissions: Record<string, boolean>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.yggdrasilSetPermissions) return null;
  return bridge.fleet.yggdrasilSetPermissions({ permissions });
}

export async function decideDesktopFleetPermissionRequest(requestId: string, approve: boolean) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.yggdrasilDecidePermissionRequest) return null;
  return bridge.fleet.yggdrasilDecidePermissionRequest({ requestId, approve });
}

export async function setDesktopFleetActiveIdentity(identityId: string, selectedChatId?: string | null, source = 'desktop') {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.setActiveIdentity) {
    return null;
  }
  return bridge.fleet.setActiveIdentity({ identityId, selectedChatId: selectedChatId || null, source });
}

export async function setDesktopFleetIdentityActiveChat(identityId: string, chatId?: string | null, source = 'desktop') {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.setIdentityActiveChat) {
    return null;
  }
  return bridge.fleet.setIdentityActiveChat({ identityId, chatId: chatId || null, source });
}

export async function createDesktopFleetLocalWorker(displayName?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.createLocalWorker) {
    return null;
  }
  return bridge.fleet.createLocalWorker({ displayName: displayName || null });
}

export async function createDesktopFleetEnrollment(displayName?: string | null, expiresInSeconds?: number | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.createEnrollment) {
    return null;
  }
  return bridge.fleet.createEnrollment({
    displayName: displayName || null,
    expiresInSeconds: expiresInSeconds || null,
  });
}

export async function renameDesktopFleetWorker(workerId: string, displayName: string, metadata?: Record<string, unknown>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.renameWorker) {
    return null;
  }
  return bridge.fleet.renameWorker({ workerId, displayName, metadata });
}

export async function resetDesktopFleetWorker(workerId: string, reason?: string | null, metadata?: Record<string, unknown>, confirmationId?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.resetWorker) {
    return null;
  }
  return bridge.fleet.resetWorker({ workerId, reason: reason || null, metadata, confirmationId });
}

export async function deleteDesktopFleetWorker(workerId: string, wipeState = true, confirmationId?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.deleteWorker) {
    return null;
  }
  return bridge.fleet.deleteWorker({ workerId, wipeState, confirmationId });
}

export async function stopDesktopFleetWorker(workerId: string, reason?: string | null, metadata?: Record<string, unknown>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.stopWorker) {
    return null;
  }
  return bridge.fleet.stopWorker({ workerId, reason: reason || null, metadata });
}

export async function stopAllDesktopFleetWorkers(reason?: string | null, metadata?: Record<string, unknown>, confirmationId?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.stopAll) {
    return null;
  }
  return bridge.fleet.stopAll({ reason: reason || null, metadata, confirmationId });
}

export async function requestDesktopFleetWorkerPreview(workerId: string): Promise<DesktopFleetPreviewResult | null> {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.requestWorkerPreview) {
    return null;
  }
  return bridge.fleet.requestWorkerPreview({ workerId });
}

export async function createDesktopFleetGroup(displayName: string, workerIds: string[] = [], description?: string | null, metadata?: Record<string, unknown>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.createGroup) {
    return null;
  }
  return bridge.fleet.createGroup({ displayName, workerIds, description: description || null, metadata });
}

export async function updateDesktopFleetGroup(groupId: string, displayName: string, workerIds: string[] = [], description?: string | null, metadata?: Record<string, unknown>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.updateGroup) {
    return null;
  }
  return bridge.fleet.updateGroup({ groupId, displayName, workerIds, description: description || null, metadata });
}

export async function deleteDesktopFleetGroup(groupId: string, confirmationId?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.deleteGroup) {
    return null;
  }
  return bridge.fleet.deleteGroup({ groupId, confirmationId });
}

export async function assignDesktopFleetTask(
  workerId: string,
  prompt: string,
  metadata?: Record<string, unknown>,
  options?: { targetSessionId?: string | null; targetMode?: string | null; workspaceId?: string | null; requiresWorkspaceWrite?: boolean },
) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.assignTask) {
    return null;
  }
  return bridge.fleet.assignTask({
    workerId,
    prompt,
    source: 'manager',
    metadata,
    targetSessionId: options?.targetSessionId || null,
    targetMode: options?.targetMode || 'auto',
    workspaceId: options?.workspaceId || null,
    requiresWorkspaceWrite: Boolean(options?.requiresWorkspaceWrite),
  });
}

export async function assignDesktopFleetGroupTask(
  groupId: string,
  prompt: string,
  metadata?: Record<string, unknown>,
  options?: { targetSessionId?: string | null; targetMode?: string | null; workspaceId?: string | null; requiresWorkspaceWrite?: boolean },
  confirmationId?: string | null,
) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.assignGroupTask) {
    return null;
  }
  return bridge.fleet.assignGroupTask({
    groupId,
    prompt,
    source: 'manager',
    metadata,
    targetSessionId: options?.targetSessionId || null,
    targetMode: options?.targetMode || 'auto',
    workspaceId: options?.workspaceId || null,
    requiresWorkspaceWrite: Boolean(options?.requiresWorkspaceWrite),
    confirmationId,
  });
}

export async function continueDesktopFleetWorkerQueue(workerId: string, reviewedReportId?: string | null, metadata?: Record<string, unknown>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.continueWorkerQueue) {
    return null;
  }
  return bridge.fleet.continueWorkerQueue({
    workerId,
    reviewedReportId: reviewedReportId || null,
    source: 'desktop',
    metadata,
  });
}

export async function reorderDesktopFleetTasks(workerId: string, taskIds: string[]) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.reorderTasks) {
    return null;
  }
  return bridge.fleet.reorderTasks({ workerId, taskIds });
}

export async function redirectDesktopFleetTask(taskId: string, direction: string, metadata?: Record<string, unknown>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.redirectTask) {
    return null;
  }
  return bridge.fleet.redirectTask({ taskId, direction, source: 'manager', metadata });
}

export async function updateDesktopFleetTaskStatus(taskId: string, status: string, metadata?: Record<string, unknown>) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.updateTaskStatus) {
    return null;
  }
  return bridge.fleet.updateTaskStatus({ taskId, status, metadata });
}

export async function createDesktopFleetTaskReport(
  taskId: string,
  summary: string,
  options?: {
    status?: string;
    evidence?: unknown[];
    artifacts?: unknown[];
    blockers?: unknown[];
    confidence?: string | null;
    nextSuggestedAction?: string | null;
    raw?: Record<string, unknown>;
  },
) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.createTaskReport) {
    return null;
  }
  return bridge.fleet.createTaskReport({
    taskId,
    summary,
    status: options?.status || 'completed',
    evidence: options?.evidence || [],
    artifacts: options?.artifacts || [],
    blockers: options?.blockers || [],
    confidence: options?.confidence || null,
    nextSuggestedAction: options?.nextSuggestedAction || null,
    raw: options?.raw || {},
  });
}

export async function searchDesktopFleetReports(query?: string, options?: { worker?: string; status?: string; limit?: number }) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.searchReports) {
    return null;
  }
  return bridge.fleet.searchReports({
    query: query || null,
    worker: options?.worker || null,
    status: options?.status || null,
    limit: options?.limit || 20,
  });
}

export async function upsertDesktopFleetWorkspaceBinding(
  workspaceId: string,
  machineId: string,
  localPath: string,
  options?: { label?: string | null; status?: string; metadata?: Record<string, unknown> },
) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.upsertWorkspaceBinding) {
    return null;
  }
  return bridge.fleet.upsertWorkspaceBinding({
    workspaceId,
    machineId,
    localPath,
    label: options?.label || null,
    status: options?.status || 'active',
    metadata: options?.metadata || {},
  });
}

export async function requestDesktopFleetToolGrant(payload: {
  targetKind?: string;
  targetId: string;
  toolPackId: string;
  reason: string;
  taskId?: string | null;
  requestedTurns?: number;
  requestedBy?: string | null;
}) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.requestToolGrant) {
    return null;
  }
  return bridge.fleet.requestToolGrant(payload);
}

export async function decideDesktopFleetToolGrant(
  grantId: string,
  approved: boolean,
  options?: { approvedTurns?: number | null; approvedBy?: string | null },
) {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.decideToolGrant) {
    return null;
  }
  return bridge.fleet.decideToolGrant({
    grantId,
    approved,
    approvedTurns: options?.approvedTurns || null,
    approvedBy: options?.approvedBy || null,
  });
}

export async function installDesktopVoicePack(packId: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.voicePacks?.install) {
    return null;
  }
  const payload = await bridge.voicePacks.install(packId);
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function removeDesktopVoicePack(packId: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.voicePacks?.remove) {
    return null;
  }
  const payload = await bridge.voicePacks.remove(packId);
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function setDesktopVoiceDefaultEngine(engine: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.voicePacks?.setDefaultEngine) {
    return null;
  }
  const payload = await bridge.voicePacks.setDefaultEngine(engine);
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function loadDesktopRuntimeStatus() {
  const bridge = getDesktopBridge();
  if (!bridge) {
    return null;
  }
  return bridge.getRuntimeStatus();
}

export function subscribeDesktopRuntime(callback: (event: DesktopBridgeEvent) => void) {
  const bridge = getDesktopBridge();
  if (!bridge) {
    return () => {};
  }
  return bridge.onRuntimeEvent(callback);
}

export async function checkDesktopUpdates(options?: { force?: boolean }) {
  const bridge = getDesktopBridge();
  if (!bridge?.updates?.check) {
    return null;
  }
  return bridge.updates.check(options);
}

export async function installDesktopUpdate() {
  const bridge = getDesktopBridge();
  if (!bridge?.updates?.install) {
    return null;
  }
  return bridge.updates.install();
}

export async function openDesktopPath(targetPath: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.shell?.openPath) {
    return null;
  }
  return bridge.shell.openPath(targetPath);
}

export async function openDesktopChromeExtensions() {
  const bridge = getDesktopBridge();
  if (!bridge?.shell?.openChromeExtensions) {
    return null;
  }
  return bridge.shell.openChromeExtensions();
}

export async function updateDesktopFleetWorkerQueuePolicy(workerId: string, queuePolicy: 'review_required' | 'auto_continue_success') {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.renameWorker) return null;
  return bridge.fleet.renameWorker({ workerId, queuePolicy, metadata: { updated_from: 'desktop_fleet_panel' } });
}

export async function runDesktopEditCommand(command: string, query?: string) {
  const bridge = getDesktopBridge();
  return bridge?.shell?.editCommand?.({ command, query });
}

export async function runDesktopZoomCommand(command: 'in' | 'out' | 'reset') {
  const bridge = getDesktopBridge();
  return bridge?.shell?.zoom?.({ command });
}

export async function loadDesktopDiagnostics() {
  const bridge = getDesktopBridge();
  return bridge?.shell?.diagnostics?.();
}

export async function requestDesktopExit(mode: 'default' | 'keep_running' | 'stop_everything' | 'force' | 'cancel') {
  const bridge = getDesktopBridge();
  return bridge?.shell?.requestExit?.({ mode });
}

export function subscribeDesktopExitRequest(callback: (payload: Record<string, any>) => void) {
  const bridge = getDesktopBridge();
  return bridge?.shell?.onExitRequested?.(callback) || (() => undefined);
}

export async function listDesktopRemoteAccountDesktops(): Promise<DesktopRemoteAccountDesktop[]> {
  return [];
}

export async function loadDesktopFleetYggdrasilStatus(): Promise<DesktopFleetYggdrasilStatus | null> {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.yggdrasilStatus) return null;
  return bridge.fleet.yggdrasilStatus();
}

export async function bootstrapDesktopFleetYggdrasil(): Promise<Record<string, unknown> | null> {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.yggdrasilBootstrap) return null;
  return bridge.fleet.yggdrasilBootstrap();
}

export async function createDesktopFleetYggdrasilPairing(
  displayName?: string | null,
  expiresInSeconds = 30 * 60,
): Promise<DesktopFleetYggdrasilPairing | null> {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.yggdrasilCreatePairing) return null;
  return bridge.fleet.yggdrasilCreatePairing({ displayName: displayName || null, expiresInSeconds });
}

export async function joinDesktopFleetYggdrasil(
  pairingToken: string,
  deviceName?: string | null,
): Promise<DesktopFleetYggdrasilJoinResult | null> {
  const bridge = getDesktopBridge();
  if (!bridge?.fleet?.yggdrasilJoin) return null;
  return bridge.fleet.yggdrasilJoin({ pairingToken, deviceName: deviceName || null });
}

export async function createDesktopShortcut() {
  const bridge = getDesktopBridge();
  if (!bridge?.shell?.createDesktopShortcut) {
    return null;
  }
  return bridge.shell.createDesktopShortcut();
}

export async function copyDesktopText(textValue: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.clipboard?.writeText) {
    return null;
  }
  return bridge.clipboard.writeText(textValue);
}

export async function loadDesktopMemory() {
  const bridge = getDesktopBridge();
  if (!bridge?.memory?.read) {
    return null;
  }
  return bridge.memory.read();
}

export async function saveDesktopMemory(content: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.memory?.write) {
    return null;
  }
  return bridge.memory.write({ content });
}

export async function loadDesktopSidebarState() {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.readState) {
    return null;
  }
  return bridge.sidebar.readState();
}

export async function saveDesktopSidebarState(state: DesktopSidebarState | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.writeState) {
    return null;
  }
  return bridge.sidebar.writeState({ state });
}

export async function pickDesktopFolder(defaultPath?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.pickFolder) {
    return null;
  }
  return bridge.sidebar.pickFolder({ defaultPath: defaultPath || null });
}

export async function createDesktopFolder(parentPath?: string | null, folderName?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.createFolder) {
    return null;
  }
  return bridge.sidebar.createFolder({
    parentPath: parentPath || null,
    folderName: folderName || null,
  });
}

export async function getDesktopPathStatus(targetPath?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.pathStatus) {
    return null;
  }
  return bridge.sidebar.pathStatus({ path: targetPath || null });
}

export async function getDesktopGitRepoInfo(targetPath?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.gitRepoInfo) {
    return null;
  }
  return bridge.sidebar.gitRepoInfo({ path: targetPath || null });
}

export async function checkoutDesktopGitBranch(targetPath?: string | null, branchName?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.checkoutBranch) {
    return null;
  }
  return bridge.sidebar.checkoutBranch({ path: targetPath || null, branch: branchName || null });
}

export async function hideDesktopWindowForSleepMode() {
  const bridge = getDesktopBridge();
  if (!bridge?.window?.hideForSleepMode) {
    return null;
  }
  return bridge.window.hideForSleepMode();
}
