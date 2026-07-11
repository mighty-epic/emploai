import type { SessionMessage } from '@/lib/appApi';

export type DesktopMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string | null;
  displayLabel?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
  sourceFormat?: string | null;
  messageKey?: string;
  pending?: boolean;
  localOnly?: boolean;
  localSessionId?: string | null;
  sourceClientId?: string | null;
  clientMessageId?: string | null;
  runMode?: 'normal' | 'plan' | 'goal' | null;
  runId?: string | null;
  runSequence?: number | null;
  raw?: Record<string, unknown>;
};

function sourceClientIdFromRaw(raw: Record<string, unknown> | undefined) {
  return String(raw?.source_client_id || raw?.client_id || '').trim() || null;
}

function clientMessageIdFromRaw(raw: Record<string, unknown> | undefined) {
  return String(raw?.client_message_id || '').trim() || null;
}

function runSequenceFromRaw(raw: Record<string, unknown> | undefined) {
  const numeric = Number(raw?.run_sequence ?? raw?.task_id ?? 0);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

export function toDesktopMessage(message: SessionMessage): DesktopMessage {
  const raw = (message.raw || {}) as Record<string, unknown>;
  return {
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp,
    displayLabel: message.display_label,
    channel: message.channel,
    sourceFormat: message.source_format,
    sourceClientId: sourceClientIdFromRaw(raw),
    clientMessageId: clientMessageIdFromRaw(raw),
    runMode: message.run_mode || (raw as any).run_mode || null,
    runId: String(raw.run_id || '').trim() || null,
    runSequence: runSequenceFromRaw(raw),
    raw: message.raw,
  };
}

export function messageIdentitySeed(message: Pick<DesktopMessage, 'role' | 'content' | 'timestamp' | 'channel' | 'displayLabel' | 'sourceFormat'>) {
  return [
    message.role || 'assistant',
    message.timestamp || '',
    message.channel || '',
    message.sourceFormat || '',
    message.displayLabel || '',
    message.content || '',
  ].join('|');
}

export function messageIdentitySeedFromSessionMessage(message: SessionMessage) {
  const raw = (message.raw || {}) as Record<string, unknown>;
  const explicitId = String(
    raw.message_id
      || raw.id
      || raw.telegram_message_id
      || raw.app_message_id
      || raw.client_message_id
      || '',
  ).trim();
  if (explicitId) {
    return `message:${explicitId}`;
  }
  return messageIdentitySeed({
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp,
    channel: message.channel,
    displayLabel: message.display_label,
    sourceFormat: message.source_format,
  });
}

export function toDesktopMessages(messages: SessionMessage[]): DesktopMessage[] {
  const occurrenceCounts = new Map<string, number>();
  return messages.map((message) => {
    const seed = messageIdentitySeedFromSessionMessage(message);
    const occurrence = (occurrenceCounts.get(seed) || 0) + 1;
    occurrenceCounts.set(seed, occurrence);
    return {
      ...toDesktopMessage(message),
      messageKey: `${seed}#${occurrence}`,
    };
  });
}

export function toLiveDesktopMessage(message: SessionMessage, existingMessages: DesktopMessage[]) {
  const seed = messageIdentitySeedFromSessionMessage(message);
  const occurrence = existingMessages.reduce((count, current) => {
    const currentSeed = current.messageKey?.replace(/#\d+$/, '') || messageIdentitySeed(current);
    return currentSeed === seed ? count + 1 : count;
  }, 0) + 1;
  return {
    ...toDesktopMessage(message),
    messageKey: `${seed}#${occurrence}`,
  };
}

export function labelForMessage(message: DesktopMessage) {
  if (message.role === 'user' && message.runMode === 'plan') return 'Sent as plan';
  if (message.role === 'user' && message.runMode === 'goal') return 'Sent as goal';
  if (message.displayLabel) return message.displayLabel;
  if (message.role === 'assistant') return 'Assistant';
  if (message.role === 'system') return 'System';
  return 'You';
}

export function extractReferenceTitle(content: string, fallback: string) {
  const headingMatch = content.match(/(?:^|\n)#{1,3}\s+\**([^*\n]+?)\**(?=\n|$)/);
  if (headingMatch?.[1]) {
    return headingMatch[1].trim();
  }

  const firstUsefulLine = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.length > 0 && !/^[-|`]/.test(line));

  if (!firstUsefulLine) {
    return fallback;
  }

  return firstUsefulLine.length > 72 ? `${firstUsefulLine.slice(0, 69)}...` : firstUsefulLine;
}

export function summarizeReferenceContent(content: string) {
  const compact = content
    .replace(/\s+/g, ' ')
    .replace(/[#*_`>-]/g, ' ')
    .trim();

  if (!compact) {
    return 'Detailed reference note';
  }

  return compact.length > 132 ? `${compact.slice(0, 129)}...` : compact;
}

export function isReferenceSidebarMessage(message: DesktopMessage, sessionName: string) {
  if (message.role !== 'assistant' || message.pending) {
    return false;
  }

  const content = String(message.content || '').trim();
  if (content.length < 900) {
    return false;
  }

  const sessionLooksLikeReference = /toolset overview|clarification/i.test(sessionName);
  const contentLooksLikeReference = /agent tools explained|tool categories|tool comparison|how to use these tools|toolset/i.test(content);
  const looksStructured = /(?:^|\n)(?:#{1,3}\s+|\d+\.\s+|- |\|)/.test(content) || content.includes('---');

  return looksStructured && (sessionLooksLikeReference || contentLooksLikeReference);
}

export function summarizeToolPayload(payload: Record<string, any> | undefined) {
  if (!payload) return 'Tool activity';
  if (typeof payload.formatted === 'string' && payload.formatted.trim()) {
    return payload.formatted.trim();
  }

  const toolName = String(payload.tool_name || 'tool');
  const durationMs = Number(payload.duration_ms || 0);
  let preview = '';
  try {
    preview = JSON.stringify(payload.tool_result ?? {});
  } catch {
    preview = String(payload.tool_result ?? '');
  }
  if (preview.length > 180) {
    preview = `${preview.slice(0, 177)}...`;
  }
  return `${toolName} -> ${preview || 'ok'} (${Math.round(durationMs)}ms)`;
}
