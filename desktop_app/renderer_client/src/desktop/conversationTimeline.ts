import type { SessionTimelineEvent } from '@/lib/appApi';

const TIMELINE_BASE64_KEYS = new Set(['image_base64', 'base64', 'image_data', 'data', 'screenshot']);

export function truncateTimelinePreview(value: unknown, limit = 220) {
  const text = String(value ?? '').trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, Math.max(0, limit - 3))}...`;
}

export function safeTimelineValuePreview(value: unknown, limit = 80) {
  if (Array.isArray(value)) {
    return truncateTimelinePreview(`Array[${value.length}]`, limit);
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>).filter((key) => !TIMELINE_BASE64_KEYS.has(key));
    return truncateTimelinePreview(keys.slice(0, 4).join(', ') || 'object', limit);
  }
  return truncateTimelinePreview(value, limit);
}

export function toolArgsPreview(toolArgs: Record<string, any>) {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(toolArgs || {}).slice(0, 4)) {
    const valueString = String(value ?? '');
    if (TIMELINE_BASE64_KEYS.has(key) && valueString.length > 100) {
      continue;
    }
    parts.push(`${key}: ${safeTimelineValuePreview(value, 80)}`);
  }
  return truncateTimelinePreview(parts.join(', '), 240);
}

export function toolResultPreview(toolResult: unknown) {
  if (toolResult && typeof toolResult === 'object' && !Array.isArray(toolResult)) {
    const resultRecord = toolResult as Record<string, unknown>;
    if ('error' in resultRecord) {
      return {
        tone: 'error' as const,
        text: `Error: ${truncateTimelinePreview(resultRecord.error, 220)}`,
      };
    }
    const safeKeys = Object.keys(resultRecord).filter((key) => !TIMELINE_BASE64_KEYS.has(key));
    return {
      tone: 'accent' as const,
      text: truncateTimelinePreview(safeKeys.slice(0, 6).join(', ') || 'ok', 220),
    };
  }
  if (typeof toolResult === 'string') {
    const clean = truncateTimelinePreview(toolResult, 220);
    return {
      tone: clean.startsWith('Error') ? ('error' as const) : ('accent' as const),
      text: clean || 'ok',
    };
  }
  return {
    tone: 'accent' as const,
    text: safeTimelineValuePreview(toolResult, 220) || 'ok',
  };
}

export function createLocalToolTimelineEvent(payload: Record<string, any>): SessionTimelineEvent | null {
  const toolName = String(payload.tool_name || '').trim();
  if (!toolName) {
    return null;
  }
  const argsPreview = toolArgsPreview((payload.tool_args || {}) as Record<string, any>);
  const resultPreview = toolResultPreview(payload.tool_result);
  const durationMs = Number(payload.duration_ms || 0);
  const callPreview = argsPreview ? `${toolName}(${argsPreview})` : `${toolName}()`;
  return {
    id: '',
    kind: 'tool',
    title: `Tool · ${toolName}`,
    content: `${callPreview}\n-> ${resultPreview.text} (${durationMs.toFixed(0)}ms)`,
    tone: resultPreview.tone,
    timestamp: typeof payload.timestamp === 'string' && payload.timestamp.trim()
      ? payload.timestamp.trim()
      : new Date().toISOString(),
    channel: 'app',
    source_format: 'app_text',
    metadata: payload,
  };
}

export function timelineEventFallbackFingerprint(event: SessionTimelineEvent, includeTimestamp = true) {
  return [
    String(event.kind || 'note'),
    String(event.title || 'Event'),
    String(event.content || ''),
    includeTimestamp ? String(event.timestamp || '') : '',
    String(event.tone || 'neutral'),
  ].join('|');
}

export function timelineEventMergeKey(event: SessionTimelineEvent) {
  const kind = String(event.kind || '').trim().toLowerCase();
  if (kind === 'tool') {
    return `fp:${timelineEventFallbackFingerprint(event, false)}`;
  }
  const id = String(event.id || '').trim();
  if (id) {
    return `id:${id}`;
  }
  return `fp:${timelineEventFallbackFingerprint(event, true)}`;
}

export function timelineEventTimestampValue(event: SessionTimelineEvent) {
  if (!event.timestamp) {
    return null;
  }
  const numeric = Date.parse(event.timestamp);
  return Number.isFinite(numeric) ? numeric : null;
}

export function normalizeTimelineEvents(events: SessionTimelineEvent[]) {
  const unique: SessionTimelineEvent[] = [];
  const seen = new Set<string>();
  for (const event of events) {
    const key = timelineEventMergeKey(event);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(event);
  }
  return unique
    .map((event, index) => ({
      event,
      index,
      timestamp: timelineEventTimestampValue(event),
    }))
    .sort((left, right) => {
      if (left.timestamp != null && right.timestamp != null && left.timestamp !== right.timestamp) {
        return left.timestamp - right.timestamp;
      }
      if (left.timestamp != null && right.timestamp == null) {
        return -1;
      }
      if (left.timestamp == null && right.timestamp != null) {
        return 1;
      }
      return left.index - right.index;
    })
    .map((entry) => entry.event);
}

export function mergeTimelineEventState(previous: SessionTimelineEvent[], incoming: SessionTimelineEvent[]) {
  const next = normalizeTimelineEvents(incoming);
  const seen = new Set(next.map((event) => timelineEventMergeKey(event)));
  for (const event of previous) {
    const kind = String(event.kind || '').trim().toLowerCase();
    if (kind !== 'tool' && kind !== 'command') {
      continue;
    }
    const key = timelineEventMergeKey(event);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    next.push(event);
  }
  return normalizeTimelineEvents(next);
}
