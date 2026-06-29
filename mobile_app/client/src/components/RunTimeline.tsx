import { StyleSheet, Text, View } from 'react-native';

import type { SessionTimelineEvent } from '@/lib/appApi';
import { formatAbsoluteTime } from '@/lib/time';

export type TimelineChatMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string | null;
  displayLabel?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
  localId?: string;
  pendingLocal?: boolean;
  ephemeralLocal?: boolean;
};

type TimelineRow =
  | { type: 'message'; key: string; sortTime: number; order: number; message: TimelineChatMessage }
  | { type: 'event'; key: string; sortTime: number; order: number; event: SessionTimelineEvent };

type Props = {
  messages: TimelineChatMessage[];
  timelineEvents: SessionTimelineEvent[];
  verboseMode: boolean;
  emptyText: string;
};

function timestampMs(value?: string | null) {
  const parsed = Date.parse(value || '');
  return Number.isFinite(parsed) ? parsed : 0;
}

function labelForMessage(message: TimelineChatMessage) {
  if (message.displayLabel) return message.displayLabel;
  if (message.role === 'assistant') return 'Assistant';
  if (message.role === 'system') return 'System';
  return 'You';
}

function compactJson(value: unknown) {
  if (value === undefined || value === null || value === '') return '';
  const raw = typeof value === 'string' ? value : JSON.stringify(value);
  return raw.length > 220 ? `${raw.slice(0, 217)}...` : raw;
}

function eventKey(event: SessionTimelineEvent) {
  const explicit = String(event.id || '').trim();
  if (explicit) return explicit;
  return [
    event.kind || 'event',
    event.title || '',
    event.content || '',
    event.timestamp || '',
  ].join('|');
}

function shouldShowEvent(event: SessionTimelineEvent, verboseMode: boolean) {
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
  return verboseMode || event.tone === 'warn' || event.tone === 'error';
}

function buildRows(messages: TimelineChatMessage[], events: SessionTimelineEvent[], verboseMode: boolean) {
  const rows: TimelineRow[] = [];
  const seenEvents = new Set<string>();
  const hasTimelineEvents = events.length > 0;

  messages.forEach((message, index) => {
    if (hasTimelineEvents && message.role === 'system' && message.ephemeralLocal) {
      return;
    }
    rows.push({
      type: 'message',
      key: message.localId || `message-${index}-${message.timestamp || ''}-${message.role}`,
      sortTime: timestampMs(message.timestamp),
      order: index * 2,
      message,
    });
  });

  events.forEach((event, index) => {
    if (!shouldShowEvent(event, verboseMode)) return;
    const key = eventKey(event);
    if (seenEvents.has(key)) return;
    seenEvents.add(key);
    rows.push({
      type: 'event',
      key: `event-${key}`,
      sortTime: timestampMs(event.timestamp),
      order: index * 2 + 1,
      event,
    });
  });

  return rows.sort((left, right) => {
    if (left.sortTime && right.sortTime && left.sortTime !== right.sortTime) {
      return left.sortTime - right.sortTime;
    }
    if (left.sortTime !== right.sortTime) {
      return left.sortTime ? 1 : -1;
    }
    return left.order - right.order;
  });
}

function RunEventCard({ event }: { event: SessionTimelineEvent }) {
  const metadata = event.metadata || {};
  const toolName = compactJson(metadata.tool_name || metadata.tool || metadata.name);
  const args = compactJson(metadata.tool_args || metadata.args || metadata.input);
  const result = compactJson(metadata.tool_result || metadata.result || metadata.output);
  const toneStyle =
    event.tone === 'error'
      ? styles.eventError
      : event.tone === 'warn'
        ? styles.eventWarn
        : event.tone === 'accent'
          ? styles.eventAccent
          : null;

  return (
    <View style={[styles.eventCard, toneStyle]}>
      <View style={styles.rowHeader}>
        <View style={styles.rowTitleBlock}>
          <Text style={styles.eventTitle} numberOfLines={1}>{toolName || event.title || event.kind || 'Run event'}</Text>
          <Text style={styles.rowMeta} numberOfLines={1}>
            {event.kind || 'event'}{event.timestamp ? ` · ${formatAbsoluteTime(event.timestamp)}` : ''}
          </Text>
        </View>
      </View>
      {event.content ? <Text style={styles.eventBody}>{event.content}</Text> : null}
      {args ? <Text style={styles.eventPreview}>Args: {args}</Text> : null}
      {result ? <Text style={styles.eventPreview}>Result: {result}</Text> : null}
    </View>
  );
}

function MessageBubble({ message }: { message: TimelineChatMessage }) {
  return (
    <View
      style={[
        styles.bubble,
        message.role === 'user'
          ? styles.userBubble
          : message.role === 'system'
            ? styles.systemBubble
            : styles.assistantBubble,
      ]}
    >
      <View style={styles.rowHeader}>
        <Text style={styles.bubbleRole}>{labelForMessage(message)}</Text>
        {message.timestamp ? (
          <Text style={styles.rowMeta}>{formatAbsoluteTime(message.timestamp)}</Text>
        ) : null}
      </View>
      <Text style={styles.bubbleText}>{message.content}</Text>
    </View>
  );
}

export function RunTimeline({ messages, timelineEvents, verboseMode, emptyText }: Props) {
  const rows = buildRows(messages, timelineEvents, verboseMode);
  if (!rows.length) {
    return (
      <View style={styles.emptyState}>
        <Text style={styles.emptyHint}>{emptyText}</Text>
      </View>
    );
  }

  return (
    <>
      {rows.map((row) => (
        row.type === 'message'
          ? <MessageBubble key={row.key} message={row.message} />
          : <RunEventCard key={row.key} event={row.event} />
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  emptyState: {
    minHeight: 240,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 18,
  },
  emptyHint: {
    color: '#8f9bb4',
    textAlign: 'center',
    lineHeight: 20,
  },
  bubble: {
    borderRadius: 8,
    padding: 14,
    borderWidth: 1,
    gap: 8,
  },
  userBubble: {
    backgroundColor: '#1f3f75',
    borderColor: '#2f5fa8',
    alignSelf: 'flex-end',
    maxWidth: '88%',
  },
  assistantBubble: {
    backgroundColor: '#151b2d',
    borderColor: '#26324f',
    alignSelf: 'stretch',
  },
  systemBubble: {
    backgroundColor: '#1b263b',
    borderColor: '#334155',
    alignSelf: 'stretch',
  },
  rowHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 10,
  },
  rowTitleBlock: {
    flex: 1,
    gap: 2,
  },
  bubbleRole: {
    color: '#dce8ff',
    fontWeight: '800',
    fontSize: 12,
  },
  rowMeta: {
    color: '#7889a8',
    fontSize: 11,
    flexShrink: 0,
  },
  bubbleText: {
    color: '#f7faff',
    fontSize: 15,
    lineHeight: 22,
  },
  eventCard: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2d3854',
    backgroundColor: '#111827',
    padding: 12,
    gap: 7,
  },
  eventAccent: {
    borderColor: '#2d5c88',
    backgroundColor: '#122238',
  },
  eventWarn: {
    borderColor: '#8a641d',
    backgroundColor: '#2d2412',
  },
  eventError: {
    borderColor: '#8b2d37',
    backgroundColor: '#2b151a',
  },
  eventTitle: {
    color: '#edf5ff',
    fontSize: 13,
    fontWeight: '800',
  },
  eventBody: {
    color: '#c8d6ef',
    fontSize: 13,
    lineHeight: 19,
  },
  eventPreview: {
    color: '#91a2c0',
    fontSize: 12,
    lineHeight: 17,
  },
});
