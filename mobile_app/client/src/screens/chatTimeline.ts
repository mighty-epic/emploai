import type { SessionTimelineEvent } from '@/lib/appApi';

export type ChatEvent = {
  type: string;
  session_id?: string;
  message?: string;
  payload?: Record<string, any>;
};

export function mergeToolLogEntries(entries: string[]) {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const entry of entries) {
    const normalized = entry.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    merged.push(normalized);
    if (merged.length >= 40) break;
  }
  return merged;
}

export function formatConfigValue(value: unknown) {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function formatRealtimeToolEntry(payload: Record<string, any> | undefined) {
  if (!payload) return '';
  if (typeof payload.formatted === 'string' && payload.formatted.trim()) {
    return payload.formatted.trim();
  }

  const toolName = String(payload.tool_name || 'tool');
  const durationMs = Number(payload.duration_ms || 0);
  let resultPreview = '';
  try {
    resultPreview = JSON.stringify(payload.tool_result ?? {});
  } catch {
    resultPreview = String(payload.tool_result ?? '');
  }
  if (resultPreview.length > 240) {
    resultPreview = `${resultPreview.slice(0, 237)}...`;
  }
  return `🔧 ${toolName} → ${resultPreview || 'ok'} (${Math.round(durationMs)}ms)`;
}

export function formatLogLine(message: string, level?: string) {
  const normalized = message.trim();
  if (!normalized) return '';
  if (level === 'error') return `[error] ${normalized}`;
  if (level === 'warn') return `[warn] ${normalized}`;
  return normalized;
}

export function isUserVisibleRuntimeMessage(message: unknown) {
  const normalized = String(message || '').trim().toLowerCase();
  if (!normalized) return false;
  if (normalized.includes('planner verifier') || normalized.includes('final quality guard')) return false;
  if (normalized.includes('candidate final:')) return false;
  return true;
}

export function formatTimelineLogEntry(event: SessionTimelineEvent) {
  const title = String(event.title || event.kind || 'Event').trim();
  const content = String(event.content || '').trim();
  if (title && content) return `[${title}] ${content}`;
  return content || title;
}

export function timelineEventsToLogLines(events: SessionTimelineEvent[] | undefined) {
  if (!Array.isArray(events)) return [];
  return events
    .filter(isUserVisibleTimelineEvent)
    .slice(-40)
    .reverse()
    .map((event) => formatTimelineLogEntry(event))
    .filter(Boolean);
}

export function timelineEventFingerprint(event: SessionTimelineEvent) {
  const explicitId = String(event.id || '').trim();
  if (explicitId) return explicitId;
  return [
    event.kind || 'event',
    event.title || '',
    event.content || '',
    event.timestamp || '',
  ].join('|');
}

export function isUserVisibleTimelineEvent(event?: SessionTimelineEvent | null) {
  if (!event) return false;
  const metadata = (event.metadata || {}) as Record<string, unknown>;
  const visibility = String(metadata.visibility || '').trim().toLowerCase();
  const sourceFormat = String(event.source_format || '').trim().toLowerCase();
  const kind = String(event.kind || '').trim().toLowerCase();
  const title = String(event.title || '').trim().toLowerCase();
  const content = String(event.content || '').trim().toLowerCase();
  if (visibility === 'internal' || visibility === 'debug' || metadata.internal === true) return false;
  if (sourceFormat === 'app_internal' || sourceFormat === 'internal') return false;
  const plannerKeys = [
    'candidate_final_preview',
    'auto_continue_count',
    'auto_continue_limit',
    'continuation_instruction',
    'retry_instruction',
    'failed_obligation',
    'evidence_gap',
    'must_use_tool',
  ];
  if (plannerKeys.some((key) => Object.prototype.hasOwnProperty.call(metadata, key))) return false;
  if (title.includes('planner verifier') || title.includes('final quality guard')) return false;
  if (content.includes('planner verifier') || content.includes('final quality guard')) return false;
  if (content.includes('candidate final:') && kind === 'runtime') return false;
  if (kind === 'planner' || kind === 'planner_verdict' || kind === 'auto_continue') return false;
  return true;
}

export function mergeTimelineEvents(previous: SessionTimelineEvent[], incoming: SessionTimelineEvent[]) {
  const seen = new Set<string>();
  const merged: SessionTimelineEvent[] = [];
  [...previous, ...incoming].filter(isUserVisibleTimelineEvent).forEach((event) => {
    const key = timelineEventFingerprint(event);
    if (!key || seen.has(key)) return;
    seen.add(key);
    merged.push(event);
  });
  return merged.slice(-160);
}

export function realtimeToolEventToTimelineEvent(payload: Record<string, any> | undefined, sessionId?: string): SessionTimelineEvent | null {
  const entry = formatRealtimeToolEntry(payload);
  if (!entry) return null;
  const toolName = String(payload?.tool_name || payload?.name || 'Tool').trim() || 'Tool';
  const level = String(payload?.level || '').toLowerCase();
  const timestamp = new Date().toISOString();
  return {
    id: String(payload?.id || payload?.event_id || `${sessionId || 'session'}-tool-${toolName}-${timestamp}-${entry.slice(0, 24)}`),
    kind: 'tool',
    title: toolName,
    content: entry,
    tone: level === 'error' ? 'error' : level === 'warn' ? 'warn' : 'neutral',
    timestamp,
    channel: 'app',
    source_format: 'app_system',
    metadata: payload || {},
  };
}

export function realtimeLogEventToTimelineEvent(data: ChatEvent, sessionId?: string): SessionTimelineEvent | null {
  const message = String(data.payload?.message || data.message || '').trim();
  if (!isUserVisibleRuntimeMessage(message)) return null;
  if (!message) return null;
  const level = typeof data.payload?.level === 'string' ? data.payload.level : undefined;
  const formatted = formatLogLine(message, level);
  if (!formatted) return null;
  const timestamp = new Date().toISOString();
  return {
    id: String(data.payload?.id || data.payload?.event_id || `${sessionId || 'session'}-${data.type}-${timestamp}-${formatted.slice(0, 24)}`),
    kind: data.type === 'status' ? 'status' : 'log',
    title: data.type === 'status' ? 'Status' : 'Run',
    content: formatted,
    tone: level === 'error' ? 'error' : level === 'warn' ? 'warn' : 'neutral',
    timestamp,
    channel: 'app',
    source_format: 'app_system',
    metadata: data.payload || {},
  };
}
