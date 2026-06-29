export type DiagnosticLevel = 'info' | 'warn' | 'error';

export type DiagnosticEntry = {
  id: string;
  at: string;
  scope: string;
  level: DiagnosticLevel;
  message: string;
  detail?: string;
};

type DiagnosticListener = () => void;

const MAX_ENTRIES = 250;
const entries: DiagnosticEntry[] = [];
const listeners = new Set<DiagnosticListener>();

function notifyListeners() {
  for (const listener of listeners) {
    listener();
  }
}

function previewText(value: string, maxLength = 420) {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
}

function formatUnknown(value: unknown): string {
  if (value == null) {
    return '';
  }
  if (typeof value === 'string') {
    return value;
  }
  if (value instanceof Error) {
    return previewText(
      [value.name, value.message, value.stack].filter(Boolean).join(' | ')
    );
  }
  try {
    return previewText(JSON.stringify(value));
  } catch {
    return previewText(String(value));
  }
}

export function logDiagnostic(scope: string, message: string, detail?: unknown, level: DiagnosticLevel = 'info') {
  const entry: DiagnosticEntry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    at: new Date().toISOString(),
    scope,
    level,
    message,
    detail: formatUnknown(detail) || undefined,
  };
  entries.unshift(entry);
  if (entries.length > MAX_ENTRIES) {
    entries.length = MAX_ENTRIES;
  }

  const consoleMethod = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
  consoleMethod(`[emploai:${scope}] ${message}${entry.detail ? ` | ${entry.detail}` : ''}`);
  notifyListeners();
}

export function listDiagnostics() {
  return [...entries];
}

export function clearDiagnostics() {
  entries.length = 0;
  notifyListeners();
}

export function subscribeDiagnostics(listener: DiagnosticListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function describeError(error: unknown) {
  if (error instanceof Error) {
    return error.message || error.name;
  }
  return typeof error === 'string' ? error : 'unknown error';
}

function normalizeErrorText(error: unknown) {
  return describeError(error).replace(/\s+/g, ' ').trim();
}

export function userFacingError(error: unknown, fallback = 'Something went wrong.') {
  const text = normalizeErrorText(error);
  const lower = text.toLowerCase();

  if (!text || lower === 'unknown error') {
    return fallback;
  }
  if (lower.includes('account with that email already exists')) {
    return 'An account with that email already exists.';
  }
  if (lower.includes('finish account verification')) {
    return 'Finish account verification before signing in. Create the account again if the code was not delivered.';
  }
  if (
    lower.includes('registered with google')
    || lower.includes('google sign-in')
    || lower.includes('continue with google')
    || lower.includes('sign in with google')
  ) {
    return 'This email is registered with Google. Sign in with Google instead.';
  }
  if (
    lower.includes('network request failed')
    || lower.includes('failed to fetch')
    || lower.includes('networkerror')
    || lower.includes('econnrefused')
    || lower.includes('connection refused')
    || lower.includes('timeout')
    || lower.includes('timed out')
  ) {
    return 'Connection problem. Try again.';
  }
  if (
    lower.includes('unauthorized')
    || lower.includes('forbidden')
    || lower.includes('session expired')
    || lower.includes('invalid token')
    || lower.includes('token expired')
    || lower.includes('401')
    || lower.includes('403')
  ) {
    return 'Sign in again.';
  }
  if (lower.includes('not found') || lower.includes('404')) {
    return 'That item is no longer available.';
  }
  if (
    lower.includes('desktop')
    && (lower.includes('offline') || lower.includes('not connected') || lower.includes('no connected'))
  ) {
    return 'Desktop is offline.';
  }
  if (lower.includes('pair')) {
    return 'Pair this phone first.';
  }
  if (lower.includes('verification') || lower.includes('otp') || lower.includes('code')) {
    return 'Check the code and try again.';
  }
  if (lower.includes('rate limit') || lower.includes('too many')) {
    return 'Too many attempts. Wait a moment.';
  }
  if (lower.includes('sqlite') || lower.includes('traceback') || lower.includes('stack') || lower.includes('http')) {
    return fallback;
  }

  return text.length > 72 ? fallback : text;
}

export function shortStatusText(value: string) {
  const normalized = value.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!normalized) return 'Idle';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}
