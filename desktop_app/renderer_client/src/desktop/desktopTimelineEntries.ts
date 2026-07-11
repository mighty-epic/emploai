import type { SessionTimelineEvent } from '@/lib/appApi';
import { timelineEventTimestampValue } from '@/desktop/conversationTimeline';
import { labelForMessage, type DesktopMessage } from '@/desktop/desktopMessages';

export type TimelineMessageEntry = {
  id: string;
  kind: 'message';
  sourceMessageIndex: number;
  timestamp: string | null;
  sortValue: number;
  label: string;
  eyebrow: string;
  body: string;
  tone: 'neutral' | 'accent' | 'warn' | 'error';
};

export type TimelineEventEntry = {
  id: string;
  kind: 'event';
  timestamp: string | null;
  sortValue: number;
  label: string;
  eyebrow: string;
  body: string;
  tone: 'neutral' | 'accent' | 'warn' | 'error';
  metadata?: Record<string, any>;
};

export type TimelineRunEntry = {
  id: string;
  kind: 'run';
  runId: string;
  runSequence: number | null;
  timestamp: string | null;
  sortValue: number;
  label: string;
  eyebrow: string;
  body: string;
  tone: 'neutral' | 'accent' | 'warn' | 'error';
  eventCount: number;
  toolCount: number;
  commandCount: number;
  errorCount: number;
  events: TimelineEventEntry[];
  metadata?: Record<string, any>;
};

export type TimelineEntry = TimelineMessageEntry | TimelineEventEntry | TimelineRunEntry;

export type TranscriptMessageEntry = {
  fullIndex: number;
  message: DesktopMessage;
};

export function messageTimestampValue(message: DesktopMessage) {
  if (!message.timestamp) {
    return null;
  }
  const numeric = Date.parse(message.timestamp);
  return Number.isFinite(numeric) ? numeric : null;
}

function liveCommandId(event: SessionTimelineEvent) {
  const metadata = (event.metadata || {}) as Record<string, any>;
  if (String(event.kind || '').toLowerCase() !== 'command' || metadata.live_command !== true) {
    return '';
  }
  return String(metadata.command_id || '').trim();
}

function runSequenceFromEvents(events: TimelineEventEntry[]) {
  for (const event of events) {
    const numeric = Number(event.metadata?.run_sequence ?? event.metadata?.task_id ?? 0);
    if (Number.isFinite(numeric) && numeric > 0) {
      return numeric;
    }
  }
  return null;
}

function shouldGroupRunEvent(entry: TimelineEventEntry) {
  if (!entry.metadata?.run_id || entry.metadata?.live_command === true) {
    return false;
  }
  const kind = String(entry.eyebrow || '').trim().toLowerCase();
  return kind === 'tool' || kind === 'command' || kind === 'runtime';
}

function buildRunEntry(runId: string, events: TimelineEventEntry[], fallbackIndex: number): TimelineEntry {
  const ordered = [...events].sort((left, right) => left.sortValue - right.sortValue);
  const first = ordered[0] || events[0];
  const latest = ordered[ordered.length - 1] || first;
  const runSequence = runSequenceFromEvents(ordered);
  const toolCount = ordered.filter((event) => String(event.eyebrow || '').toLowerCase() === 'tool').length;
  const commandCount = ordered.filter((event) => String(event.eyebrow || '').toLowerCase() === 'command').length;
  const errorCount = ordered.filter((event) => event.tone === 'error').length;
  const warnCount = ordered.filter((event) => event.tone === 'warn').length;
  const title = runSequence ? `Run #${runSequence}` : `Run ${runId.slice(-8)}`;
  const preview = latest?.body || latest?.label || `${ordered.length} run events`;
  return {
    id: `run-${runId}`,
    kind: 'run',
    runId,
    runSequence,
    timestamp: latest?.timestamp || first?.timestamp || null,
    sortValue: first?.sortValue ?? Number.MAX_SAFE_INTEGER + fallbackIndex,
    label: title,
    eyebrow: 'run',
    body: preview,
    tone: errorCount > 0 ? 'error' : warnCount > 0 ? 'warn' : 'accent',
    eventCount: ordered.length,
    toolCount,
    commandCount,
    errorCount,
    events: ordered,
    metadata: {
      run_id: runId,
      run_sequence: runSequence,
    },
  };
}

