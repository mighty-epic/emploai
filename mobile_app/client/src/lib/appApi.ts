import { requestJson } from '../../lib/appHttp';

export type AppProfile = {
  user_id: number;
  current_session_id?: string | null;
  current_model?: string | null;
  current_variant?: string | null;
  device_id?: string | null;
  device_name?: string | null;
  device_platform?: string | null;
};

export type SessionSummary = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  model: string;
  message_count: number;
  workspace?: string;
  latest_preview?: string | null;
  origin_channels: string[];
};

export type SessionMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
  source_format?: string | null;
  display_label?: string | null;
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
  name: string;
  prompt: string;
  schedule?: string | null;
  enabled: boolean;
  run_count?: number | null;
  error_count?: number | null;
  next_run_at?: string | null;
  last_run_at?: string | null;
  interval_seconds?: number | null;
  due?: boolean;
  owner_user_id?: number | null;
};

export type CronFeedItem = {
  id: string;
  timestamp?: string | null;
  kind: 'announcement' | 'result';
  content: string;
  session_id?: string | null;
  session_name?: string | null;
  job_id?: string | null;
  job_name?: string | null;
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
  status: 'active' | 'completed' | 'blocked' | 'paused';
  state: 'idle' | 'candidate' | 'active' | 'reassessing' | 'blocked_waiting_user' | 'completed_collapsed';
  display_mode: 'active' | 'completed_collapsed';
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
  task_board?: TaskBoard | null;
  completed_task_boards: TaskBoard[];
};

