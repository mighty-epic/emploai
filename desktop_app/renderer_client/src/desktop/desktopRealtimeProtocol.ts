export type RealtimeChannel = 'chat' | 'voice';

export type DesktopRealtimeEvent = {
  type: string;
  session_id?: string;
  message?: string;
  payload: Record<string, unknown>;
};

export type PendingChatMessage = {
  clientMessageId: string;
  text: string;
  sourceFormat: string;
  interruptPolicy: string;
  sessionId?: string;
  deliveryState?: 'queued' | 'sent';
  modeOptions?: {
    runMode?: string | null;
    planAction?: string | null;
    planAnswer?: Record<string, unknown> | null;
  };
};

const NON_RECONNECTABLE_CLOSE_CODES = new Set([4401, 4403, 4404]);

export function createClientMessageId(clientId: string, now = Date.now(), randomValue = Math.random()) {
  const normalizedClientId = String(clientId || 'desktop').replace(/[^A-Za-z0-9_.:-]+/g, '-').slice(0, 48);
  const randomPart = Math.floor(Math.max(0, Math.min(0.999999999, randomValue)) * 0xFFFFFFFF)
    .toString(36)
    .padStart(7, '0');
  return `${normalizedClientId}:${Math.max(0, Math.trunc(now)).toString(36)}:${randomPart}`.slice(0, 128);
}

export function parseDesktopRealtimeEvent(raw: unknown): DesktopRealtimeEvent {
  const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Realtime event must be an object.');
  }
  const record = parsed as Record<string, unknown>;
  const type = typeof record.type === 'string' ? record.type.trim() : '';
  if (!type || type.length > 96) {
    throw new Error('Realtime event type is missing or invalid.');
  }
  const sessionId = record.session_id;
  if (sessionId !== undefined && sessionId !== null && typeof sessionId !== 'string') {
    throw new Error('Realtime event session_id is invalid.');
  }
  const payload = record.payload;
  if (payload !== undefined && (payload === null || typeof payload !== 'object' || Array.isArray(payload))) {
    throw new Error('Realtime event payload is invalid.');
  }
  return {
    type,
    ...(typeof sessionId === 'string' && sessionId.trim() ? { session_id: sessionId.trim() } : {}),
    ...(typeof record.message === 'string' ? { message: record.message } : {}),
    payload: (payload || {}) as Record<string, unknown>,
  };
}

export function realtimeEventMatchesSession(event: DesktopRealtimeEvent, socketSessionId: string) {
  const expected = String(socketSessionId || '').trim();
  const actual = String(event.session_id || '').trim();
  return !expected || !actual || expected === actual;
}

export function shouldReconnectChatSocket(closeCode: number) {
  return !NON_RECONNECTABLE_CLOSE_CODES.has(Number(closeCode));
}

export function chatReconnectDelayMs(
  attempt: number,
  baseDelayMs: number,
  randomValue = Math.random(),
) {
  const safeAttempt = Math.max(0, Math.min(8, Math.trunc(attempt)));
  const safeBase = Math.max(100, Math.trunc(baseDelayMs));
  const exponential = Math.min(15_000, safeBase * (2 ** safeAttempt));
  const jitter = 0.8 + (Math.max(0, Math.min(1, randomValue)) * 0.4);
  return Math.max(100, Math.round(exponential * jitter));
}
