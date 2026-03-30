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

export type SessionDetail = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  model: string;
  variant: string;
  agent_mode: string;
  workspace?: string;
  messages: SessionMessage[];
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

export async function createSession(apiBaseUrl: string, token: string, name?: string) {
  return requestJson<{ session: SessionDetail }>({
    scope: 'sessions.create',
    url: `${apiBaseUrl}/api/app/sessions`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name }),
    },
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
