import type { SessionMessage } from '@/lib/appApi';

export const LOCAL_MESSAGE_SYNC_GRACE_MS = 5 * 60_000;

export type ChatMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string | null;
  displayLabel?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
  localId?: string;
  localSessionId?: string | null;
  pendingLocal?: boolean;
  ephemeralLocal?: boolean;
};

export function toChatMessage(message: SessionMessage): ChatMessage {
  return {
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp,
    displayLabel: message.display_label,
    channel: message.channel,
  };
}

export function normalizeMessageContent(value: string) {
  return value.trim().replace(/\s+/g, ' ');
}

export function messageTimestampMs(message: ChatMessage) {
  const parsed = Date.parse(message.timestamp || '');
  return Number.isFinite(parsed) ? parsed : 0;
}

export function localMessageBelongsToSession(message: ChatMessage, sessionId: string) {
  return !message.localSessionId || message.localSessionId === sessionId;
}

export function isLocalMessageFresh(message: ChatMessage, nowMs = Date.now()) {
  const timestamp = messageTimestampMs(message);
  return !timestamp || nowMs - timestamp <= LOCAL_MESSAGE_SYNC_GRACE_MS;
}

export function messagesMatch(left: ChatMessage, right: ChatMessage) {
  if (left.role !== right.role) return false;
  const leftContent = normalizeMessageContent(left.content || '');
  const rightContent = normalizeMessageContent(right.content || '');
  if (!leftContent || !rightContent) return false;
  if (leftContent === rightContent) return true;
  if (left.role === 'assistant') {
    return leftContent.startsWith(rightContent) || rightContent.startsWith(leftContent);
  }
  return false;
}

export function findMatchingMessageIndex(messages: ChatMessage[], candidate: ChatMessage, usedIndexes?: Set<number>) {
  for (let index = 0; index < messages.length; index += 1) {
    if (usedIndexes?.has(index)) continue;
    if (messagesMatch(messages[index], candidate)) return index;
  }
  return -1;
}

export function shouldPreserveLocalMessage(message: ChatMessage, serverMessages: ChatMessage[], sessionId: string) {
  if (!localMessageBelongsToSession(message, sessionId)) return false;
  if (!isLocalMessageFresh(message)) return false;
  if (findMatchingMessageIndex(serverMessages, message) >= 0) return false;
  return Boolean(
    (message.pendingLocal && message.role === 'user')
    || message.ephemeralLocal
  );
}

export function mergeSessionMessagesWithLocalState(
  serverMessages: ChatMessage[],
  previousMessages: ChatMessage[],
  sessionId: string,
  preservePreviousOrder: boolean
) {
  if (!preservePreviousOrder) {
    const preserved = previousMessages.filter((message) => shouldPreserveLocalMessage(message, serverMessages, sessionId));
    return [...serverMessages, ...preserved];
  }

  const usedServerIndexes = new Set<number>();
  const merged: ChatMessage[] = [];

  for (const previous of previousMessages) {
    const matchingServerIndex = findMatchingMessageIndex(serverMessages, previous, usedServerIndexes);
    if (matchingServerIndex >= 0) {
      usedServerIndexes.add(matchingServerIndex);
      merged.push(serverMessages[matchingServerIndex]);
      continue;
    }
    if (shouldPreserveLocalMessage(previous, serverMessages, sessionId)) {
      merged.push(previous);
    }
  }

  serverMessages.forEach((message, index) => {
    if (!usedServerIndexes.has(index)) {
      merged.push(message);
    }
  });

  return merged;
}

export function mergeLiveMessage(previousMessages: ChatMessage[], incomingMessage: ChatMessage) {
  const next = [...previousMessages];
  const matchingIndex = findMatchingMessageIndex(next, incomingMessage);
  if (matchingIndex >= 0) {
    next[matchingIndex] = incomingMessage;
    return next;
  }
  return [...next, incomingMessage];
}