export type AgentConfigurePayload = {
  model?: string;
  variant?: string;
  planner_model?: string | null;
  max_turns?: number;
  workspace?: string;
  auto_reply_enabled?: boolean;
  verbose_mode?: boolean;
  bridge_enabled?: boolean;
  heartbeat_enabled?: boolean;
  heartbeat_interval_seconds?: number;
  headless_mode?: 'headless' | 'headed';
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

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export async function fetchProfile(apiBaseUrl: string, token: string) {
  return requestJson<AppProfile>({
    scope: 'profile.me',
    url: `${apiBaseUrl}/api/app/me`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessions(apiBaseUrl: string, token: string) {
  return requestJson<SessionSummary[]>({
    scope: 'sessions.list',
    url: `${apiBaseUrl}/api/app/sessions`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessionDetail(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<SessionDetail>({
    scope: 'sessions.detail',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}`,
    init: { headers: authHeaders(token) },
  });
}

export async function searchSessions(
  apiBaseUrl: string,
  token: string,
  query: string,
  limit = 40,
) {
  return requestJson<{ results: SessionSearchResult[] }>({
    scope: 'sessions.search',
    url: `${apiBaseUrl}/api/app/sessions/search`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query, limit }),
    },
  });
}

export async function appendSessionTimelineEvent(
  apiBaseUrl: string,
  token: string,
  sessionId: string,
  payload: {
    kind: string;
    title: string;
    content: string;
    tone?: 'neutral' | 'accent' | 'warn' | 'error';
    channel?: 'telegram' | 'app' | 'system';
    source_format?: string;
    metadata?: Record<string, unknown>;
    source_client_id?: string;
  }
) {
  return requestJson<{ event: SessionTimelineEvent }>({
    scope: 'session-timeline-append',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/timeline`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
}

export async function createSession(
  apiBaseUrl: string,
  token: string,
  nameOrOptions?: string | { name?: string; workspace?: string },
  workspaceArg?: string,
) {
  const payload = typeof nameOrOptions === 'string'
    ? { name: nameOrOptions, workspace: workspaceArg }
    : {
        name: nameOrOptions?.name,
        workspace: nameOrOptions?.workspace,
      };
  return requestJson<{ session: SessionDetail }>({
    scope: 'sessions.create',
    url: `${apiBaseUrl}/api/app/sessions`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
}

export async function activateSession(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<SessionDetail>({
    scope: 'sessions.activate',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}/activate`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchJobs(apiBaseUrl: string, token: string) {
  return requestJson<ScheduledJob[]>({
    scope: 'jobs.list',
    url: `${apiBaseUrl}/api/app/jobs`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchCronFeed(apiBaseUrl: string, token: string) {
  return requestJson<CronFeedItem[]>({
    scope: 'cron.feed',
    url: `${apiBaseUrl}/api/app/cron/feed`,
    init: { headers: authHeaders(token) },
  });
}

export async function createJob(apiBaseUrl: string, token: string, payload: { name: string; prompt: string; schedule: string }) {
  return requestJson<ScheduledJob>({
    scope: 'jobs.create',
    url: `${apiBaseUrl}/api/app/jobs`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function actOnJob(apiBaseUrl: string, token: string, jobId: string, action: 'run' | 'enable' | 'disable' | 'delete') {
  const method = action === 'delete' ? 'DELETE' : 'POST';
  const url = action === 'delete'
    ? `${apiBaseUrl}/api/app/jobs/${jobId}`
    : `${apiBaseUrl}/api/app/jobs/${jobId}/${action}`;

  return requestJson({
    scope: `jobs.${action}`,
    url,
    init: {
      method,
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentOverview(
  apiBaseUrl: string,
  token: string,
  params?: { sessionId?: string; historyCount?: number; analyticsDays?: number }
) {
  const query = new URLSearchParams();
  if (params?.sessionId) query.set('session_id', params.sessionId);
  if (params?.historyCount) query.set('history_count', String(params.historyCount));
  if (params?.analyticsDays) query.set('analytics_days', String(params.analyticsDays));

  return requestJson<AgentOverview>({
    scope: 'agent.overview',
    url: `${apiBaseUrl}/api/app/agent/overview${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchTaskBoard(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<{ task_board?: TaskBoard | null }>({
    scope: 'agent.taskboard.get',
    url: `${apiBaseUrl}/api/app/agent/task-board${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function forceTaskBoardReassess(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.taskboard.reassess',
    url: `${apiBaseUrl}/api/app/agent/task-board/reassess${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function configureAgent(
  apiBaseUrl: string,
  token: string,
  payload: AgentConfigurePayload,
  sessionId?: string
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.configure',
    url: `${apiBaseUrl}/api/app/agent/configure${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function fetchBridgeStatus(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<BridgeStatus>({
    scope: 'agent.bridge.status',
    url: `${apiBaseUrl}/api/app/agent/bridge-status${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchAgentConfig(apiBaseUrl: string, token: string, key?: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (key) query.set('key', key);
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<{ items: ConfigEntry[] }>({
    scope: 'agent.config.list',
    url: `${apiBaseUrl}/api/app/agent/config${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function updateAgentConfig(
  apiBaseUrl: string,
  token: string,
  payload: { key: string; value: unknown },
  sessionId?: string
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<ConfigEntry>({
    scope: 'agent.config.update',
    url: `${apiBaseUrl}/api/app/agent/config${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function searchAgentMemory(apiBaseUrl: string, token: string, query: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<{ query: string; results: MemorySearchResult[] }>({
    scope: 'agent.memory.search',
    url: `${apiBaseUrl}/api/app/agent/memory/search${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    },
    timeoutMs: 30000,
  });
}

export async function appendAgentMemoryNote(apiBaseUrl: string, token: string, note: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.memory.note',
    url: `${apiBaseUrl}/api/app/agent/memory/note${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ note }),
    },
    timeoutMs: 30000,
  });
}

export async function clearAgentPendingFiles(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.files.clear',
    url: `${apiBaseUrl}/api/app/agent/files/clear${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function forgetLastAgentMessage(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.forget',
    url: `${apiBaseUrl}/api/app/agent/forget-last${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function resetAgentContext(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.reset',
    url: `${apiBaseUrl}/api/app/agent/reset${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function compactAgentContext(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.compact',
    url: `${apiBaseUrl}/api/app/agent/compact${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentSkills(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<{ items: SkillSummary[] }>({
    scope: 'agent.skills.list',
    url: `${apiBaseUrl}/api/app/agent/skills${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function activateAgentSkill(
  apiBaseUrl: string,
  token: string,
  payload: { name: string; active?: boolean },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.skills.activate',
    url: `${apiBaseUrl}/api/app/agent/skills/activate${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function validateAgentSkill(apiBaseUrl: string, token: string, name: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SkillValidation>({
    scope: 'agent.skills.validate',
    url: `${apiBaseUrl}/api/app/agent/skills/validate${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name, active: true }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchSubAgents(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SubAgentStatus>({
    scope: 'agent.subagents.list',
    url: `${apiBaseUrl}/api/app/agent/subagents${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function spawnSubAgent(
  apiBaseUrl: string,
  token: string,
  payload: { prompt: string; headless?: boolean; max_turns?: number },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.subagents.spawn',
    url: `${apiBaseUrl}/api/app/agent/subagents${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function controlAgentRun(
  apiBaseUrl: string,
  token: string,
  action: 'pause' | 'stop' | 'restart',
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: `agent.control.${action}`,
    url: `${apiBaseUrl}/api/app/agent/control/${action}${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}