function buildLiveCommandEntry(commandId: string, events: SessionTimelineEvent[], fallbackIndex: number): TimelineEntry {
  const ordered = [...events].sort((left, right) => {
    const leftTime = timelineEventTimestampValue(left) ?? Number.MAX_SAFE_INTEGER;
    const rightTime = timelineEventTimestampValue(right) ?? Number.MAX_SAFE_INTEGER;
    return leftTime - rightTime;
  });
  const first = ordered[0] || events[0];
  const latest = ordered[ordered.length - 1] || first;
  const metadata: Record<string, any> = {
    ...((latest?.metadata || {}) as Record<string, any>),
    command_events: ordered,
  };
  return {
    id: `live-command-${commandId}`,
    kind: 'event',
    timestamp: latest?.timestamp || first?.timestamp || null,
    sortValue: timelineEventTimestampValue(first) ?? Number.MAX_SAFE_INTEGER + fallbackIndex,
    label: latest?.title || `Command · ${commandId}`,
    eyebrow: 'command',
    body: String(latest?.content || metadata.command || ''),
    tone: latest?.tone || 'neutral',
    metadata,
  };
}

export function mergeTimelineEntries(messageRows: TranscriptMessageEntry[], timelineEvents: SessionTimelineEvent[]) {
  const messageEntries: TimelineEntry[] = messageRows
    .filter(({ message }) => !message.localOnly)
    .map(({ message, fullIndex }) => ({
      id: message.messageKey || `message-${message.timestamp || 'pending'}-${fullIndex}`,
      kind: 'message',
      sourceMessageIndex: fullIndex,
      timestamp: message.timestamp || null,
      sortValue: messageTimestampValue(message) ?? Number.MAX_SAFE_INTEGER - 1 + fullIndex,
      label: labelForMessage(message),
      eyebrow: message.role === 'assistant' ? 'Assistant' : message.role === 'system' ? 'System' : 'User',
      body: String(message.content || ''),
      tone: message.role === 'assistant' ? 'accent' : message.role === 'system' ? 'neutral' : 'neutral',
    }));

  const liveCommandGroups = new Map<string, SessionTimelineEvent[]>();
  const regularEvents: SessionTimelineEvent[] = [];
  for (const event of timelineEvents) {
    const commandId = liveCommandId(event);
    if (!commandId) {
      regularEvents.push(event);
      continue;
    }
    const group = liveCommandGroups.get(commandId) || [];
    group.push(event);
    liveCommandGroups.set(commandId, group);
  }

  const eventEntries: TimelineEntry[] = regularEvents.map((event, index) => ({
    id: event.id || `event-${event.timestamp || 'pending'}-${index}`,
    kind: 'event',
    timestamp: event.timestamp || null,
    sortValue: timelineEventTimestampValue(event) ?? Number.MAX_SAFE_INTEGER + index,
    label: event.title || 'Event',
    eyebrow: event.kind ? event.kind.replace(/_/g, ' ') : 'Event',
    body: String(event.content || ''),
    tone: event.tone || 'neutral',
    metadata: (event.metadata || {}) as Record<string, any>,
  }));
  for (const [commandId, events] of liveCommandGroups.entries()) {
    eventEntries.push(buildLiveCommandEntry(commandId, events, eventEntries.length));
  }

  const runGroups = new Map<string, Array<Extract<TimelineEntry, { kind: 'event' }>>>();
  const ungroupedEntries: TimelineEntry[] = [];
  for (const entry of eventEntries) {
    if (entry.kind !== 'event' || !shouldGroupRunEvent(entry)) {
      ungroupedEntries.push(entry);
      continue;
    }
    const runId = String(entry.metadata?.run_id || '').trim();
    const group = runGroups.get(runId) || [];
    group.push(entry);
    runGroups.set(runId, group);
  }
  for (const [runId, events] of runGroups.entries()) {
    ungroupedEntries.push(buildRunEntry(runId, events, ungroupedEntries.length));
  }

  return [...messageEntries, ...ungroupedEntries].sort((left, right) => {
    if (left.sortValue !== right.sortValue) {
      return left.sortValue - right.sortValue;
    }
    if (left.kind !== right.kind) {
      return left.kind === 'message' ? -1 : 1;
    }
    return left.id.localeCompare(right.id);
  });
}
