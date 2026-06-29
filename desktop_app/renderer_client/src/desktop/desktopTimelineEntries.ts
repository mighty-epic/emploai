import type { SessionTimelineEvent } from '@/lib/appApi';
import { timelineEventTimestampValue } from '@/desktop/conversationTimeline';
import { labelForMessage, type DesktopMessage } from '@/desktop/desktopMessages';

export type TimelineEntry =
  | {
      id: string;
      kind: 'message';
      sourceMessageIndex: number;
      timestamp: string | null;
      sortValue: number;
      label: string;
      eyebrow: string;
      body: string;
      tone: 'neutral' | 'accent' | 'warn' | 'error';
    }
  | {
      id: string;
      kind: 'event';
      timestamp: string | null;
      sortValue: number;
      label: string;
      eyebrow: string;
      body: string;
      tone: 'neutral' | 'accent' | 'warn' | 'error';
    };

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

  const eventEntries: TimelineEntry[] = timelineEvents.map((event, index) => ({
    id: event.id || `event-${event.timestamp || 'pending'}-${index}`,
    kind: 'event',
    timestamp: event.timestamp || null,
    sortValue: timelineEventTimestampValue(event) ?? Number.MAX_SAFE_INTEGER + index,
    label: event.title || 'Event',
    eyebrow: event.kind ? event.kind.replace(/_/g, ' ') : 'Event',
    body: String(event.content || ''),
    tone: event.tone || 'neutral',
  }));

  return [...messageEntries, ...eventEntries].sort((left, right) => {
    if (left.sortValue !== right.sortValue) {
      return left.sortValue - right.sortValue;
    }
    if (left.kind !== right.kind) {
      return left.kind === 'message' ? -1 : 1;
    }
    return left.id.localeCompare(right.id);
  });
}
