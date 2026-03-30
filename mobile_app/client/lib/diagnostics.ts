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
